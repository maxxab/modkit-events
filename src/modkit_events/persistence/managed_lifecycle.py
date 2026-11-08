"""Bounded native managed records sharing the canonical T1 authority.

No driver import on this leaf; the explicit optional native_sync leaf owns I/O.
Caller-retained inert anchors/handles are outside the canonical payload bound.
"""

from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from sys import getsizeof
from threading import get_ident
from uuid import UUID, SafeUUID

from . import resource_lifecycle as _registry
from .bindings import FrozenRequest, _freeze_parameters
from .catalog import WireType, get_statement
from .errors import ErrorCode, _fail, _reject_validation, _ValidationReject
from .observations import OutboxRow
from .rows import _decode_columns_raw, _decode_outbox_raw


@dataclass(frozen=True, slots=True, kw_only=True)
class LifecycleLimits:
    retained_cells: int
    admitted_live: int
    checkouts: int
    roots: int
    roots_per_checkout: int
    executions: int
    preparations: int
    preparations_per_execution: int
    prepare_bytes: int
    prepare_bytes_per_execution: int
    results: int
    results_per_ticket: int
    result_bytes: int
    result_bytes_per_ticket: int
    cleanup_bundles: int
    cleanup_bytes: int
    construction_slots: int


class _Handle:
    __slots__ = ("_stamp", "_key", "_pstamp", "_kind", "_subject")

    def start_root(self, *, execution_ledger):
        from .native_sync import start_root

        return start_root(self, execution_ledger=execution_ledger)

    def rollback(self, *, execution_ledger):
        from .native_sync import rollback

        return rollback(self, execution_ledger=execution_ledger)

    def commit(self, *, execution_ledger):
        from .native_sync import commit

        return commit(self, execution_ledger=execution_ledger)

    def close(self, *, execution_ledger):
        from .native_sync import close

        return close(self, execution_ledger=execution_ledger)

    def __new__(cls):
        raise TypeError("managed handles are issued internally")

    def __init_subclass__(cls, **kwargs):
        raise TypeError("managed handles cannot be subclassed")

    def __setattr__(self, name, value):
        raise AttributeError("managed handles are immutable")

    def __delattr__(self, name):
        raise AttributeError("managed handles are immutable")

    def __repr__(self):
        return "<ManagedHandle>"

    def __copy__(self):
        raise TypeError("managed handles cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("managed handles cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("managed handles cannot be serialized")


class CommitOutcome(Enum):
    """Actual normal fixed-COMMIT command responses, not E11 authority."""

    COMMITTED = "committed"
    ABORTED_COMMIT_ROLLED_BACK = "aborted_commit_rolled_back"


class CommitResultReceipt:
    """Inert exact issuer token; only the native COMMIT issuer can publish one."""

    __slots__ = _Handle.__slots__
    __new__ = _Handle.__new__
    __setattr__ = _Handle.__setattr__
    __delattr__ = _Handle.__delattr__
    __copy__ = _Handle.__copy__
    __deepcopy__ = _Handle.__deepcopy__
    __reduce_ex__ = _Handle.__reduce_ex__

    def __init_subclass__(cls, **kwargs):
        raise TypeError("CommitResultReceipt cannot be subclassed")

    def __repr__(self):
        return "<CommitResultReceipt>"


def _handle(kind, key=None, pstamp=None, subject=None):
    cls = CommitResultReceipt if kind == "COMMIT_RESULT" else _Handle
    value = object.__new__(cls)
    for name, field in (
        ("_stamp", object()),
        ("_key", key),
        ("_pstamp", pstamp),
        ("_kind", kind),
        ("_subject", subject),
    ):
        object.__setattr__(value, name, field)
    return value


_names = ("P", "V", "C", "R", "X", "A", "AB", "B", "BB", "K", "KB", "D")
_limit_names = (
    "retained_cells",
    "admitted_live",
    "checkouts",
    "roots",
    "executions",
    "preparations",
    "prepare_bytes",
    "results",
    "result_bytes",
    "cleanup_bundles",
    "cleanup_bytes",
    "construction_slots",
)
_limits = None
_counts = dict.fromkeys(_names, 0)
_executions = {}  # Charged X records; never a second physical registry.
_preparations = {}
_results = {}
_native_type = _cell_descriptor = None


def _context(ledger):
    return _registry._context(ledger)


def _reject(code, flag):
    _registry._reject(code, flag)


def _active():
    return _registry._mode == "MANAGED" and not _registry._domain.stopped


def _charge(delta):
    """Under canonical synchronization; integer-only atomic vector admission."""
    for name, amount in delta.items():
        limit = getattr(_limits, _limit_names[_names.index(name)])
        if _counts[name] + amount > limit:
            return False
    for name, amount in delta.items():
        _counts[name] += amount
    return True


def _refund(delta):
    for name, amount in delta.items():
        assert _counts[name] >= amount
        _counts[name] -= amount


class _ConstructionReservation:
    """Private same-thread proof of an already-paid live issuer frame."""

    __slots__ = ("active", "thread")

    def __new__(cls):
        raise TypeError("construction reservations are issued internally")

    def __init_subclass__(cls, **kwargs):
        raise TypeError("construction reservations cannot be subclassed")


@contextmanager
def _construction(flag):
    """Charge candidates/_outgoing frames before allocation; drop before refund."""
    code = None
    with _registry._synchronized():
        if _limits is None:
            code = ErrorCode.PROFILE_REJECTED
        elif not _charge({"D": 1}):
            code = ErrorCode.CAPACITY_EXCEEDED
    _reject(code, flag)
    reservation = None
    try:
        reservation = object.__new__(_ConstructionReservation)
        reservation.active, reservation.thread = True, get_ident()
        yield reservation
    except BaseException as primary:
        # An escaping traceback can retain candidate/_outgoing frames. Keep D
        # charged and contain without replacing the first failure metadata.
        cause = BaseException.__cause__.__get__(primary)
        context = BaseException.__context__.__get__(primary)
        suppressed = BaseException.__suppress_context__.__get__(primary)
        try:
            _registry._domain.trip()
        except BaseException:
            pass
        BaseException.__cause__.__set__(primary, cause)
        BaseException.__context__.__set__(primary, context)
        BaseException.__suppress_context__.__set__(primary, suppressed)
        raise
    else:
        with _registry._synchronized():
            _refund({"D": 1})
    finally:
        if reservation is not None:
            reservation.active = False


def configure_managed_registry(*, limits, execution_ledger):
    """Select once; execution_ledger supplies errors only, never reserves X."""
    global _limits
    flag = _context(execution_ledger)
    if type(limits) is not LifecycleLimits:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=flag)
    for field in fields(limits):
        value = getattr(limits, field.name)
        if type(value) is not int or value <= 0:
            _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=flag)
    for parent, total in (
        ("admitted_live", "retained_cells"),
        ("checkouts", "retained_cells"),
        ("roots_per_checkout", "roots"),
        ("preparations_per_execution", "preparations"),
        ("prepare_bytes_per_execution", "prepare_bytes"),
        ("results_per_ticket", "results"),
        ("result_bytes_per_ticket", "result_bytes"),
    ):
        if getattr(limits, parent) > getattr(limits, total):
            _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=flag)
    code = None
    with _registry._synchronized():
        if _registry._limit is not None or _registry._domain.stopped:
            code = ErrorCode.PROFILE_REJECTED
        else:
            _limits = limits
            _registry._mode = "MANAGED"
            _registry._limit = limits.retained_cells
    _reject(code, flag)


def _execution(handle, ledger):
    if type(handle) is not _Handle or handle._kind != "X":
        return None
    record = _executions.get(handle._stamp)
    return (
        record
        if record is not None and record["token"] is handle and record["ledger"] is ledger
        else None
    )


def reserve_execution(ledger, /):
    flag = _context(ledger)
    code = None
    with _construction(flag):
        token = _handle("X")
        candidate = {
            "token": token,
            "ledger": ledger,
            "links": 0,
            "drops": 0,
            "preparations": 0,
            "prepare_bytes": 0,
        }
        with _registry._synchronized():
            if not _active():
                code = ErrorCode.PROFILE_REJECTED
            elif ledger._managed_execution is not None:
                code = ErrorCode.INVALID_OBSERVATION
            elif not _charge({"X": 1}):
                code = ErrorCode.CAPACITY_EXCEEDED
            else:
                ledger._managed_execution = token
                _executions[token._stamp] = candidate
        candidate = None
    _reject(code, flag)
    return token


def dispose_execution(execution, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, execution)
    code = None
    with _construction(flag):
        record = _outgoing = None
        with _registry._synchronized():
            record = _execution(execution, execution_ledger)
            if record is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif record["links"] or record["drops"] or record["preparations"]:
                code = ErrorCode.RESOURCE_BUSY
            else:
                _outgoing = _executions.pop(execution._stamp)
                _refund({"X": 1})
        record = _outgoing = None  # Drop all package graphs before D is refunded.
    _reject(code, flag)


def capacity_snapshot(*, execution_ledger):
    flag = _context(execution_ledger)
    code = None
    with _registry._synchronized():
        if _limits is None:
            code = ErrorCode.PROFILE_REJECTED
        snapshot = dict(_counts)
    _reject(code, flag)
    return snapshot


def _lookup(actual, *, execution_ledger):
    flag = _context(execution_ledger)
    if _native_type is None or type(actual) is not _native_type:
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=flag)
    try:
        cell = _cell_descriptor.__get__(actual, _native_type)
    except AttributeError:
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=flag)
    if type(cell) is not _registry.ResourceCell or cell._key != id(actual):
        _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=flag)
    return cell  # Identity only: terminal/stopped lookup gives no authority.


def _size(value, flag):
    if type(value) is not int or value <= 0:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=flag)


def _envelope(token, ledger, kind):
    if type(token) is not _Handle or token._kind != kind:
        return None
    table = _preparations if kind == "A" else _results
    record = table.get(token._stamp)
    return (
        record
        if record is not None and record["token"] is token and record["x"]["ledger"] is ledger
        else None
    )


def _require_paid_preparation(reservation, unreturned=False):
    if not _reservation_live(reservation) or type(unreturned) is not bool:
        _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=True)


def _reserve_preparation_paid(execution, capacity, ledger, reservation):
    """Canonical reservation inside an already-paid construction frame."""
    _require_paid_preparation(reservation)
    code = None
    token = _handle("A")
    candidate = {
        "token": token,
        "capacity": capacity,
        "data": None,
        "borrows": 0,
        "x": None,
        "builder": reservation,
        "profile": None,
    }
    x = None
    with _registry._synchronized():
        x = _execution(execution, ledger)
        if x is None:
            code = ErrorCode.INVALID_OBSERVATION
        elif not _active():
            code = ErrorCode.PROFILE_REJECTED
        elif (
            x["preparations"] >= _limits.preparations_per_execution
            or x["prepare_bytes"] + capacity > _limits.prepare_bytes_per_execution
            or not _charge({"A": 1, "AB": capacity})
        ):
            code = ErrorCode.CAPACITY_EXCEEDED
        else:
            candidate["x"] = x
            x["preparations"] += 1
            x["prepare_bytes"] += capacity
            _preparations[token._stamp] = candidate
    x = candidate = None
    return token, code


def reserve_preparation(execution, capacity, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, execution)
    _size(capacity, flag)
    with _construction(flag) as paid:
        token, code = _reserve_preparation_paid(execution, capacity, execution_ledger, paid)
    _reject(code, flag)
    return token


def _preparation_size(payload, operation=None):
    if operation is not None:
        from .native_profile import _request_size

        return _request_size(payload, operation)
    if type(payload) is bytes:
        return len(payload)
    if type(payload) is not FrozenRequest:
        _reject_validation()
    # Validate without replacing any part of the retained execution graph.
    _freeze_parameters(
        payload.statement,
        payload.parameters,
        payload.context,
        _reject=_reject_validation,
    )
    return (
        getsizeof(payload)
        + getsizeof(payload.parameters)
        + sum(getsizeof(value) for value in payload.parameters)
        + getsizeof(payload.context)
        + getsizeof(payload.context.expected)
    )


def _set_preparation_paid(
    preparation, payload, ledger, reservation, *, unreturned=False, operation=None
):
    """Validate and publish under existing D; known rejections return codes."""
    _require_paid_preparation(reservation, unreturned)
    code = None
    try:
        size = _preparation_size(payload, operation)
    except _ValidationReject as error:
        if type(error) is not _ValidationReject:
            raise
        code = ErrorCode.LOCAL_INVALID_ARGUMENT
    record = None
    if code is None:
        with _registry._synchronized():
            record = _envelope(preparation, ledger, "A")
            if (
                record is None
                or record["data"] is not None
                or (unreturned and record.get("builder") is not reservation)
            ):
                code = ErrorCode.INVALID_OBSERVATION
            elif not _active():
                code = ErrorCode.PROFILE_REJECTED
            elif size > record["capacity"]:
                code = ErrorCode.CAPACITY_EXCEEDED
            else:
                record["data"] = payload
                record["profile"] = operation
    record = None
    return code


def set_preparation(preparation, payload, /, *, execution_ledger):
    """Retain exact immutable bytes or the actual paid E14/E28 FrozenRequest."""
    flag = _context(execution_ledger)
    _require_handles(flag, preparation)
    with _construction(flag) as paid:
        code = _set_preparation_paid(preparation, payload, execution_ledger, paid)
    _reject(code, flag)


def _release_preparation_paid(preparation, ledger, reservation, *, unreturned=False):
    """Drop references before refund, optionally only this builder's new A."""
    _require_paid_preparation(reservation, unreturned)
    code = None
    record = x = _outgoing = None
    amount = 0
    with _registry._synchronized():
        record = _envelope(preparation, ledger, "A")
        if record is None or (unreturned and record.get("builder") is not reservation):
            code = ErrorCode.INVALID_OBSERVATION
        elif record["borrows"]:
            code = ErrorCode.RESOURCE_BUSY
        else:
            x = record["x"]
            x["drops"] += 1
            amount = record["capacity"]
            _outgoing = _preparations.pop(preparation._stamp)
    record = _outgoing = None
    if x is not None:
        with _registry._synchronized():
            x["preparations"] -= 1
            x["prepare_bytes"] -= amount
            x["drops"] -= 1
            _refund({"A": 1, "AB": amount})
    x = None
    return code


def release_preparation(preparation, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, preparation)
    with _construction(flag) as paid:
        code = _release_preparation_paid(preparation, execution_ledger, paid)
    _reject(code, flag)


class _Physical:
    __slots__ = (
        "resource",
        "cell",
        "checkout",
        "x",
        "pgconn",
        "roots",
        "current",
        "operation",
        "retired",
        "cleanup",
        "close_receipt",
        "close_state",
        "close_ack",
        "blocked_root",
    )

    def __init__(self, actual, cell, checkout, x, pgconn):
        self.resource, self.cell, self.checkout = actual, cell, checkout
        self.x, self.pgconn = x, pgconn
        self.roots = {}
        self.current = self.operation = self.cleanup = None
        self.retired = self.close_ack = self.blocked_root = False
        self.close_receipt = self.close_state = None


def _physical(handle, ledger):
    if type(handle) not in (_Handle, CommitResultReceipt):
        return None
    state = _registry._cells.get(handle._key)
    if (
        type(state) is _Physical
        and state.cell._stamp is handle._pstamp
        and state.x["ledger"] is ledger
    ):
        return state
    return None


def _checkout(handle, ledger):
    state = _physical(handle, ledger)
    return state if state is not None and state.checkout is handle else None


def _root(handle, ledger):
    state = _physical(handle, ledger)
    if state is None or handle._kind != "R":
        return None, None
    root = state.roots.get(handle._stamp)
    return (state, root) if root is not None and root["token"] is handle else (None, None)


def _usable(state):
    return _active() and not state.retired and not state.cell._terminal


def attach_native(actual, execution, /, *, execution_ledger):
    """Cooperative fresh/unpooled lifetime; exact class is not pool detection."""
    flag = _context(execution_ledger)
    _require_handles(flag, execution)
    cell = _lookup(actual, execution_ledger=execution_ledger)
    pgconn = actual.pgconn
    if actual.closed or actual.autocommit or pgconn.transaction_status != 0:
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=flag)
    code = None
    with _construction(flag):
        token = _handle("C", id(actual), cell._stamp)
        candidate = _Physical(actual, cell, token, None, pgconn)
        x = current = None
        with _registry._synchronized():
            x = _execution(execution, execution_ledger)
            current = _registry._cells.get(id(actual))
            if x is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif not _active() or cell._terminal:
                code = ErrorCode.PROFILE_REJECTED
            elif current is not None:
                code = ErrorCode.INVALID_OBSERVATION
            elif not _charge({"P": 1, "V": 1, "C": 1}):
                code = ErrorCode.CAPACITY_EXCEEDED
            else:
                candidate.x = x
                _registry._cells[id(actual)] = candidate
                x["links"] += 1
        candidate = x = current = None
    _reject(code, flag)
    return token


def _reserve_root(checkout, ledger):
    """Private issuer reservation. Caller owns a charged D construction frame."""
    token = _handle("R", checkout._key, checkout._pstamp)
    op = _handle("START", checkout._key, checkout._pstamp, token._stamp)
    candidate = {
        "token": token,
        "state": "STARTING",
        "operation": op,
        "receipt": None,
        "ack": False,
        "commit_outcome": None,
        "observed_commit_tag": None,
    }
    operation = {
        "token": op,
        "kind": "START",
        "root": token._stamp,
        "running": True,
        "prep": None,
        "results": 0,
        "bytes": 0,
    }
    code = None
    with _registry._synchronized():
        p = _checkout(checkout, ledger)
        if p is None:
            code = ErrorCode.INVALID_OBSERVATION
        elif not _usable(p) or p.blocked_root:
            code = ErrorCode.PROFILE_REJECTED
        elif p.current is not None or p.operation is not None:
            code = ErrorCode.RESOURCE_BUSY
        elif len(p.roots) >= _limits.roots_per_checkout or not _charge({"R": 1}):
            code = ErrorCode.CAPACITY_EXCEEDED
        else:
            p.roots[token._stamp] = candidate
            p.current = token
            p.operation = operation
    return token, code


def _complete_start(root, ledger, *, known):
    _outgoing = None
    with _registry._synchronized():
        p, record = _root(root, ledger)
        assert record is not None and record["state"] == "STARTING"
        p.operation["running"] = False
        record["state"] = "ACTIVE" if known else "UNKNOWN"
        if not known:
            p.blocked_root = True
        if known:
            _outgoing, p.operation = p.operation, None
    _outgoing = p = record = None


def admit(root, preparation, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, root, preparation)
    if type(root) is not _Handle:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=flag)
    code = None
    with _construction(flag):
        token = _handle("OP", root._key, root._pstamp, root._stamp)
        candidate = {
            "token": token,
            "kind": "OP",
            "root": root._stamp,
            "prep": None,
            "running": False,
            "state": "ADMITTED",
            "result_stamp": None,
            "results": 0,
            "bytes": 0,
        }
        with _registry._synchronized():
            p, r = _root(root, execution_ledger)
            a = _envelope(preparation, execution_ledger, "A")
            if p is None or a is None or a["x"] is not p.x or a["data"] is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif not _usable(p):
                code = ErrorCode.PROFILE_REJECTED
            elif r["state"] != "ACTIVE" or p.current is not root:
                code = ErrorCode.INVALID_OBSERVATION
            elif p.operation is not None:
                code = ErrorCode.RESOURCE_BUSY
            else:
                a["borrows"] += 1
                candidate["prep"] = a
                p.operation = candidate
        p = r = a = candidate = None
    _reject(code, flag)
    return token


def _ticket(token, ledger):
    p = _physical(token, ledger)
    if p is None or p.operation is None or p.operation["token"] is not token or token._kind != "OP":
        return None
    return p


def _start_operation(ticket, result, ledger, *, reservation=None):
    """Issuer-only start; return the exact paid request, never caller live args."""
    flag = _context(ledger)
    _require_handles(flag, ticket, result)
    if reservation is not None and not _reservation_live(reservation):
        _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=flag)
    code = request = None
    with _construction(flag):
        p = record = root = None
        with _registry._synchronized():
            p = _ticket(ticket, ledger)
            record = _envelope(result, ledger, "B")
            if p is None or record is None or record["operation"] is not p.operation:
                code = ErrorCode.INVALID_OBSERVATION
            elif not _usable(p):
                code = ErrorCode.PROFILE_REJECTED
            elif p.operation["state"] != "ADMITTED":
                code = ErrorCode.INVALID_OBSERVATION
            elif type(p.operation["prep"]["data"]) is not FrozenRequest:
                code = ErrorCode.PROFILE_REJECTED
            elif p.operation["results"] != 1 or record["populated"]:
                code = ErrorCode.INVALID_OBSERVATION
            else:
                root = p.roots.get(ticket._subject)
                if root is None or root["token"] is not p.current or root["state"] != "ACTIVE":
                    code = ErrorCode.INVALID_OBSERVATION
                else:
                    request = p.operation["prep"]["data"]
                    p.operation["result_stamp"] = result._stamp
                    p.operation["state"] = "RUNNING"
                    p.operation["running"] = True
                    p.operation["issuer"] = reservation
        p = record = root = None
    _reject(code, flag)
    return request


def _reservation_live(reservation):
    return (
        type(reservation) is _ConstructionReservation
        and reservation.active
        and reservation.thread == get_ident()
    )


def _owns_operation_paid(ticket, ledger, reservation):
    """Identify only this live issuer's atomic start, including a lost return."""
    if not _reservation_live(reservation):
        return False
    with _registry._synchronized():
        p = _ticket(ticket, ledger)
        owned = p is not None and p.operation.get("issuer") is reservation
        p = None
    return owned


def _fail_operation_paid(ticket, ledger, reservation, *, stopped):
    """This issuer's failure under its live D; hold before fallible ledger work.

    Atomic start binds the exact reservation. A rejected competing attempt has
    no authority over an older operation. stopped=True remains the issuer's
    observation, never waiter cancellation or physical-close receipt authority.
    """
    if not _reservation_live(reservation) or type(stopped) is not bool:
        _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=True)
    valid = False
    with _registry._synchronized():
        p = _ticket(ticket, ledger)
        if (
            p is not None
            and p.operation.get("issuer") is reservation
            and p.operation["state"] in ("RUNNING", "HELD", "COMPLETED")
        ):
            p.operation["state"] = "HELD"
            p.roots[ticket._subject]["state"] = "UNKNOWN"
            p.blocked_root = True
            if stopped:
                p.operation["running"] = False
            valid = True
        p = None
    if not valid:
        _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=True)
    ledger.note_incident(ErrorCode.OUTCOME_UNKNOWN)


def _hold_operation(ticket, ledger):
    """Mark uncertainty without claiming that the physical worker has stopped."""
    flag = _context(ledger)
    _require_handles(flag, ticket)
    code = None
    with _construction(flag):
        p = None
        with _registry._synchronized():
            p = _ticket(ticket, ledger)
            if (
                p is None
                or not p.operation["running"]
                or p.operation["state"] not in ("RUNNING", "HELD")
            ):
                code = ErrorCode.INVALID_OBSERVATION
            else:
                p.operation["state"] = "HELD"
                p.roots[ticket._subject]["state"] = "UNKNOWN"
                p.blocked_root = True
        p = None
        if code is None:
            ledger.note_incident(ErrorCode.OUTCOME_UNKNOWN)
    _reject(code, flag)


def _complete_operation(ticket, ledger, *, known):
    """Issuer-only actual worker completion, never cancellation of its waiter."""
    flag = _context(ledger)
    _require_handles(flag, ticket)
    if type(known) is not bool:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=flag)
    code = None
    held = False
    with _construction(flag):
        p = result = None
        with _registry._synchronized():
            p = _ticket(ticket, ledger)
            if (
                p is None
                or not p.operation["running"]
                or p.operation["state"] not in ("RUNNING", "HELD")
            ):
                code = ErrorCode.INVALID_OBSERVATION
            elif known and p.operation["state"] == "RUNNING" and _active():
                result = _results.get(p.operation["result_stamp"])
                if result is None or not result["populated"]:
                    code = ErrorCode.INVALID_OBSERVATION
                else:
                    p.operation["state"] = "COMPLETED"
                    p.operation["running"] = False
            else:
                # Actual work has stopped. Publish HELD before the fallible
                # ledger union, so no concurrent release or completion can win.
                p.operation["state"] = "HELD"
                p.operation["running"] = False
                p.roots[ticket._subject]["state"] = "UNKNOWN"
                p.blocked_root = held = True
        p = result = None
        if held:
            ledger.note_incident(ErrorCode.OUTCOME_UNKNOWN)
    _reject(code, flag)


def read_result(result, /, *, execution_ledger):
    """Borrow a completed paid typed value; this is not a commit acknowledgement."""
    flag = _context(execution_ledger)
    _require_handles(flag, result)
    code = payload = None
    with _construction(flag):
        record = None
        with _registry._synchronized():
            record = _envelope(result, execution_ledger, "B")
            if record is None or type(record["operation"]["prep"]["data"]) is not FrozenRequest:
                code = ErrorCode.INVALID_OBSERVATION
            elif (
                record["operation"]["running"]
                or record["operation"]["state"] != "COMPLETED"
                or not record["populated"]
            ):
                code = ErrorCode.RESOURCE_BUSY
            elif not _active():
                code = ErrorCode.PROFILE_REJECTED
            else:
                payload = record["data"]
        record = None
    _reject(code, flag)
    return payload


def validate_ticket(ticket, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, ticket)
    with _construction(flag):
        code = None
        with _registry._synchronized():
            p = _ticket(ticket, execution_ledger)
            if p is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif not _usable(p) or p.operation["state"] == "HELD":
                code = ErrorCode.PROFILE_REJECTED
            elif p.current is None or p.current._stamp is not ticket._subject:
                code = ErrorCode.INVALID_OBSERVATION
        p = None
    _reject(code, flag)


def release_ticket(ticket, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, ticket)
    code = None
    with _construction(flag):
        _outgoing = p = None
        with _registry._synchronized():
            p = _ticket(ticket, execution_ledger)
            if p is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif p.operation["results"] or p.operation["running"] or p.operation["state"] == "HELD":
                code = ErrorCode.RESOURCE_BUSY
            else:
                _outgoing, p.operation = p.operation, None
                _outgoing["prep"]["borrows"] -= 1
        p = _outgoing = None
    _reject(code, flag)


def reserve_result(ticket, capacity, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, ticket)
    _size(capacity, flag)
    code = None
    with _construction(flag):
        token = (
            _handle("B", ticket._key, ticket._pstamp, ticket._stamp)
            if type(ticket) is _Handle
            else None
        )
        candidate = {
            "token": token,
            "capacity": capacity,
            "data": None,
            "populated": False,
            "x": None,
            "operation": None,
        }
        with _registry._synchronized():
            p = _ticket(ticket, execution_ledger)
            if p is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif not _usable(p):
                code = ErrorCode.PROFILE_REJECTED
            elif p.operation["state"] != "ADMITTED":
                code = ErrorCode.RESOURCE_BUSY
            elif (
                p.operation["results"] >= _limits.results_per_ticket
                or p.operation["bytes"] + capacity > _limits.result_bytes_per_ticket
                or not _charge({"B": 1, "BB": capacity})
            ):
                code = ErrorCode.CAPACITY_EXCEEDED
            else:
                candidate["x"], candidate["operation"] = p.x, p.operation
                p.operation["results"] += 1
                p.operation["bytes"] += capacity
                _results[token._stamp] = candidate
        p = candidate = None
    _reject(code, flag)
    return token


def _retained_scalar_size(value, column):
    """Finite canonical E14/E28 storage only, with no coercion or user hooks."""
    if value is None:
        if not column.nullable:
            _reject_validation()
        return getsizeof(None)
    expected = {
        WireType.BYTEA: bytes,
        WireType.TEXT: str,
        WireType.INT4: int,
        WireType.INT8: int,
        WireType.XID8: int,
        WireType.UUID: UUID,
        WireType.TIMESTAMPTZ: datetime,
    }.get(column.wire_type)
    if expected is None or type(value) is not expected:
        _reject_validation()
    if expected is datetime and value.tzinfo is not timezone.utc:
        _reject_validation()
    if expected is UUID:
        # UUID's public constructor retains int/is_safe without exact-type
        # checks. Reject caller graphs and hooks before any sizing or decoding.
        integer, safety = value.int, value.is_safe
        if type(integer) is not int or not 0 <= integer < 2**128:
            _reject_validation()
        if not (safety is SafeUUID.safe or safety is SafeUUID.unsafe or safety is SafeUUID.unknown):
            _reject_validation()
        return getsizeof(value) + getsizeof(integer)
    return getsizeof(value)


def _typed_result_size(request, payload):
    columns = request.statement.result.columns
    if request.statement is get_statement("E14"):
        size = _retained_scalar_size(payload, columns[0])
        _decode_columns_raw(columns, (payload,))
        return size
    if request.statement is not get_statement("E28"):
        _reject_validation()
    if payload is None:
        return getsizeof(None)
    if type(payload) is not OutboxRow:
        _reject_validation()
    values = tuple(getattr(payload, column.name) for column in columns)
    # Preflight the actual retained graph before normalizing wire validators.
    size = getsizeof(payload) + sum(
        _retained_scalar_size(value, column) for value, column in zip(values, columns)
    )
    _decode_outbox_raw(values)
    if payload.event_id != request.parameters[0]:
        _reject_validation()
    return size


def _result_publication_error(record, result):
    if record is None or record["populated"]:
        return ErrorCode.INVALID_OBSERVATION
    operation = record["operation"]
    if type(operation["prep"]["data"]) is FrozenRequest:
        if not _active():
            return ErrorCode.PROFILE_REJECTED
        if (
            not operation["running"]
            or operation["state"] != "RUNNING"
            or operation["result_stamp"] is not result._stamp
        ):
            return ErrorCode.INVALID_OBSERVATION
    return None


def set_result(result, payload, /, *, execution_ledger):
    """Retain a fully validated typed result under the running operation's charge."""
    flag = _context(execution_ledger)
    _require_handles(flag, result)
    with _construction(flag):
        code = request = record = operation = None
        with _registry._synchronized():
            record = _envelope(result, execution_ledger, "B")
            code = _result_publication_error(record, result)
            if code is None:
                request = record["operation"]["prep"]["data"]
                operation = record["operation"]["prep"].get("profile")
        record = None
        if code is None:
            try:
                if type(request) is FrozenRequest:
                    if operation is None:
                        size = _typed_result_size(request, payload)
                    else:
                        from .native_profile import _result_size

                        size = _result_size(request, payload, operation)
                elif type(payload) is bytes:
                    size = len(payload)
                else:
                    _reject_validation()
            except _ValidationReject as error:
                if type(error) is not _ValidationReject:
                    raise
                code = (
                    ErrorCode.INVALID_OBSERVATION
                    if type(request) is FrozenRequest
                    else ErrorCode.LOCAL_INVALID_ARGUMENT
                )
        if code is None:
            with _registry._synchronized():
                record = _envelope(result, execution_ledger, "B")
                code = _result_publication_error(record, result)
                if code is None:
                    if size > record["capacity"]:
                        code = ErrorCode.CAPACITY_EXCEEDED
                    else:
                        record["data"] = payload
                        record["populated"] = True
        record = request = operation = None
    _reject(code, flag)


def release_result(result, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, result)
    code = None
    with _construction(flag):
        record = _outgoing = operation = None
        amount = 0
        with _registry._synchronized():
            record = _envelope(result, execution_ledger, "B")
            if record is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif record["operation"]["running"] or record["operation"]["state"] == "HELD":
                code = ErrorCode.RESOURCE_BUSY
            else:
                amount, operation = record["capacity"], record["operation"]
                _outgoing = _results.pop(result._stamp)
        record = _outgoing = None
        if operation is not None:
            with _registry._synchronized():
                operation["results"] -= 1
                operation["bytes"] -= amount
                _refund({"B": 1, "BB": amount})
        operation = None
    _reject(code, flag)


def abandon_root(subject, /, *, execution_ledger):
    """Cleanup-only revocation; C can revoke a lost-return current root."""
    flag = _context(execution_ledger)
    _require_handles(flag, subject)
    code = None
    with _construction(flag):
        marker = {
            "token": None,
            "kind": "ABANDON",
            "root": None,
            "running": True,
            "prep": None,
            "results": 0,
            "bytes": 0,
        }
        _outgoing = p = r = None
        with _registry._synchronized():
            p = _physical(subject, execution_ledger)
            if p is None:
                code = ErrorCode.INVALID_OBSERVATION
            else:
                token = p.current if p.checkout is subject else subject
                p, r = _root(token, execution_ledger)
                if r is None:
                    code = ErrorCode.INVALID_OBSERVATION
                elif p.operation is not None and (
                    p.operation["running"] or p.operation["kind"] == "OP"
                ):
                    code = ErrorCode.RESOURCE_BUSY
                elif r["state"] == "ENDED":
                    code = ErrorCode.INVALID_OBSERVATION
                else:
                    p.blocked_root = True
                    r["state"] = "ABANDONING"
                    _outgoing, p.operation = p.operation, marker
        if code is None:
            # Hold the common gate while the exact L union completes outside it.
            execution_ledger.note_incident(ErrorCode.OUTCOME_UNKNOWN)
            with _registry._synchronized():
                assert p.operation is marker and r["state"] == "ABANDONING"
                r["state"] = "ABANDONED"
                p.current = None
                p.operation = None
        _outgoing = p = r = marker = None
    _reject(code, flag)


def release_root(root, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, root)
    code = None
    with _construction(flag):
        p = record = _outgoing = None
        with _registry._synchronized():
            p, record = _root(root, execution_ledger)
            if record is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif record["state"] != "ENDED" and not (
                record["state"] == "ABANDONED" and p.close_ack
            ):
                code = ErrorCode.RESOURCE_BUSY
            elif p.operation is not None and p.operation["root"] is root._stamp:
                code = ErrorCode.RESOURCE_BUSY
            else:
                _outgoing = p.roots.pop(root._stamp)
                _refund({"R": 1})
        p = record = _outgoing = None
    _reject(code, flag)


def retire(checkout, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, checkout)
    with _construction(flag):
        code = None
        with _registry._synchronized():
            p = _checkout(checkout, execution_ledger)
            if p is None:
                code = ErrorCode.INVALID_OBSERVATION
            else:
                p.retired = True
        p = None
    _reject(code, flag)


def prepare_cleanup(checkout, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, checkout)
    code = None
    with _construction(flag):
        token = (
            _handle("CLEANUP_INTENT", checkout._key, checkout._pstamp)
            if type(checkout) is _Handle
            else None
        )
        candidate = {"intent": token, "reservation": None, "permit": None, "capacity": 0}
        with _registry._synchronized():
            p = _checkout(checkout, execution_ledger)
            if p is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif not p.retired:
                code = ErrorCode.PROFILE_REJECTED
            elif p.operation is not None or p.current is not None:
                code = ErrorCode.RESOURCE_BUSY
            elif p.cleanup is not None:
                code = ErrorCode.INVALID_OBSERVATION
            else:
                p.cleanup = candidate
        p = candidate = None
    _reject(code, flag)
    return token


def reserve_cleanup(intent, capacity, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, intent)
    _size(capacity, flag)
    code = None
    with _construction(flag):
        token = (
            _handle("CLEANUP_RESERVATION", intent._key, intent._pstamp)
            if type(intent) is _Handle
            else None
        )
        with _registry._synchronized():
            p = _physical(intent, execution_ledger)
            if (
                p is None
                or p.cleanup is None
                or p.cleanup["intent"] is not intent
                or p.cleanup["reservation"] is not None
            ):
                code = ErrorCode.INVALID_OBSERVATION
            elif not _charge({"K": 1, "KB": capacity}):
                code = ErrorCode.CAPACITY_EXCEEDED
            else:
                p.cleanup["capacity"] = capacity
                p.cleanup["reservation"] = token
        p = None
    _reject(code, flag)
    return token


def pin_cleanup(reservation, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, reservation)
    code = None
    with _construction(flag):
        token = (
            _handle("CLOSE_PERMIT", reservation._key, reservation._pstamp)
            if type(reservation) is _Handle
            else None
        )
        with _registry._synchronized():
            p = _physical(reservation, execution_ledger)
            if (
                p is None
                or p.cleanup is None
                or p.cleanup["reservation"] is not reservation
                or p.cleanup["permit"] is not None
            ):
                code = ErrorCode.INVALID_OBSERVATION
            else:
                p.cleanup["permit"] = token
        p = None
    _reject(code, flag)
    return token


def _reserve_close(permit, ledger):
    op = _handle("CLOSE_OP", permit._key, permit._pstamp)
    receipt = _handle("CLOSE_RECEIPT", permit._key, permit._pstamp)
    candidate = {
        "token": op,
        "kind": "CLOSE",
        "root": None,
        "running": True,
        "prep": None,
        "results": 0,
        "bytes": 0,
    }
    code = None
    with _registry._synchronized():
        p = _physical(permit, ledger)
        if p is None or p.cleanup is None or p.cleanup["permit"] is not permit:
            code = ErrorCode.INVALID_OBSERVATION
        elif not p.retired or p.close_state is not None:
            code = ErrorCode.PROFILE_REJECTED
        elif p.operation is not None or p.current is not None:
            code = ErrorCode.RESOURCE_BUSY
        else:
            p.close_receipt = receipt
            p.close_state = "RUNNING"
            p.operation = candidate
    return op, receipt, code


def _complete_close(permit, ledger, *, known):
    with _registry._synchronized():
        p = _physical(permit, ledger)
        assert p is not None and p.close_state == "RUNNING"
        p.close_state = "RECORDED" if known else "UNKNOWN"
        p.operation["running"] = False


def acknowledge_physical_close(receipt, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, receipt)
    code = None
    with _construction(flag):
        p = _outgoing = None
        with _registry._synchronized():
            p = _physical(receipt, execution_ledger)
            if p is None or p.close_receipt is not receipt or p.close_state != "RECORDED":
                code = ErrorCode.INVALID_OBSERVATION
            elif not p.close_ack:
                p.close_ack = True
                _outgoing, p.operation = p.operation, None
                _refund({"V": 1})
        p = _outgoing = None
    _reject(code, flag)


def release_cleanup(reservation, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, reservation)
    code = None
    with _construction(flag):
        p = _outgoing = None
        amount = 0
        with _registry._synchronized():
            p = _physical(reservation, execution_ledger)
            if p is None or p.cleanup is None or p.cleanup["reservation"] is not reservation:
                code = ErrorCode.INVALID_OBSERVATION
            elif not p.close_ack or p.operation is not None:
                code = ErrorCode.RESOURCE_BUSY
            else:
                amount = p.cleanup["capacity"]
                _outgoing, p.cleanup = p.cleanup, None
        p = _outgoing = None
        if amount:
            with _registry._synchronized():
                _refund({"K": 1, "KB": amount})
    _reject(code, flag)


def detach_terminal(checkout, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, checkout)
    code = None
    with _construction(flag):
        p = _outgoing = x = None
        with _registry._synchronized():
            p = _checkout(checkout, execution_ledger)
            if p is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif (
                not p.close_ack
                or p.operation is not None
                or p.roots
                or p.current is not None
                or p.cleanup is not None
            ):
                code = ErrorCode.RESOURCE_BUSY
            else:
                x = p.x
                x["drops"] += 1
                x["links"] -= 1
                object.__setattr__(p.cell, "_terminal", True)
                _outgoing = _registry._cells.pop(checkout._key)
                _refund({"P": 1, "C": 1})
        p = _outgoing = None
        if x is not None:
            with _registry._synchronized():
                x["drops"] -= 1
        x = None
    _reject(code, flag)


def _reserve_rollback(root, ledger, *, commit=False):
    kind = "COMMIT" if commit else "ROLLBACK"
    op = _handle(kind, root._key, root._pstamp, root._stamp)
    receipt = _handle(
        "COMMIT_RESULT" if commit else "ROOT_END", root._key, root._pstamp, root._stamp
    )
    candidate = {
        "token": op,
        "kind": kind,
        "root": root._stamp,
        "running": True,
        "prep": None,
        "results": 0,
        "bytes": 0,
    }
    code = None
    with _registry._synchronized():
        p, r = _root(root, ledger)
        if r is None:
            code = ErrorCode.INVALID_OBSERVATION
        elif not _usable(p):
            code = ErrorCode.PROFILE_REJECTED
        elif r["state"] != "ACTIVE" or p.current is not root:
            code = ErrorCode.INVALID_OBSERVATION
        elif p.operation is not None:
            code = ErrorCode.RESOURCE_BUSY
        else:
            r["operation"] = op
            r["receipt"] = receipt
            r["state"] = "FINALIZING"
            p.operation = candidate
    return op, receipt, code


def _complete_rollback(root, ledger, *, known):
    if not known:
        ledger.note_incident(ErrorCode.OUTCOME_UNKNOWN)
    with _registry._synchronized():
        p, r = _root(root, ledger)
        assert r is not None and r["state"] == "FINALIZING"
        r["state"] = "RECORDED" if known else "UNKNOWN"
        if not known:
            p.blocked_root = True
        p.operation["running"] = False


def _complete_commit(root, ledger, *, outcome, observed_tag):
    # Persist fixed observed evidence before potentially failing L bookkeeping.
    # No raw result/error/cursor graph enters canonical metadata.
    with _registry._synchronized():
        p, r = _root(root, ledger)
        assert r is not None and r["state"] == "FINALIZING"
        r["observed_commit_tag"] = observed_tag
    if outcome is None:
        ledger.note_incident(ErrorCode.OUTCOME_UNKNOWN)
    with _registry._synchronized():
        p, r = _root(root, ledger)
        assert r is not None and r["state"] == "FINALIZING"
        r["commit_outcome"] = outcome
        r["state"] = "RECORDED" if outcome is not None else "UNKNOWN"
        if outcome is None:
            p.blocked_root = True
        p.operation["running"] = False
    p = r = None


def acknowledge_commit_result(receipt, /, *, execution_ledger):
    """Echo the exact normally returned COMMIT receipt; never reconstruct one."""
    flag = _context(execution_ledger)
    if type(receipt) is not CommitResultReceipt:
        _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=flag)
    code = outcome = None
    with _construction(flag):
        p = r = _outgoing = None
        with _registry._synchronized():
            p = _physical(receipt, execution_ledger)
            r = p.roots.get(receipt._subject) if p is not None else None
            if (
                r is None
                or receipt._kind != "COMMIT_RESULT"
                or r["receipt"] is not receipt
                or r["state"] not in ("RECORDED", "ENDED")
                or type(r["commit_outcome"]) is not CommitOutcome
            ):
                code = ErrorCode.INVALID_OBSERVATION
            elif not r["ack"]:
                if (
                    p.current is not r["token"]
                    or p.operation is None
                    or p.operation["token"] is not r["operation"]
                    or p.operation["kind"] != "COMMIT"
                    or p.operation["running"]
                ):
                    code = ErrorCode.INVALID_OBSERVATION
                else:
                    r["ack"] = True
                    r["state"] = "ENDED"
                    p.current = None
                    _outgoing, p.operation = p.operation, None
                    outcome = r["commit_outcome"]
            else:
                outcome = r["commit_outcome"]
        p = r = _outgoing = None
    _reject(code, flag)
    return outcome


def acknowledge_root_end(receipt, /, *, execution_ledger):
    flag = _context(execution_ledger)
    _require_handles(flag, receipt)
    code = None
    with _construction(flag):
        p = r = _outgoing = None
        with _registry._synchronized():
            p = _physical(receipt, execution_ledger)
            r = p.roots.get(receipt._subject) if p is not None else None
            if (
                type(receipt) is not _Handle
                or receipt._kind != "ROOT_END"
                or r is None
                or r["receipt"] is not receipt
                or r["state"] not in ("RECORDED", "ENDED")
            ):
                code = ErrorCode.INVALID_OBSERVATION
            elif not r["ack"]:
                if (
                    p.operation is None
                    or p.operation["token"] is not r["operation"]
                    or p.operation["kind"] != "ROLLBACK"
                    or p.operation["running"]
                ):
                    code = ErrorCode.INVALID_OBSERVATION
                else:
                    r["ack"] = True
                    r["state"] = "ENDED"
                    p.current = None
                    _outgoing, p.operation = p.operation, None
        p = r = _outgoing = None
    _reject(code, flag)


def _require_handles(flag, *values):
    if any(type(value) not in (_Handle, CommitResultReceipt) for value in values):
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=flag)


def _prepare_component(execution, operation, logical_request, /, *, execution_ledger):
    """One canonical D and fixed A, both paid before the trusted builder."""
    from .native_profile import _preparation_capacity, _validate_operation

    flag = _context(execution_ledger)
    _require_handles(flag, execution)
    with _construction(flag) as paid:
        code = request = preparation = None
        reserved = False
        try:
            _validate_operation(operation)
            if type(logical_request) is not operation.request_type:
                _reject_validation()
            capacity = _preparation_capacity(operation)
            preparation, code = _reserve_preparation_paid(
                execution, capacity, execution_ledger, paid
            )
            reserved = code is None
            if reserved:
                request = operation.build_request(logical_request)
                code = _set_preparation_paid(
                    preparation,
                    request,
                    execution_ledger,
                    paid,
                    unreturned=True,
                    operation=operation,
                )
        except _ValidationReject as error:
            if type(error) is not _ValidationReject:
                raise
            code = ErrorCode.LOCAL_INVALID_ARGUMENT
        request = None
        if code is not None:
            if reserved:
                cleanup_code = _release_preparation_paid(
                    preparation, execution_ledger, paid, unreturned=True
                )
                _reject(cleanup_code, flag)
            preparation = None
    _reject(code, flag)
    return preparation


def _operation_profile(ticket, ledger, /, *, reservation):
    """Return only this live issuer's profile from the existing RUNNING A."""
    flag = _context(ledger)
    _require_handles(flag, ticket)
    if not _reservation_live(reservation):
        _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=flag)
    code = profile = None
    with _registry._synchronized():
        physical = _ticket(ticket, ledger)
        if (
            physical is None
            or physical.operation.get("issuer") is not reservation
            or physical.operation["state"] != "RUNNING"
            or not physical.operation["running"]
        ):
            code = ErrorCode.INVALID_OBSERVATION
        else:
            profile = physical.operation["prep"].get("profile")
        physical = None
    _reject(code, flag)
    return profile

"""Bounded canonical T1 identity/exclusion primitive, not a driver adapter.

One initial association per retained cell. No reset, reclamation, pool reuse,
transaction-history proof, physical-close authority or outcome receipts.
Load this canonical module once; reload/aliases/private mutation/fork unsupported.
"""

from contextlib import contextmanager
from threading import Lock

from .errors import ErrorCode, _fail
from .ledger import ExecutionLedger
from .resource_registry import resource_domain


class _Opaque:
    __slots__ = ()

    def __new__(cls):
        raise TypeError("Lifecycle identities are issued internally")

    def __init_subclass__(cls, **kwargs):
        if cls.__bases__ != (_Opaque,):
            raise TypeError("Lifecycle identities cannot be subclassed")

    def __setattr__(self, name, value):
        raise AttributeError("Lifecycle identities are immutable")

    def __delattr__(self, name):
        raise AttributeError("Lifecycle identities are immutable")

    def __repr__(self):
        return "<" + type(self).__name__ + ">"

    def __copy__(self):
        raise TypeError("Lifecycle identities cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("Lifecycle identities cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("Lifecycle identities cannot be serialized")


class ResourceCell(_Opaque):
    """One retained actual-resource identity; no resource authority itself."""

    __slots__ = ("_key", "_stamp", "_terminal")


class ResourceAssociation(_Opaque):
    """One-shot exact checkout/root/ledger association, generation one only."""

    __slots__ = ("_cell", "_checkout", "_root", "_ledger")

    @property
    def generation(self):
        return 1


class OperationTicket(_Opaque):
    """Single current operation identity, with no historical ticket retention."""

    __slots__ = ("_association",)


class RetirementReceipt(_Opaque):
    """Only the permanent local retirement, never driver-close authority."""

    __slots__ = ("_association",)


def _issue(kind, **fields):
    value = object.__new__(kind)
    for name, field in fields.items():
        object.__setattr__(value, name, field)
    return value


class _CellState:
    __slots__ = ("resource", "cell", "association", "ticket", "retired", "receipt", "acknowledged")

    def __init__(self, resource):
        self.resource = resource
        self.cell = _issue(ResourceCell, _key=id(resource))
        self.association = self.ticket = self.receipt = None
        self.retired = self.acknowledged = False


_domain = resource_domain()
_lock = Lock()
_limit = None
_mode = None  # Once-only T1 or managed startup, same canonical table/mutex.
_cells = {}  # Integer keys only; each value permanently retains the real object.


def _context(ledger):
    # Never called with registry mutex held. This exact ledger is the authority
    # for a contextual snapshot, not copied categories or a facade's local flag.
    if type(ledger) is not ExecutionLedger:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=False)
    return ledger.uncertainty.present


@contextmanager
def _synchronized():
    primary = None
    try:
        with _lock:
            try:
                yield
            except BaseException as error:
                # Retain fields before fallible mutex exit can replace this
                # failure or interpreter chaining can alter its context.
                # Built-in descriptors invoke no exception-subclass hooks.
                primary = error
                cause = BaseException.__cause__.__get__(primary)
                context = BaseException.__context__.__get__(primary)
                suppressed = BaseException.__suppress_context__.__get__(primary)
                raise
    except BaseException as error:
        if primary is None:
            primary = error
            cause = BaseException.__cause__.__get__(primary)
            context = BaseException.__context__.__get__(primary)
            suppressed = BaseException.__suppress_context__.__get__(primary)
        # Lock/publication outcome may be unknown. Containment uses a separate
        # permanent latch; never substitute a fresh registry or replace primary.
        try:
            _domain.trip()
        except BaseException:
            pass
        try:
            raise primary
        except BaseException:
            # Restore captured primary fields after cleanup/containment; no
            # transitive secondary metadata or traceback identity is promised.
            BaseException.__cause__.__set__(primary, cause)
            BaseException.__context__.__set__(primary, context)
            BaseException.__suppress_context__.__set__(primary, suppressed)
            raise


def _reject(code, unconfirmed):
    # Expected rejections are raised only after leaving the registry mutex.
    if code is not None:
        _fail(code, unconfirmed=unconfirmed)


def _state_for_cell(cell):
    state = _cells.get(cell._key)
    return state if state is not None and state.cell is cell else None


def _state_for_association(association, root, ledger):
    state = _state_for_cell(association._cell)
    if (
        state is not None
        and state.association is association
        and association._root is root
        and association._ledger is ledger
    ):
        return state
    return None


def _binding_context(association, root, ledger):
    unconfirmed = _context(ledger)
    if type(association) is not ResourceAssociation or root is None:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=unconfirmed)
    return unconfirmed


def _usable(state):
    return _limit is not None and not _domain.stopped and not state.retired


def configure_registry(*, retained_cell_limit, execution_ledger):
    """Configure once, explicitly; no default, reset or proportional allocation."""
    global _limit, _mode
    unconfirmed = _context(execution_ledger)
    if type(retained_cell_limit) is not int or retained_cell_limit <= 0:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=unconfirmed)
    code = None
    with _synchronized():
        if _limit is not None or _domain.stopped:
            code = ErrorCode.PROFILE_REJECTED
        else:
            _limit = retained_cell_limit
            _mode = "T1"
    _reject(code, unconfirmed)


def resource_cell(actual_resource, /, *, execution_ledger):
    """Resolve already-observed physical identity; caller resolves all aliases."""
    unconfirmed = _context(execution_ledger)
    if actual_resource is None:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=unconfirmed)
    if _mode == "MANAGED":
        from .managed_lifecycle import _lookup

        return _lookup(actual_resource, execution_ledger=execution_ledger)
    # Candidate and argument retain all external refs through mutex exit. The
    # graph has no state->cell->state cycle whose later GC could finalize here.
    candidate = _CellState(actual_resource)
    key = id(actual_resource)
    cell, code = None, None
    managed_selected = False
    with _synchronized():
        if _mode == "MANAGED":
            # Startup selection linearizes before ANY T1 table publication.
            managed_selected = True
        else:
            current = _cells.get(key)
            if current is not None:
                if current.resource is actual_resource:
                    cell = current.cell
                else:
                    # Retention makes real id reuse impossible; never overwrite.
                    code = ErrorCode.INVALID_OBSERVATION
            elif _limit is None or _domain.stopped:
                code = ErrorCode.PROFILE_REJECTED
            elif len(_cells) >= _limit:
                code = ErrorCode.CAPACITY_EXCEEDED
            else:
                _cells[key] = candidate
                cell = candidate.cell
    if managed_selected:
        # Optional lookup/driver-shape resolution never executes under _lock.
        from .managed_lifecycle import _lookup

        return _lookup(actual_resource, execution_ledger=execution_ledger)
    _reject(code, unconfirmed)
    return cell


def bind_initial(cell, /, *, checkout_witness, root_witness, execution_ledger):
    """Issue one association once; repeating arguments cannot recover its return."""
    unconfirmed = _context(execution_ledger)
    if type(cell) is not ResourceCell or checkout_witness is None or root_witness is None:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=unconfirmed)
    if _mode == "MANAGED":
        _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=unconfirmed)
    candidate = _issue(
        ResourceAssociation,
        _cell=cell,
        _checkout=checkout_witness,
        _root=root_witness,
        _ledger=execution_ledger,
    )
    code = None
    with _synchronized():
        if _mode == "MANAGED":
            code = ErrorCode.PROFILE_REJECTED
        else:
            state = _state_for_cell(cell)
            if state is None:
                code = ErrorCode.INVALID_OBSERVATION
            elif state.association is not None:
                code = ErrorCode.INVALID_OBSERVATION
            elif not _usable(state):
                code = ErrorCode.PROFILE_REJECTED
            else:
                state.association = candidate
    _reject(code, unconfirmed)
    return candidate


def try_admit(association, /, *, root_witness, execution_ledger):
    """Publish one exact operation ticket; a contender fails immediately."""
    unconfirmed = _binding_context(association, root_witness, execution_ledger)
    candidate = _issue(OperationTicket, _association=association)
    code = None
    with _synchronized():
        state = _state_for_association(association, root_witness, execution_ledger)
        if state is None:
            code = ErrorCode.INVALID_OBSERVATION
        elif not _usable(state):
            code = ErrorCode.PROFILE_REJECTED
        elif state.ticket is not None:
            code = ErrorCode.RESOURCE_BUSY
        else:
            state.ticket = candidate
    _reject(code, unconfirmed)
    return candidate


def _ticket_operation(ticket, association, root, ledger, *, release):
    unconfirmed = _binding_context(association, root, ledger)
    if type(ticket) is not OperationTicket:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=unconfirmed)
    code = None
    with _synchronized():
        state = _state_for_association(association, root, ledger)
        if state is None or ticket._association is not association or state.ticket is not ticket:
            code = ErrorCode.INVALID_OBSERVATION
        elif release:
            # Function argument retains ticket through exit; no finalizer here.
            state.ticket = None
        elif not _usable(state):
            code = ErrorCode.PROFILE_REJECTED
    _reject(code, unconfirmed)


def validate_ticket(ticket, /, *, association, root_witness, execution_ledger):
    """Validate current ticket at acceptance; retirement/stop wins if first."""
    _ticket_operation(ticket, association, root_witness, execution_ledger, release=False)


def release_ticket(ticket, /, *, association, root_witness, execution_ledger):
    """Consume exact current ticket, including cleanup after retirement/stop."""
    _ticket_operation(ticket, association, root_witness, execution_ledger, release=True)


def retire_cell(association, /, *, root_witness, execution_ledger):
    """One-shot local retirement; lost return cannot be reconstructed/reissued."""
    unconfirmed = _binding_context(association, root_witness, execution_ledger)
    candidate = _issue(RetirementReceipt, _association=association)
    code = None
    with _synchronized():
        state = _state_for_association(association, root_witness, execution_ledger)
        if state is None:
            code = ErrorCode.INVALID_OBSERVATION
        elif not _usable(state):
            code = ErrorCode.PROFILE_REJECTED
        else:
            state.retired = True
            state.receipt = candidate
    _reject(code, unconfirmed)
    return candidate


def acknowledge_retirement(receipt, /, *, association, root_witness, execution_ledger):
    """Echo exact delivered local receipt; repeated acknowledgement has no effect."""
    unconfirmed = _binding_context(association, root_witness, execution_ledger)
    if type(receipt) is not RetirementReceipt:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=unconfirmed)
    code = None
    with _synchronized():
        state = _state_for_association(association, root_witness, execution_ledger)
        if (
            state is None
            or receipt._association is not association
            or not state.retired
            or state.receipt is not receipt
        ):
            code = ErrorCode.INVALID_OBSERVATION
        else:
            state.acknowledged = True
    _reject(code, unconfirmed)

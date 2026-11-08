"""Explicit optional psycopg 3.3.8 synchronous lifecycle issuer.

Supported integration is cooperative fresh ManagedConnection.connect, no direct
PGconn wrapping/reinitialization/pool transfer/raw transaction bypass. Exact
class does not prove that provenance. No autonomous finalization or DB connect.
Normal COMMIT responses are distinguished; final guard rejection remains UNKNOWN.
"""

import psycopg
from psycopg import pq
from psycopg.rows import tuple_row

from . import managed_lifecycle as _managed
from . import resource_lifecycle as _registry
from .errors import ErrorCode, _fail


class ManagedConnection(psycopg.Connection):
    """Actual driver object with a permanent inert canonical identity anchor."""

    __slots__ = ("__cell",)

    def __init_subclass__(cls, **kwargs):
        raise TypeError("ManagedConnection cannot be subclassed")

    def __init__(self, pgconn, row_factory=tuple_row):
        try:
            _anchor_slot.__get__(self, ManagedConnection)
        except AttributeError:
            pass
        else:
            raise TypeError("ManagedConnection cannot be reinitialized")
        if not _managed._active() or psycopg.__version__ != "3.3.8":
            raise TypeError("select managed startup before construction")
        super().__init__(pgconn, row_factory=row_factory)
        cell = _registry._issue(
            _registry.ResourceCell, _key=id(self), _stamp=object(), _terminal=False
        )
        _anchor_slot.__set__(self, cell)

    @classmethod
    def connect(cls, conninfo="", *, execution_ledger, **kwargs):
        """Caller-owned acquisition; admitted-live budgets start only at attach."""
        flag = _managed._context(execution_ledger)
        if not _managed._active() or psycopg.__version__ != "3.3.8":
            _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=flag)
        return super().connect(conninfo, **kwargs)


_anchor_slot = ManagedConnection.__dict__["_ManagedConnection__cell"]
# One explicitly imported optional implementation, never a public issuer registry.
assert _managed._native_type is None
_managed._native_type = ManagedConnection
_managed._cell_descriptor = _anchor_slot


def attach_native(actual, execution, /, *, execution_ledger):
    return _managed.attach_native(actual, execution, execution_ledger=execution_ledger)


def _shape(handle, ledger):
    flag = _managed._context(ledger)
    if type(handle) is not _managed._Handle:
        _fail(ErrorCode.LOCAL_INVALID_ARGUMENT, unconfirmed=flag)
    return flag


def _borrow(handle, ledger):
    with _registry._synchronized():
        state = _managed._physical(handle, ledger)
        assert state is not None
        actual, original = state.resource, state.pgconn
    state = None
    return actual, original


def _live(actual, original, statuses):
    # All public driver observations stay outside registry synchronization.
    return (
        actual.pgconn is original
        and not actual.closed
        and not actual.autocommit
        and original.transaction_status in statuses
        and original.pipeline_status == pq.PipelineStatus.OFF
    )


def _capture(error):
    return (
        error,
        BaseException.__cause__.__get__(error),
        BaseException.__context__.__get__(error),
        BaseException.__suppress_context__.__get__(error),
    )


def _raise_primary(primary):
    error, cause, context, suppressed = primary
    try:
        raise error
    except BaseException:
        BaseException.__cause__.__set__(error, cause)
        BaseException.__context__.__set__(error, context)
        BaseException.__suppress_context__.__set__(error, suppressed)
        raise


def start_root(checkout, /, *, execution_ledger):
    """Caller explicitly starts via bounded SELECT 1 and driver implicit BEGIN."""
    flag = _shape(checkout, execution_ledger)
    primary = None
    code = None
    known = False
    try:
        with _managed._construction(flag):
            root, code = _managed._reserve_root(checkout, execution_ledger)
            actual = original = cursor = None
            if code is None:
                actual, original = _borrow(root, execution_ledger)
                try:
                    if not _live(actual, original, (pq.TransactionStatus.IDLE,)):
                        code = ErrorCode.PROFILE_REJECTED
                    else:
                        cursor = psycopg.Cursor(actual, row_factory=tuple_row)
                        cursor.execute("SELECT 1", prepare=False)
                except BaseException as error:
                    primary = _capture(error)
                finally:
                    if cursor is not None:
                        try:
                            cursor.close()
                        except BaseException as error:
                            if primary is None:
                                primary = _capture(error)
                try:
                    known = (
                        code is None
                        and primary is None
                        and _live(actual, original, (pq.TransactionStatus.INTRANS,))
                    )
                except BaseException as error:
                    if primary is None:
                        primary = _capture(error)
                if not known:
                    execution_ledger.note_incident(ErrorCode.OUTCOME_UNKNOWN)
                    if code is None:
                        code = ErrorCode.OUTCOME_UNKNOWN
                _managed._complete_start(root, execution_ledger, known=known)
            cursor = actual = original = None
            if primary is not None:
                # Escape while D still owns driver/cursor traceback frames.
                # UNKNOWN bookkeeping above precedes permanent containment.
                _raise_primary(primary)
    except BaseException as failure:
        # A secondary union/publication/cleanup failure cannot replace the
        # first actual public-call failure. Construction retains D/contains.
        if primary is None:
            primary = _capture(failure)
        actual = original = None
    if primary is not None:
        _raise_primary(primary)
    _managed._reject(code, _managed._context(execution_ledger))
    return root


def rollback(root, /, *, execution_ledger):
    """Observe actual full-root rollback, never idle/no-op or savepoint history."""
    flag = _shape(root, execution_ledger)
    primary = None
    code = None
    known = False
    try:
        with _managed._construction(flag):
            _operation, receipt, code = _managed._reserve_rollback(root, execution_ledger)
            actual = original = None
            if code is None:
                actual, original = _borrow(root, execution_ledger)
                try:
                    if not _live(
                        actual,
                        original,
                        (pq.TransactionStatus.INTRANS, pq.TransactionStatus.INERROR),
                    ):
                        code = ErrorCode.PROFILE_REJECTED
                    else:
                        psycopg.Connection.rollback(actual)
                        known = _live(actual, original, (pq.TransactionStatus.IDLE,))
                except BaseException as error:
                    primary = _capture(error)
                _managed._complete_rollback(root, execution_ledger, known=known)
                if not known and code is None:
                    code = ErrorCode.OUTCOME_UNKNOWN
            actual = original = _operation = None
            if primary is not None:
                # Escape while D still owns driver/cursor traceback frames.
                # UNKNOWN bookkeeping above precedes permanent containment.
                _raise_primary(primary)
    except BaseException as failure:
        # A secondary union/publication/cleanup failure cannot replace the
        # first actual public-call failure. Construction retains D/contains.
        if primary is None:
            primary = _capture(failure)
        actual = original = None
    if primary is not None:
        _raise_primary(primary)
    _managed._reject(code, _managed._context(execution_ledger))
    return receipt


def commit(root, /, *, execution_ledger):
    """Observe fixed public COMMIT response; errors retain conservative S2."""
    flag = _shape(root, execution_ledger)
    primary = None
    observed_tag = outcome = None
    try:
        with _managed._construction(flag):
            _operation, receipt, code = _managed._reserve_rollback(
                root, execution_ledger, commit=True
            )
            actual = original = cursor = result = tag = None
            if code is None:
                actual, original = _borrow(root, execution_ledger)
                try:
                    if not _live(
                        actual,
                        original,
                        (pq.TransactionStatus.INTRANS, pq.TransactionStatus.INERROR),
                    ):
                        code = ErrorCode.PROFILE_REJECTED
                    else:
                        cursor = psycopg.Cursor(actual, row_factory=tuple_row)
                        cursor.execute("COMMIT", prepare=False)
                        result = cursor.pgresult
                        if result is not None and result.status == pq.ExecStatus.COMMAND_OK:
                            tag = result.command_status
                            if tag == b"COMMIT":
                                observed_tag = _managed.CommitOutcome.COMMITTED
                            elif tag == b"ROLLBACK":
                                observed_tag = _managed.CommitOutcome.ABORTED_COMMIT_ROLLED_BACK
                            if (
                                observed_tag is not None
                                and cursor.statusmessage == _observed_tag_command(observed_tag)
                                and cursor.nextset() is None
                            ):
                                outcome = observed_tag
                except BaseException as error:
                    primary = _capture(error)
                finally:
                    if cursor is not None:
                        try:
                            cursor.close()
                        except BaseException as error:
                            if primary is None:
                                primary = _capture(error)
                try:
                    if (
                        code is not None
                        or primary is not None
                        or not _live(actual, original, (pq.TransactionStatus.IDLE,))
                    ):
                        outcome = None
                except BaseException as error:
                    if primary is None:
                        primary = _capture(error)
                    outcome = None
                _managed._complete_commit(
                    root, execution_ledger, outcome=outcome, observed_tag=observed_tag
                )
                if outcome is None and code is None:
                    code = ErrorCode.OUTCOME_UNKNOWN
            result = cursor = tag = actual = original = _operation = None
            if primary is not None:
                # Escape with all actual/cursor/result traceback graphs charged.
                _raise_primary(primary)
    except BaseException as failure:
        if primary is None:
            primary = _capture(failure)
        result = cursor = tag = actual = original = None
    if primary is not None:
        _raise_primary(primary)
    _managed._reject(code, _managed._context(execution_ledger))
    return receipt


def _observed_tag_command(outcome):
    # Fixed internal classification; never a public arbitrary issuer/getter.
    return "COMMIT" if outcome is _managed.CommitOutcome.COMMITTED else "ROLLBACK"


def close(permit, /, *, execution_ledger):
    """Observe caller-selected public close under the cooperative unpooled profile."""
    flag = _shape(permit, execution_ledger)
    primary = None
    known = False
    try:
        with _managed._construction(flag):
            _operation, receipt, code = _managed._reserve_close(permit, execution_ledger)
            actual = original = None
            if code is None:
                actual, original = _borrow(permit, execution_ledger)
                try:
                    if actual.pgconn is not original or actual.closed:
                        code = ErrorCode.PROFILE_REJECTED
                    else:
                        psycopg.Connection.close(actual)
                        known = actual.pgconn is original and actual.closed
                except BaseException as error:
                    primary = _capture(error)
                if not known:
                    execution_ledger.note_incident(ErrorCode.OUTCOME_UNKNOWN)
                    if code is None:
                        code = ErrorCode.OUTCOME_UNKNOWN
                _managed._complete_close(permit, execution_ledger, known=known)
            actual = original = _operation = None
            if primary is not None:
                # Escape while D still owns driver/cursor traceback frames.
                # UNKNOWN bookkeeping above precedes permanent containment.
                _raise_primary(primary)
    except BaseException as failure:
        # A secondary union/publication/cleanup failure cannot replace the
        # first actual public-call failure. Construction retains D/contains.
        if primary is None:
            primary = _capture(failure)
        actual = original = None
    if primary is not None:
        _raise_primary(primary)
    _managed._reject(code, _managed._context(execution_ledger))
    return receipt

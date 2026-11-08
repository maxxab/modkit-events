"""Optional fixed E14/E28 issuer on the original caller-owned managed root.

Cooperative fresh/unpooled psycopg 3.3.8, libpq 180006 profile. No nested/raw
transaction bypass, global/custom adapter changes, concurrent direct connection
use, or endpoint/schema replacement. No automatic finalization or replay.
"""

import psycopg
from psycopg import pq
from psycopg.rows import tuple_row
from psycopg.types.string import ByteaBinaryLoader, BytesBinaryDumper

from . import managed_lifecycle as _managed
from . import native_sync as _native
from .bindings import _freeze_request_raw, _return_context_raw
from .catalog import CardinalityKind, get_statement
from .errors import ErrorCode, PersistenceError, _fail, _ValidationReject
from .native_codec import _decode_binary_transport_row, _selected_sql_descriptor
from .rows import _decode_outbox_raw

_PREPARATION_BYTES = 1024
_FIXED_WIDTHS = {16: 1, 5069: 8, 23: 4, 2950: 16, 20: 8, 1184: 8, 17: -1}


def prepare(execution, statement, parameters, /, *, execution_ledger):
    """One paid frame reserves before freezing; no database or nested D use."""
    flag = _managed._context(execution_ledger)
    _managed._require_handles(flag, execution)
    with _managed._construction(flag) as paid:
        preparation, code = _managed._reserve_preparation_paid(
            execution, _PREPARATION_BYTES, execution_ledger, paid
        )
        reserved = code is None
        request = None
        if reserved:
            try:
                request = _freeze_request_raw(statement, parameters, context=_return_context_raw())
            except _ValidationReject as error:
                if type(error) is not _ValidationReject:
                    raise
                code = ErrorCode.LOCAL_INVALID_ARGUMENT
            if code is None:
                code = _managed._set_preparation_paid(
                    preparation, request, execution_ledger, paid, unreturned=True
                )
        # Known rejection cleanup is still under this reservation. Never
        # refund backing while the local request or helper's outgoing survives.
        request = None
        if code is not None:
            if reserved:
                cleanup_code = _managed._release_preparation_paid(
                    preparation, execution_ledger, paid, unreturned=True
                )
                # Failure to release this exact unreturned A is unexpected;
                # contain it instead of converting an uncertain drop to success.
                _managed._reject(cleanup_code, flag)
            preparation = None
    _managed._reject(code, flag)
    return preparation


def _invalid():
    _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=True)


def _materialize(cursor, request, descriptor):
    """Validate fixed metadata and SQL caps before copying the bounded row."""
    result = cursor.pgresult
    if (
        result is None
        or result.status != pq.ExecStatus.TUPLES_OK
        or result.nfields != len(descriptor.transport_columns)
        or result.binary_tuples != 1
    ):
        _invalid()
    count = result.ntuples
    if (
        type(count) is not int
        or count not in (0, 1)
        or (descriptor.cardinality is CardinalityKind.EXACT_ONE and count != 1)
        or result.command_status != (b"SELECT 1" if count else b"SELECT 0")
        or result.command_tuples != count
        or cursor.rowcount != count
        or cursor.statusmessage != ("SELECT 1" if count else "SELECT 0")
    ):
        _invalid()
    for index, column in enumerate(descriptor.transport_columns):
        if (
            result.fname(index) != column.name.encode("ascii")
            or result.ftype(index) != column.oid
            or result.fformat(index) != 1
            or result.fsize(index) != _FIXED_WIDTHS[column.oid]
        ):
            _invalid()
    value = None
    if count:
        cap = result.get_value(0, 0)
        if type(cap) is not bytes or cap != b"\x01":
            _invalid()
        # Fixed SQL CASE expressions cap variable fields before they enter
        # PGresult. Built-in binary OIDs bound fixed fields; no private pointer
        # access or post-copy length check masquerades as a pre-copy proof.
        copied = (cap,) + tuple(result.get_value(0, i) for i in range(1, result.nfields))
        try:
            decoded = _decode_binary_transport_row(request.statement, copied)
            value = (
                decoded[0]
                if request.statement is get_statement("E14")
                else _decode_outbox_raw(decoded)
            )
        except _ValidationReject as error:
            if type(error) is not _ValidationReject:
                raise
            _invalid()
    if cursor.nextset() is not None:
        _invalid()
    return value


def _stopped(actual, original):
    """Conservative original-connection quiescence, never closure recovery."""
    return (
        actual is not None
        and original is not None
        and actual.pgconn is original
        and not actual.closed
        and original.transaction_status
        in (pq.TransactionStatus.IDLE, pq.TransactionStatus.INTRANS, pq.TransactionStatus.INERROR)
    )


def execute(ticket, result, /, *, execution_ledger):
    """Populate the reserved result on the caller root, without finalizing it.

    The caller must reserve one result before this call (64 bytes for E14 or
    4 MiB for every valid E28 row). Read it through managed read_result after
    return. Capacity/setter rejection after execution is held, not retryable.
    """
    flag = _native._shape(ticket, execution_ledger)
    primary = expected = None
    with _managed._construction(flag) as paid:
        started = close_attempted = False
        actual = original = cursor = request = descriptor = value = None
        try:
            request = _managed._start_operation(ticket, result, execution_ledger, reservation=paid)
            started = True
            actual, original = _native._borrow(ticket, execution_ledger)
            if (
                psycopg.__version__ != "3.3.8"
                or pq.version() != 180006
                or not _native._live(actual, original, (pq.TransactionStatus.INTRANS,))
            ):
                _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=True)
            descriptor = _selected_sql_descriptor(request.statement)
            cursor = psycopg.RawCursor(actual, row_factory=tuple_row)
            cursor.adapters.register_dumper(bytes, BytesBinaryDumper)
            for column in descriptor.transport_columns:
                cursor.adapters.register_loader(column.oid, ByteaBinaryLoader)
            cursor.execute(descriptor.sql, request.parameters, prepare=False, binary=True)
            if not _native._live(actual, original, (pq.TransactionStatus.INTRANS,)):
                _invalid()
            value = _materialize(cursor, request, descriptor)
            close_attempted = True
            cursor.close()
            cursor = None
            if not _native._live(actual, original, (pq.TransactionStatus.INTRANS,)):
                _invalid()
            _managed.set_result(result, value, execution_ledger=execution_ledger)
            _managed._complete_operation(ticket, execution_ledger, known=True)
            _managed.validate_ticket(ticket, execution_ledger=execution_ledger)
        except BaseException as error:
            primary = _native._capture(error)
            owned = False
            try:
                owned = _managed._owns_operation_paid(ticket, execution_ledger, paid)
            except BaseException:
                # An uncertain ownership observation cannot authorize another
                # operation's transition or classify this as a local rejection.
                _native._raise_primary(primary)
            if not started and not owned and type(error) is PersistenceError:
                # Canonical pre-start rejection has no driver/cursor/request
                # graph. Drop this frame normally before rethrowing, so an
                # invalid or duplicate invocation cannot poison its neighbour.
                expected = primary
            else:
                if cursor is not None and not close_attempted:
                    try:
                        cursor.close()
                    except BaseException:
                        pass
                if owned:
                    stopped = False
                    try:
                        stopped = _stopped(actual, original)
                    except BaseException:
                        pass
                    try:
                        _managed._fail_operation_paid(
                            ticket, execution_ledger, paid, stopped=stopped
                        )
                    except BaseException:
                        # HELD precedes ledger union. Unexpected mutex failure
                        # still causes outer construction containment.
                        pass
                _native._raise_primary(primary)
        actual = original = cursor = request = descriptor = value = primary = None
    if expected is not None:
        _native._raise_primary(expected)

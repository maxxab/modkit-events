"""Optional fixed E14/E28 and W01/W02/W03 issuer on the original caller-owned managed root.

Cooperative fresh/unpooled psycopg 3.3.8, libpq 180006 profile. No nested/raw
transaction bypass, global/custom adapter changes, concurrent direct connection
use, or endpoint/schema replacement. No automatic finalization or replay.
"""

from datetime import datetime
from uuid import UUID

import psycopg
from psycopg import pq
from psycopg.rows import tuple_row
from psycopg.types.datetime import DatetimeBinaryDumper
from psycopg.types.numeric import Int4BinaryDumper
from psycopg.types.string import ByteaBinaryLoader, BytesBinaryDumper, StrBinaryDumper
from psycopg.types.uuid import UUIDBinaryDumper

from . import managed_lifecycle as _managed
from . import native_sync as _native
from .bindings import _freeze_request_raw, _return_context_raw
from .catalog import CardinalityKind, get_statement
from .errors import ErrorCode, PersistenceError, _fail, _ValidationReject
from .native_codec import _decode_binary_transport_row, _selected_sql_descriptor
from .rows import _decode_outbox_raw

_PREPARATION_BYTES = 1024
_FIXED_WIDTHS = {16: 1, 5069: 8, 23: 4, 2950: 16, 20: 8, 1184: 8, 17: -1}
# Exact canonical W03 positions, counted as occurrences even when bytes alias.
_W03_LARGE_COLUMNS = (
    13,  # intent_evidence
    14,  # semantic_input
    15,  # replay_input
    16,  # protected_binding
    30,  # result
    49,  # resolution_record_result
    52,  # resolution_record_evidence
    53,  # resolution_record_binding
    60,  # job_protected_binding
    61,  # job_semantic_input
    63,  # protected_sidecar
    64,  # protected_reference
    68,  # protected_recovery_metadata
    70,  # projection_metadata
)


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


def prepare_component(
    execution, operation, logical_request, /, *, execution_ledger, max_page_payload_bytes=None
):
    """Use the existing controller's one-D, reserve-before-builder boundary."""
    return _managed._prepare_component(
        execution,
        operation,
        logical_request,
        execution_ledger=execution_ledger,
        max_page_payload_bytes=max_page_payload_bytes,
    )


def _invalid():
    _fail(ErrorCode.INVALID_OBSERVATION, unconfirmed=True)


def _materialize(cursor, request, descriptor, operation=None, *, max_page_payload_bytes=None):
    """Validate the complete bounded page before publishing any typed result."""
    result = cursor.pgresult
    if (
        result is None
        or result.status != pq.ExecStatus.TUPLES_OK
        or result.nfields != len(descriptor.transport_columns)
        or result.binary_tuples != 1
    ):
        _invalid()
    limit = 1
    if operation is not None:
        from .native_profile import _result_row_limit

        try:
            limit = _result_row_limit(request, operation)
            if request.statement.key == "W03":
                from .native_profile import _validate_max_page_payload_bytes

                _validate_max_page_payload_bytes(max_page_payload_bytes)
        except _ValidationReject as error:
            if type(error) is not _ValidationReject:
                raise
            _invalid()
    count = result.ntuples
    if (
        type(count) is not int
        or not 0 <= count <= limit
        or (descriptor.cardinality is CardinalityKind.EXACT_ONE and count != 1)
    ):
        _invalid()
    tag = "SELECT " + str(count)
    if (
        result.command_status != tag.encode("ascii")
        or result.command_tuples != count
        or cursor.rowcount != count
        or cursor.statusmessage != tag
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
    page_payload_bytes = 0
    accumulator = [None] * count if operation is not None else None
    for row_index in range(count):
        cap = result.get_value(row_index, 0)
        if type(cap) is not bytes or cap != b"\x01":
            _invalid()
        # Fixed SQL CASE expressions cap variable fields before they enter
        # PGresult. Only this current bounded row is copied, never a driver page.
        copied = (cap,) + tuple(
            result.get_value(row_index, index) for index in range(1, result.nfields)
        )
        try:
            decoded = _decode_binary_transport_row(
                request.statement,
                copied,
                operation,
                request=request,
                max_page_payload_bytes=max_page_payload_bytes,
            )
            if max_page_payload_bytes is not None:
                # Binary decoding already preflighted exact bytes/None and caps.
                for index in _W03_LARGE_COLUMNS:
                    cell = decoded[index]
                    if cell is not None:
                        page_payload_bytes += len(cell)
                cell = None
                if page_payload_bytes > max_page_payload_bytes:
                    _invalid()
            if operation is not None:
                accumulator[row_index] = decoded
            else:
                value = (
                    decoded[0]
                    if request.statement is get_statement("E14")
                    else _decode_outbox_raw(decoded)
                )
        except _ValidationReject as error:
            if type(error) is not _ValidationReject:
                raise
            _invalid()
        copied = decoded = None
    if cursor.nextset() is not None:
        _invalid()
    if operation is not None:
        rows = tuple(accumulator)
        accumulator = None
        try:
            # One canonical page and the exact retained request enter the
            # package-owned whole-page callback under the issuer's existing D.
            value = operation.decode_rows(request, rows)
        except _ValidationReject as error:
            if type(error) is not _ValidationReject:
                raise
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
    4 MiB for every valid E28 row; Workers uses its retained-ticket capacity).
    Read it through managed read_result after return. Capacity/setter rejection
    after execution is held, not retryable.
    """
    flag = _native._shape(ticket, execution_ledger)
    primary = expected = None
    with _managed._construction(flag) as paid:
        started = close_attempted = False
        actual = original = cursor = request = operation = descriptor = value = None
        parameters = max_page_payload_bytes = None
        try:
            request = _managed._start_operation(ticket, result, execution_ledger, reservation=paid)
            started = True
            operation = _managed._operation_profile(ticket, execution_ledger, reservation=paid)
            if operation is not None and request.statement.key == "W03":
                max_page_payload_bytes = _managed._operation_max_page_payload_bytes(
                    ticket, execution_ledger, reservation=paid
                )
            actual, original = _native._borrow(ticket, execution_ledger)
            if (
                psycopg.__version__ != "3.3.8"
                or pq.version() != 180006
                or not _native._live(actual, original, (pq.TransactionStatus.INTRANS,))
            ):
                _fail(ErrorCode.PROFILE_REJECTED, unconfirmed=True)
            try:
                descriptor = _selected_sql_descriptor(
                    request.statement,
                    operation,
                    request=request,
                    max_page_payload_bytes=max_page_payload_bytes,
                )
            except _ValidationReject as error:
                if type(error) is not _ValidationReject:
                    raise
                _invalid()
            cursor = psycopg.RawCursor(actual, row_factory=tuple_row)
            cursor.adapters.register_dumper(bytes, BytesBinaryDumper)
            cursor.adapters.register_dumper(UUID, UUIDBinaryDumper)
            cursor.adapters.register_dumper(str, StrBinaryDumper)
            parameters = request.parameters
            if max_page_payload_bytes is not None:
                from psycopg.types.numeric import Int8BinaryDumper

                # W03's fixed SQL casts the retained limit to INT4 and Q to INT8.
                cursor.adapters.register_dumper(int, Int8BinaryDumper)
                parameters = parameters + (max_page_payload_bytes,)
            else:
                cursor.adapters.register_dumper(int, Int4BinaryDumper)
            cursor.adapters.register_dumper(datetime, DatetimeBinaryDumper)
            for column in descriptor.transport_columns:
                cursor.adapters.register_loader(column.oid, ByteaBinaryLoader)
            cursor.execute(descriptor.sql, parameters, prepare=False, binary=True)
            if not _native._live(actual, original, (pq.TransactionStatus.INTRANS,)):
                _invalid()
            value = _materialize(
                cursor,
                request,
                descriptor,
                operation,
                max_page_payload_bytes=max_page_payload_bytes,
            )
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
        actual = original = cursor = request = operation = descriptor = value = primary = None
        parameters = max_page_payload_bytes = None
    if expected is not None:
        _native._raise_primary(expected)

"""Raw selected-column decoding has bounded admission and no sanitizer."""

from datetime import datetime, timedelta, timezone, tzinfo
from uuid import UUID

import pytest

from modkit_events.persistence import catalog as C
from modkit_events.persistence import errors as E
from modkit_events.persistence import rows as R

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
UUID_TEXT = "12345678-1234-5678-9abc-123456789abc"
OUTBOX = (b"id", 1, b"envelope", b"replay", "pending", None, 0, None, None, None, None, NOW, NOW)


def capture(call):
    try:
        call()
    except BaseException as error:
        return error
    raise AssertionError("operation unexpectedly succeeded")


def raw(columns, values):
    function = getattr(R, "_decode_columns_raw", None)
    assert callable(function), "raw selected columns are missing"
    return function(columns, values)


def columns(key="E14"):
    return C.get_statement(key).result.columns


@pytest.mark.parametrize("value", [1, "1", 18446744073709551615, "18446744073709551615"])
def test_raw_e14_normalizes_one_xid(value):
    actual = raw(columns(), (value,))
    assert type(actual) is tuple and len(actual) == 1 and type(actual[0]) is int
    assert actual == (int(value),)
    assert R._decode_columns(columns(), [value]) == actual


def test_raw_e28_decodes_all_thirteen_columns_without_record_semantics():
    values = list(OUTBOX)
    values[5], values[7], values[8], values[9], values[10] = (
        UUID_TEXT,
        NOW,
        UUID_TEXT,
        b"receipt",
        b"outcome",
    )
    expected = list(values)
    expected[5] = expected[8] = UUID(UUID_TEXT)
    assert raw(columns("E28"), tuple(values)) == tuple(expected)
    assert R._decode_columns(columns("E28"), values) == tuple(expected)


def test_raw_e28_rejects_offset_timestamp_instead_of_normalizing():
    values = list(OUTBOX)
    values[7] = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))
    assert type(capture(lambda: raw(columns("E28"), tuple(values)))) is E._ValidationReject


def test_raw_e28_rejects_custom_timezone_before_hook():
    class HostileZone(tzinfo):
        def utcoffset(self, value):
            raise AssertionError("timezone hook invoked")

    values = list(OUTBOX)
    values[7] = datetime(2026, 1, 1, tzinfo=HostileZone())
    assert type(capture(lambda: raw(columns("E28"), tuple(values)))) is E._ValidationReject


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4, 6, 11, 12])
def test_raw_e28_nonnullable_columns_reject_none(index):
    values = list(OUTBOX)
    values[index] = None
    assert type(capture(lambda: raw(columns("E28"), tuple(values)))) is E._ValidationReject


@pytest.mark.parametrize("index", [5, 7, 8, 9, 10])
def test_raw_e28_nullable_columns_accept_none(index):
    assert raw(columns("E28"), OUTBOX)[index] is None


@pytest.mark.parametrize("index", [0, 2, 3, 9, 10])
def test_raw_e28_rejects_mutable_byte_columns_but_public_normalizes(index):
    values = list(OUTBOX)
    values[index] = bytearray(b"x")
    assert type(capture(lambda: raw(columns("E28"), tuple(values)))) is E._ValidationReject
    assert R._decode_columns(columns("E28"), values)[index] == b"x"


def test_raw_columns_accept_current_selected_statement_metadata():
    assert raw(columns("E06"), (1,)) == (1,)


@pytest.mark.parametrize("kind", ["copy", "list", "tuple_subclass", "foreign"])
def test_raw_columns_identity_gate_rejects_noncanonical_metadata_without_iteration(kind):
    class Foreign:
        def __iter__(self):
            raise AssertionError("foreign metadata iteration")

        def __eq__(self, other):
            raise AssertionError("foreign metadata equality")

    class Tuple(tuple):
        pass

    value = {
        "copy": tuple(list(columns())),
        "list": list(columns()),
        "tuple_subclass": Tuple(columns()),
        "foreign": Foreign(),
    }[kind]
    assert value is not columns()
    assert type(capture(lambda: raw(value, (1,)))) is E._ValidationReject


@pytest.mark.parametrize("kind", ["list", "iterator", "tuple_subclass", "foreign", "bytes"])
def test_raw_values_exact_tuple_admission_precedes_snapshot(monkeypatch, kind):
    class Tuple(tuple):
        pass

    class Foreign:
        def __iter__(self):
            raise AssertionError("foreign values iteration")

    value = {
        "list": [1],
        "iterator": iter([1]),
        "tuple_subclass": Tuple((1,)),
        "foreign": Foreign(),
        "bytes": b"1",
    }[kind]

    def fault(*args, **kwargs):
        raise AssertionError("snapshot reached before tuple admission")

    monkeypatch.setattr(R, "_snapshot_sequence", fault)
    assert type(capture(lambda: raw(columns(), value))) is E._ValidationReject


@pytest.mark.parametrize("count", [0, 2, 257])
def test_raw_arity_rejection_precedes_wire_work(monkeypatch, count):
    def fault(*args, **kwargs):
        raise AssertionError("wire conversion reached before arity check")

    monkeypatch.setattr(R, "_wire_scalar_raw", fault)
    assert type(capture(lambda: raw(columns(), (1,) * count))) is E._ValidationReject


@pytest.mark.parametrize("kind", ["list", "non_column", "over_bound"])
def test_raw_selected_columns_shape_is_revalidated(monkeypatch, kind):
    def fault(*args, **kwargs):
        raise AssertionError("snapshot reached before column shape admission")

    monkeypatch.setattr(R, "_snapshot_sequence", fault)
    result = C.get_statement("E14").result
    original = result.columns
    value = {"list": list(original), "non_column": (object(),), "over_bound": original * 257}[kind]
    try:
        object.__setattr__(result, "columns", value)
        assert type(capture(lambda: raw(value, (1,)))) is E._ValidationReject
    finally:
        object.__setattr__(result, "columns", original)


@pytest.mark.parametrize("field,value", [("name", ""), ("wire_type", "xid8"), ("nullable", 1)])
def test_raw_column_metadata_revalidation_precedes_scalar(monkeypatch, field, value):
    column = columns()[0]
    original = getattr(column, field)

    def fault(*args, **kwargs):
        raise AssertionError("scalar reached before metadata validation")

    monkeypatch.setattr(R, "_wire_scalar_raw", fault)
    try:
        object.__setattr__(column, field, value)
        assert type(capture(lambda: raw(columns(), (1,)))) is E._ValidationReject
    finally:
        object.__setattr__(column, field, original)


def test_raw_all_metadata_is_checked_before_any_scalar(monkeypatch):
    column = columns("E28")[-1]
    original = column.name

    def fault(*args, **kwargs):
        raise AssertionError("scalar reached before all metadata validation")

    monkeypatch.setattr(R, "_wire_scalar_raw", fault)
    try:
        object.__setattr__(column, "name", "")
        assert type(capture(lambda: raw(columns("E28"), OUTBOX))) is E._ValidationReject
    finally:
        object.__setattr__(column, "name", original)


def test_raw_column_metadata_avoids_public_constructor_boundary(monkeypatch):
    def fault(*args, **kwargs):
        raise AssertionError("public metadata validator reached")

    monkeypatch.setattr(C.ColumnSpec, "__post_init__", fault)
    assert raw(columns(), ("1",)) == (1,)


@pytest.mark.parametrize("boundary", ["catalog", "snapshot", "metadata", "wire"])
@pytest.mark.parametrize(
    "error_type", [MemoryError, ValueError, OverflowError, TypeError, RuntimeError, BaseException]
)
def test_raw_column_unexpected_faults_preserve_identity_and_metadata(
    monkeypatch, boundary, error_type
):
    primary = error_type("opaque")
    previous = capture(lambda: (_ for _ in ()).throw(primary)).__traceback__
    cause, context = LookupError("cause"), OSError("context")
    primary.__cause__, primary.__context__, primary.__suppress_context__ = cause, context, False
    primary.add_note("retained note")
    primary.opaque = object()
    opaque = primary.opaque
    selected = columns()

    def fault(*args, **kwargs):
        raise primary

    name = {
        "catalog": "get_statement",
        "snapshot": "_snapshot_sequence",
        "metadata": "_validate_column_spec",
        "wire": "_wire_scalar_raw",
    }[boundary]
    monkeypatch.setattr(R, name, fault, raising=False)
    caught = capture(lambda: raw(selected, (1,)))
    assert caught is primary
    assert (
        caught.__cause__ is cause
        and caught.__context__ is context
        and caught.__suppress_context__ is False
    )
    assert caught.__notes__ == ["retained note"] and caught.opaque is opaque
    trace = caught.__traceback__
    while trace is not None and trace is not previous:
        trace = trace.tb_next
    assert trace is previous


def test_public_columns_keep_generic_sequence_and_copy_metadata_support():
    class Sequence:
        def __len__(self):
            return 1

        def __getitem__(self, index):
            if index == 0:
                return "1"
            raise IndexError

    from collections.abc import Sequence as ABCSequence

    ABCSequence.register(Sequence)
    assert R._decode_columns(tuple(list(columns())), Sequence()) == (1,)


@pytest.mark.parametrize("values", [(), ("0",), (None,), (1, 2)])
def test_public_columns_failure_policy_stays_detached(values):
    caught = capture(lambda: R._decode_columns(columns(), values))
    assert type(caught) is E.PersistenceError and caught.code is E.ErrorCode.INVALID_OBSERVATION
    assert caught.unconfirmed is True
    assert (
        caught.__cause__ is None
        and caught.__context__ is None
        and caught.__suppress_context__ is True
    )

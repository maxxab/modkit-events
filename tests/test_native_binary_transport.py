"""Pure binary transport conversion is not a driver or result authority."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from modkit_events.persistence import bindings as B
from modkit_events.persistence import catalog as C
from modkit_events.persistence import errors as E
from modkit_events.persistence import native_codec as N
from modkit_events.persistence import rows as R

UTC = timezone.utc
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
IDENTITY = UUID("12345678-1234-5678-9abc-123456789abc")
WIRE_UUID = bytes.fromhex("12345678123456789abc123456789abc")
STATES = ("pending", "claimed", "publishing", "published", "rejected", "held")


def wire(**changes):
    values = [
        b"\x01",
        b"id",
        b"\x00\x00\x00\x01",
        b"envelope",
        b"replay",
        b"pending",
        None,
        bytes(8),
        None,
        None,
        None,
        None,
        bytes(8),
        bytes(8),
    ]
    for key, value in changes.items():
        values[int(key)] = value
    return tuple(values)


def raw(values, key="E28"):
    fn = getattr(N, "_decode_binary_transport_row", None)
    assert callable(fn), "pure binary transport row decoder is missing"
    return fn(C.get_statement(key), values)


def captured(call):
    try:
        call()
    except BaseException as error:
        return error
    raise AssertionError("operation unexpectedly succeeded")


def rejected(values, key="E28"):
    assert type(captured(lambda: raw(values, key))) is E._ValidationReject


@pytest.mark.parametrize(
    "encoded,want",
    [
        (b"\x00\x00\x00\x00\x00\x00\x00\x01", 1),
        (b"\xff" * 8, 18446744073709551615),
        (b"\x01\x02\x03\x04\x05\x06\x07\x08", 72623859790382856),
    ],
)
def test_e14_unsigned_network_xid(encoded, want):
    actual = raw((b"\x01", encoded), "E14")
    assert type(actual) is tuple and type(actual[0]) is int and actual == (want,)


def test_e14_zero_is_rejected_by_shared_raw_scalar():
    rejected((b"\x01", bytes(8)), "E14")


@pytest.mark.parametrize("state", STATES)
def test_e28_transports_all_states_without_interpreting_business_state(state):
    values = wire(
        **{
            "5": state.encode(),
            "6": WIRE_UUID,
            "8": bytes(8),
            "9": WIRE_UUID,
            "10": b"receipt",
            "11": b"outcome",
        }
    )
    actual = raw(values)
    assert actual == (
        b"id",
        1,
        b"envelope",
        b"replay",
        state,
        IDENTITY,
        0,
        EPOCH,
        IDENTITY,
        b"receipt",
        b"outcome",
        EPOCH,
        EPOCH,
    )
    for index in (1, 3, 4, 10, 11):
        assert actual[index - 1] is values[index]
    assert type(actual[4]) is str and type(actual[5]) is UUID
    assert actual[11].tzinfo is UTC


def test_nullables_remain_none_and_invalid_payload_is_not_parsed():
    result = raw(wire(**{"3": b"\xff", "4": b"\xff"}))
    assert result[2:4] == (b"\xff", b"\xff")
    assert all(result[index] is None for index in (5, 7, 8, 9, 10))


@pytest.mark.parametrize(
    "index,encoded,want",
    [
        (2, b"\x80\x00\x00\x00", -2147483648),
        (2, b"\x7f\xff\xff\xff", 2147483647),
        (2, b"\xff" * 4, -1),
        (7, b"\x80" + bytes(7), -9223372036854775808),
        (7, b"\x7f" + b"\xff" * 7, 9223372036854775807),
        (7, b"\xff" * 8, -1),
    ],
)
def test_fixed_signed_integer_network_order(index, encoded, want):
    value = raw(wire(**{str(index): encoded}))[index - 1]
    assert type(value) is int and value == want


@pytest.mark.parametrize(
    "micros,want",
    [
        (-63082281600000000, datetime(1, 1, 1, tzinfo=UTC)),
        (252455615999999999, datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)),
        (-1, datetime(1999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)),
        (0, EPOCH),
        (1, datetime(2000, 1, 1, 0, 0, 0, 1, tzinfo=UTC)),
        (86400000000, datetime(2000, 1, 2, tzinfo=UTC)),
        (5097600000000, datetime(2000, 2, 29, tzinfo=UTC)),
        (-946684800000000, datetime(1970, 1, 1, tzinfo=UTC)),
    ],
)
@pytest.mark.parametrize("index", [8, 12, 13])
def test_timestamp_epoch_precision_and_supported_utc_bounds(micros, want, index):
    actual = raw(wire(**{str(index): micros.to_bytes(8, "big", signed=True)}))[index - 1]
    assert type(actual) is datetime and actual == want and actual.tzinfo is UTC


@pytest.mark.parametrize("micros", [-63082281600000001, 252455616000000000, -(2**63), 2**63 - 1])
@pytest.mark.parametrize("index", [8, 12, 13])
def test_timestamp_unsupported_or_infinite_rejected_before_datetime(micros, index, monkeypatch):
    def guard(**kwargs):
        assert kwargs["microseconds"] != micros, "constructed unsupported timestamp"
        return timedelta(**kwargs)

    monkeypatch.setattr(N, "timedelta", guard, raising=False)
    rejected(wire(**{str(index): micros.to_bytes(8, "big", signed=True)}))


@pytest.mark.parametrize(
    "index,width", [(2, 4), (6, 16), (7, 8), (8, 8), (9, 16), (12, 8), (13, 8)]
)
@pytest.mark.parametrize("delta", [-1, 1])
def test_every_fixed_width_is_exact(index, width, delta):
    rejected(wire(**{str(index): bytes(width + delta)}))


@pytest.mark.parametrize("size", [0, 7, 9])
def test_xid_width_is_exact(size):
    rejected((b"\x01", bytes(size)), "E14")


@pytest.mark.parametrize(
    "index,limit", [(1, 256), (3, 1048576), (4, 1048576), (5, 10), (10, 4096), (11, 1048576)]
)
def test_every_variable_cap_accepts_boundary_and_rejects_overflow(index, limit):
    data = b"x" * limit
    actual = raw(wire(**{str(index): data}))[index - 1]
    assert actual == (data.decode() if index == 5 else data)
    if index != 5:
        assert actual is data
    rejected(wire(**{str(index): data + b"x"}))


@pytest.mark.parametrize(
    "encoded,want", [(b"", ""), (b"\xc3\xa9", "é"), (b"\xf0\x9f\x98\x80", "😀")]
)
def test_state_uses_strict_utf8_with_a_byte_not_character_cap(encoded, want):
    assert raw(wire(**{"5": encoded}))[4] == want


@pytest.mark.parametrize(
    "value",
    [
        b"\xff",
        b"\xc0\xaf",
        b"\xed\xa0\x80",
        b"\xc3",
        "text",
        bytearray(b"text"),
        memoryview(b"text"),
    ],
)
def test_state_invalid_encoding_and_mutable_views_rejected(value):
    rejected(wire(**{"5": value}))


@pytest.mark.parametrize("index", [1, 2, 3, 4, 5, 7, 12, 13])
def test_nonnullable_data_columns_reject_null(index):
    rejected(wire(**{str(index): None}))


@pytest.mark.parametrize("index", range(1, 14))
@pytest.mark.parametrize("value", [1, True, "text", bytearray(b"x"), memoryview(b"x")])
def test_data_cells_are_exact_immutable_bytes_or_permitted_null(index, value):
    rejected(wire(**{str(index): value}))


class Hostile:
    def __len__(self):
        raise AssertionError("foreign length")

    def __iter__(self):
        raise AssertionError("foreign iteration")

    def __eq__(self, other):
        raise AssertionError("foreign equality")

    def __bool__(self):
        raise AssertionError("foreign truthiness")

    def __bytes__(self):
        raise AssertionError("foreign bytes")


class BytesSubclass(bytes):
    def decode(self, *args, **kwargs):
        raise AssertionError("subclass decode")


class TupleSubclass(tuple):
    def __iter__(self):
        raise AssertionError("subclass iteration")


@pytest.mark.parametrize(
    "value",
    [None, 1, Hostile(), [], list(wire()), TupleSubclass(wire()), wire()[:-1], wire() + (None,)],
)
def test_row_exact_type_and_count_before_callback(value):
    rejected(value)


@pytest.mark.parametrize(
    "value",
    [b"\x00", b"\x02", b"", b"\x01\x00", True, 1, None, Hostile(), BytesSubclass(b"\x01")],
    ids=[f"cap-{i}" for i in range(9)],
)
def test_cap_rejects_before_inspecting_other_cells(value):
    rejected((value,) + (Hostile(),) * 13)


@pytest.mark.parametrize("index", range(1, 14))
def test_byte_subclasses_never_invoke_custom_behavior(index):
    rejected(wire(**{str(index): BytesSubclass(b"x")}))


@pytest.mark.parametrize("key", [f"E{i:02d}" for i in range(1, 35) if i not in (14, 28)])
def test_unsupported_statements_reject_before_values(key):
    rejected(Hostile(), key)


@pytest.mark.parametrize(
    "spec", [None, "E14", object(), Hostile(), object.__new__(C.StatementSpec)]
)
def test_fake_or_uninitialized_spec_rejects_before_values(spec):
    fn = getattr(N, "_decode_binary_transport_row", None)
    assert callable(fn), "pure binary transport row decoder is missing"
    assert type(captured(lambda: fn(spec, Hostile()))) is E._ValidationReject


@pytest.mark.parametrize("index,bad", [(13, b""), (13, None), (11, b"x" * 1048577), (5, b"x" * 11)])
def test_all_shape_preflight_precedes_any_conversion(index, bad, monkeypatch):
    class NoInt:
        @staticmethod
        def from_bytes(*args, **kwargs):
            raise AssertionError("converted before preflight")

    monkeypatch.setattr(N, "int", NoInt, raising=False)
    rejected(wire(**{str(index): bad}))


def test_raw_column_authority_receives_exact_canonical_tuple(monkeypatch):
    seen = []

    def inspect(columns, values):
        seen.append((columns, values))
        return values

    monkeypatch.setattr(N, "_decode_columns_raw", inspect, raising=False)
    actual = raw(wire())
    assert seen == [(C.get_statement("E28").result.columns, actual)]
    assert seen[0][0] is C.get_statement("E28").result.columns


def test_public_sanitizers_and_post_init_are_not_used(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("public sanitizer")

    monkeypatch.setattr(B, "_scalar", forbidden)
    monkeypatch.setattr(R, "_wire_scalar", forbidden)
    monkeypatch.setattr(C.ColumnSpec, "__post_init__", forbidden)
    assert raw((b"\x01", b"\x00\x00\x00\x00\x00\x00\x00\x01"), "E14") == (1,)


@pytest.mark.parametrize("boundary", ["select", "int", "uuid", "text", "timestamp", "columns"])
@pytest.mark.parametrize(
    "error_type", [MemoryError, ValueError, TypeError, OverflowError, RuntimeError, BaseException]
)
def test_unexpected_failures_preserve_exact_primary_and_received_tail(
    boundary, error_type, monkeypatch
):
    primary = error_type("opaque")
    previous = captured(lambda: (_ for _ in ()).throw(primary)).__traceback__
    cause, context = LookupError("cause"), OSError("context")
    primary.__cause__, primary.__context__, primary.__suppress_context__ = cause, context, False
    primary.add_note("retained")
    primary.opaque = object()
    opaque = primary.opaque

    def fault(*args, **kwargs):
        raise primary

    if boundary == "select":
        monkeypatch.setattr(N, "_selected_sql_descriptor", fault)
    elif boundary == "int":

        class BrokenInt:
            from_bytes = staticmethod(fault)

        monkeypatch.setattr(N, "int", BrokenInt, raising=False)
    else:
        monkeypatch.setattr(
            N,
            {
                "uuid": "UUID",
                "text": "_decode_utf8",
                "timestamp": "timedelta",
                "columns": "_decode_columns_raw",
            }[boundary],
            fault,
            raising=False,
        )
    caught = captured(lambda: raw(wire(**{"6": WIRE_UUID})))
    assert caught is primary
    assert (
        caught.__cause__ is cause
        and caught.__context__ is context
        and caught.__suppress_context__ is False
    )
    assert caught.__notes__ == ["retained"] and caught.opaque is opaque
    trace = caught.__traceback__
    while trace is not None and trace is not previous:
        trace = trace.tb_next
    assert trace is previous


@pytest.mark.parametrize("values", [(), (b"\x01",), (b"\x01", bytes(8), None)])
def test_e14_transport_count_is_exact(values):
    rejected(values, "E14")


@pytest.mark.parametrize("boundary", ["uuid", "text", "timestamp", "columns"])
def test_malformed_final_cell_blocks_every_converter(boundary, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("conversion before complete preflight")

    monkeypatch.setattr(
        N,
        {
            "uuid": "UUID",
            "text": "_decode_utf8",
            "timestamp": "timedelta",
            "columns": "_decode_columns_raw",
        }[boundary],
        forbidden,
        raising=False,
    )
    rejected(wire(**{"6": WIRE_UUID, "8": bytes(8), "13": b""}))


@pytest.mark.parametrize("index", [1, 3, 4, 5, 13])
def test_even_valid_width_byte_subclasses_reject_before_converters(index, monkeypatch):
    values = wire()
    replacement = BytesSubclass(values[index])

    class NoInt:
        @staticmethod
        def from_bytes(*args, **kwargs):
            raise AssertionError("subclass passed preflight")

    monkeypatch.setattr(N, "int", NoInt, raising=False)
    rejected(wire(**{str(index): replacement}))

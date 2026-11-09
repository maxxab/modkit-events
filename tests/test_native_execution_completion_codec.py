"""Pure completion transport tests; no driver or database qualification."""

from uuid import UUID

import pytest

from modkit_events.persistence.catalog import CardinalityKind, get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.native_codec import (
    _decode_binary_transport_row,
    _selected_sql_descriptor,
)


@pytest.mark.parametrize(
    "key,cap,width,cardinality",
    [
        ("E06", 5, 2, CardinalityKind.EXACT_ONE),
        ("E08", 123, 12, CardinalityKind.EXACT_ONE),
        ("E09", 123, 12, CardinalityKind.OPTIONAL_ONE),
        ("E10", 2, 2, CardinalityKind.EXACT_ONE),
    ],
)
def test_fixed_descriptors(key, cap, width, cardinality):
    descriptor = _selected_sql_descriptor(get_statement(key))
    assert descriptor.max_admitted_cell_payload_bytes == cap
    assert len(descriptor.transport_columns) == width
    assert descriptor.cardinality is cardinality
    assert descriptor.sentinel_limit == 2
    assert descriptor.sql.endswith(b"LIMIT 2")
    assert b"modkit_events." + key.lower().encode() + b"(" in descriptor.sql
    assert descriptor.canonical_columns == get_statement(key).result.columns


def guard_wire():
    return (
        b"\x01",
        UUID(int=1).bytes,
        UUID(int=2).bytes,
        (2**64 - 1).to_bytes(8, "big"),
        UUID(int=3).bytes,
        (2**63 - 1).to_bytes(8, "big"),
        (1).to_bytes(4, "big"),
        (1000).to_bytes(4, "big"),
        b"\x00",
        None,
        None,
        None,
    )


@pytest.mark.parametrize("key", ["E08", "E09"])
def test_complete_guard_transport(key):
    row = _decode_binary_transport_row(get_statement(key), guard_wire())
    assert len(row) == 11
    assert row[2] == 2**64 - 1
    assert row[4] == 2**63 - 1
    assert row[7:] == (False, None, None, None)
    d = _selected_sql_descriptor(get_statement(key))
    assert [(c.name, c.oid, c.nullable) for c in d.transport_columns[-3:]] == [
        ("final_fence_at", 1184, True),
        ("terminal_state", 17, True),
        ("result_digest", 17, True),
    ]
    assert b"convert_to" in d.sql and b"CASE WHEN c.cap_ok" in d.sql


@pytest.mark.parametrize(
    "index,value",
    [
        (0, b"\x00"),
        (1, None),
        (3, bytes(7)),
        (8, b"\x02"),
        (10, b"x" * 10),
        (11, b"x" * 33),
        (1, bytearray(16)),
    ],
)
def test_reject_malformed_guard_transport(index, value):
    row = list(guard_wire())
    row[index] = value
    with pytest.raises(_ValidationReject):
        _decode_binary_transport_row(get_statement("E08"), tuple(row))


def test_scalar_and_unsigned_root_cast():
    assert _decode_binary_transport_row(get_statement("E06"), (b"\x01", b"\x00\x00\x00\x01")) == (
        1,
    )
    assert _decode_binary_transport_row(get_statement("E10"), (b"\x01", b"\x01")) == (True,)
    d = _selected_sql_descriptor(get_statement("E10"))
    assert d.parameter_casts[2] == "pg_catalog.text"
    assert b"$3::pg_catalog.text::pg_catalog.xid8" in d.sql

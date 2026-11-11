"""Fixed bounded E32 binary transport; no actual driver qualification."""

import pytest
from test_native_uncertainty_contract import request, values

from modkit_events.persistence.catalog import CardinalityKind, get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.native_codec import (
    _decode_binary_transport_row,
    _selected_sql_descriptor,
)


def wire(req):
    v = values(req)
    return (
        b"\x01",
        v[0].bytes,
        v[1].bytes,
        v[2].bytes,
        v[3].to_bytes(8, "big"),
        v[4].to_bytes(4, "big"),
        v[5].to_bytes(4, "big"),
        v[6].bytes,
        v[7].to_bytes(8, "big"),
        v[8].encode(),
        v[9],
        v[10],
        v[11].to_bytes(8, "big"),
        bytes(8),
    )


def test_fixed_caps_and_unsigned_transport():
    d = _selected_sql_descriptor(get_statement("E32"))
    assert d.parameter_casts == (
        "pg_catalog.uuid",
        "pg_catalog.uuid",
        "pg_catalog.int8",
        "pg_catalog.int4",
        "pg_catalog.int4",
        "pg_catalog.text",
        "pg_catalog.uuid",
        "pg_catalog.text",
        "pg_catalog.bytea",
        "pg_catalog.bytea",
    )
    assert b"$6::pg_catalog.text::pg_catalog.xid8" in d.sql
    assert d.cardinality is CardinalityKind.EXACT_ONE and d.sentinel_limit == 2
    assert d.max_admitted_cell_payload_bytes == 2097513
    assert len(d.transport_columns) == 14
    assert [c.oid for c in d.transport_columns] == [
        16,
        2950,
        2950,
        2950,
        20,
        23,
        23,
        2950,
        5069,
        17,
        17,
        17,
        20,
        1184,
    ]
    assert all(not c.nullable for c in d.transport_columns)
    assert [c.max_payload_bytes for c in d.transport_columns] == [
        1,
        16,
        16,
        16,
        8,
        4,
        4,
        16,
        8,
        256,
        1048576,
        1048576,
        8,
        8,
    ]
    for xid in (1, 2**63 - 1, 2**63, 2**64 - 1):
        req = request(xid=xid, large=True)
        row = _decode_binary_transport_row(req.statement, wire(req))
        assert row[7] == xid and row[8:11] == req.parameters[7:10]


@pytest.mark.parametrize(
    "index,value",
    [
        (0, b"\x00"),
        (0, None),
        (1, None),
        (1, bytes(15)),
        (4, bytes(7)),
        (8, bytes(9)),
        (9, b"x" * 257),
        (9, b"\xff"),
        (10, b"x" * 1048577),
        (11, b"x" * 1048577),
        (12, bytearray(8)),
        (13, b"\x7f" * 8),
    ],
)
def test_binary_caps_types_widths_and_timestamps(index, value):
    req = request()
    row = list(wire(req))
    row[index] = value
    with pytest.raises(_ValidationReject):
        _decode_binary_transport_row(req.statement, tuple(row))


@pytest.mark.parametrize("change", [lambda r: r[:-1], lambda r: r + (b"",), list])
def test_binary_exact_column_count_and_immutable_tuple(change):
    req = request()
    with pytest.raises(_ValidationReject):
        _decode_binary_transport_row(req.statement, change(wire(req)))

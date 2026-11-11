"""Fixed E31 wire bounds; pure tests, not libpq qualification."""

import pytest
from test_native_resolution_contract import OUTCOMES, request, values

from modkit_events.persistence.catalog import CardinalityKind, WireType, get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.native_codec import (
    _decode_binary_transport_row,
    _selected_sql_descriptor,
)


def wire(req):
    cells = [b"\x01"]
    for col, v in zip(req.statement.result.columns, values(req)):
        if v is None:
            cells.append(None)
        elif col.wire_type is WireType.UUID:
            cells.append(v.bytes)
        elif col.wire_type is WireType.TEXT:
            cells.append(v.encode())
        elif col.wire_type is WireType.BYTEA:
            cells.append(v)
        elif col.wire_type is WireType.TIMESTAMPTZ:
            cells.append(bytes(8))
        else:
            cells.append(v.to_bytes(4 if col.wire_type is WireType.INT4 else 8, "big"))
    return tuple(cells)


def test_exact_physical_descriptor():
    d = _selected_sql_descriptor(get_statement("E31"))
    assert d.parameter_casts == tuple(
        "pg_catalog." + x
        for x in (
            "uuid",
            "int8",
            "int4",
            "int4",
            "uuid",
            "uuid",
            "text",
            "timestamptz",
            "bytea",
            "bytea",
            "bytea",
        )
    )
    assert [c.name for c in d.transport_columns] == ["cap_ok"] + [
        c.name for c in get_statement("E31").result.columns
    ]
    assert [c.oid for c in d.transport_columns] == [
        16,
        2950,
        17,
        2950,
        20,
        23,
        23,
        2950,
        17,
        1184,
        17,
        17,
        17,
        17,
        17,
        5069,
        1184,
    ]
    assert [c.max_payload_bytes for c in d.transport_columns] == [
        1,
        16,
        14,
        16,
        8,
        4,
        4,
        16,
        19,
        8,
        1048576,
        32,
        0,
        1048576,
        1048576,
        8,
        8,
    ]
    assert [i for i, c in enumerate(d.transport_columns) if c.nullable] == [9, 10, 11, 12]
    assert d.max_admitted_cell_payload_bytes == 3145882
    assert d.cardinality is CardinalityKind.EXACT_ONE and d.sentinel_limit == 2
    assert b"source AS MATERIALIZED" in d.sql and b"LIMIT 2" in d.sql
    assert b"c.reason" not in d.sql.split(b"SELECT c.cap_ok")[1]
    assert b"s.reason IS NULL" in d.sql
    assert b"pg_catalog.convert_to" in d.sql


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_binary_all_outcomes(outcome):
    req = request(outcome)
    assert _decode_binary_transport_row(req.statement, wire(req)) == values(req)


@pytest.mark.parametrize(
    "index,value",
    [
        (0, None),
        (0, b"\x00"),
        (1, bytes(15)),
        (1, None),
        (2, b"\xff"),
        (2, b"x" * 15),
        (4, bytes(7)),
        (5, bytes(5)),
        (8, b"x" * 20),
        (10, b"x" * 1048577),
        (11, b"x" * 33),
        (12, b"x"),
        (13, b"x" * 1048577),
        (14, b"x" * 1048577),
        (15, bytes(9)),
        (16, b"\x7f" * 8),
        (13, bytearray(b"x")),
    ],
)
def test_binary_preflight(index, value):
    req = request()
    row = list(wire(req))
    row[index] = value
    with pytest.raises(_ValidationReject):
        _decode_binary_transport_row(req.statement, tuple(row))


@pytest.mark.parametrize("change", [lambda r: r[:-1], lambda r: r + (b"",), list])
def test_exact_wire_shape(change):
    req = request()
    with pytest.raises(_ValidationReject):
        _decode_binary_transport_row(req.statement, change(wire(req)))

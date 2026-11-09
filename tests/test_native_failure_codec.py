"""Pure fixed E11 wire checks; not actual driver qualification."""

import pytest

from modkit_events.persistence.catalog import CardinalityKind, get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.native_codec import (
    _decode_binary_transport_row,
    _selected_sql_descriptor,
)


def test_e11_fixed_abi_and_unit_transport():
    descriptor = _selected_sql_descriptor(get_statement("E11"))
    assert descriptor.parameter_casts == (
        "pg_catalog.uuid", "pg_catalog.uuid", "pg_catalog.int8", "pg_catalog.int4",
        "pg_catalog.int4", "pg_catalog.text", "pg_catalog.text",
        "pg_catalog.timestamptz", "pg_catalog.text", "pg_catalog.bytea",
    )
    assert b"modkit_events.e11(" in descriptor.sql
    assert b"$6::pg_catalog.text::pg_catalog.xid8" in descriptor.sql
    assert descriptor.sql.endswith(b"LIMIT 2")
    assert descriptor.cardinality is CardinalityKind.EXACT_ONE
    assert descriptor.sentinel_limit == 2
    assert descriptor.max_admitted_cell_payload_bytes == 2
    assert [(c.name, c.oid, c.nullable, c.max_payload_bytes)
            for c in descriptor.transport_columns] == [
                ("cap_ok", 16, False, 1), ("ok", 16, False, 1)]
    assert _decode_binary_transport_row(get_statement("E11"), (b"\x01", b"\x01")) == (True,)


@pytest.mark.parametrize("row", [
    (), (b"\x01",), (b"\x01", b"\x01", b"\x01"),
    (b"\x00", b"\x01"), (None, b"\x01"), (b"\x01", None),
    (b"\x01", b"\x02"), (b"\x01", b"\x01\x00"),
    (b"\x01", bytearray(b"\x01")),
])
def test_e11_rejects_malformed_binary_carriers(row):
    with pytest.raises(_ValidationReject):
        _decode_binary_transport_row(get_statement("E11"), row)

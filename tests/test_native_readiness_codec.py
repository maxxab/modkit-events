"""Exact fixed binary E33 transport, not live qualification."""
import pytest

from modkit_events.persistence.catalog import CardinalityKind, get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.native_codec import (
    _decode_binary_transport_row,
    _selected_sql_descriptor,
)

WIRE = (b"\x01", b"events", (1).to_bytes(4, "big"), b"x"*32,
        b"modkit-pg-ab-2", b"MKSC-1", b"MKPF-1")


def test_e33_descriptor_and_binary_decoding():
    d = _selected_sql_descriptor(get_statement("E33"))
    assert d.parameter_casts == ("pg_catalog.text",)
    assert d.cardinality is CardinalityKind.READINESS and d.sentinel_limit == 3
    assert d.max_admitted_cell_payload_bytes == 812
    assert [(c.name, c.oid, c.max_payload_bytes) for c in d.transport_columns] == [
        ("cap_ok", 16, 1), ("component", 17, 7), ("version", 23, 4),
        ("migration_digest", 17, 32), ("catalog_contract_id", 17, 256),
        ("scope_format_id", 17, 256), ("intent_format_id", 17, 256)]
    assert _decode_binary_transport_row(get_statement("E33"), WIRE) == (
        "events", 1, b"x"*32, "modkit-pg-ab-2", "MKSC-1", "MKPF-1")


@pytest.mark.parametrize("index,value", [
    (0, b"\x00"), (0, None), (1, b"x"*8), (1, b"\xff"), (2, b"x"*3),
    (2, b"x"*5), (3, b"x"*33), (4, b"x"*257), (5, b"\xff"), (6, None),
])
def test_e33_invalid_binary_cells(index, value):
    row = list(WIRE)
    row[index] = value
    with pytest.raises(_ValidationReject):
        _decode_binary_transport_row(get_statement("E33"), tuple(row))

"""Fixed E05 timestamp transport; does not qualify the driver or SQL."""

from datetime import datetime, timezone

import pytest

from modkit_events.persistence.catalog import CardinalityKind, get_statement
from modkit_events.persistence.errors import _ValidationReject
from modkit_events.persistence.native_codec import (
    _decode_binary_transport_row,
    _selected_sql_descriptor,
)


def test_fixed_e05_descriptor_and_timestamp_decoding():
    spec = get_statement("E05")
    d = _selected_sql_descriptor(spec)
    assert d.parameter_casts == (
        "pg_catalog.uuid",
        "pg_catalog.uuid",
        "pg_catalog.int8",
        "pg_catalog.int4",
        "pg_catalog.int4",
        "pg_catalog.float8",
    )
    assert b"modkit_events.e05(" in d.sql and b"$6::pg_catalog.float8" in d.sql
    assert d.cardinality is CardinalityKind.EXACT_ONE
    assert d.sentinel_limit == 2 and d.max_admitted_cell_payload_bytes == 9
    assert [(c.name, c.oid, c.nullable, c.max_payload_bytes) for c in d.transport_columns] == [
        ("cap_ok", 16, False, 1),
        ("lease_until", 1184, False, 8),
    ]
    assert _decode_binary_transport_row(spec, (b"\x01", bytes(8))) == (
        datetime(2000, 1, 1, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    "micros,want",
    [
        (-63082281600000000, datetime(1, 1, 1, tzinfo=timezone.utc)),
        (252455615999999999, datetime.max.replace(tzinfo=timezone.utc)),
        (-1, datetime(1999, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)),
    ],
)
def test_supported_timestamp_boundaries(micros, want):
    assert _decode_binary_transport_row(
        get_statement("E05"), (b"\x01", micros.to_bytes(8, "big", signed=True))
    ) == (want,)


@pytest.mark.parametrize(
    "cells",
    [
        (),
        (b"\x01",),
        (b"\x01", bytes(8), b""),
        [b"\x01", bytes(8)],
        (b"\x00", bytes(8)),
        (None, bytes(8)),
        (b"\x01", None),
        (b"\x01", bytes(7)),
        (b"\x01", bytes(9)),
        (b"\x01", bytearray(8)),
    ]
    + [
        (b"\x01", n.to_bytes(8, "big", signed=True))
        for n in (
            -(2**63),
            2**63 - 1,
            -63082281600000001,
            252455616000000000,
        )
    ],
)
def test_malformed_or_out_of_domain_binary_row_rejected(cells):
    with pytest.raises(_ValidationReject):
        _decode_binary_transport_row(get_statement("E05"), cells)

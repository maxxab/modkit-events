"""Fixed transport metadata and complete pre-conversion refusal."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from recovery_test_support import requires_recovery_profile
from test_native_recovery_contract import header, request

from modkit_events.persistence import native_codec as N
from modkit_events.persistence.catalog import get_statement
from modkit_events.persistence.errors import _ValidationReject


def wire_header():
    return (b"\x01", b"header", (0).to_bytes(4, "big"), None, b"\x01") + (None,) * 56


@requires_recovery_profile
class CodecTests(unittest.TestCase):
    def plan(self, req=None):
        try:
            return N._selected_sql_descriptor(get_statement("E13"), request=req or request())
        except _ValidationReject:
            self.fail("canonical E13 descriptor missing")

    def test_abi_and_sentinel(self):
        for limit in (1, 256):
            d = self.plan(request(limit=limit, discovery_budget=4096))
            self.assertEqual(
                d.parameter_casts,
                (
                    "pg_catalog.bytea",
                    "pg_catalog.text",
                    "pg_catalog.int4",
                    "pg_catalog.uuid",
                    "pg_catalog.int4",
                ),
            )
            self.assertEqual(len(d.canonical_columns), 60)
            self.assertEqual(len(d.transport_columns), 61)
            self.assertEqual(d.sentinel_limit, limit + 2)
            self.assertEqual(d.max_admitted_cell_payload_bytes, 8395973)
            self.assertIn(b"LIMIT ($3::pg_catalog.int4 + 2)", d.sql)
            self.assertNotIn(b"$6", d.sql)

    def test_header_raw_whitelist(self):
        self.plan()
        self.assertEqual(
            N._decode_binary_transport_row(get_statement("E13"), wire_header(), request=request()),
            header(),
        )

    def test_all_cells_preflight_before_conversion(self):
        d = self.plan()
        for index, col in enumerate(d.transport_columns[1:], 1):
            cells = list(wire_header())
            cells[index] = b"x" * (col.max_payload_bytes + 1)
            with (
                self.subTest(column=col.name),
                patch.object(N, "_decode_utf8", side_effect=AssertionError("early conversion")),
            ):
                with self.assertRaises(_ValidationReject):
                    N._decode_binary_transport_row(
                        get_statement("E13"), tuple(cells), request=request()
                    )
        with self.assertRaises(_ValidationReject):
            N._selected_sql_descriptor(replace(get_statement("E13")), request=request())

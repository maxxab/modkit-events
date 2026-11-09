"""Static E31 source/ABI guards only; database qualification lives in native tests.
No product imports, driver imports, connections, or environment setup.
"""

import hashlib
import os
import re
import unittest
from pathlib import Path

SQL = Path(
    os.environ.get(
        "E31_SQL_PATH",
        str(Path(__file__).parents[1] / "src/modkit_events/persistence/sql/0001_initial.sql"),
    )
)
PARAMETERS = (
    ("work_id", "uuid"),
    ("expected_revision", "int8"),
    ("cycle", "int4"),
    ("attempt", "int4"),
    ("dispatch_id", "uuid"),
    ("operation_id", "uuid"),
    ("outcome", "text"),
    ("retry_at", "timestamptz"),
    ("result", "bytea"),
    ("evidence", "bytea"),
    ("binding", "bytea"),
)
COLUMNS = (
    ("operation_id", "uuid"),
    ("operation_kind", "text"),
    ("work_id", "uuid"),
    ("expected_revision", "int8"),
    ("cycle", "int4"),
    ("attempt", "int4"),
    ("dispatch_id", "uuid"),
    ("outcome", "text"),
    ("retry_at", "timestamptz"),
    ("result", "bytea"),
    ("result_digest", "bytea"),
    ("reason", "text"),
    ("evidence", "bytea"),
    ("binding", "bytea"),
    ("resolution_root_xid", "xid8"),
    ("recorded_at", "timestamptz"),
)


def body():
    text = SQL.read_text()
    start = text.find("CREATE FUNCTION modkit_events.e31(")
    assert start >= 0, "E31 body missing"
    return text[start : text.index("$body$;", start) + len("$body$;")]


class E31Source(unittest.TestCase):
    def test_frozen_prefix(self):
        self.assertEqual(
            hashlib.sha256(SQL.read_bytes()[:472978]).hexdigest(),
            "6d742a29c8f293ea33f5dc67b904b2bd376c9842b2d7cdfbd013c64edeab0df9",
        )

    def test_exact_abi_private_security(self):
        s = body()
        a, b = s.split("RETURNS TABLE(", 1)
        self.assertEqual(
            re.findall(r"(\w+) pg_catalog\.(\w+)", a), [("p_" + n, t) for n, t in PARAMETERS]
        )
        self.assertEqual(
            re.findall(r"(\w+) pg_catalog\.(\w+)", b.split(")\nLANGUAGE", 1)[0]), list(COLUMNS)
        )
        self.assertIn("LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT", s)
        self.assertIn("SET search_path = pg_catalog, pg_temp AS $body$", s)
        sig = ",".join("pg_catalog." + t for _, t in PARAMETERS)
        self.assertIn(
            f"REVOKE ALL ON FUNCTION modkit_events.e31({sig}) FROM PUBLIC;", SQL.read_text()
        )
        self.assertNotRegex(s, r"\b(COMMIT|ROLLBACK|CREATE TABLE|GRANT)\b")

    def test_lock_and_snapshot_order(self):
        s = body()
        offsets = [
            s.index(x)
            for x in (
                "FOR NO KEY UPDATE OF parent",
                "FOR NO KEY UPDATE OF stored",
                "FOR NO KEY UPDATE OF current_attempt",
                "CROSS JOIN LATERAL modkit_events.e15",
                "SELECT stored.* INTO operation_row",
            )
        ]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("fresh_work IS DISTINCT FROM w", s)
        self.assertIn("attempt_row IS DISTINCT FROM locked_attempt", s)

    def test_receipt_first_and_exact_request(self):
        s = body()
        repeat = s.index("RETURN QUERY SELECT operation_row.operation_id")
        self.assertLess(repeat, s.index("MESSAGE='stale resolution fence'"))
        for stored, submitted in (
            ("work_id", "work_id"),
            ("expected_revision", "expected_revision"),
            ("cycle", "cycle"),
            ("attempt", "attempt"),
            ("dispatch_id", "dispatch_id"),
            ("retry_at", "retry_at"),
            ("requested_result", "result"),
            ("evidence", "evidence"),
            ("binding", "binding"),
        ):
            self.assertIn(f"operation_row.{stored} IS DISTINCT FROM p_{submitted}", s)
        self.assertIn(
            "pg_catalog.convert_to(operation_row.requested_outcome,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(p_outcome,'UTF8')",
            s,
        )
        for name in (
            "event_id",
            "event_digest",
            "token",
            "failed_business_root",
            "requested_receipt",
            "requested_reason",
            "resulting_revision",
        ):
            self.assertIn(f"operation_row.{name} IS NOT NULL", s)
        self.assertIn(
            "operation_row.result_digest IS DISTINCT FROM pg_catalog.sha256(operation_row.requested_result)",
            s,
        )

    def test_arbitration_and_post_wait_clock(self):
        s = body()
        insert = s.index("INSERT INTO modkit_events.mutation_operations")
        self.assertLess(s.index("p_attempt=1000"), insert)
        self.assertIn("ERRCODE='PZ004',MESSAGE='unsafe resolution retry'", s)
        self.assertIn("ON CONFLICT ON CONSTRAINT mutation_operations_pkey DO NOTHING", s)
        self.assertLess(insert, s.index("authority_time := pg_catalog.clock_timestamp()"))
        self.assertIn("p_retry_at<=authority_time", s)
        self.assertIn("w.attempt_count>=w.max_attempts", s)
        self.assertIn("w.cancellation_requested", s)
        self.assertNotIn("EXCEPTION WHEN", s)

    def test_four_outcomes_and_history(self):
        s = body()
        for value in (
            "confirmed_success",
            "confirmed_rejection",
            "confirmed_cancelled",
            "safe_retry",
            "reconcile_success",
            "reconcile_rejection",
            "reconcile_cancelled",
            "reconcile_safe_retry",
        ):
            self.assertIn("'" + value + "'", s)
        for value in (
            "expected_work.dispatch_id := NULL",
            "expected_work.available_at := p_retry_at",
            "expected_work.success_origin := 'reconciled'",
            "expected_work.resolution_operation_id := p_operation_id",
            "expected_work.terminal_resolution_operation_id := p_operation_id",
        ):
            self.assertIn(value, s)
        self.assertIn(
            "expected_parent.nonterminal_count := subscription_row.nonterminal_count-1", s
        )
        self.assertIn(
            "transition_code,NULL,updated_work.ownership_revision,p_evidence,record_time", s
        )

    def test_history_reread_and_byte_exact_success_origin(self):
        s = body()
        self.assertIn("updated_history IS DISTINCT FROM history_row", s)
        self.assertIn("pg_catalog.convert_to(updated_history.reason,'UTF8')", s)
        self.assertIn("pg_catalog.convert_to(updated_work.success_origin,'UTF8')", s)
        self.assertIn("pg_catalog.convert_to(fresh_work.success_origin,'UTF8')", s)

    def test_whole_postimages_and_actual_root(self):
        s = body()
        for value in (
            "actual_root := pg_catalog.pg_current_xact_id()",
            "updated_attempt IS DISTINCT FROM expected_attempt",
            "updated_work IS DISTINCT FROM expected_work",
            "updated_parent IS DISTINCT FROM expected_parent",
            "operation_row IS DISTINCT FROM expected_operation",
            "history_row.evidence IS DISTINCT FROM p_evidence",
            "history_row.recorded_at IS DISTINCT FROM record_time",
            "locked_attempt IS DISTINCT FROM expected_attempt",
        ):
            self.assertIn(value, s)
        self.assertGreaterEqual(s.count("CROSS JOIN LATERAL modkit_events.e15"), 2)
        self.assertIn("updated_operation IS DISTINCT FROM expected_operation", s)


if __name__ == "__main__":
    unittest.main()

"""E32 source/ABI guards, not PostgreSQL behavior or concurrency qualification.

Pure imports must use an accepted pinned snapshot during concurrent development.
E32_SQL_PATH selects the separately frozen SQL candidate for independent review.
"""
import hashlib
import os
import re
from pathlib import Path

import pytest

from modkit_events.persistence.catalog import get_statement

PARAMETERS = (
    ("work_id", "uuid"), ("token", "uuid"), ("ownership_revision", "int8"),
    ("cycle", "int4"), ("expected_attempt", "int4"),
    ("failed_business_root", "xid8"), ("operation_id", "uuid"),
    ("reason", "text"), ("evidence", "bytea"), ("binding", "bytea"),
)
COLUMNS = (
    ("operation_id", "uuid"), ("work_id", "uuid"), ("token", "uuid"),
    ("expected_revision", "int8"), ("cycle", "int4"), ("attempt", "int4"),
    ("dispatch_id", "uuid"), ("failed_business_root", "xid8"),
    ("reason", "text"), ("evidence", "bytea"), ("binding", "bytea"),
    ("resulting_revision", "int8"), ("recorded_at", "timestamptz"),
)


def sql():
    default = Path(__file__).parents[1] / "src/modkit_events/persistence/sql/0001_initial.sql"
    return Path(os.environ.get("E32_SQL_PATH", default)).read_text()


def body():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e32(")
    assert start >= 0, "E32 body missing"
    return source[start:source.index("$body$;", start) + len("$body$;")]


def test_frozen_prefix():
    assert hashlib.sha256(sql().encode()[:448641]).hexdigest() == (
        "ed8c7032cdd7bd6a67dc2a41e38c1384e0173094544de63bb37e9ddac4a35429"
    )


def test_exact_abi_and_private_security():
    source = body()
    parameters, output = source.split("RETURNS TABLE(", 1)
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + name, kind) for name, kind in PARAMETERS
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == list(COLUMNS)
    spec = get_statement("E32")
    assert [(p.name, p.wire_type.value) for p in spec.parameters] == list(PARAMETERS)
    assert [(c.name, c.wire_type.value) for c in spec.result.columns] == list(COLUMNS)
    assert not any(c.nullable for c in spec.result.columns)
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    signature = ",".join("pg_catalog." + kind for _, kind in PARAMETERS)
    assert f"REVOKE ALL ON FUNCTION modkit_events.e32({signature}) FROM PUBLIC;" in sql()


@pytest.mark.parametrize("fragment", (
    "p_cycle IS DISTINCT FROM 1",
    "p_expected_attempt NOT BETWEEN 0 AND 1000",
    "p_failed_business_root<='0'::pg_catalog.xid8",
    "p_operation_id IS NULL",
    "pg_catalog.octet_length(p_evidence)>1048576",
    "pg_catalog.octet_length(p_binding)>1048576",
    "'^[a-z][a-z0-9_]{0,255}$'",
))
def test_input_before_discovery(fragment):
    source = body()
    assert source.index("ERRCODE='PZ005'") < source.index(fragment)
    assert source.index(fragment) < source.index("FROM modkit_events.e15(p_work_id)")


def test_locks_and_coherent_preimages_before_operation():
    source = body()
    offsets = [source.index(fragment) for fragment in (
        "FOR NO KEY UPDATE OF parent",
        "FOR NO KEY UPDATE OF stored",
        "FOR NO KEY UPDATE OF current_attempt",
        "CROSS JOIN LATERAL modkit_events.e15",
        "SELECT stored.* INTO operation_row",
    )]
    assert offsets == sorted(offsets)
    assert "fresh_work IS DISTINCT FROM w" in source
    assert "attempt_row IS DISTINCT FROM locked_attempt" in source


def test_repeat_precedes_live_fence_without_reapplying():
    source = body()
    validation = source.index("invalid uncertain operation")
    repeat_return = source.index("RETURN QUERY SELECT operation_row.operation_id")
    fence = source.index("MESSAGE='stale uncertain fence'")
    assert validation < repeat_return < fence
    repeat = source[source.index("IF operation_found THEN"):fence]
    assert "RETURN;" in repeat
    assert "pg_catalog.clock_timestamp()" not in repeat
    assert "UPDATE modkit_events." not in repeat


@pytest.mark.parametrize("field", (
    "event_id", "event_digest", "requested_outcome", "retry_at",
    "requested_result", "result_digest", "requested_receipt", "resolution_root_xid",
))
def test_receipt_rejects_other_union_fields(field):
    assert f"operation_row.{field} IS NOT NULL" in body()


@pytest.mark.parametrize("field", (
    "work_id", "token", "expected_revision", "cycle", "attempt",
    "failed_business_root", "requested_reason", "evidence", "binding",
))
def test_receipt_request_exact_match(field):
    source = body()
    assert re.search(r"operation_row\." + field + r".*IS DISTINCT FROM", source)


def test_fresh_authority_after_arbitration_for_every_winner():
    source = body()
    offsets = [source.index(fragment) for fragment in (
        "record_time := pg_catalog.clock_timestamp()",
        "INSERT INTO modkit_events.mutation_operations",
        "ON CONFLICT ON CONSTRAINT mutation_operations_pkey DO NOTHING",
        "authority_time := pg_catalog.clock_timestamp()",
        "authority_time>=w.deadline",
        "authority_time>=w.lease_until",
        "UPDATE modkit_events.attempts",
    )]
    assert offsets == sorted(offsets)
    assert "expected_operation.recorded_at := record_time" in source
    assert "expected_work.updated_at := record_time" in source
    assert "history_row.recorded_at IS DISTINCT FROM record_time" in source
    assert "EXCEPTION WHEN" not in source
    assert source.count("authority_time :=") == 1


def test_new_operation_precedence_and_structural_roots():
    source = body()
    assert source.index("MESSAGE='stale uncertain fence'") < source.index(
        "IF NOT is_job AND subscription_row.nonterminal_count<=0"
    )
    assert "actual_root=p_failed_business_root" in source
    assert "actual_root=attempt_row.dispatch_root_xid" in source
    assert "p_failed_business_root=attempt_row.dispatch_root_xid" in source
    assert source.index("ownership_revision=9223372036854775807") < source.index(
        "expected_work.ownership_revision := w.ownership_revision+1"
    )


def test_hold_preserves_capacity_dispatch_and_complete_receipts():
    source = body()
    assert "expected_work.state := 'held'" in source
    assert "expected_attempt.outcome := 'uncertain'" in source
    for fragment in (
        "updated_attempt IS DISTINCT FROM expected_attempt",
        "updated_work IS DISTINCT FROM expected_work",
        "operation_row IS DISTINCT FROM expected_operation",
        "updated_parent IS DISTINCT FROM subscription_row",
        "history_row.evidence IS DISTINCT FROM p_evidence",
        "invalid uncertain poststate",
    ):
        assert fragment in source
    assert "UPDATE modkit_events.subscriptions" not in source
    assert "SET dispatch_id" not in source
    assert "expected_work.dispatch_id :=" not in source
    assert "UPDATE modkit_events.finalization_guards" not in source
    assert "pg_xact_status" not in source
    assert not re.search(r"\b(COMMIT|ROLLBACK)\s*;", source)

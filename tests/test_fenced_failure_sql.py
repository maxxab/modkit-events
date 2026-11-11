"""E11 source guards only, not PostgreSQL execution."""

import hashlib
from importlib.resources import files

from _installation_artifact_helpers import historical_prefix_view


def test_e11_contract():
    sql = files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()
    assert (
        hashlib.sha256(historical_prefix_view(sql.encode())[:432362]).hexdigest()
        == "0cdea5bcf410584fe2960bc977663f843191598d5968199435bfebb171e92268"
    )
    assert "CREATE FUNCTION modkit_events.e11(" in sql, "E11 body missing"
    body = sql.split("CREATE FUNCTION modkit_events.e11(", 1)[1]
    for fragment in (
        "RETURNS TABLE(ok pg_catalog.bool)",
        "actual_root=p_failed_business_root",
        "actual_root=attempt_row.dispatch_root_xid",
        "p_failed_business_root=attempt_row.dispatch_root_xid",
        "w.attempt_count>=w.max_attempts",
        "p_retry_at<=final_time",
        "p_retry_at>=w.deadline",
        "expected_attempt.outcome :=",
        "expected_attempt.evidence := p_evidence",
        "expected_work.dispatch_id := NULL",
        "expected_work.available_at := p_retry_at",
        "updated_attempt IS DISTINCT FROM expected_attempt",
        "updated_work IS DISTINCT FROM expected_work",
        "updated_parent IS DISTINCT FROM expected_parent",
        "history_row.evidence IS DISTINCT FROM p_evidence",
        "failure_terminal",
        "failure_cancelled",
        "failure_retry",
        "invalid failure poststate",
        "RETURN QUERY SELECT TRUE::pg_catalog.bool",
        "REVOKE ALL ON FUNCTION modkit_events.e11(",
    ):
        assert fragment in body
    assert body.index("final_time>=w.deadline") < body.index("final_time>=w.lease_until")
    assert body.index("FOR NO KEY UPDATE OF current_attempt") < body.index("final_time :=")
    assert "INSERT INTO modkit_events.attempts" not in body
    assert "pg_xact_status" not in body


def test_e11_spent_fence_precedes_positive_parent_count():
    """A lawful last-item terminal row has count zero, not corruption."""
    sql = files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()
    body = sql.split("CREATE FUNCTION modkit_events.e11(", 1)[1]
    integrity = body.index("CROSS JOIN LATERAL modkit_events.e15")
    fence = body.index("MESSAGE='stale failure fence'")
    running = body.index("MESSAGE='failure requires running work'")
    positive_parent = body.index("IF NOT is_job AND subscription_row.nonterminal_count<=0")
    assert integrity < fence < running < positive_parent

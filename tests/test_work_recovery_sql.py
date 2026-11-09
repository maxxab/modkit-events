"""E13 source guards only; no PostgreSQL parsing or runtime qualification."""

from _installation_artifact_helpers import historical_prefix_view

import hashlib
import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e13(")
    assert start >= 0, "E13 is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e13_exact_abi_security_and_prefix():
    body = function()
    params, output = body.split("RETURNS TABLE(", 1)
    spec = get_statement("E13")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", params) == [
        ("p_" + p.name, p.wire_type.value) for p in spec.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (c.name, c.wire_type.value) for c in spec.result.columns
    ]
    assert "VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in body
    assert "SET search_path = pg_catalog, pg_temp" in body
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e13(pg_catalog.bytea,pg_catalog.text,pg_catalog.int4,pg_catalog.uuid,pg_catalog.int4) FROM PUBLIC;"
        in sql()
    )
    assert hashlib.sha256(historical_prefix_view(sql().encode())[:378764]).hexdigest() == (
        "ef9c3eafac5713a2ad07c62dbde476c1d0d751897a03d0e685788a8766fc2731"
    )


@pytest.mark.parametrize(
    "guard",
    (
        "_utf8_valid(p_namespace,256,TRUE)",
        "p_limit NOT BETWEEN 1 AND 256",
        "p_discovery_budget NOT BETWEEN 1 AND 4096",
        "p_discovery_budget<p_limit",
    ),
)
def test_e13_arguments_before_discovery(guard):
    body = function()
    assert body.index("ERRCODE='PZ005'") < body.index(guard)
    assert body.index(guard) < body.index("WHILE visited_count")
    assert "ERRCODE='PZ006'" in body


def test_e13_raw_progress_and_nonblocking_order():
    body = function()
    visit = body.index("visited_count := visited_count+1")
    candidate = body.index("IF (discovered.state")
    parent = body.index("FOR NO KEY UPDATE OF parent SKIP LOCKED")
    work = body.index("FOR NO KEY UPDATE OF stored SKIP LOCKED")
    attempt = body.index("FOR NO KEY UPDATE OF current_attempt SKIP LOCKED")
    assert visit < candidate < parent < work < attempt
    assert "wr.work_id>cursor_value" in body
    assert "cursor_value := discovered.work_id" in body
    for message in (
        "missing work subscription",
        "missing discovered work",
        "missing current dispatch",
    ):
        assert message in body
    assert body.count("SKIP LOCKED") == 3
    assert "AND current_attempt.dispatch_id=w.dispatch_id" in body


def test_e13_fresh_integrity_before_time_and_max():
    body = function()
    integrity = body.index("CROSS JOIN LATERAL modkit_events.e15")
    assert integrity > body.index("FOR NO KEY UPDATE OF current_attempt SKIP LOCKED")
    assert integrity < body.index("final_time := pg_catalog.clock_timestamp()")
    assert integrity < body.index("IF w.ownership_revision=9223372036854775807")
    assert "captured.selected_count IS DISTINCT FROM 1" in body
    assert "attempt_row IS DISTINCT FROM locked_attempt" in body
    assert "nonterminal_count<=0" in body
    assert body.index("IF (discovered.state") < body.index("nonterminal_count<=0")


def test_e13_deadline_budget_claim_precedence():
    body = function()
    expired = body.index("transition_code := 'recover_expired_predispatch'")
    exhausted = body.index("transition_code := 'recover_exhausted_predispatch'")
    claim = body.index("transition_code := 'recover_claim'")
    assert expired < exhausted < claim
    assert "final_time>=w.deadline" in body
    assert "w.attempt_count>=w.max_attempts" in body
    assert "final_time>=w.lease_until" in body
    assert "history_reason := 'attempts_exhausted'" in body
    assert "expected_work.available_at :=" not in body
    assert "expected_work.attempt_count :=" not in body
    assert "expected_work.cancellation_requested :=" not in body


def test_e13_running_holds_uncertainty_without_retry():
    body = function()
    assert "transition_code := 'recover_dispatched'" in body
    assert "expected_work.state := 'held'" in body
    assert "expected_attempt.outcome := 'uncertain'" in body
    assert "expected_attempt.evidence := ''::pg_catalog.bytea" in body
    assert "updated_attempt IS DISTINCT FROM expected_attempt" in body
    assert "expected_work.dispatch_id :=" not in body
    assert "application_safe" not in body
    assert "INSERT INTO modkit_events.attempts" not in body


def test_e13_exact_mutation_capacity_history_receipts():
    body = function()
    assert "expected_work.ownership_revision := w.ownership_revision+1" in body
    assert "expected_work.token := NULL" in body
    assert "expected_work.lease_until := NULL" in body
    assert "updated_work IS DISTINCT FROM expected_work" in body
    assert (
        "IF expected_work.state COLLATE pg_catalog.\"C\" IN ('expired','failed') AND NOT is_job THEN"
        in body
    )
    assert "subscription_row.nonterminal_count-1" in body
    assert "updated_parent IS DISTINCT FROM expected_parent" in body
    for field in ("work_id", "cycle", "attempt", "ownership_revision", "evidence", "recorded_at"):
        assert f"history_row.{field} IS DISTINCT FROM" in body
    assert "history_row.token IS NOT NULL" in body
    assert "pg_catalog.convert_to(history_row.reason,'UTF8')" in body
    assert body.count("INSERT INTO modkit_events.work_history") == 1


def test_e13_buffered_scan_and_no_hidden_execution():
    body = function()
    assert "emitted_rows := pg_catalog.array_append(emitted_rows,updated_work)" in body
    assert "IF visited_count=p_discovery_budget OR item_count=p_limit THEN" in body
    assert "FOREACH emitted IN ARRAY emitted_rows LOOP" in body
    assert "'header'::pg_catalog.text,visited_count,cursor_value,exhausted_value" in body
    assert (
        "'item'::pg_catalog.text,NULL::pg_catalog.int4,NULL::pg_catalog.uuid,NULL::pg_catalog.bool"
        in body
    )
    assert body.index("RETURN QUERY") > body.index("item_count := item_count+1")
    calls = re.findall(r"modkit_events\.(e\d+)\(", body.split("AS $body$", 1)[1])
    assert calls == ["e15"]
    assert not re.search(
        r"\b(?:DELETE|MERGE|TRUNCATE|EXECUTE|COMMIT|ROLLBACK|OFFSET)\b|EXCEPTION WHEN|setval|nextval|pg_notify",
        body,
    )

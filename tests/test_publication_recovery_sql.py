"""Source contract guards for E26; PostgreSQL behavior has separate fixtures."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e26(")
    assert start >= 0, "E26 is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e26_catalog_abi():
    source = function()
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement("E26")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + item.name, item.wire_type.value) for item in expected.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (item.name, item.wire_type.value) for item in expected.result.columns
    ]


def test_e26_security_and_scope():
    source = function()
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e26(pg_catalog.int4,pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;"
        in sql()
    )
    body = source.split("AS $body$", 1)[1]
    assert re.findall(r"modkit_events\.(e\d+)\(", body) == ["e28"]
    assert not re.search(
        r"\b(?:DELETE|MERGE|TRUNCATE|EXECUTE|COMMIT|ROLLBACK|OFFSET)\b|EXCEPTION WHEN|setval|nextval|pg_notify",
        body,
    )


@pytest.mark.parametrize(
    "guard",
    (
        "p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256",
        "p_discovery_budget IS NULL OR p_discovery_budget NOT BETWEEN 1 AND 4096",
        "p_discovery_budget<p_limit",
        "pg_catalog.octet_length(p_scan_after)<>32",
    ),
)
def test_e26_rejects_inputs_before_storage(guard):
    source = function()
    assert (
        source.index("ERRCODE='PZ005'")
        < source.index(guard)
        < source.index("FROM modkit_events.outbox")
    )
    assert source.index("ERRCODE='PZ006'") < source.index("FROM modkit_events.outbox")


def test_e26_bounded_raw_discovery_then_nonblocking_lock():
    source = function()
    assert "WHILE visited_count<p_discovery_budget AND item_count<p_limit LOOP" in source
    discovery = source[
        source.index("IF cursor_value IS NULL THEN") : source.index("IF NOT FOUND THEN")
    ]
    assert discovery.count("ORDER BY listed.event_digest LIMIT 1") == 2
    assert "listed.event_digest>cursor_value" in discovery
    assert "WHERE listed.state" not in discovery
    assert source.index("visited_count := visited_count+1") < source.index(
        "FOR NO KEY UPDATE OF stored SKIP LOCKED"
    )
    assert "cursor_value := discovered.event_digest" in source
    assert source.count("FOR NO KEY UPDATE OF stored SKIP LOCKED") == 1
    assert "modkit_events.e22" not in source


def test_e26_fresh_preimage_and_exact_retained_postimage():
    source = function()
    assert (
        source.index("FOR NO KEY UPDATE OF stored SKIP LOCKED")
        < source.index("modkit_events.e28(")
        < source.index("UPDATE modkit_events.outbox")
    )
    assert "captured.selected_count IS DISTINCT FROM 1" in source
    assert "fresh_outbox IS DISTINCT FROM locked_outbox" in source
    assert "updated_outbox IS DISTINCT FROM expected_outbox" in source
    assert "emitted_rows := pg_catalog.array_append(emitted_rows,updated_outbox)" in source
    assert source.index("RETURN QUERY SELECT 'header'") < source.index("RETURN QUERY SELECT 'item'")
    item = source[source.index("RETURN QUERY SELECT 'item'") :]
    assert re.findall(r"emitted\.(\w+)", item) == [
        c.name for c in get_statement("E28").result.columns
    ]


def test_e26_validates_owned_preimage_before_expiry_and_revision_skips():
    source = function()
    assert (
        source.index("modkit_events.e28(")
        < source.index("final_time := pg_catalog.clock_timestamp()")
        < source.index("IF locked_outbox.lease_until>final_time THEN")
    )
    assert (
        source.index("IF locked_outbox.lease_until>final_time THEN")
        < source.index("IF locked_outbox.ownership_revision=9223372036854775807")
        < source.index("next_revision := locked_outbox.ownership_revision+1")
    )
    assert "IF modkit_events._instant_bytes(final_time) IS NULL THEN" in source
    assert source.count("IN ('claimed','publishing')") == 2
    assert "ERRCODE='PZ004'" not in source


def test_e26_recovers_preintent_only_and_holds_intent():
    source = function()
    assert "WHEN 'claimed' THEN 'pending'" in source
    assert "WHEN 'publishing' THEN 'held'" in source
    assert "WHEN 'claimed' THEN 'recover_publication_preintent'" in source
    assert "WHEN 'publishing' THEN 'recover_publication_intent'" in source
    assert "safe_retry" not in source
    assert "pg_catalog.gen_random_uuid" not in source


def test_e26_releases_fence_without_replacing_publication_material():
    source = function()
    update = source[
        source.index("UPDATE modkit_events.outbox") : source.index("GET DIAGNOSTICS affected")
    ]
    assert "SET state=next_state,token=NULL," in update
    assert "ownership_revision=next_revision,lease_until=NULL,updated_at=final_time" in update
    for field in (
        "event_id",
        "canonical_version",
        "envelope_evidence",
        "replay_input",
        "intent_id",
        "receipt",
        "outcome_evidence",
        "created_at",
    ):
        assert not re.search(r"\b" + field + r"\s*=", update)
    for assignment in (
        "state := next_state",
        "token := NULL",
        "ownership_revision := next_revision",
        "lease_until := NULL",
        "updated_at := final_time",
    ):
        assert "expected_outbox." + assignment in source


def test_e26_history_uses_retained_intent_and_generated_empty_evidence():
    source = function()
    assert source.count("INSERT INTO modkit_events.publication_history") == 1
    assert "VALUES(updated_outbox.event_id,updated_outbox.intent_id,NULL," in source
    assert "history_status,NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,final_time)" in source
    assert "history_id_value IS NULL OR history_id_value<=0" in source
    assert (
        source.index("updated_outbox IS DISTINCT FROM expected_outbox")
        < source.index("INSERT INTO modkit_events.publication_history")
        < source.index("emitted_rows := pg_catalog.array_append(emitted_rows,updated_outbox)")
    )


def test_e26_bound_hit_never_claims_pass_exhaustion():
    source = function()
    assert "IF visited_count=p_discovery_budget OR item_count=p_limit THEN" in source
    assert "exhausted_value := FALSE" in source
    assert "cursor_value := p_scan_after" in source
    assert "IF NOT FOUND THEN\n            exhausted_value := TRUE;" in source


def test_e26_stored_identifier_corruption_is_not_an_argument_error():
    source = function()
    guard = "modkit_events._utf8_valid(locked_outbox.event_id,256,TRUE) IS NOT TRUE"
    assert source.index(guard) < source.index("modkit_events.e28(")
    assert "ERRCODE='PZ012'" in source[source.index(guard) : source.index("modkit_events.e28(")]

"""E25 SQL source contract guards; behavioral SQL fixture is reviewed separately."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e25(")
    assert start >= 0, "E25 is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e25_exact_catalog_abi_and_security():
    source = function()
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement("E25")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + p.name, p.wire_type.value) for p in expected.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (c.name, c.wire_type.value) for c in expected.result.columns
    ]
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e25(pg_catalog.bytea,pg_catalog.uuid,pg_catalog.int8,pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;"
        in sql()
    )


@pytest.mark.parametrize(
    "guard",
    (
        "modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE",
        "p_token IS NULL",
        "p_ownership_revision IS NULL OR p_ownership_revision<=0",
        "p_intent_id IS NULL",
        "p_status COLLATE pg_catalog.\"C\" IN ('confirmed','rejected','uncertain')",
        "pg_catalog.octet_length(p_receipt)>4096",
        "p_evidence IS NULL OR pg_catalog.octet_length(p_evidence)>1048576",
    ),
)
def test_e25_input_guards_precede_storage(guard):
    source = function()
    assert source.index("ERRCODE='PZ005'") < source.index(guard)
    assert source.index(guard) < source.index("FROM modkit_events.outbox")
    assert source.index("ERRCODE='PZ006'") < source.index("FROM modkit_events.outbox")


def test_e25_blocking_digest_mutex_fresh_fence_and_intent():
    source = function()
    lock = source.index("FOR NO KEY UPDATE OF stored;")
    fresh = source.index("SELECT stored.* INTO locked_outbox", lock)
    fence = source.index("locked_outbox.token IS DISTINCT FROM p_token", fresh)
    state = source.index("locked_outbox.state COLLATE pg_catalog.", fence)
    validation = source.index("modkit_events.e28(")
    intent = source.index("locked_outbox.intent_id IS DISTINCT FROM p_intent_id")
    assert lock < fresh < fence < state < validation < intent
    assert "stored.event_digest=pg_catalog.sha256(p_event_id)" in source[:lock]
    assert "stored.event_id=p_event_id" not in source
    assert "locked_outbox.ownership_revision IS DISTINCT FROM p_ownership_revision" in source
    assert "locked_outbox.state COLLATE pg_catalog.\"C\"='publishing'" in source
    assert "ERRCODE='PZ003',MESSAGE='stale publication intent'" in source[intent:]


def test_e25_one_complete_preimage_before_mutation():
    source = function()
    assert re.findall(r"modkit_events\.(e\d+)\(", source.split("AS $body$", 1)[1]) == ["e28"]
    assert "FROM modkit_events.e28(p_event_id) AS observed" in source
    assert "captured.selected_count IS DISTINCT FROM 1" in source
    assert "fresh_outbox IS DISTINCT FROM locked_outbox" in source
    assert source.index("modkit_events.e28(") < source.index("UPDATE modkit_events.outbox")
    assert not re.search(
        r"\b(?:DELETE|MERGE|TRUNCATE|EXECUTE|COMMIT|ROLLBACK)\b|SKIP LOCKED|EXCEPTION WHEN|nextval|setval|gen_random_uuid|pg_notify",
        source,
    )


def test_e25_revision_overflow_and_live_final_clock():
    source = function()
    assert (
        source.index("modkit_events.e28(")
        < source.index("locked_outbox.ownership_revision=9223372036854775807")
        < source.index("next_revision := locked_outbox.ownership_revision+1")
        < source.index("final_time := pg_catalog.clock_timestamp()")
        < source.index("IF final_time>=locked_outbox.lease_until THEN")
        < source.index("UPDATE modkit_events.outbox")
    )
    assert "ERRCODE='PZ004',MESSAGE='ownership revision exhausted'" in source


@pytest.mark.parametrize(
    ("status", "state", "history"),
    (
        ("confirmed", "published", "publication_confirmed"),
        ("rejected", "rejected", "publication_rejected"),
        ("uncertain", "held", "publication_uncertain"),
    ),
)
def test_e25_exact_outcome_mapping(status, state, history):
    source = function()
    assert f"WHEN '{status}' THEN '{state}'" in source
    assert f"WHEN '{status}' THEN '{history}'" in source


def test_e25_releases_fence_retains_material_and_records_supplied_bytes():
    source = function()
    update = source[
        source.index("UPDATE modkit_events.outbox") : source.index("GET DIAGNOSTICS affected")
    ]
    assert (
        "SET state=next_state,token=NULL,ownership_revision=next_revision,lease_until=NULL,"
        in update
    )
    assert "receipt=p_receipt,outcome_evidence=p_evidence,updated_at=final_time" in update
    for assignment in (
        "state := next_state",
        "token := NULL",
        "ownership_revision := next_revision",
        "lease_until := NULL",
        "receipt := p_receipt",
        "outcome_evidence := p_evidence",
        "updated_at := final_time",
    ):
        assert "expected_outbox." + assignment in source
    assert not re.search(
        r"intent_id\s*=|event_id\s*=|replay_input\s*=|envelope_evidence\s*=", update
    )
    assert "updated_outbox IS DISTINCT FROM expected_outbox" in source


def test_e25_postupdate_liveness_precedes_one_history_and_true():
    source = function()
    assert (
        source.index("updated_outbox IS DISTINCT FROM expected_outbox")
        < source.index("post_update_time := pg_catalog.clock_timestamp()")
        < source.index("IF modkit_events._instant_bytes(post_update_time) IS NULL THEN")
        < source.index("IF post_update_time>=locked_outbox.lease_until THEN")
        < source.index("INSERT INTO modkit_events.publication_history")
    )
    assert source.count("INSERT INTO modkit_events.publication_history") == 1
    assert "VALUES(updated_outbox.event_id,updated_outbox.intent_id,NULL," in source
    assert "history_status,p_receipt,p_evidence,''::pg_catalog.bytea,final_time)" in source
    assert "history_id_value IS NULL OR history_id_value<=0" in source
    assert "RETURN QUERY SELECT TRUE" in source

"""Source contract guards for E24; runtime behavior has a separate SQL fixture."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e24(")
    assert start >= 0, "E24 is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e24_exact_catalog_abi_and_security():
    source = function()
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement("E24")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + p.name, p.wire_type.value) for p in expected.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (c.name, c.wire_type.value) for c in expected.result.columns
    ]
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e24(pg_catalog.bytea,pg_catalog.uuid,pg_catalog.int8,pg_catalog.uuid) FROM PUBLIC;"
        in sql()
    )


@pytest.mark.parametrize(
    "guard",
    (
        "modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE",
        "p_token IS NULL",
        "p_ownership_revision IS NULL OR p_ownership_revision<=0",
        "p_intent_id IS NULL",
    ),
)
def test_e24_input_guards_precede_storage(guard):
    source = function()
    assert source.index("ERRCODE='PZ005'") < source.index(guard)
    assert source.index(guard) < source.index("FROM modkit_events.outbox")
    assert source.index("ERRCODE='PZ006'") < source.index("FROM modkit_events.outbox")


def test_e24_blocking_digest_mutex_and_fresh_claimed_fence():
    source = function()
    lock = source.index("FOR NO KEY UPDATE OF stored;")
    fresh = source.index("SELECT stored.* INTO locked_outbox", lock)
    fence = source.index("locked_outbox.token IS DISTINCT FROM p_token", fresh)
    state = source.index("locked_outbox.state COLLATE pg_catalog.", fence)
    assert lock < fresh < fence < state < source.index("modkit_events.e28(")
    assert "stored.event_digest=pg_catalog.sha256(p_event_id)" in source[:lock]
    assert "stored.event_id=p_event_id" not in source
    assert "locked_outbox.ownership_revision IS DISTINCT FROM p_ownership_revision" in source
    assert """locked_outbox.state COLLATE pg_catalog."C"='claimed'""" in source
    assert "ERRCODE='PZ003'" in source[lock:fence]
    assert "ERRCODE='PZ004'" in source[state:]


def test_e24_one_preimage_validator_before_writes():
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


def test_e24_successor_headroom_and_final_live_clock():
    source = function()
    assert (
        source.index("modkit_events.e28(")
        < source.index("locked_outbox.ownership_revision=9223372036854775807")
        < source.index("final_time := pg_catalog.clock_timestamp()")
        < source.index("IF final_time>=locked_outbox.lease_until THEN")
        < source.index("UPDATE modkit_events.outbox")
    )
    assert "ERRCODE='PZ004',MESSAGE='ownership revision exhausted'" in source


def test_e24_updates_only_intent_state_and_time():
    source = function()
    update = source[
        source.index("UPDATE modkit_events.outbox") : source.index(
            "GET DIAGNOSTICS affected", source.index("UPDATE modkit_events.outbox")
        )
    ]
    assert "SET state='publishing',intent_id=p_intent_id,updated_at=final_time" in update
    assert not re.search(
        r"ownership_revision\s*=|token\s*=|lease_until\s*=|receipt\s*=|outcome_evidence\s*=", update
    )
    assert "expected_outbox.state := 'publishing'" in source
    assert "expected_outbox.intent_id := p_intent_id" in source
    assert "updated_outbox IS DISTINCT FROM expected_outbox" in source


def test_e24_one_intent_history_and_exact_success_result():
    source = function()
    assert source.count("INSERT INTO modkit_events.publication_history") == 1
    assert "VALUES(updated_outbox.event_id,updated_outbox.intent_id,NULL," in source
    assert (
        "'publication_intent',NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,final_time)" in source
    )
    assert "history_id_value IS NULL OR history_id_value<=0" in source
    assert "RETURN QUERY SELECT TRUE" in source


def test_e24_rechecks_lease_after_potential_unique_index_wait_before_history():
    source = function()
    assert (
        source.index("updated_outbox IS DISTINCT FROM expected_outbox")
        < source.index("post_update_time := pg_catalog.clock_timestamp()")
        < source.index("IF modkit_events._instant_bytes(post_update_time) IS NULL THEN")
        < source.index("IF post_update_time>=locked_outbox.lease_until THEN")
        < source.index("INSERT INTO modkit_events.publication_history")
    )
    assert "ERRCODE='PZ003',MESSAGE='publication lease expired after update'" in source

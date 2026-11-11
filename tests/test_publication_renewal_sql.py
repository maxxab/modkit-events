"""Source contract guards for E23; runtime behavior has a separate SQL fixture."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function(key="e23"):
    source = sql()
    start = source.find(f"CREATE FUNCTION modkit_events.{key}(")
    assert start >= 0, f"{key.upper()} is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e23_exact_catalog_abi_and_security():
    source = function()
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement("E23")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + p.name, p.wire_type.value) for p in expected.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (c.name, c.wire_type.value) for c in expected.result.columns
    ]
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e23(pg_catalog.bytea,pg_catalog.uuid,pg_catalog.int8,pg_catalog.float8) FROM PUBLIC;"
        in sql()
    )


@pytest.mark.parametrize(
    "guard",
    (
        "modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE",
        "p_token IS NULL",
        "p_ownership_revision IS NULL OR p_ownership_revision<=0",
        "(p_lease_seconds>0::pg_catalog.float8 AND p_lease_seconds<=3600::pg_catalog.float8) IS NOT TRUE",
    ),
)
def test_e23_input_guards_precede_storage(guard):
    source = function()
    assert source.index("ERRCODE='PZ005'") < source.index(guard)
    assert source.index(guard) < source.index("FROM modkit_events.outbox")
    assert source.index("ERRCODE='PZ006'") < source.index("FROM modkit_events.outbox")


def test_e23_blocking_digest_mutex_then_fresh_exact_fence():
    source = function()
    lock = source.index("FOR NO KEY UPDATE OF stored;")
    fresh = source.index("SELECT stored.* INTO locked_outbox", lock)
    fence = source.index("locked_outbox.token IS DISTINCT FROM p_token", fresh)
    state = source.index("locked_outbox.state COLLATE pg_catalog.", fence)
    assert lock < fresh < fence < state < source.index("modkit_events.e28(")
    assert "stored.event_digest=pg_catalog.sha256(p_event_id)" in source[:lock]
    assert "stored.event_id=p_event_id" not in source
    assert "locked_outbox.ownership_revision IS DISTINCT FROM p_ownership_revision" in source
    assert "IN ('claimed','publishing')" in source
    assert "ERRCODE='PZ003'" in source[lock:fence]
    assert "ERRCODE='PZ004'" in source[state:]


def test_e23_one_preimage_validator_retains_identity_and_integrity():
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


def test_e23_reuses_exact_binary64_quantization():
    def block(source):
        return source[
            source.index("    -- Exact ceil") : source.index(
                "    END IF;", source.index("    IF lease_us IS NULL")
            )
            + len("    END IF;")
        ]

    assert block(function()) == block(function("e05")) == block(function("e22"))


def test_e23_live_expiry_and_nonshortening_lease_retain_revision():
    source = function()
    assert (
        source.index("modkit_events.e28(")
        < source.index("final_time := pg_catalog.clock_timestamp()")
        < source.index("IF final_time>=locked_outbox.lease_until THEN")
    )
    assert "candidate_lease := locked_outbox.lease_until" in source
    assert "candidate_lease<=final_time" in source
    assert "modkit_events._instant_bytes(candidate_lease) IS NULL" in source
    update = source[
        source.index("UPDATE modkit_events.outbox") : source.index(
            "GET DIAGNOSTICS affected", source.index("UPDATE modkit_events.outbox")
        )
    ]
    assert "SET lease_until=candidate_lease,updated_at=final_time" in update
    assert not re.search(r"ownership_revision\s*=|token\s*=|intent_id\s*=|state\s*=", update)


def test_e23_retained_postimage_and_history():
    source = function()
    assert "updated_outbox IS DISTINCT FROM expected_outbox" in source
    assert "RETURN QUERY SELECT updated_outbox.lease_until" in source
    assert source.count("INSERT INTO modkit_events.publication_history") == 1
    assert "VALUES(updated_outbox.event_id,updated_outbox.intent_id,NULL," in source
    assert (
        "'renew_publication',NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,final_time)" in source
    )
    assert "history_id_value IS NULL OR history_id_value<=0" in source

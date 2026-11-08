"""Source contract guards for E22; PostgreSQL behavior has separate fixtures."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e22(")
    assert start >= 0, "E22 is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e22_catalog_abi():
    source = function()
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement("E22")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + item.name, item.wire_type.value) for item in expected.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (item.name, item.wire_type.value) for item in expected.result.columns
    ]


def test_e22_security_and_scope():
    source = function()
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e22(pg_catalog.int4,pg_catalog.float8,pg_catalog.bytea,pg_catalog.int4) FROM PUBLIC;"
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
        "(p_lease_seconds>0::pg_catalog.float8 AND p_lease_seconds<=3600::pg_catalog.float8) IS NOT TRUE",
    ),
)
def test_e22_rejects_inputs_before_storage(guard):
    source = function()
    assert (
        source.index("ERRCODE='PZ005'")
        < source.index(guard)
        < source.index("FROM modkit_events.outbox")
    )
    assert source.index("ERRCODE='PZ006'") < source.index("FROM modkit_events.outbox")


def test_e22_bounded_raw_discovery_then_nonblocking_lock():
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
    assert "modkit_events.e26" not in source


def test_e22_fresh_preimage_and_exact_retained_postimage():
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


def test_e22_exact_lease_and_successor_revision():
    source = function()
    assert "pg_catalog.float8send(p_lease_seconds)" in source
    assert "pg_catalog.div(numerator+denominator-1,denominator)" in source
    assert "locked_outbox.ownership_revision>=9223372036854775806::pg_catalog.int8" in source
    assert source.index("modkit_events.e28(") < source.index(
        "final_time := pg_catalog.clock_timestamp()"
    )
    assert "candidate_lease<=final_time" in source
    assert "claim_token := pg_catalog.gen_random_uuid()" in source
    assert "next_revision := locked_outbox.ownership_revision+1" in source


def test_e22_history_and_exhaustion():
    source = function()
    assert source.count("INSERT INTO modkit_events.publication_history") == 1
    assert "'claim_publication',NULL,''::pg_catalog.bytea,''::pg_catalog.bytea,final_time" in source
    assert "history_id_value IS NULL OR history_id_value<=0" in source
    assert "IF visited_count=p_discovery_budget OR item_count=p_limit THEN" in source
    assert "exhausted_value := FALSE" in source


def test_e22_stored_identifier_corruption_is_not_an_argument_error():
    source = function()
    guard = "modkit_events._utf8_valid(locked_outbox.event_id,256,TRUE) IS NOT TRUE"
    assert source.index(guard) < source.index("modkit_events.e28(")
    assert "ERRCODE='PZ012'" in source[source.index(guard) : source.index("modkit_events.e28(")]

"""Source contract guards for E29; these do not execute PostgreSQL."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement

CODES = (
    "enqueue",
    "claim_publication",
    "renew_publication",
    "publication_intent",
    "publication_confirmed",
    "publication_rejected",
    "publication_uncertain",
    "recover_publication_preintent",
    "recover_publication_intent",
    "repair_published",
    "repair_rejected",
)


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e29(")
    assert start >= 0, "E29 is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e29_catalog_abi_and_projection():
    source = function()
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement("E29")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + item.name, item.wire_type.value) for item in expected.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (item.name, item.wire_type.value) for item in expected.result.columns
    ]
    returned = re.search(r"RETURN QUERY SELECT (.*?);", source, re.S).group(1)
    assert re.findall(r"stored\.(\w+)", returned) == [item.name for item in expected.result.columns]


def test_e29_stable_security_and_no_side_effects():
    source = function()
    assert "LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e29(pg_catalog.bytea,pg_catalog.int8,"
        "pg_catalog.int4) FROM PUBLIC;" in sql()
    )
    assert not re.search(
        r"\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE|EXECUTE|OFFSET|COMMIT|ROLLBACK)\b"
        r"|FOR SHARE|FOR KEY SHARE|clock_timestamp|nextval|setval|EXCEPTION WHEN"
        r"|modkit_events\.e\d+\(",
        source.split("AS $body$", 1)[1],
    )


def test_e29_validates_before_digest_keyset_query():
    source = function()
    query = source[source.index("FOR stored IN") : source.index("LOOP")]
    relation = source.index("FROM modkit_events.publication_history")
    for guard in (
        "pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed'",
        "modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE",
        "p_after_id IS NULL OR p_after_id<0",
        "p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256",
    ):
        assert source.index(guard) < relation
    assert source.index("ERRCODE='PZ005'") < source.index("ERRCODE='PZ006'") < relation
    assert source.count("FROM modkit_events.") == 1
    assert "WHERE listed.event_digest=pg_catalog.sha256(p_event_id)" in query
    assert "listed.history_id>p_after_id" in query
    assert "ORDER BY listed.history_id LIMIT p_limit" in query
    assert "listed.event_id" not in query
    assert " OR " not in query


def test_e29_selected_integrity_precedes_full_id_conflict():
    source = function()
    for guard in (
        "stored.history_id IS NULL OR stored.history_id<=0",
        "modkit_events._utf8_valid(stored.event_id,256,TRUE) IS NOT TRUE",
        "stored.event_digest IS DISTINCT FROM pg_catalog.sha256(stored.event_id)",
        "stored.event_digest IS DISTINCT FROM pg_catalog.sha256(p_event_id)",
        "stored.evidence IS NULL OR pg_catalog.octet_length(stored.evidence)>1048576",
        "stored.binding IS NULL OR pg_catalog.octet_length(stored.binding)>1048576",
        "pg_catalog.octet_length(stored.receipt)>4096",
        "modkit_events._instant_bytes(stored.recorded_at) IS NULL",
    ):
        assert source.index("LIMIT p_limit") < source.index(guard) < source.index("ERRCODE='PZ012'")
    assert source.index("ERRCODE='PZ012'") < source.index(
        "stored.event_id IS DISTINCT FROM p_event_id"
    )
    assert source.index("END LOOP;") < source.index("ERRCODE='PZ002'")
    assert "IF identity_conflict THEN" in source


@pytest.mark.parametrize("code", CODES)
def test_e29_validates_publication_status_domain(code):
    assert "'" + code + "'" in function()


def test_e29_validates_record_shape_and_provenance():
    source = function()
    assert 'stored.status COLLATE pg_catalog."C"' in source
    assert (
        "AND stored.intent_id IS NULL AND stored.operation_id IS NULL AND stored.receipt IS NULL"
        in source
    )
    assert "AND stored.intent_id IS NOT NULL AND stored.operation_id IS NOT NULL" in source
    assert "AND stored.binding<>''::pg_catalog.bytea" in source
    assert "AND stored.evidence<>''::pg_catalog.bytea" in source
    assert ") IS NOT TRUE" in source


def test_e29_reuses_existing_history_index():
    assert (
        "CREATE INDEX publication_history_page ON modkit_events.publication_history"
        "(event_digest,history_id);" in sql()
    )

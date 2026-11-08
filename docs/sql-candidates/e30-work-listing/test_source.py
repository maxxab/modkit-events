"""Source guards only. They neither parse nor execute PostgreSQL."""
import re
from pathlib import Path

import pytest

from modkit_events.persistence.catalog import CardinalityKind, WireType, get_statement

PATH = Path(__file__).with_name("e30.sql")
TYPES = {kind: kind.value for kind in WireType}
TYPES[WireType.BYTEA_ARRAY] = "bytea[]"
TYPES[WireType.INT4_ARRAY] = "int4[]"


def sql():
    assert PATH.is_file(), "E30 SQL candidate is missing"
    return PATH.read_text(encoding="utf-8")


def body():
    matches = re.findall(r"CREATE FUNCTION modkit_events\.e30\((.*?)\n\$body\$;", sql(), re.S)
    assert len(matches) == 1, "E30 must have one explicit source body"
    return re.sub(r"--[^\n]*", "", matches[0])


def test_full_catalog_abi_and_result():
    spec = get_statement("E30")
    source = body()
    params = source.split(")\nRETURNS TABLE", 1)[0]
    result = source.split("RETURNS TABLE(", 1)[1].split(")\nLANGUAGE", 1)[0]
    assert re.findall(r"p_(\w+)\s+pg_catalog\.(\w+)", params) == [(p.name, TYPES[p.wire_type]) for p in spec.parameters]
    assert re.findall(r"(\w+)\s+pg_catalog\.(\w+)", result) == [(c.name, TYPES[c.wire_type]) for c in spec.result.columns]
    assert spec.result.cardinality is CardinalityKind.LIMIT
    assert len(spec.result.columns) == 56


def test_secure_read_only_function():
    source = body()
    assert "LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert "REVOKE ALL ON FUNCTION modkit_events.e30(pg_catalog.bytea,pg_catalog.timestamptz,pg_catalog.uuid,pg_catalog.int4) FROM PUBLIC;" in sql()
    assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE|EXECUTE|EXCEPTION WHEN|COMMIT|ROLLBACK|GRANT)\b|FOR SHARE|FOR KEY SHARE|clock_timestamp|nextval|setval|modkit_events\.e10\(", source)


@pytest.mark.parametrize("guard", [
    "pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed'",
    "modkit_events._utf8_valid(p_namespace,256,TRUE) IS NOT TRUE",
    "p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256",
    "(p_after_created_at IS NULL) <> (p_after_work_id IS NULL)",
    "p_after_created_at IS NOT NULL AND modkit_events._instant_bytes(p_after_created_at) IS NULL",
])
def test_invalid_inputs_reject_before_relation_access(guard):
    source = body()
    assert guard in source
    assert source.index(guard) < source.index("FROM modkit_events.work")
    assert source.index("ERRCODE='PZ005'") < source.index("ERRCODE='PZ006'") < source.index("FROM modkit_events.work")


def test_bounded_first_and_cursor_page_queries():
    source = body()
    assert "IF p_after_created_at IS NULL THEN" in source
    queries = re.findall(r"RETURN QUERY(.*?);", source, re.S)
    assert len(queries) == 2
    for query in queries:
        assert "WITH page AS MATERIALIZED (" in query
        assert "WHERE listed.namespace=p_namespace" in query
        assert "ORDER BY listed.created_at,listed.work_id" in query
        assert "LIMIT p_limit" in query
        assert query.index("LIMIT p_limit") < query.index("CROSS JOIN LATERAL modkit_events.e15(page.work_id) AS observed")
        assert "SELECT observed.*" in query
        assert "ORDER BY page.created_at,page.work_id" in query
        assert "OFFSET" not in query and " OR " not in query
        assert "kind" not in query  # E30 lists the whole namespace, not only jobs.
    assert "p_after_work_id" not in queries[0]
    assert "(listed.created_at,listed.work_id)>(p_after_created_at,p_after_work_id)" in queries[1]


def test_matching_listing_indexes_and_job_filter():
    source = sql()
    assert "CREATE INDEX work_namespace_created_page ON modkit_events.work (namespace,created_at,work_id);" in source
    assert "CREATE INDEX work_jobs_created_page ON modkit_events.work (namespace,created_at,work_id)" in source
    assert "WHERE kind COLLATE pg_catalog.\"C\" = 'job' COLLATE pg_catalog.\"C\";" in source
    assert source.index("CREATE INDEX work_namespace_created_page") < source.index("CREATE FUNCTION modkit_events.e30")


def test_candidate_has_no_installation_or_readiness_claim():
    source = sql()
    assert "NOT_READY" in source
    assert "schema_versions" not in source and "manifest.json" not in source
    assert "CREATE SCHEMA" not in source and "CREATE TABLE" not in source

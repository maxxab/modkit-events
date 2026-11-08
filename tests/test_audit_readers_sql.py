"""Source contract checks for the bounded audit readers; no database execution."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement

TABLES = {"E19": "work_history", "E20": "delivery_history", "E21": "attempts"}


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function(key):
    source = sql()
    start = source.find(f"CREATE FUNCTION modkit_events.{key.lower()}(")
    assert start >= 0, f"{key} is missing from the migration"
    end = source.index("$body$;", start) + len("$body$;")
    return source[start:end]


def pairs(text):
    return re.findall(r"(\w+) pg_catalog\.(\w+)", text)


@pytest.mark.parametrize("key", TABLES)
def test_reader_abi_matches_catalog(key):
    source = function(key)
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement(key)
    assert pairs(parameters) == [
        ("p_" + item.name, item.wire_type.value) for item in expected.parameters
    ]
    assert pairs(output.split(")\nLANGUAGE", 1)[0]) == [
        (item.name, item.wire_type.value) for item in expected.result.columns
    ]
    returned = re.search(r"RETURN QUERY SELECT (.*?);", source, re.S).group(1)
    assert re.findall(r"stored\.(\w+)", returned) == [item.name for item in expected.result.columns]


@pytest.mark.parametrize("key", TABLES)
def test_reader_security_and_read_only_snapshot(key):
    source = function(key)
    assert "LANGUAGE plpgsql STABLE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    signature = ",".join(
        "pg_catalog." + item.wire_type.value for item in get_statement(key).parameters
    )
    assert f"REVOKE ALL ON FUNCTION modkit_events.{key.lower()}({signature}) FROM PUBLIC;" in sql()
    assert not re.search(
        r"\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE|EXECUTE|OFFSET|COMMIT|ROLLBACK)\b"
        r"|FOR SHARE|FOR KEY SHARE|clock_timestamp|nextval|setval|EXCEPTION WHEN"
        r"|modkit_events\.e(?:10|15)\(",
        source,
    )


@pytest.mark.parametrize("key,table", TABLES.items())
def test_reader_validates_before_bounded_indexed_query(key, table):
    source = function(key)
    relation = source.index("FROM modkit_events." + table)
    for guard in (
        "pg_catalog.current_setting('transaction_isolation') IS DISTINCT FROM 'read committed'",
        "p_work_id IS NULL",
        "p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 256",
    ):
        assert source.index(guard) < relation
    assert source.index("ERRCODE='PZ005'") < source.index("ERRCODE='PZ006'") < relation
    assert source.count("FROM modkit_events.") == 1
    assert "WHERE listed.work_id=p_work_id" in source
    assert "LIMIT p_limit" in source
    if key == "E21":
        assert "p_after_cycle IS NULL OR p_after_cycle<0" in source
        assert "p_after_attempt IS NULL OR p_after_attempt<0" in source
        assert "(listed.cycle,listed.attempt)>(p_after_cycle,p_after_attempt)" in source
        assert "ORDER BY listed.cycle,listed.attempt" in source
    else:
        assert "p_after_id IS NULL OR p_after_id<0" in source
        assert "listed.history_id>p_after_id" in source
        assert "ORDER BY listed.history_id" in source
    query = source[source.index("FOR stored IN") : source.index("LOOP")]
    assert " OR " not in query


@pytest.mark.parametrize("key", TABLES)
def test_selected_record_integrity_is_checked_after_limit(key):
    source = function(key)
    assert source.index("LIMIT p_limit") < source.index("ERRCODE='PZ012'")
    assert "stored.work_id IS DISTINCT FROM p_work_id" in source
    assert "modkit_events._instant_bytes(stored.recorded_at) IS NULL" in source
    assert source.index("ERRCODE='PZ012'") < source.index("RETURN QUERY SELECT")
    if key in ("E19", "E21"):
        assert "stored.cycle IS DISTINCT FROM 1" in source
        assert "pg_catalog.octet_length(stored.evidence)>1048576" in source


def test_readers_reuse_existing_indexes():
    source = sql()
    assert (
        "CREATE INDEX work_history_page ON modkit_events.work_history(work_id,history_id);"
        in source
    )
    assert (
        "CREATE INDEX delivery_history_page ON modkit_events.delivery_history(work_id,history_id);"
        in source
    )
    assert "PRIMARY KEY (work_id,cycle,attempt)" in source

"""Source guards only: PostgreSQL compilation/behavior require separate DB QA."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import WireType, get_statement

TYPE = {
    WireType.BYTEA: "bytea",
    WireType.TEXT: "text",
    WireType.UUID: "uuid",
    WireType.INT4: "int4",
    WireType.INT8: "int8",
    WireType.FLOAT8: "float8",
    WireType.BOOL: "bool",
    WireType.TIMESTAMPTZ: "timestamptz",
    WireType.XID8: "xid8",
    WireType.BYTEA_ARRAY: "bytea[]",
    WireType.INT4_ARRAY: "int4[]",
}


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function(key):
    matches = re.findall(
        r"CREATE FUNCTION modkit_events\." + key.lower() + r"\((.*?)\n\$body\$;", sql(), re.S
    )
    spec = get_statement(key)
    wanted = [(parameter.name, TYPE[parameter.wire_type]) for parameter in spec.parameters]
    selected = []
    for match in matches:
        parameters = match.split(")\nRETURNS TABLE", 1)[0]
        parsed = re.findall(r"p_(\w+)\s+pg_catalog\.(\w+(?:\[\])?)", parameters)
        if parsed == wanted:
            selected.append(match)
    assert len(selected) == 1, f"missing unique catalog-matching {key} SQL source body"
    return re.sub(r"--[^\n]*", "", selected[0])


def ordered(text, *parts):
    pos = -1
    for part in parts:
        new = text.find(part, pos + 1)
        assert new > pos, f"missing/order regression: {part}"
        pos = new


@pytest.mark.parametrize("key", ["E04", "E05", "E06", "E07"])
def test_literal_catalog_signature_result_and_secure_body(key):
    text = function(key)
    spec = get_statement(key)
    params = text.split(")\nRETURNS TABLE", 1)[0]
    parsed = re.findall(r"p_(\w+)\s+pg_catalog\.(\w+(?:\[\])?)", params)
    assert parsed == [(p.name, TYPE[p.wire_type]) for p in spec.parameters]
    result = text.split("RETURNS TABLE(", 1)[1].split(")\nLANGUAGE", 1)[0]
    assert re.findall(r"(\w+)\s+pg_catalog\.(\w+(?:\[\])?)", result) == [
        (c.name, TYPE[c.wire_type]) for c in spec.result.columns
    ]
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in text
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in text
    signature = ",".join("pg_catalog." + TYPE[p.wire_type] for p in spec.parameters)
    assert f"REVOKE ALL ON FUNCTION modkit_events.{key.lower()}({signature}) FROM PUBLIC;" in sql()
    for forbidden in (
        "EXECUTE ",
        "EXCEPTION WHEN",
        "modkit_events.e10(",
        "COMMIT;",
        "ROLLBACK;",
        "CREATE TABLE",
        "CREATE TYPE",
        "GRANT ",
        "DROP ",
        "setval(",
    ):
        assert forbidden not in text


@pytest.mark.parametrize("key", ["E04", "E05"])
def test_exact_lease_quantization_precedes_relations_and_clock(key):
    text = function(key)
    ordered(
        text,
        "ERRCODE='PZ005'",
        "ERRCODE='PZ006'",
        "pg_catalog.float8send(p_lease_seconds)",
        "IF exponent_bits <= 1002 THEN",
        "lease_us := 1;",
        "significand::pg_catalog.numeric * 1000000::pg_catalog.numeric",
        "1..(1075-exponent_bits)",
        "pg_catalog.div(numerator+denominator-1,denominator)::pg_catalog.int8",
        "FROM modkit_events.work",
    )
    assert (
        "p_lease_seconds>0::pg_catalog.float8 AND p_lease_seconds<=3600::pg_catalog.float8" in text
    )
    assert "lease_us<1 OR lease_us>3600000000" in text
    assert "INTERVAL '1 microsecond' * lease_us::pg_catalog.float8" in text
    assert "ceil(" not in text and "p_lease_seconds *" not in text


def test_e04_progress_and_actual_empty_probe_semantics():
    text = function("E04")
    assert "WHILE visited_count<p_discovery_budget AND item_count<p_limit LOOP" in text
    ordered(
        text,
        "ORDER BY wr.work_id LIMIT 1",
        "IF NOT FOUND THEN",
        "exhausted_value := TRUE;",
        "visited_count := visited_count+1;",
        "cursor_value := discovered.work_id;",
    )
    assert "wr.namespace=p_namespace" in text and "wr.work_id>cursor_value" in text
    assert "IF cursor_value IS NULL THEN" in text
    assert "cursor_value IS NULL OR" not in text
    assert text.count("wr.kind=p_kind") == 2
    assert text.count("ORDER BY wr.work_id LIMIT 1") == 2
    assert "IF visited_count=p_discovery_budget OR item_count=p_limit THEN" in text
    assert "exhausted_value := FALSE;" in text
    ordered(
        text,
        "'header'::pg_catalog.text",
        "FOREACH emitted IN ARRAY emitted_rows LOOP",
        "'item'::pg_catalog.text",
    )


def test_e04_zipped_arrays_and_revision_headroom():
    text = function("E04")
    for phrase in (
        "pg_catalog.array_ndims(p_command_types)",
        "pg_catalog.array_ndims(p_schema_versions)",
        "pg_catalog.cardinality(p_command_types)",
        "pg_catalog.cardinality(p_schema_versions)",
        "pg_catalog.array_lower(p_command_types,1)",
        "pg_catalog.array_lower(p_schema_versions,1)",
        "FOR pair_index IN 1..pair_count LOOP",
        "FOR prior_index IN 1..pair_index-1 LOOP",
    ):
        assert phrase in text
    assert "p_schema_versions[version_lower+(pair_index-1)]" in text
    assert "w.ownership_revision>=9223372036854775806::pg_catalog.int8" in text
    ordered(
        text,
        "w.ownership_revision>=9223372036854775806::pg_catalog.int8",
        "next_revision := w.ownership_revision+1;",
        "UPDATE modkit_events.work",
    )
    assert text.count("pg_catalog.clock_timestamp()") == 1
    assert text.count("FOR NO KEY UPDATE OF parent SKIP LOCKED") == 1
    assert text.count("FOR NO KEY UPDATE OF stored SKIP LOCKED") == 1
    ordered(
        text,
        "FOR NO KEY UPDATE OF parent SKIP LOCKED",
        "FOR NO KEY UPDATE OF stored SKIP LOCKED",
        "modkit_events.e15(stored.work_id)",
        "pg_catalog.clock_timestamp()",
        "UPDATE modkit_events.work",
    )
    assert "emitted_rows := pg_catalog.array_append(emitted_rows,updated_work)" in text
    assert "modkit_events.e15(" not in text.split("UPDATE modkit_events.work", 1)[1]


@pytest.mark.parametrize("key", ["E05", "E06", "E07"])
def test_single_work_fence_state_then_fresh_composition_before_clock(key):
    text = function(key)
    ordered(
        text,
        "FOR NO KEY UPDATE OF parent",
        "FOR NO KEY UPDATE OF stored",
        "MESSAGE='stale work fence'",
        "MESSAGE='invalid work state'",
        "modkit_events.e15(stored.work_id)",
        "pg_catalog.clock_timestamp()",
        "MESSAGE='work cancellation requested'",
        "MESSAGE='work deadline reached'",
        "MESSAGE='work lease expired'",
        "UPDATE modkit_events.work",
    )
    for clause in (
        "w.token IS DISTINCT FROM p_token",
        "w.ownership_revision IS DISTINCT FROM p_ownership_revision",
        "w.cycle IS DISTINCT FROM p_cycle",
        "w.attempt_count IS DISTINCT FROM p_expected_attempt",
    ):
        assert clause in text
    assert "SKIP LOCKED" not in text


@pytest.mark.parametrize(
    "key,expected",
    [
        ("E04", {"state", "token", "ownership_revision", "lease_until", "updated_at"}),
        ("E05", {"lease_until", "updated_at"}),
        ("E06", {"state", "attempt_count", "dispatch_id", "updated_at"}),
        (
            "E07",
            {"state", "token", "lease_until", "ownership_revision", "available_at", "updated_at"},
        ),
    ],
)
def test_exact_work_update_fields_and_history(key, expected):
    text = function(key)
    block = re.search(r"UPDATE modkit_events.work AS stored SET (.*?)\n\s*WHERE", text, re.S).group(
        1
    )
    assert set(re.findall(r"(?:^|,)\s*(\w+)\s*=", block)) == expected
    assert text.count("UPDATE modkit_events.work AS stored SET") == 1
    assert text.count("INSERT INTO modkit_events.work_history") == 1
    assert "RETURNING stored.history_id INTO history_id_value" in text
    assert "history_id_value IS NULL OR history_id_value<=0" in text
    assert "RETURNING stored.* INTO updated_work" in text
    assert "GET DIAGNOSTICS affected = ROW_COUNT;" in text
    for table in (
        "subscriptions",
        "inbox",
        "job_payloads",
        "finalization_guards",
        "mutation_operations",
        "delivery_history",
        "outbox",
        "publication_history",
    ):
        assert f"UPDATE modkit_events.{table}" not in text
        assert f"INSERT INTO modkit_events.{table}" not in text


def test_e05_nonshortening_lease_and_no_revision_replacement():
    text = function("E05")
    ordered(
        text,
        "candidate_lease := final_time+",
        "modkit_events._instant_bytes(candidate_lease)",
        "IF candidate_lease<w.lease_until THEN",
        "candidate_lease := w.lease_until;",
        "IF w.deadline IS NOT NULL AND candidate_lease>w.deadline THEN",
    )
    assert "RETURN QUERY SELECT updated_work.lease_until;" in text


def test_e06_max_defense_before_root_clock_attempt_and_no_revision_change():
    text = function("E06")
    ordered(
        text,
        "modkit_events.e15(stored.work_id)",
        "w.ownership_revision=9223372036854775807::pg_catalog.int8",
        "MESSAGE='ownership revision exhausted'",
        "pg_catalog.clock_timestamp()",
        "dispatch_root := pg_catalog.pg_current_xact_id()",
        "INSERT INTO modkit_events.attempts",
        "UPDATE modkit_events.work",
    )
    assert "next_attempt := w.attempt_count+1;" in text
    assert "RETURN QUERY SELECT updated_work.attempt_count;" in text


def test_e07_future_schedule_successor_no_attempt_or_root():
    text = function("E07")
    assert "p_available_at<=final_time" in text
    assert "p_available_at>=w.deadline" in text
    assert "next_revision := w.ownership_revision+1;" in text
    assert "state='queued',token=NULL,lease_until=NULL" in text
    assert "INSERT INTO modkit_events.attempts" not in text
    assert "pg_current_xact_id" not in text
    assert "RETURN QUERY SELECT TRUE::pg_catalog.bool;" in text


def test_e04_lower_bound_index_addition_cannot_overflow_intermediate():
    text = function("E04")
    for lower in ("command_lower", "version_lower"):
        for index in ("pair_index", "prior_index"):
            assert lower + "+(" + index + "-1)" in text
            assert lower + "+" + index + "-1" not in text


def test_e04_fresh_terminal_skip_precedes_positive_parent_count():
    text = function("E04")
    fresh_state = (
        "IF (w.state COLLATE pg_catalog.\"C\" IN ('queued','retry_waiting')) IS NOT TRUE THEN"
    )
    count_guard = (
        "IF NOT is_job AND (subscription_row.subscription_id IS DISTINCT FROM w.subscription_id"
    )
    ordered(
        text,
        "modkit_events.e15(stored.work_id)",
        "w := fresh_work;",
        fresh_state,
        "CONTINUE;",
        "END IF;",
        count_guard,
        "subscription_row.nonterminal_count IS NULL OR subscription_row.nonterminal_count<=0",
        "MESSAGE='invalid nonterminal parent count'",
        "pg_catalog.clock_timestamp()",
        "UPDATE modkit_events.work",
    )
    # Require one real skip block and one retained count guard, not moved comments.
    assert text.count(fresh_state) == 1
    assert text.count(count_guard) == 1
    skip = text.split(fresh_state, 1)[1].split("END IF;", 1)[0]
    assert skip.strip() == "CONTINUE;"

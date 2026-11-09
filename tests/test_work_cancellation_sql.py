"""E12 source-contract guards. These do not parse or execute PostgreSQL."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e12(")
    assert start >= 0, "E12 is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e12_exact_catalog_abi_and_security():
    source = function()
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement("E12")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + p.name, p.wire_type.value) for p in expected.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (c.name, c.wire_type.value) for c in expected.result.columns
    ]
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e12(pg_catalog.uuid,pg_catalog.uuid,pg_catalog.int8,pg_catalog.text) FROM PUBLIC;"
        in sql()
    )


@pytest.mark.parametrize(
    "guard",
    (
        "p_work_id IS NULL",
        "(p_expected_token IS NULL) IS DISTINCT FROM (p_expected_revision IS NULL)",
        "p_expected_revision<0",
        "p_reason IS NULL",
        "'^[a-z][a-z0-9_]{0,255}$'",
    ),
)
def test_e12_arguments_precede_storage(guard):
    source = function()
    assert source.index("ERRCODE='PZ005'") < source.index(guard)
    assert source.index(guard) < source.index("FROM modkit_events.e15(p_work_id)")
    assert "p_expected_revision<=0" not in source


def test_e12_discovery_preserves_absence_and_corruption():
    source = function()
    discovery = source.index("FROM modkit_events.e15(p_work_id)")
    parent = source.index("FOR NO KEY UPDATE OF parent")
    assert discovery < source.index("IF NOT FOUND THEN", discovery) < parent
    assert "discovered.selected_count IS DISTINCT FROM 1" in source[discovery:parent]
    assert "ERRCODE='PZ003'" in source[discovery:parent]
    assert "ERRCODE='PZ012'" in source[discovery:parent]
    assert source.count("pg_catalog.count(*) OVER () AS selected_count") == 2


def test_e12_parent_work_attempt_order_and_fresh_capture():
    source = function()
    parent = source.index("FOR NO KEY UPDATE OF parent")
    work = source.index("FOR NO KEY UPDATE OF stored", parent)
    fresh = source.index("SELECT stored.* INTO w", work)
    attempt = source.index("FOR NO KEY UPDATE OF current_attempt", fresh)
    capture = source.index("INTO captured", attempt)
    coherent = source.index("modkit_events.e15(stored.work_id)", capture)
    assert parent < work < fresh < attempt < capture < coherent
    assert "w.work_id IS DISTINCT FROM discovered.work_id" in source[fresh:attempt]
    assert "captured.selected_count IS DISTINCT FROM 1" in source[coherent:]
    assert "fresh_work IS DISTINCT FROM w" in source[coherent:]
    assert "attempt_row IS DISTINCT FROM locked_attempt" in source[coherent:]
    assert "current_attempt.dispatch_id=w.dispatch_id" in source


def test_e12_terminal_then_conditional_then_held_repeat():
    source = function()
    integrity = source.index("invalid nonterminal parent count")
    terminal = source.index("-- Terminal observation")
    conditional = source.index("IF p_expected_token IS NOT NULL")
    repeat = source.index("-- Held repeat")
    overflow = source.index("ownership revision exhausted")
    clock = source.index("final_time := pg_catalog.clock_timestamp()")
    assert integrity < terminal < conditional < repeat < overflow < clock
    assert "RETURN QUERY SELECT w.state;" in source[terminal:conditional]
    assert "RETURN QUERY SELECT w.state;" in source[repeat:overflow]
    assert "w.token IS DISTINCT FROM p_expected_token" in source[conditional:repeat]
    assert "w.ownership_revision IS DISTINCT FROM p_expected_revision" in source[conditional:repeat]
    assert "w.cancellation_requested" in source[repeat:overflow]
    assert source.count("pg_catalog.clock_timestamp()") == 1
    assert not re.search(r"final_time\s*[<>=]+\s*w\.(?:deadline|lease_until|updated_at)", source)


def test_e12_running_holds_effect_and_preserves_attempt_identity():
    source = function()
    running = source.index("transition_code := 'cancel_running'")
    held = source.index("transition_code := 'cancel_held'")
    update = source[source.index("UPDATE modkit_events.attempts", running) : held]
    assert "SET outcome='cancelled_unresolved',evidence=''::pg_catalog.bytea" in update
    assert "updated_attempt IS DISTINCT FROM expected_attempt" in update
    assert "expected_attempt := attempt_row;" in source[running:held]
    assert "expected_attempt.outcome := 'cancelled_unresolved';" in source[running:held]
    assert not re.search(r"SET\s+(?:dispatch_id|dispatch_root_xid|recorded_at)", update)
    assert source.count("UPDATE modkit_events.attempts") == 1
    assert source.index("expected_work.state := 'held'", running) < held


def test_e12_revision_capacity_history_postimages():
    source = function()
    assert source.index("ownership revision exhausted") < source.index("w.ownership_revision+1")
    for field in (
        "state",
        "cancellation_requested",
        "token",
        "lease_until",
        "ownership_revision",
        "updated_at",
    ):
        assert f"expected_work.{field} :=" in source
    assert "updated_work IS DISTINCT FROM expected_work" in source
    assert "expected_parent.nonterminal_count := subscription_row.nonterminal_count-1;" in source
    assert "updated_parent IS DISTINCT FROM expected_parent" in source
    assert (
        "IF transition_code COLLATE pg_catalog.\"C\" = 'cancel_predispatch' AND NOT is_job THEN"
        in source
    )
    assert source.count("UPDATE modkit_events.subscriptions") == 1
    assert source.count("INSERT INTO modkit_events.work_history") == 1
    assert "history_row.reason,'UTF8'" in source
    assert "history_row.recorded_at IS DISTINCT FROM final_time" in source
    assert (
        "history_row.ownership_revision IS DISTINCT FROM updated_work.ownership_revision" in source
    )
    assert "history_row.token IS NOT NULL" in source
    assert "history_row.evidence IS DISTINCT FROM ''::pg_catalog.bytea" in source
    assert "RETURN QUERY SELECT updated_work.state;" in source


def test_e12_no_new_execution_or_guard_authority():
    source = function().split("AS $body$", 1)[1]
    assert sorted(set(re.findall(r"modkit_events\.(e\d+)\(", source))) == ["e15"]
    assert not re.search(
        r"\b(?:DELETE|MERGE|TRUNCATE|EXECUTE|COMMIT|ROLLBACK)\b|SKIP LOCKED|EXCEPTION WHEN|nextval|setval",
        source,
    )
    assert not re.search(
        r"(?:UPDATE|INSERT INTO) modkit_events\.(?:finalization_guards|mutation_operations|inbox|job_payloads|delivery_history)",
        source,
    )

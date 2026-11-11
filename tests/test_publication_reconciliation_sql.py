"""E27 source guards; actual behavior is checked by the separately reviewed SQL fixture."""

import re
from importlib.resources import files

import pytest

from modkit_events.persistence.catalog import get_statement


def sql():
    return files("modkit_events.persistence.sql").joinpath("0001_initial.sql").read_text()


def function():
    source = sql()
    start = source.find("CREATE FUNCTION modkit_events.e27(")
    assert start >= 0, "E27 is missing from the migration"
    return source[start : source.index("$body$;", start) + len("$body$;")]


def test_e27_exact_abi_and_security():
    source = function()
    parameters, output = source.split("RETURNS TABLE(", 1)
    expected = get_statement("E27")
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", parameters) == [
        ("p_" + p.name, p.wire_type.value) for p in expected.parameters
    ]
    assert re.findall(r"(\w+) pg_catalog\.(\w+)", output.split(")\nLANGUAGE", 1)[0]) == [
        (c.name, c.wire_type.value) for c in expected.result.columns
    ]
    assert "LANGUAGE plpgsql VOLATILE SECURITY DEFINER CALLED ON NULL INPUT" in source
    assert "SET search_path = pg_catalog, pg_temp AS $body$" in source
    assert (
        "REVOKE ALL ON FUNCTION modkit_events.e27(pg_catalog.bytea,pg_catalog.int8,pg_catalog.uuid,pg_catalog.text,pg_catalog.bytea,pg_catalog.bytea,pg_catalog.bytea) FROM PUBLIC;"
        in sql()
    )


@pytest.mark.parametrize(
    "guard",
    (
        "modkit_events._utf8_valid(p_event_id,256,TRUE) IS NOT TRUE",
        "p_expected_revision IS NULL OR p_expected_revision<0",
        "p_operation_id IS NULL",
        "p_status COLLATE pg_catalog.\"C\" IN ('published','rejected')",
        "pg_catalog.octet_length(p_receipt)>4096",
        "p_evidence IS NULL OR pg_catalog.octet_length(p_evidence)>1048576",
        "p_binding IS NULL OR pg_catalog.octet_length(p_binding)>1048576",
    ),
)
def test_e27_complete_input_before_lock(guard):
    source = function()
    assert source.index("ERRCODE='PZ005'") < source.index(guard)
    assert source.index(guard) < source.index("FROM modkit_events.outbox")


def test_e27_digest_mutex_fresh_snapshot_and_complete_preimage():
    source = function()
    lock = source.index("FOR NO KEY UPDATE OF stored;")
    fresh = source.index("SELECT stored.* INTO locked_outbox", lock)
    validation = source.index("FROM modkit_events.e28(p_event_id) AS observed")
    registry = source.index("SELECT stored.* INTO operation_row")
    assert lock < fresh < validation < registry
    assert "stored.event_digest=pg_catalog.sha256(p_event_id)" in source[:lock]
    assert "stored.event_id=p_event_id" not in source
    assert "captured.selected_count IS DISTINCT FROM 1" in source
    assert "fresh_outbox IS DISTINCT FROM locked_outbox" in source
    assert re.findall(r"modkit_events\.(e\d+)\(", source.split("AS $body$", 1)[1]) == ["e28"]


def test_e27_repeat_registry_precedes_new_operation_fence_state_and_clock():
    source = function()
    read = source.index("SELECT stored.* INTO operation_row")
    absent = source.index("IF NOT FOUND THEN", read)
    fence = source.index("locked_outbox.ownership_revision IS DISTINCT FROM p_expected_revision")
    state = source.index("locked_outbox.state COLLATE pg_catalog.\"C\"='held'")
    clock = source.index("final_time := pg_catalog.clock_timestamp()")
    assert read < absent < fence < state < clock
    assert "ERRCODE='PZ003',MESSAGE='stale publication revision'" in source
    assert "ERRCODE='PZ004',MESSAGE='invalid publication repair state'" in source


def test_e27_global_registry_collision_uses_fresh_read_without_retry():
    source = function()
    insert = source.index("INSERT INTO modkit_events.mutation_operations")
    conflict = source.index("ON CONFLICT ON CONSTRAINT mutation_operations_pkey DO NOTHING")
    reread = source.index("SELECT stored.* INTO operation_row", insert)
    validation = source.index("MESSAGE='invalid publication repair operation'")
    update = source.index("UPDATE modkit_events.outbox")
    assert insert < conflict < reread < validation < update
    assert "created_operation := affected=1" in source
    assert "IF created_operation THEN" in source[:update]
    assert source.count("INSERT INTO modkit_events.mutation_operations") == 1
    assert source.count("UPDATE modkit_events.outbox") == 1
    assert not re.search(
        r"\b(?:DELETE|MERGE|TRUNCATE|EXECUTE|COMMIT|ROLLBACK|LOOP)\b|SKIP LOCKED|EXCEPTION WHEN|pg_advisory",
        source,
    )


def test_e27_validates_complete_stored_repair_union():
    source = function()
    for field in (
        "work_id",
        "token",
        "cycle",
        "attempt",
        "dispatch_id",
        "failed_business_root",
        "retry_at",
        "requested_result",
        "result_digest",
        "requested_reason",
        "resolution_root_xid",
    ):
        assert f"operation_row.{field} IS NOT NULL" in source
    for guard in (
        "operation_row.operation_id IS DISTINCT FROM p_operation_id",
        "operation_row.event_digest IS DISTINCT FROM pg_catalog.sha256(operation_row.event_id)",
        "operation_row.expected_revision IS NULL OR operation_row.expected_revision<0",
        "operation_row.resulting_revision::pg_catalog.numeric",
        "operation_row.expected_revision::pg_catalog.numeric+1",
        "pg_catalog.octet_length(operation_row.requested_receipt)>4096",
        "operation_row.evidence IS NULL",
        "operation_row.binding IS NULL",
        "modkit_events._instant_bytes(operation_row.recorded_at) IS NULL",
    ):
        assert guard in source
    assert "pg_catalog.convert_to(operation_row.operation_kind,'UTF8')" in source
    assert (
        "operation_row.requested_outcome COLLATE pg_catalog.\"C\" IN ('published','rejected')"
        in source
    )


def test_e27_compares_all_request_fields_and_returns_original_observation():
    source = function()
    for field, parameter in (
        ("event_id", "event_id"),
        ("expected_revision", "expected_revision"),
        ("requested_receipt", "receipt"),
        ("evidence", "evidence"),
        ("binding", "binding"),
    ):
        assert f"operation_row.{field} IS DISTINCT FROM p_{parameter}" in source
    assert (
        "pg_catalog.convert_to(operation_row.requested_outcome,'UTF8') IS DISTINCT FROM pg_catalog.convert_to(p_status,'UTF8')"
        in source
    )
    assert "ERRCODE='PZ002',MESSAGE='publication repair operation conflict'" in source
    assert (
        "RETURN QUERY SELECT operation_row.operation_id,operation_row.event_id,operation_row.expected_revision,"
        in source
    )
    assert (
        "operation_row.binding,operation_row.resulting_revision,operation_row.recorded_at" in source
    )


def test_e27_overflow_exact_postimage_and_single_history():
    source = function()
    assert (
        source.index("locked_outbox.ownership_revision=9223372036854775807")
        < source.index("next_revision := locked_outbox.ownership_revision+1")
        < source.index("INSERT INTO modkit_events.mutation_operations")
    )
    assert "updated_outbox IS DISTINCT FROM expected_outbox" in source
    assert "operation_row IS DISTINCT FROM expected_operation" in source
    update = source[
        source.index("UPDATE modkit_events.outbox") : source.index(
            "RETURNING stored.* INTO updated_outbox"
        )
    ]
    assert "state=p_status,token=NULL,ownership_revision=next_revision,lease_until=NULL" in update
    assert "receipt=p_receipt,outcome_evidence=p_evidence,updated_at=final_time" in update
    assert not re.search(
        r"intent_id\s*=|event_id\s*=|replay_input\s*=|envelope_evidence\s*=", update
    )
    assert source.count("INSERT INTO modkit_events.publication_history") == 1
    assert "WHEN 'published' THEN 'repair_published'" in source
    assert "WHEN 'rejected' THEN 'repair_rejected'" in source
    assert "VALUES(updated_outbox.event_id,updated_outbox.intent_id,p_operation_id," in source
    assert "history_status,p_receipt,p_evidence,p_binding,final_time)" in source

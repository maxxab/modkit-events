"""Pure selection/SQL-output contract; no driver or SQL execution."""

import importlib
import importlib.util
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from modkit_events.persistence import catalog as C
from modkit_events.persistence import errors as E


def module():
    name = "modkit_events.persistence.native_codec"
    assert importlib.util.find_spec(name) is not None, "pure SQL descriptor module is missing"
    return importlib.import_module(name)


def select(spec):
    function = getattr(module(), "_selected_sql_descriptor", None)
    assert callable(function), "pure SQL descriptor selector is missing"
    return function(spec)


def capture(call):
    try:
        call()
    except BaseException as error:
        return error
    raise AssertionError("operation unexpectedly succeeded")


E14_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.root_xid
    FROM modkit_events.e14() AS s
)
SELECT TRUE::pg_catalog.bool AS cap_ok, s.root_xid
FROM source AS s
LIMIT 2"""
E28_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.event_id, s.canonical_version, s.envelope_evidence, s.replay_input, s.state, s.token, s.ownership_revision, s.lease_until, s.intent_id, s.receipt, s.outcome_evidence, s.created_at, s.updated_at
    FROM modkit_events.e28($1::pg_catalog.bytea) AS s
), checked AS (
    SELECT s.*, (
        (s.event_id IS NOT NULL AND pg_catalog.octet_length(s.event_id) OPERATOR(pg_catalog.<=) 256)
        AND (s.envelope_evidence IS NOT NULL AND pg_catalog.octet_length(s.envelope_evidence) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.replay_input IS NOT NULL AND pg_catalog.octet_length(s.replay_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.state IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.state, 'UTF8')) OPERATOR(pg_catalog.<=) 10)
        AND (s.receipt IS NULL OR pg_catalog.octet_length(s.receipt) OPERATOR(pg_catalog.<=) 4096)
        AND (s.outcome_evidence IS NULL OR pg_catalog.octet_length(s.outcome_evidence) OPERATOR(pg_catalog.<=) 1048576)
    ) IS TRUE AS cap_ok
    FROM source AS s
)
SELECT c.cap_ok,
       CASE WHEN c.cap_ok THEN c.event_id ELSE NULL::pg_catalog.bytea END AS event_id,
       c.canonical_version,
       CASE WHEN c.cap_ok THEN c.envelope_evidence ELSE NULL::pg_catalog.bytea END AS envelope_evidence,
       CASE WHEN c.cap_ok THEN c.replay_input ELSE NULL::pg_catalog.bytea END AS replay_input,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS state,
       c.token,
       c.ownership_revision,
       c.lease_until,
       c.intent_id,
       CASE WHEN c.cap_ok THEN c.receipt ELSE NULL::pg_catalog.bytea END AS receipt,
       CASE WHEN c.cap_ok THEN c.outcome_evidence ELSE NULL::pg_catalog.bytea END AS outcome_evidence,
       c.created_at,
       c.updated_at
FROM checked AS c
LIMIT 2"""
E14_COLUMNS = (
    ("cap_ok", C.WireType.BOOL, 16, False, 1),
    ("root_xid", C.WireType.XID8, 5069, False, 8),
)
E28_COLUMNS = (
    ("cap_ok", C.WireType.BOOL, 16, False, 1),
    ("event_id", C.WireType.BYTEA, 17, False, 256),
    ("canonical_version", C.WireType.INT4, 23, False, 4),
    ("envelope_evidence", C.WireType.BYTEA, 17, False, 1048576),
    ("replay_input", C.WireType.BYTEA, 17, False, 1048576),
    ("state", C.WireType.BYTEA, 17, False, 10),
    ("token", C.WireType.UUID, 2950, True, 16),
    ("ownership_revision", C.WireType.INT8, 20, False, 8),
    ("lease_until", C.WireType.TIMESTAMPTZ, 1184, True, 8),
    ("intent_id", C.WireType.UUID, 2950, True, 16),
    ("receipt", C.WireType.BYTEA, 17, True, 4096),
    ("outcome_evidence", C.WireType.BYTEA, 17, True, 1048576),
    ("created_at", C.WireType.TIMESTAMPTZ, 1184, False, 8),
    ("updated_at", C.WireType.TIMESTAMPTZ, 1184, False, 8),
)


@pytest.mark.parametrize(
    "key,sql,casts,columns,cardinality,total",
    [
        ("E14", E14_SQL, (), E14_COLUMNS, C.CardinalityKind.EXACT_ONE, 9),
        (
            "E28",
            E28_SQL,
            ("pg_catalog.bytea",),
            E28_COLUMNS,
            C.CardinalityKind.OPTIONAL_ONE,
            3150159,
        ),
    ],
)
def test_selection_emits_complete_reviewed_sql_and_physical_contract(
    key, sql, casts, columns, cardinality, total
):
    spec = C.get_statement(key)
    actual = select(spec)
    assert type(actual.sql) is bytes and actual.sql == sql
    assert type(actual.parameter_casts) is tuple and actual.parameter_casts == casts
    assert actual.canonical_columns is spec.result.columns
    assert actual.cardinality is cardinality
    assert actual.sentinel_limit == 2 and type(actual.sentinel_limit) is int
    assert actual.max_admitted_cell_payload_bytes == total
    assert type(actual.transport_columns) is tuple
    assert (
        tuple(
            (c.name, c.wire_type, c.oid, c.nullable, c.max_payload_bytes)
            for c in actual.transport_columns
        )
        == columns
    )
    assert actual is select(spec)


def test_state_transport_is_bytea_while_canonical_state_remains_text():
    actual = select(C.get_statement("E28"))
    assert actual.transport_columns[5].wire_type is C.WireType.BYTEA
    assert actual.transport_columns[5].oid == 17
    assert actual.canonical_columns[4].wire_type is C.WireType.TEXT
    assert actual.transport_columns[5].name == actual.canonical_columns[4].name == "state"


@pytest.mark.parametrize("key", ["E05", "E06", "E08", "E09", "E10", "E11", "E14", "E28", "E32"])
def test_selected_plan_and_column_metadata_are_immutable(key):
    actual = select(C.get_statement(key))
    with pytest.raises(FrozenInstanceError):
        actual.sql = b"SELECT unreviewed"
    with pytest.raises(FrozenInstanceError):
        actual.transport_columns[0].oid = 25
    assert not hasattr(actual, "__dict__")
    assert not hasattr(actual.transport_columns[0], "__dict__")


@pytest.mark.parametrize(
    "key", [f"E{i:02}" for i in range(1, 35) if i not in (5, 6, 8, 9, 10, 11, 14, 28, 32, 33)]
)
def test_every_unselected_event_spec_refuses_a_descriptor(key):
    assert type(capture(lambda: select(C.get_statement(key)))) is E._ValidationReject


@pytest.mark.parametrize("key", ["W01", "W02", "W03", "W04", "W05"])
def test_foreign_worker_descriptor_shape_is_not_an_events_authority(key):
    foreign = SimpleNamespace(key=key, result=C.get_statement("E14").result)
    assert type(capture(lambda: select(foreign))) is E._ValidationReject


@pytest.mark.parametrize("value", [None, "E14", "E28", b"E28", (), {}, object()])
def test_raw_identity_gate_rejects_noncanonical_inputs(value):
    assert type(capture(lambda: select(value))) is E._ValidationReject


@pytest.mark.parametrize("key", ["E14", "E28"])
def test_metadata_clone_and_uninitialized_carrier_cannot_select_sql(key):
    original = C.get_statement(key)
    for candidate in (replace(original), object.__new__(C.StatementSpec)):
        assert type(capture(lambda: select(candidate))) is E._ValidationReject


def test_foreign_callbacks_are_not_used_to_choose_sql():
    class Foreign:
        def __getattribute__(self, name):
            raise AssertionError("foreign field callback")

        def __eq__(self, other):
            raise AssertionError("foreign equality callback")

        def __hash__(self):
            raise AssertionError("foreign hash callback")

    assert type(capture(lambda: select(Foreign()))) is E._ValidationReject


@pytest.mark.parametrize("key", ["E14", "E28"])
def test_selection_uses_shared_raw_metadata_revalidation(key):
    spec = C.get_statement(key)
    before = spec.mutation
    try:
        object.__setattr__(spec, "mutation", None)
        assert type(capture(lambda: select(spec))) is E._ValidationReject
    finally:
        object.__setattr__(spec, "mutation", before)


@pytest.mark.parametrize("key", ["E14", "E28"])
def test_selection_does_not_call_public_post_init_sanitizers(monkeypatch, key):
    module()

    def forbidden(*args, **kwargs):
        raise AssertionError("public metadata post-init reached")

    for cls in (C.StatementSpec, C.ResultSpec, C.ParameterSpec, C.ColumnSpec):
        monkeypatch.setattr(cls, "__post_init__", forbidden)
    assert select(C.get_statement(key)).sql in (E14_SQL, E28_SQL)


@pytest.mark.parametrize(
    "error_type", [MemoryError, RuntimeError, ValueError, TypeError, BaseException]
)
def test_unexpected_raw_metadata_failure_preserves_received_primary(monkeypatch, error_type):
    module()
    primary = error_type("opaque")
    old_tb = capture(lambda: (_ for _ in ()).throw(primary)).__traceback__
    cause, context = LookupError("cause"), OSError("context")
    primary.__cause__, primary.__context__, primary.__suppress_context__ = cause, context, False

    def fault(*args, **kwargs):
        raise primary

    monkeypatch.setattr(C, "_validate_statement_spec", fault)
    caught = capture(lambda: select(C.get_statement("E28")))
    assert caught is primary
    assert caught.__cause__ is cause and caught.__context__ is context
    assert caught.__suppress_context__ is False
    node = caught.__traceback__
    while node is not None and node is not old_tb:
        node = node.tb_next
    assert node is old_tb

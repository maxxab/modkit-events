"""Pure fixed SQL plans for completion/E14/E28 and W01/W02/W03/W04/W05 transport.

No driver, I/O, readiness or execution authority is provided here. Physical
capacity, bootstrap, lifecycle and actual SQL/driver qualification remain gates.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from .bindings import _decode_utf8, _statement_shape_raw
from .catalog import CardinalityKind, ColumnSpec, StatementSpec, WireType, get_statement
from .errors import _reject_validation
from .rows import _decode_columns_raw


@dataclass(frozen=True, slots=True, kw_only=True)
class _TransportColumn:
    name: str
    wire_type: WireType
    oid: int
    nullable: bool
    max_payload_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _SqlDescriptor:
    sql: bytes
    parameter_casts: tuple[str, ...]
    canonical_columns: tuple[ColumnSpec, ...]
    transport_columns: tuple[_TransportColumn, ...]
    cardinality: CardinalityKind
    sentinel_limit: int
    max_admitted_cell_payload_bytes: int


_E05_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.lease_until
    FROM modkit_events.e05($1::pg_catalog.uuid, $2::pg_catalog.uuid, $3::pg_catalog.int8, $4::pg_catalog.int4, $5::pg_catalog.int4, $6::pg_catalog.float8) AS s
)
SELECT TRUE::pg_catalog.bool AS cap_ok, s.lease_until
FROM source AS s
LIMIT 2"""
_E05 = _SqlDescriptor(
    sql=_E05_SQL,
    parameter_casts=("pg_catalog.uuid", "pg_catalog.uuid", "pg_catalog.int8",
                     "pg_catalog.int4", "pg_catalog.int4", "pg_catalog.float8"),
    canonical_columns=get_statement("E05").result.columns,
    transport_columns=(
        _TransportColumn(name="cap_ok", wire_type=WireType.BOOL, oid=16,
                         nullable=False, max_payload_bytes=1),
        _TransportColumn(name="lease_until", wire_type=WireType.TIMESTAMPTZ, oid=1184,
                         nullable=False, max_payload_bytes=8),
    ),
    cardinality=CardinalityKind.EXACT_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=9,
)


_E14_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.root_xid
    FROM modkit_events.e14() AS s
)
SELECT TRUE::pg_catalog.bool AS cap_ok, s.root_xid
FROM source AS s
LIMIT 2"""
_E28_SQL = b"""WITH source AS MATERIALIZED (
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

# Startup-retained immutable plans, not a native readiness receipt. The state
# field is physically UTF-8 BYTEA while its canonical column remains TEXT.
_E14 = _SqlDescriptor(
    sql=_E14_SQL,
    parameter_casts=(),
    canonical_columns=get_statement("E14").result.columns,
    transport_columns=(
        _TransportColumn(
            name="cap_ok", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
        ),
        _TransportColumn(
            name="root_xid", wire_type=WireType.XID8, oid=5069, nullable=False, max_payload_bytes=8
        ),
    ),
    cardinality=CardinalityKind.EXACT_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=9,
)

_E28 = _SqlDescriptor(
    sql=_E28_SQL,
    parameter_casts=("pg_catalog.bytea",),
    canonical_columns=get_statement("E28").result.columns,
    transport_columns=(
        _TransportColumn(
            name="cap_ok", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
        ),
        _TransportColumn(
            name="event_id", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=256
        ),
        _TransportColumn(
            name="canonical_version",
            wire_type=WireType.INT4,
            oid=23,
            nullable=False,
            max_payload_bytes=4,
        ),
        _TransportColumn(
            name="envelope_evidence",
            wire_type=WireType.BYTEA,
            oid=17,
            nullable=False,
            max_payload_bytes=1048576,
        ),
        _TransportColumn(
            name="replay_input",
            wire_type=WireType.BYTEA,
            oid=17,
            nullable=False,
            max_payload_bytes=1048576,
        ),
        _TransportColumn(
            name="state", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=10
        ),
        _TransportColumn(
            name="token", wire_type=WireType.UUID, oid=2950, nullable=True, max_payload_bytes=16
        ),
        _TransportColumn(
            name="ownership_revision",
            wire_type=WireType.INT8,
            oid=20,
            nullable=False,
            max_payload_bytes=8,
        ),
        _TransportColumn(
            name="lease_until",
            wire_type=WireType.TIMESTAMPTZ,
            oid=1184,
            nullable=True,
            max_payload_bytes=8,
        ),
        _TransportColumn(
            name="intent_id", wire_type=WireType.UUID, oid=2950, nullable=True, max_payload_bytes=16
        ),
        _TransportColumn(
            name="receipt", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=4096
        ),
        _TransportColumn(
            name="outcome_evidence",
            wire_type=WireType.BYTEA,
            oid=17,
            nullable=True,
            max_payload_bytes=1048576,
        ),
        _TransportColumn(
            name="created_at",
            wire_type=WireType.TIMESTAMPTZ,
            oid=1184,
            nullable=False,
            max_payload_bytes=8,
        ),
        _TransportColumn(
            name="updated_at",
            wire_type=WireType.TIMESTAMPTZ,
            oid=1184,
            nullable=False,
            max_payload_bytes=8,
        ),
    ),
    cardinality=CardinalityKind.OPTIONAL_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=3150159,
)


# Four fixed Events completion plans; no runtime statement compiler.
_E06_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.attempt
    FROM modkit_events.e06($1::pg_catalog.uuid, $2::pg_catalog.uuid, $3::pg_catalog.int8, $4::pg_catalog.int4, $5::pg_catalog.int4, $6::pg_catalog.uuid, $7::pg_catalog.bytea, $8::pg_catalog.bytea, $9::pg_catalog.bytea) AS s
)
SELECT TRUE::pg_catalog.bool AS cap_ok, s.attempt
FROM source AS s
LIMIT 2"""

_E06_COLUMNS = (
    _E14.transport_columns[0],
    _TransportColumn(
        name="attempt", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
)
_E06 = _SqlDescriptor(
    sql=_E06_SQL,
    parameter_casts=(
        "pg_catalog.uuid",
        "pg_catalog.uuid",
        "pg_catalog.int8",
        "pg_catalog.int4",
        "pg_catalog.int4",
        "pg_catalog.uuid",
        "pg_catalog.bytea",
        "pg_catalog.bytea",
        "pg_catalog.bytea",
    ),
    canonical_columns=get_statement("E06").result.columns,
    transport_columns=_E06_COLUMNS,
    cardinality=CardinalityKind.EXACT_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=sum(c.max_payload_bytes for c in _E06_COLUMNS),
)

_E08_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.guard_id, s.work_id, s.root_xid, s.token, s.ownership_revision, s.cycle, s.expected_attempt, s.satisfied, s.final_fence_at, s.terminal_state, s.result_digest
    FROM modkit_events.e08($1::pg_catalog.uuid, $2::pg_catalog.uuid, $3::pg_catalog.int8, $4::pg_catalog.int4, $5::pg_catalog.int4) AS s
), checked AS (
    SELECT s.*, (
        (s.terminal_state IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.terminal_state, 'UTF8')) OPERATOR(pg_catalog.<=) 9)
        AND (s.result_digest IS NULL OR pg_catalog.octet_length(s.result_digest) OPERATOR(pg_catalog.<=) 32)
    ) IS TRUE AS cap_ok
    FROM source AS s
)
SELECT c.cap_ok, c.guard_id, c.work_id, c.root_xid, c.token,
       c.ownership_revision, c.cycle, c.expected_attempt, c.satisfied, c.final_fence_at,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.terminal_state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS terminal_state,
       CASE WHEN c.cap_ok THEN c.result_digest ELSE NULL::pg_catalog.bytea END AS result_digest
FROM checked AS c
LIMIT 2"""

_E08_COLUMNS = (
    _E14.transport_columns[0],
    _TransportColumn(
        name="guard_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="work_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="root_xid", wire_type=WireType.XID8, oid=5069, nullable=False, max_payload_bytes=8
    ),
    _TransportColumn(
        name="token", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="ownership_revision",
        wire_type=WireType.INT8,
        oid=20,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="cycle", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
    _TransportColumn(
        name="expected_attempt",
        wire_type=WireType.INT4,
        oid=23,
        nullable=False,
        max_payload_bytes=4,
    ),
    _TransportColumn(
        name="satisfied", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
    ),
    _TransportColumn(
        name="final_fence_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="terminal_state", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=9
    ),
    _TransportColumn(
        name="result_digest", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=32
    ),
)
_E08 = _SqlDescriptor(
    sql=_E08_SQL,
    parameter_casts=(
        "pg_catalog.uuid",
        "pg_catalog.uuid",
        "pg_catalog.int8",
        "pg_catalog.int4",
        "pg_catalog.int4",
    ),
    canonical_columns=get_statement("E08").result.columns,
    transport_columns=_E08_COLUMNS,
    cardinality=CardinalityKind.EXACT_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=sum(c.max_payload_bytes for c in _E08_COLUMNS),
)

_E09_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.guard_id, s.work_id, s.root_xid, s.token, s.ownership_revision, s.cycle, s.expected_attempt, s.satisfied, s.final_fence_at, s.terminal_state, s.result_digest
    FROM modkit_events.e09($1::pg_catalog.uuid, $2::pg_catalog.uuid, $3::pg_catalog.int8, $4::pg_catalog.int4, $5::pg_catalog.int4) AS s
), checked AS (
    SELECT s.*, (
        (s.terminal_state IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.terminal_state, 'UTF8')) OPERATOR(pg_catalog.<=) 9)
        AND (s.result_digest IS NULL OR pg_catalog.octet_length(s.result_digest) OPERATOR(pg_catalog.<=) 32)
    ) IS TRUE AS cap_ok
    FROM source AS s
)
SELECT c.cap_ok, c.guard_id, c.work_id, c.root_xid, c.token,
       c.ownership_revision, c.cycle, c.expected_attempt, c.satisfied, c.final_fence_at,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.terminal_state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS terminal_state,
       CASE WHEN c.cap_ok THEN c.result_digest ELSE NULL::pg_catalog.bytea END AS result_digest
FROM checked AS c
LIMIT 2"""

_E09_COLUMNS = (
    _E14.transport_columns[0],
    _TransportColumn(
        name="guard_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="work_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="root_xid", wire_type=WireType.XID8, oid=5069, nullable=False, max_payload_bytes=8
    ),
    _TransportColumn(
        name="token", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="ownership_revision",
        wire_type=WireType.INT8,
        oid=20,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="cycle", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
    _TransportColumn(
        name="expected_attempt",
        wire_type=WireType.INT4,
        oid=23,
        nullable=False,
        max_payload_bytes=4,
    ),
    _TransportColumn(
        name="satisfied", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
    ),
    _TransportColumn(
        name="final_fence_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="terminal_state", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=9
    ),
    _TransportColumn(
        name="result_digest", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=32
    ),
)
_E09 = _SqlDescriptor(
    sql=_E09_SQL,
    parameter_casts=(
        "pg_catalog.uuid",
        "pg_catalog.uuid",
        "pg_catalog.int8",
        "pg_catalog.int4",
        "pg_catalog.int4",
    ),
    canonical_columns=get_statement("E09").result.columns,
    transport_columns=_E09_COLUMNS,
    cardinality=CardinalityKind.OPTIONAL_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=sum(c.max_payload_bytes for c in _E09_COLUMNS),
)

_E10_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.ok
    FROM modkit_events.e10($1::pg_catalog.uuid, $2::pg_catalog.uuid, $3::pg_catalog.text::pg_catalog.xid8, $4::pg_catalog.uuid, $5::pg_catalog.int8, $6::pg_catalog.int4, $7::pg_catalog.int4, $8::pg_catalog.bytea) AS s
)
SELECT TRUE::pg_catalog.bool AS cap_ok, s.ok
FROM source AS s
LIMIT 2"""

_E10_COLUMNS = (
    _E14.transport_columns[0],
    _TransportColumn(
        name="ok", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
    ),
)
_E10 = _SqlDescriptor(
    sql=_E10_SQL,
    parameter_casts=(
        "pg_catalog.uuid",
        "pg_catalog.uuid",
        "pg_catalog.text",
        "pg_catalog.uuid",
        "pg_catalog.int8",
        "pg_catalog.int4",
        "pg_catalog.int4",
        "pg_catalog.bytea",
    ),
    canonical_columns=get_statement("E10").result.columns,
    transport_columns=_E10_COLUMNS,
    cardinality=CardinalityKind.EXACT_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=sum(c.max_payload_bytes for c in _E10_COLUMNS),
)

_E11_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.ok
    FROM modkit_events.e11($1::pg_catalog.uuid, $2::pg_catalog.uuid, $3::pg_catalog.int8, $4::pg_catalog.int4, $5::pg_catalog.int4, $6::pg_catalog.text::pg_catalog.xid8, $7::pg_catalog.text, $8::pg_catalog.timestamptz, $9::pg_catalog.text, $10::pg_catalog.bytea) AS s
)
SELECT TRUE::pg_catalog.bool AS cap_ok, s.ok
FROM source AS s
LIMIT 2"""

_E11 = _SqlDescriptor(
    sql=_E11_SQL,
    parameter_casts=(
        "pg_catalog.uuid",
        "pg_catalog.uuid",
        "pg_catalog.int8",
        "pg_catalog.int4",
        "pg_catalog.int4",
        "pg_catalog.text",
        "pg_catalog.text",
        "pg_catalog.timestamptz",
        "pg_catalog.text",
        "pg_catalog.bytea",
    ),
    canonical_columns=get_statement("E11").result.columns,
    transport_columns=_E10_COLUMNS,
    cardinality=CardinalityKind.EXACT_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=2,
)

# Fixed Workers plans. No import of Workers and no runtime SQL generation.
_W01_SQL = b"""SELECT TRUE::pg_catalog.bool AS cap_ok, s.work_id, s.inserted
FROM modkit_workers.w01($1::pg_catalog.uuid, $2::pg_catalog.text, $3::pg_catalog.bytea, $4::pg_catalog.bytea, $5::pg_catalog.bytea, $6::pg_catalog.bytea, $7::pg_catalog.bytea, $8::pg_catalog.int4, $9::pg_catalog.bytea, $10::pg_catalog.bytea, $11::pg_catalog.bytea, $12::pg_catalog.bytea, $13::pg_catalog.bytea, $14::pg_catalog.bytea, $15::pg_catalog.bytea, $16::pg_catalog.bytea, $17::pg_catalog.text, $18::pg_catalog.int4, $19::pg_catalog.timestamptz, $20::pg_catalog.timestamptz, $21::pg_catalog.text, $22::pg_catalog.bytea, $23::pg_catalog.bytea, $24::pg_catalog.bytea, $25::pg_catalog.bytea, $26::pg_catalog.timestamptz, $27::pg_catalog.bytea, $28::pg_catalog.text, $29::pg_catalog.bytea) AS s
LIMIT 2"""
_JOB_SOURCE_PROJECTION = b"""    SELECT s.work_id, s.kind, s.subscription_id, s.namespace, s.command_type, s.schema_version_decimal, s.runnable_version, s.canonical_version, s.scope_evidence, s.scope_application, s.scope_tenant, s.scope_owner, s.idempotency_key, s.intent_evidence, s.semantic_input, s.replay_input, s.protected_binding, s.replay_policy, s.max_attempts, s.deadline, s.original_available_at, s.state, s.cancellation_requested, s.token, s.ownership_revision, s.lease_until, s.available_at, s.cycle, s.attempt_count, s.dispatch_id, s.result, s.created_at, s.updated_at, s.success_origin, s.completion_guard_id, s.final_fence_at, s.completion_result_digest, s.resolution_operation_id, s.terminal_resolution_operation_id, s.resolution_present, s.resolution_record_operation_id, s.resolution_record_operation_kind, s.resolution_record_work_id, s.resolution_record_expected_revision, s.resolution_record_cycle, s.resolution_record_attempt, s.resolution_record_dispatch_id, s.resolution_record_outcome, s.resolution_record_retry_at, s.resolution_record_result, s.resolution_record_result_digest, s.resolution_record_reason, s.resolution_record_evidence, s.resolution_record_binding, s.resolution_record_resolution_root_xid, s.resolution_record_recorded_at, s.job_work_id, s.job_application, s.job_tenant, s.job_owner, s.job_protected_binding, s.job_semantic_input, s.material_state, s.protected_sidecar, s.protected_reference, s.protected_codec, s.protected_key_version, s.protected_expires_at, s.protected_recovery_metadata, s.protected_cleanup_policy, s.projection_metadata"""
_JOB_CAP_PREDICATE = b"""        (s.kind IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.kind, 'UTF8')) OPERATOR(pg_catalog.<=) 3)
        AND (s.subscription_id IS NULL OR pg_catalog.octet_length(s.subscription_id) OPERATOR(pg_catalog.<=) 256)
        AND (s.namespace IS NOT NULL AND pg_catalog.octet_length(s.namespace) OPERATOR(pg_catalog.<=) 256)
        AND (s.command_type IS NOT NULL AND pg_catalog.octet_length(s.command_type) OPERATOR(pg_catalog.<=) 256)
        AND (s.schema_version_decimal IS NOT NULL AND pg_catalog.octet_length(s.schema_version_decimal) OPERATOR(pg_catalog.<=) 4096)
        AND (s.scope_evidence IS NOT NULL AND pg_catalog.octet_length(s.scope_evidence) OPERATOR(pg_catalog.<=) 781)
        AND (s.scope_application IS NOT NULL AND pg_catalog.octet_length(s.scope_application) OPERATOR(pg_catalog.<=) 256)
        AND (s.scope_tenant IS NULL OR pg_catalog.octet_length(s.scope_tenant) OPERATOR(pg_catalog.<=) 256)
        AND (s.scope_owner IS NULL OR pg_catalog.octet_length(s.scope_owner) OPERATOR(pg_catalog.<=) 256)
        AND (s.idempotency_key IS NULL OR pg_catalog.octet_length(s.idempotency_key) OPERATOR(pg_catalog.<=) 256)
        AND (s.intent_evidence IS NOT NULL AND pg_catalog.octet_length(s.intent_evidence) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.semantic_input IS NOT NULL AND pg_catalog.octet_length(s.semantic_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.replay_input IS NOT NULL AND pg_catalog.octet_length(s.replay_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_binding IS NOT NULL AND pg_catalog.octet_length(s.protected_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.replay_policy IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.replay_policy, 'UTF8')) OPERATOR(pg_catalog.<=) 16)
        AND (s.state IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.state, 'UTF8')) OPERATOR(pg_catalog.<=) 14)
        AND (s.result IS NULL OR pg_catalog.octet_length(s.result) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.success_origin IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.success_origin, 'UTF8')) OPERATOR(pg_catalog.<=) 10)
        AND (s.completion_result_digest IS NULL OR pg_catalog.octet_length(s.completion_result_digest) OPERATOR(pg_catalog.<=) 32)
        AND (s.resolution_record_operation_kind IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_operation_kind, 'UTF8')) OPERATOR(pg_catalog.<=) 14)
        AND (s.resolution_record_outcome IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_outcome, 'UTF8')) OPERATOR(pg_catalog.<=) 19)
        AND (s.resolution_record_result IS NULL OR pg_catalog.octet_length(s.resolution_record_result) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.resolution_record_result_digest IS NULL OR pg_catalog.octet_length(s.resolution_record_result_digest) OPERATOR(pg_catalog.<=) 32)
        AND (s.resolution_record_reason IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_reason, 'UTF8')) OPERATOR(pg_catalog.<=) 256)
        AND (s.resolution_record_evidence IS NULL OR pg_catalog.octet_length(s.resolution_record_evidence) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.resolution_record_binding IS NULL OR pg_catalog.octet_length(s.resolution_record_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.job_application IS NOT NULL AND pg_catalog.octet_length(s.job_application) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_tenant IS NULL OR pg_catalog.octet_length(s.job_tenant) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_owner IS NULL OR pg_catalog.octet_length(s.job_owner) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_protected_binding IS NOT NULL AND pg_catalog.octet_length(s.job_protected_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.job_semantic_input IS NOT NULL AND pg_catalog.octet_length(s.job_semantic_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.material_state IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.material_state, 'UTF8')) OPERATOR(pg_catalog.<=) 7)
        AND (s.protected_sidecar IS NULL OR pg_catalog.octet_length(s.protected_sidecar) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_reference IS NULL OR pg_catalog.octet_length(s.protected_reference) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_codec IS NULL OR pg_catalog.octet_length(s.protected_codec) OPERATOR(pg_catalog.<=) 256)
        AND (s.protected_key_version IS NULL OR pg_catalog.octet_length(s.protected_key_version) OPERATOR(pg_catalog.<=) 256)
        AND (s.protected_recovery_metadata IS NOT NULL AND pg_catalog.octet_length(s.protected_recovery_metadata) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_cleanup_policy IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.protected_cleanup_policy, 'UTF8')) OPERATOR(pg_catalog.<=) 20)
        AND (s.projection_metadata IS NOT NULL AND pg_catalog.octet_length(s.projection_metadata) OPERATOR(pg_catalog.<=) 1048576)
"""
_JOB_RESULT_PROJECTION = b"""SELECT c.cap_ok,
       c.work_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.kind, 'UTF8') ELSE NULL::pg_catalog.bytea END AS kind,
       CASE WHEN c.cap_ok THEN c.subscription_id ELSE NULL::pg_catalog.bytea END AS subscription_id,
       CASE WHEN c.cap_ok THEN c.namespace ELSE NULL::pg_catalog.bytea END AS namespace,
       CASE WHEN c.cap_ok THEN c.command_type ELSE NULL::pg_catalog.bytea END AS command_type,
       CASE WHEN c.cap_ok THEN c.schema_version_decimal ELSE NULL::pg_catalog.bytea END AS schema_version_decimal,
       c.runnable_version,
       c.canonical_version,
       CASE WHEN c.cap_ok THEN c.scope_evidence ELSE NULL::pg_catalog.bytea END AS scope_evidence,
       CASE WHEN c.cap_ok THEN c.scope_application ELSE NULL::pg_catalog.bytea END AS scope_application,
       CASE WHEN c.cap_ok THEN c.scope_tenant ELSE NULL::pg_catalog.bytea END AS scope_tenant,
       CASE WHEN c.cap_ok THEN c.scope_owner ELSE NULL::pg_catalog.bytea END AS scope_owner,
       CASE WHEN c.cap_ok THEN c.idempotency_key ELSE NULL::pg_catalog.bytea END AS idempotency_key,
       CASE WHEN c.cap_ok THEN c.intent_evidence ELSE NULL::pg_catalog.bytea END AS intent_evidence,
       CASE WHEN c.cap_ok THEN c.semantic_input ELSE NULL::pg_catalog.bytea END AS semantic_input,
       CASE WHEN c.cap_ok THEN c.replay_input ELSE NULL::pg_catalog.bytea END AS replay_input,
       CASE WHEN c.cap_ok THEN c.protected_binding ELSE NULL::pg_catalog.bytea END AS protected_binding,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.replay_policy, 'UTF8') ELSE NULL::pg_catalog.bytea END AS replay_policy,
       c.max_attempts,
       c.deadline,
       c.original_available_at,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS state,
       c.cancellation_requested,
       c.token,
       c.ownership_revision,
       c.lease_until,
       c.available_at,
       c.cycle,
       c.attempt_count,
       c.dispatch_id,
       CASE WHEN c.cap_ok THEN c.result ELSE NULL::pg_catalog.bytea END AS result,
       c.created_at,
       c.updated_at,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.success_origin, 'UTF8') ELSE NULL::pg_catalog.bytea END AS success_origin,
       c.completion_guard_id,
       c.final_fence_at,
       CASE WHEN c.cap_ok THEN c.completion_result_digest ELSE NULL::pg_catalog.bytea END AS completion_result_digest,
       c.resolution_operation_id,
       c.terminal_resolution_operation_id,
       c.resolution_present,
       c.resolution_record_operation_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_operation_kind, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_operation_kind,
       c.resolution_record_work_id,
       c.resolution_record_expected_revision,
       c.resolution_record_cycle,
       c.resolution_record_attempt,
       c.resolution_record_dispatch_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_outcome, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_outcome,
       c.resolution_record_retry_at,
       CASE WHEN c.cap_ok THEN c.resolution_record_result ELSE NULL::pg_catalog.bytea END AS resolution_record_result,
       CASE WHEN c.cap_ok THEN c.resolution_record_result_digest ELSE NULL::pg_catalog.bytea END AS resolution_record_result_digest,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_reason, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_reason,
       CASE WHEN c.cap_ok THEN c.resolution_record_evidence ELSE NULL::pg_catalog.bytea END AS resolution_record_evidence,
       CASE WHEN c.cap_ok THEN c.resolution_record_binding ELSE NULL::pg_catalog.bytea END AS resolution_record_binding,
       c.resolution_record_resolution_root_xid,
       c.resolution_record_recorded_at,
       c.job_work_id,
       CASE WHEN c.cap_ok THEN c.job_application ELSE NULL::pg_catalog.bytea END AS job_application,
       CASE WHEN c.cap_ok THEN c.job_tenant ELSE NULL::pg_catalog.bytea END AS job_tenant,
       CASE WHEN c.cap_ok THEN c.job_owner ELSE NULL::pg_catalog.bytea END AS job_owner,
       CASE WHEN c.cap_ok THEN c.job_protected_binding ELSE NULL::pg_catalog.bytea END AS job_protected_binding,
       CASE WHEN c.cap_ok THEN c.job_semantic_input ELSE NULL::pg_catalog.bytea END AS job_semantic_input,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.material_state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS material_state,
       CASE WHEN c.cap_ok THEN c.protected_sidecar ELSE NULL::pg_catalog.bytea END AS protected_sidecar,
       CASE WHEN c.cap_ok THEN c.protected_reference ELSE NULL::pg_catalog.bytea END AS protected_reference,
       CASE WHEN c.cap_ok THEN c.protected_codec ELSE NULL::pg_catalog.bytea END AS protected_codec,
       CASE WHEN c.cap_ok THEN c.protected_key_version ELSE NULL::pg_catalog.bytea END AS protected_key_version,
       c.protected_expires_at,
       CASE WHEN c.cap_ok THEN c.protected_recovery_metadata ELSE NULL::pg_catalog.bytea END AS protected_recovery_metadata,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.protected_cleanup_policy, 'UTF8') ELSE NULL::pg_catalog.bytea END AS protected_cleanup_policy,
       CASE WHEN c.cap_ok THEN c.projection_metadata ELSE NULL::pg_catalog.bytea END AS projection_metadata
FROM checked AS c
"""
_W02_SQL = (
    b"WITH source AS MATERIALIZED (\n"
    + _JOB_SOURCE_PROJECTION
    + b"\n    FROM modkit_workers.w02($1::pg_catalog.uuid) AS s\n"
    b"), checked AS (\n    SELECT s.*, (\n"
    + _JOB_CAP_PREDICATE
    + b"    ) IS TRUE AS cap_ok\n    FROM source AS s\n)\n"
    + _JOB_RESULT_PROJECTION
    + b"LIMIT 2"
)
_W03_SQL = (
    b"WITH source AS MATERIALIZED (\n"
    + _JOB_SOURCE_PROJECTION
    + b"\n    FROM modkit_workers.w03($1::pg_catalog.bytea, "
    b"$2::pg_catalog.timestamptz, $3::pg_catalog.uuid, "
    b"$4::pg_catalog.int4, $5::pg_catalog.int8) AS s\n"
    b"    LIMIT ($4::pg_catalog.int4 + 1)\n"
    b"), checked AS (\n    SELECT s.*, (\n"
    + _JOB_CAP_PREDICATE
    + b"""        AND (
            pg_catalog.sum(
                COALESCE(pg_catalog.octet_length(s.intent_evidence)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.semantic_input)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.replay_input)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_binding)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.result)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.resolution_record_result)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.resolution_record_evidence)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.resolution_record_binding)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.job_protected_binding)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.job_semantic_input)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_sidecar)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_reference)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_recovery_metadata)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.projection_metadata)::pg_catalog.int8, 0::pg_catalog.int8)
            ) OVER () OPERATOR(pg_catalog.<=) $5::pg_catalog.int8::pg_catalog.numeric
        )
    ) IS TRUE AS cap_ok
    FROM source AS s
)
"""
    + _JOB_RESULT_PROJECTION
    + b"ORDER BY c.created_at, c.work_id\nLIMIT ($4::pg_catalog.int4 + 1)"
)

# W04 permits an inbox collision with an absent, all-null job half.
_W04_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.work_id, s.kind, s.subscription_id, s.namespace, s.command_type, s.schema_version_decimal, s.runnable_version, s.canonical_version, s.scope_evidence, s.scope_application, s.scope_tenant, s.scope_owner, s.idempotency_key, s.intent_evidence, s.semantic_input, s.replay_input, s.protected_binding, s.replay_policy, s.max_attempts, s.deadline, s.original_available_at, s.state, s.cancellation_requested, s.token, s.ownership_revision, s.lease_until, s.available_at, s.cycle, s.attempt_count, s.dispatch_id, s.result, s.created_at, s.updated_at, s.success_origin, s.completion_guard_id, s.final_fence_at, s.completion_result_digest, s.resolution_operation_id, s.terminal_resolution_operation_id, s.resolution_present, s.resolution_record_operation_id, s.resolution_record_operation_kind, s.resolution_record_work_id, s.resolution_record_expected_revision, s.resolution_record_cycle, s.resolution_record_attempt, s.resolution_record_dispatch_id, s.resolution_record_outcome, s.resolution_record_retry_at, s.resolution_record_result, s.resolution_record_result_digest, s.resolution_record_reason, s.resolution_record_evidence, s.resolution_record_binding, s.resolution_record_resolution_root_xid, s.resolution_record_recorded_at, s.job_half_present, s.job_work_id, s.job_application, s.job_tenant, s.job_owner, s.job_protected_binding, s.job_semantic_input, s.material_state, s.protected_sidecar, s.protected_reference, s.protected_codec, s.protected_key_version, s.protected_expires_at, s.protected_recovery_metadata, s.protected_cleanup_policy, s.projection_metadata
    FROM modkit_workers.w04($1::pg_catalog.uuid, $2::pg_catalog.text, $3::pg_catalog.bytea, $4::pg_catalog.bytea, $5::pg_catalog.bytea, $6::pg_catalog.bytea, $7::pg_catalog.bytea) AS s
), checked AS (
    SELECT s.*, (
        (s.kind IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.kind, 'UTF8')) OPERATOR(pg_catalog.<=) 5)
        AND (s.subscription_id IS NULL OR pg_catalog.octet_length(s.subscription_id) OPERATOR(pg_catalog.<=) 256)
        AND (s.namespace IS NOT NULL AND pg_catalog.octet_length(s.namespace) OPERATOR(pg_catalog.<=) 256)
        AND (s.command_type IS NOT NULL AND pg_catalog.octet_length(s.command_type) OPERATOR(pg_catalog.<=) 256)
        AND (s.schema_version_decimal IS NOT NULL AND pg_catalog.octet_length(s.schema_version_decimal) OPERATOR(pg_catalog.<=) 4096)
        AND (s.scope_evidence IS NOT NULL AND pg_catalog.octet_length(s.scope_evidence) OPERATOR(pg_catalog.<=) 781)
        AND (s.scope_application IS NOT NULL AND pg_catalog.octet_length(s.scope_application) OPERATOR(pg_catalog.<=) 256)
        AND (s.scope_tenant IS NULL OR pg_catalog.octet_length(s.scope_tenant) OPERATOR(pg_catalog.<=) 256)
        AND (s.scope_owner IS NULL OR pg_catalog.octet_length(s.scope_owner) OPERATOR(pg_catalog.<=) 256)
        AND (s.idempotency_key IS NULL OR pg_catalog.octet_length(s.idempotency_key) OPERATOR(pg_catalog.<=) 256)
        AND (s.intent_evidence IS NOT NULL AND pg_catalog.octet_length(s.intent_evidence) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.semantic_input IS NOT NULL AND pg_catalog.octet_length(s.semantic_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.replay_input IS NOT NULL AND pg_catalog.octet_length(s.replay_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_binding IS NOT NULL AND pg_catalog.octet_length(s.protected_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.replay_policy IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.replay_policy, 'UTF8')) OPERATOR(pg_catalog.<=) 16)
        AND (s.state IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.state, 'UTF8')) OPERATOR(pg_catalog.<=) 14)
        AND (s.result IS NULL OR pg_catalog.octet_length(s.result) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.success_origin IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.success_origin, 'UTF8')) OPERATOR(pg_catalog.<=) 10)
        AND (s.completion_result_digest IS NULL OR pg_catalog.octet_length(s.completion_result_digest) OPERATOR(pg_catalog.<=) 32)
        AND (s.resolution_record_operation_kind IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_operation_kind, 'UTF8')) OPERATOR(pg_catalog.<=) 14)
        AND (s.resolution_record_outcome IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_outcome, 'UTF8')) OPERATOR(pg_catalog.<=) 19)
        AND (s.resolution_record_result IS NULL OR pg_catalog.octet_length(s.resolution_record_result) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.resolution_record_result_digest IS NULL OR pg_catalog.octet_length(s.resolution_record_result_digest) OPERATOR(pg_catalog.<=) 32)
        AND (s.resolution_record_reason IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_reason, 'UTF8')) OPERATOR(pg_catalog.<=) 256)
        AND (s.resolution_record_evidence IS NULL OR pg_catalog.octet_length(s.resolution_record_evidence) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.resolution_record_binding IS NULL OR pg_catalog.octet_length(s.resolution_record_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.job_application IS NULL OR pg_catalog.octet_length(s.job_application) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_tenant IS NULL OR pg_catalog.octet_length(s.job_tenant) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_owner IS NULL OR pg_catalog.octet_length(s.job_owner) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_protected_binding IS NULL OR pg_catalog.octet_length(s.job_protected_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.job_semantic_input IS NULL OR pg_catalog.octet_length(s.job_semantic_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.material_state IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.material_state, 'UTF8')) OPERATOR(pg_catalog.<=) 7)
        AND (s.protected_sidecar IS NULL OR pg_catalog.octet_length(s.protected_sidecar) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_reference IS NULL OR pg_catalog.octet_length(s.protected_reference) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_codec IS NULL OR pg_catalog.octet_length(s.protected_codec) OPERATOR(pg_catalog.<=) 256)
        AND (s.protected_key_version IS NULL OR pg_catalog.octet_length(s.protected_key_version) OPERATOR(pg_catalog.<=) 256)
        AND (s.protected_recovery_metadata IS NULL OR pg_catalog.octet_length(s.protected_recovery_metadata) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_cleanup_policy IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.protected_cleanup_policy, 'UTF8')) OPERATOR(pg_catalog.<=) 20)
        AND (s.projection_metadata IS NULL OR pg_catalog.octet_length(s.projection_metadata) OPERATOR(pg_catalog.<=) 1048576)
    ) IS TRUE AS cap_ok
    FROM source AS s
)
SELECT c.cap_ok,
       c.work_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.kind, 'UTF8') ELSE NULL::pg_catalog.bytea END AS kind,
       CASE WHEN c.cap_ok THEN c.subscription_id ELSE NULL::pg_catalog.bytea END AS subscription_id,
       CASE WHEN c.cap_ok THEN c.namespace ELSE NULL::pg_catalog.bytea END AS namespace,
       CASE WHEN c.cap_ok THEN c.command_type ELSE NULL::pg_catalog.bytea END AS command_type,
       CASE WHEN c.cap_ok THEN c.schema_version_decimal ELSE NULL::pg_catalog.bytea END AS schema_version_decimal,
       c.runnable_version,
       c.canonical_version,
       CASE WHEN c.cap_ok THEN c.scope_evidence ELSE NULL::pg_catalog.bytea END AS scope_evidence,
       CASE WHEN c.cap_ok THEN c.scope_application ELSE NULL::pg_catalog.bytea END AS scope_application,
       CASE WHEN c.cap_ok THEN c.scope_tenant ELSE NULL::pg_catalog.bytea END AS scope_tenant,
       CASE WHEN c.cap_ok THEN c.scope_owner ELSE NULL::pg_catalog.bytea END AS scope_owner,
       CASE WHEN c.cap_ok THEN c.idempotency_key ELSE NULL::pg_catalog.bytea END AS idempotency_key,
       CASE WHEN c.cap_ok THEN c.intent_evidence ELSE NULL::pg_catalog.bytea END AS intent_evidence,
       CASE WHEN c.cap_ok THEN c.semantic_input ELSE NULL::pg_catalog.bytea END AS semantic_input,
       CASE WHEN c.cap_ok THEN c.replay_input ELSE NULL::pg_catalog.bytea END AS replay_input,
       CASE WHEN c.cap_ok THEN c.protected_binding ELSE NULL::pg_catalog.bytea END AS protected_binding,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.replay_policy, 'UTF8') ELSE NULL::pg_catalog.bytea END AS replay_policy,
       c.max_attempts,
       c.deadline,
       c.original_available_at,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS state,
       c.cancellation_requested,
       c.token,
       c.ownership_revision,
       c.lease_until,
       c.available_at,
       c.cycle,
       c.attempt_count,
       c.dispatch_id,
       CASE WHEN c.cap_ok THEN c.result ELSE NULL::pg_catalog.bytea END AS result,
       c.created_at,
       c.updated_at,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.success_origin, 'UTF8') ELSE NULL::pg_catalog.bytea END AS success_origin,
       c.completion_guard_id,
       c.final_fence_at,
       CASE WHEN c.cap_ok THEN c.completion_result_digest ELSE NULL::pg_catalog.bytea END AS completion_result_digest,
       c.resolution_operation_id,
       c.terminal_resolution_operation_id,
       c.resolution_present,
       c.resolution_record_operation_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_operation_kind, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_operation_kind,
       c.resolution_record_work_id,
       c.resolution_record_expected_revision,
       c.resolution_record_cycle,
       c.resolution_record_attempt,
       c.resolution_record_dispatch_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_outcome, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_outcome,
       c.resolution_record_retry_at,
       CASE WHEN c.cap_ok THEN c.resolution_record_result ELSE NULL::pg_catalog.bytea END AS resolution_record_result,
       CASE WHEN c.cap_ok THEN c.resolution_record_result_digest ELSE NULL::pg_catalog.bytea END AS resolution_record_result_digest,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_reason, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_reason,
       CASE WHEN c.cap_ok THEN c.resolution_record_evidence ELSE NULL::pg_catalog.bytea END AS resolution_record_evidence,
       CASE WHEN c.cap_ok THEN c.resolution_record_binding ELSE NULL::pg_catalog.bytea END AS resolution_record_binding,
       c.resolution_record_resolution_root_xid,
       c.resolution_record_recorded_at,
       c.job_half_present,
       c.job_work_id,
       CASE WHEN c.cap_ok THEN c.job_application ELSE NULL::pg_catalog.bytea END AS job_application,
       CASE WHEN c.cap_ok THEN c.job_tenant ELSE NULL::pg_catalog.bytea END AS job_tenant,
       CASE WHEN c.cap_ok THEN c.job_owner ELSE NULL::pg_catalog.bytea END AS job_owner,
       CASE WHEN c.cap_ok THEN c.job_protected_binding ELSE NULL::pg_catalog.bytea END AS job_protected_binding,
       CASE WHEN c.cap_ok THEN c.job_semantic_input ELSE NULL::pg_catalog.bytea END AS job_semantic_input,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.material_state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS material_state,
       CASE WHEN c.cap_ok THEN c.protected_sidecar ELSE NULL::pg_catalog.bytea END AS protected_sidecar,
       CASE WHEN c.cap_ok THEN c.protected_reference ELSE NULL::pg_catalog.bytea END AS protected_reference,
       CASE WHEN c.cap_ok THEN c.protected_codec ELSE NULL::pg_catalog.bytea END AS protected_codec,
       CASE WHEN c.cap_ok THEN c.protected_key_version ELSE NULL::pg_catalog.bytea END AS protected_key_version,
       c.protected_expires_at,
       CASE WHEN c.cap_ok THEN c.protected_recovery_metadata ELSE NULL::pg_catalog.bytea END AS protected_recovery_metadata,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.protected_cleanup_policy, 'UTF8') ELSE NULL::pg_catalog.bytea END AS protected_cleanup_policy,
       CASE WHEN c.cap_ok THEN c.projection_metadata ELSE NULL::pg_catalog.bytea END AS projection_metadata
FROM checked AS c
ORDER BY c.work_id
LIMIT 3"""

_W01_CASTS = (
    "pg_catalog.uuid",
    "pg_catalog.text",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.int4",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.text",
    "pg_catalog.int4",
    "pg_catalog.timestamptz",
    "pg_catalog.timestamptz",
    "pg_catalog.text",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.bytea",
    "pg_catalog.timestamptz",
    "pg_catalog.bytea",
    "pg_catalog.text",
    "pg_catalog.bytea",
)

_W01_COLUMNS = (
    _TransportColumn(
        name="cap_ok", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
    ),
    _TransportColumn(
        name="work_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="inserted", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
    ),
)

_W02_COLUMNS = (
    _TransportColumn(
        name="cap_ok", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
    ),
    _TransportColumn(
        name="work_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="kind", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=3
    ),
    _TransportColumn(
        name="subscription_id",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="namespace", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=256
    ),
    _TransportColumn(
        name="command_type", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=256
    ),
    _TransportColumn(
        name="schema_version_decimal",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=4096,
    ),
    _TransportColumn(
        name="runnable_version", wire_type=WireType.INT4, oid=23, nullable=True, max_payload_bytes=4
    ),
    _TransportColumn(
        name="canonical_version",
        wire_type=WireType.INT4,
        oid=23,
        nullable=False,
        max_payload_bytes=4,
    ),
    _TransportColumn(
        name="scope_evidence",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=781,
    ),
    _TransportColumn(
        name="scope_application",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="scope_tenant", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=256
    ),
    _TransportColumn(
        name="scope_owner", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=256
    ),
    _TransportColumn(
        name="idempotency_key",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="intent_evidence",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="semantic_input",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="replay_input",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="protected_binding",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="replay_policy", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="max_attempts", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
    _TransportColumn(
        name="deadline",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="original_available_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="state", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=14
    ),
    _TransportColumn(
        name="cancellation_requested",
        wire_type=WireType.BOOL,
        oid=16,
        nullable=False,
        max_payload_bytes=1,
    ),
    _TransportColumn(
        name="token", wire_type=WireType.UUID, oid=2950, nullable=True, max_payload_bytes=16
    ),
    _TransportColumn(
        name="ownership_revision",
        wire_type=WireType.INT8,
        oid=20,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="lease_until",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="available_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="cycle", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
    _TransportColumn(
        name="attempt_count", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
    _TransportColumn(
        name="dispatch_id", wire_type=WireType.UUID, oid=2950, nullable=True, max_payload_bytes=16
    ),
    _TransportColumn(
        name="result", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=1048576
    ),
    _TransportColumn(
        name="created_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="updated_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="success_origin", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=10
    ),
    _TransportColumn(
        name="completion_guard_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="final_fence_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="completion_result_digest",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=32,
    ),
    _TransportColumn(
        name="resolution_operation_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="terminal_resolution_operation_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="resolution_present",
        wire_type=WireType.BOOL,
        oid=16,
        nullable=False,
        max_payload_bytes=1,
    ),
    _TransportColumn(
        name="resolution_record_operation_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="resolution_record_operation_kind",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=14,
    ),
    _TransportColumn(
        name="resolution_record_work_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="resolution_record_expected_revision",
        wire_type=WireType.INT8,
        oid=20,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="resolution_record_cycle",
        wire_type=WireType.INT4,
        oid=23,
        nullable=True,
        max_payload_bytes=4,
    ),
    _TransportColumn(
        name="resolution_record_attempt",
        wire_type=WireType.INT4,
        oid=23,
        nullable=True,
        max_payload_bytes=4,
    ),
    _TransportColumn(
        name="resolution_record_dispatch_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="resolution_record_outcome",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=19,
    ),
    _TransportColumn(
        name="resolution_record_retry_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="resolution_record_result",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="resolution_record_result_digest",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=32,
    ),
    _TransportColumn(
        name="resolution_record_reason",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="resolution_record_evidence",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="resolution_record_binding",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="resolution_record_resolution_root_xid",
        wire_type=WireType.XID8,
        oid=5069,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="resolution_record_recorded_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="job_work_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="job_application",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="job_tenant", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=256
    ),
    _TransportColumn(
        name="job_owner", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=256
    ),
    _TransportColumn(
        name="job_protected_binding",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="job_semantic_input",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="material_state", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=7
    ),
    _TransportColumn(
        name="protected_sidecar",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="protected_reference",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="protected_codec",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="protected_key_version",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="protected_expires_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="protected_recovery_metadata",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="protected_cleanup_policy",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=20,
    ),
    _TransportColumn(
        name="projection_metadata",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
)


_W04_COLUMNS = (
    _TransportColumn(
        name="cap_ok", wire_type=WireType.BOOL, oid=16, nullable=False, max_payload_bytes=1
    ),
    _TransportColumn(
        name="work_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="kind", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=5
    ),
    _TransportColumn(
        name="subscription_id",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="namespace", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=256
    ),
    _TransportColumn(
        name="command_type", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=256
    ),
    _TransportColumn(
        name="schema_version_decimal",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=4096,
    ),
    _TransportColumn(
        name="runnable_version", wire_type=WireType.INT4, oid=23, nullable=True, max_payload_bytes=4
    ),
    _TransportColumn(
        name="canonical_version",
        wire_type=WireType.INT4,
        oid=23,
        nullable=False,
        max_payload_bytes=4,
    ),
    _TransportColumn(
        name="scope_evidence",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=781,
    ),
    _TransportColumn(
        name="scope_application",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="scope_tenant", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=256
    ),
    _TransportColumn(
        name="scope_owner", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=256
    ),
    _TransportColumn(
        name="idempotency_key",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="intent_evidence",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="semantic_input",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="replay_input",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="protected_binding",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=False,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="replay_policy", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=16
    ),
    _TransportColumn(
        name="max_attempts", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
    _TransportColumn(
        name="deadline",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="original_available_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="state", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=14
    ),
    _TransportColumn(
        name="cancellation_requested",
        wire_type=WireType.BOOL,
        oid=16,
        nullable=False,
        max_payload_bytes=1,
    ),
    _TransportColumn(
        name="token", wire_type=WireType.UUID, oid=2950, nullable=True, max_payload_bytes=16
    ),
    _TransportColumn(
        name="ownership_revision",
        wire_type=WireType.INT8,
        oid=20,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="lease_until",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="available_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="cycle", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
    _TransportColumn(
        name="attempt_count", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4
    ),
    _TransportColumn(
        name="dispatch_id", wire_type=WireType.UUID, oid=2950, nullable=True, max_payload_bytes=16
    ),
    _TransportColumn(
        name="result", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=1048576
    ),
    _TransportColumn(
        name="created_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="updated_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=False,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="success_origin", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=10
    ),
    _TransportColumn(
        name="completion_guard_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="final_fence_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="completion_result_digest",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=32,
    ),
    _TransportColumn(
        name="resolution_operation_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="terminal_resolution_operation_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="resolution_present",
        wire_type=WireType.BOOL,
        oid=16,
        nullable=False,
        max_payload_bytes=1,
    ),
    _TransportColumn(
        name="resolution_record_operation_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="resolution_record_operation_kind",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=14,
    ),
    _TransportColumn(
        name="resolution_record_work_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="resolution_record_expected_revision",
        wire_type=WireType.INT8,
        oid=20,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="resolution_record_cycle",
        wire_type=WireType.INT4,
        oid=23,
        nullable=True,
        max_payload_bytes=4,
    ),
    _TransportColumn(
        name="resolution_record_attempt",
        wire_type=WireType.INT4,
        oid=23,
        nullable=True,
        max_payload_bytes=4,
    ),
    _TransportColumn(
        name="resolution_record_dispatch_id",
        wire_type=WireType.UUID,
        oid=2950,
        nullable=True,
        max_payload_bytes=16,
    ),
    _TransportColumn(
        name="resolution_record_outcome",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=19,
    ),
    _TransportColumn(
        name="resolution_record_retry_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="resolution_record_result",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="resolution_record_result_digest",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=32,
    ),
    _TransportColumn(
        name="resolution_record_reason",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="resolution_record_evidence",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="resolution_record_binding",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="resolution_record_resolution_root_xid",
        wire_type=WireType.XID8,
        oid=5069,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="resolution_record_recorded_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="job_half_present",
        wire_type=WireType.BOOL,
        oid=16,
        nullable=False,
        max_payload_bytes=1,
    ),
    _TransportColumn(
        name="job_work_id", wire_type=WireType.UUID, oid=2950, nullable=True, max_payload_bytes=16
    ),
    _TransportColumn(
        name="job_application",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="job_tenant", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=256
    ),
    _TransportColumn(
        name="job_owner", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=256
    ),
    _TransportColumn(
        name="job_protected_binding",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="job_semantic_input",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="material_state", wire_type=WireType.BYTEA, oid=17, nullable=True, max_payload_bytes=7
    ),
    _TransportColumn(
        name="protected_sidecar",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="protected_reference",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="protected_codec",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="protected_key_version",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=256,
    ),
    _TransportColumn(
        name="protected_expires_at",
        wire_type=WireType.TIMESTAMPTZ,
        oid=1184,
        nullable=True,
        max_payload_bytes=8,
    ),
    _TransportColumn(
        name="protected_recovery_metadata",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
    _TransportColumn(
        name="protected_cleanup_policy",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=20,
    ),
    _TransportColumn(
        name="projection_metadata",
        wire_type=WireType.BYTEA,
        oid=17,
        nullable=True,
        max_payload_bytes=1048576,
    ),
)


# Fixed bounded acquisition transport; original source order is checked before sorting.
_W05_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.*
    FROM modkit_workers.w05($1::pg_catalog.bytea, $2::pg_catalog.bytea[], $3::pg_catalog.int4[], $4::pg_catalog.int4, $5::pg_catalog.float8, $6::pg_catalog.uuid, $7::pg_catalog.int4, $8::pg_catalog.int8)
    WITH ORDINALITY AS s(record_type, visited, next_cursor, pass_exhausted, work_id, kind, subscription_id, namespace, command_type, schema_version_decimal, runnable_version, canonical_version, scope_evidence, scope_application, scope_tenant, scope_owner, idempotency_key, intent_evidence, semantic_input, replay_input, protected_binding, replay_policy, max_attempts, deadline, original_available_at, state, cancellation_requested, token, ownership_revision, lease_until, available_at, cycle, attempt_count, dispatch_id, result, created_at, updated_at, success_origin, completion_guard_id, final_fence_at, completion_result_digest, resolution_operation_id, terminal_resolution_operation_id, resolution_present, resolution_record_operation_id, resolution_record_operation_kind, resolution_record_work_id, resolution_record_expected_revision, resolution_record_cycle, resolution_record_attempt, resolution_record_dispatch_id, resolution_record_outcome, resolution_record_retry_at, resolution_record_result, resolution_record_result_digest, resolution_record_reason, resolution_record_evidence, resolution_record_binding, resolution_record_resolution_root_xid, resolution_record_recorded_at, job_work_id, job_application, job_tenant, job_owner, job_protected_binding, job_semantic_input, material_state, protected_sidecar, protected_reference, protected_codec, protected_key_version, protected_expires_at, protected_recovery_metadata, protected_cleanup_policy, projection_metadata, source_ordinal)
    LIMIT ($4::pg_catalog.int4 + 2)
), ordered AS (
    SELECT s.*, pg_catalog.lag(s.work_id) OVER (ORDER BY s.source_ordinal) AS previous_work_id
    FROM source AS s
), framed AS (
    SELECT s.*, (
        (s.record_type OPERATOR(pg_catalog.=) 'header'
            AND s.source_ordinal OPERATOR(pg_catalog.=) 1
            AND s.visited IS NOT NULL AND s.pass_exhausted IS NOT NULL
            AND s.work_id IS NULL
                AND s.kind IS NULL
                AND s.subscription_id IS NULL
                AND s.namespace IS NULL
                AND s.command_type IS NULL
                AND s.schema_version_decimal IS NULL
                AND s.runnable_version IS NULL
                AND s.canonical_version IS NULL
                AND s.scope_evidence IS NULL
                AND s.scope_application IS NULL
                AND s.scope_tenant IS NULL
                AND s.scope_owner IS NULL
                AND s.idempotency_key IS NULL
                AND s.intent_evidence IS NULL
                AND s.semantic_input IS NULL
                AND s.replay_input IS NULL
                AND s.protected_binding IS NULL
                AND s.replay_policy IS NULL
                AND s.max_attempts IS NULL
                AND s.deadline IS NULL
                AND s.original_available_at IS NULL
                AND s.state IS NULL
                AND s.cancellation_requested IS NULL
                AND s.token IS NULL
                AND s.ownership_revision IS NULL
                AND s.lease_until IS NULL
                AND s.available_at IS NULL
                AND s.cycle IS NULL
                AND s.attempt_count IS NULL
                AND s.dispatch_id IS NULL
                AND s.result IS NULL
                AND s.created_at IS NULL
                AND s.updated_at IS NULL
                AND s.success_origin IS NULL
                AND s.completion_guard_id IS NULL
                AND s.final_fence_at IS NULL
                AND s.completion_result_digest IS NULL
                AND s.resolution_operation_id IS NULL
                AND s.terminal_resolution_operation_id IS NULL
                AND s.resolution_present IS NULL
                AND s.resolution_record_operation_id IS NULL
                AND s.resolution_record_operation_kind IS NULL
                AND s.resolution_record_work_id IS NULL
                AND s.resolution_record_expected_revision IS NULL
                AND s.resolution_record_cycle IS NULL
                AND s.resolution_record_attempt IS NULL
                AND s.resolution_record_dispatch_id IS NULL
                AND s.resolution_record_outcome IS NULL
                AND s.resolution_record_retry_at IS NULL
                AND s.resolution_record_result IS NULL
                AND s.resolution_record_result_digest IS NULL
                AND s.resolution_record_reason IS NULL
                AND s.resolution_record_evidence IS NULL
                AND s.resolution_record_binding IS NULL
                AND s.resolution_record_resolution_root_xid IS NULL
                AND s.resolution_record_recorded_at IS NULL
                AND s.job_work_id IS NULL
                AND s.job_application IS NULL
                AND s.job_tenant IS NULL
                AND s.job_owner IS NULL
                AND s.job_protected_binding IS NULL
                AND s.job_semantic_input IS NULL
                AND s.material_state IS NULL
                AND s.protected_sidecar IS NULL
                AND s.protected_reference IS NULL
                AND s.protected_codec IS NULL
                AND s.protected_key_version IS NULL
                AND s.protected_expires_at IS NULL
                AND s.protected_recovery_metadata IS NULL
                AND s.protected_cleanup_policy IS NULL
                AND s.projection_metadata IS NULL)
        OR (s.record_type OPERATOR(pg_catalog.=) 'item'
            AND s.source_ordinal OPERATOR(pg_catalog.>) 1
            AND s.visited IS NULL AND s.next_cursor IS NULL AND s.pass_exhausted IS NULL
            AND s.work_id IS NOT NULL
            AND (s.source_ordinal OPERATOR(pg_catalog.=) 2
                 OR s.work_id OPERATOR(pg_catalog.>) s.previous_work_id)
            AND (
        (s.kind IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.kind, 'UTF8')) OPERATOR(pg_catalog.<=) 3)
        AND (s.subscription_id IS NULL OR pg_catalog.octet_length(s.subscription_id) OPERATOR(pg_catalog.<=) 256)
        AND (s.namespace IS NOT NULL AND pg_catalog.octet_length(s.namespace) OPERATOR(pg_catalog.<=) 256)
        AND (s.command_type IS NOT NULL AND pg_catalog.octet_length(s.command_type) OPERATOR(pg_catalog.<=) 256)
        AND (s.schema_version_decimal IS NOT NULL AND pg_catalog.octet_length(s.schema_version_decimal) OPERATOR(pg_catalog.<=) 4096)
        AND (s.scope_evidence IS NOT NULL AND pg_catalog.octet_length(s.scope_evidence) OPERATOR(pg_catalog.<=) 781)
        AND (s.scope_application IS NOT NULL AND pg_catalog.octet_length(s.scope_application) OPERATOR(pg_catalog.<=) 256)
        AND (s.scope_tenant IS NULL OR pg_catalog.octet_length(s.scope_tenant) OPERATOR(pg_catalog.<=) 256)
        AND (s.scope_owner IS NULL OR pg_catalog.octet_length(s.scope_owner) OPERATOR(pg_catalog.<=) 256)
        AND (s.idempotency_key IS NULL OR pg_catalog.octet_length(s.idempotency_key) OPERATOR(pg_catalog.<=) 256)
        AND (s.intent_evidence IS NOT NULL AND pg_catalog.octet_length(s.intent_evidence) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.semantic_input IS NOT NULL AND pg_catalog.octet_length(s.semantic_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.replay_input IS NOT NULL AND pg_catalog.octet_length(s.replay_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_binding IS NOT NULL AND pg_catalog.octet_length(s.protected_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.replay_policy IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.replay_policy, 'UTF8')) OPERATOR(pg_catalog.<=) 16)
        AND (s.state IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.state, 'UTF8')) OPERATOR(pg_catalog.<=) 14)
        AND (s.result IS NULL OR pg_catalog.octet_length(s.result) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.success_origin IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.success_origin, 'UTF8')) OPERATOR(pg_catalog.<=) 10)
        AND (s.completion_result_digest IS NULL OR pg_catalog.octet_length(s.completion_result_digest) OPERATOR(pg_catalog.<=) 32)
        AND (s.resolution_record_operation_kind IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_operation_kind, 'UTF8')) OPERATOR(pg_catalog.<=) 14)
        AND (s.resolution_record_outcome IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_outcome, 'UTF8')) OPERATOR(pg_catalog.<=) 19)
        AND (s.resolution_record_result IS NULL OR pg_catalog.octet_length(s.resolution_record_result) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.resolution_record_result_digest IS NULL OR pg_catalog.octet_length(s.resolution_record_result_digest) OPERATOR(pg_catalog.<=) 32)
        AND (s.resolution_record_reason IS NULL OR pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_reason, 'UTF8')) OPERATOR(pg_catalog.<=) 256)
        AND (s.resolution_record_evidence IS NULL OR pg_catalog.octet_length(s.resolution_record_evidence) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.resolution_record_binding IS NULL OR pg_catalog.octet_length(s.resolution_record_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.job_application IS NOT NULL AND pg_catalog.octet_length(s.job_application) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_tenant IS NULL OR pg_catalog.octet_length(s.job_tenant) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_owner IS NULL OR pg_catalog.octet_length(s.job_owner) OPERATOR(pg_catalog.<=) 256)
        AND (s.job_protected_binding IS NOT NULL AND pg_catalog.octet_length(s.job_protected_binding) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.job_semantic_input IS NOT NULL AND pg_catalog.octet_length(s.job_semantic_input) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.material_state IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.material_state, 'UTF8')) OPERATOR(pg_catalog.<=) 7)
        AND (s.protected_sidecar IS NULL OR pg_catalog.octet_length(s.protected_sidecar) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_reference IS NULL OR pg_catalog.octet_length(s.protected_reference) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_codec IS NULL OR pg_catalog.octet_length(s.protected_codec) OPERATOR(pg_catalog.<=) 256)
        AND (s.protected_key_version IS NULL OR pg_catalog.octet_length(s.protected_key_version) OPERATOR(pg_catalog.<=) 256)
        AND (s.protected_recovery_metadata IS NOT NULL AND pg_catalog.octet_length(s.protected_recovery_metadata) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.protected_cleanup_policy IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.protected_cleanup_policy, 'UTF8')) OPERATOR(pg_catalog.<=) 20)
        AND (s.projection_metadata IS NOT NULL AND pg_catalog.octet_length(s.projection_metadata) OPERATOR(pg_catalog.<=) 1048576)
            ))
    ) IS TRUE AS frame_ok
    FROM ordered AS s
), checked AS (
    SELECT s.*, (
        pg_catalog.bool_and(s.frame_ok) OVER ()
        AND pg_catalog.count(*) OVER () OPERATOR(pg_catalog.<=) ($4::pg_catalog.int4 + 1)
        AND pg_catalog.count(*) FILTER (WHERE s.record_type OPERATOR(pg_catalog.=) 'header') OVER () OPERATOR(pg_catalog.=) 1
        AND pg_catalog.sum(
                COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.record_type, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.kind, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.subscription_id)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.namespace)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.command_type)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.schema_version_decimal)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.scope_evidence)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.scope_application)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.scope_tenant)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.scope_owner)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.idempotency_key)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.intent_evidence)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.semantic_input)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.replay_input)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_binding)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.replay_policy, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.state, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.result)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.success_origin, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.completion_result_digest)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_operation_kind, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_outcome, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.resolution_record_result)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.resolution_record_result_digest)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.resolution_record_reason, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.resolution_record_evidence)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.resolution_record_binding)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.job_application)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.job_tenant)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.job_owner)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.job_protected_binding)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.job_semantic_input)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.material_state, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_sidecar)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_reference)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_codec)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_key_version)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.protected_recovery_metadata)::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(pg_catalog.convert_to(s.protected_cleanup_policy, 'UTF8'))::pg_catalog.int8, 0::pg_catalog.int8)
                + COALESCE(pg_catalog.octet_length(s.projection_metadata)::pg_catalog.int8, 0::pg_catalog.int8)
        ) OVER () OPERATOR(pg_catalog.<=) $8::pg_catalog.int8::pg_catalog.numeric
    ) IS TRUE AS cap_ok
    FROM framed AS s
)
SELECT c.cap_ok,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.record_type, 'UTF8') ELSE NULL::pg_catalog.bytea END AS record_type,
       c.visited,
       c.next_cursor,
       c.pass_exhausted,
       c.work_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.kind, 'UTF8') ELSE NULL::pg_catalog.bytea END AS kind,
       CASE WHEN c.cap_ok THEN c.subscription_id ELSE NULL::pg_catalog.bytea END AS subscription_id,
       CASE WHEN c.cap_ok THEN c.namespace ELSE NULL::pg_catalog.bytea END AS namespace,
       CASE WHEN c.cap_ok THEN c.command_type ELSE NULL::pg_catalog.bytea END AS command_type,
       CASE WHEN c.cap_ok THEN c.schema_version_decimal ELSE NULL::pg_catalog.bytea END AS schema_version_decimal,
       c.runnable_version,
       c.canonical_version,
       CASE WHEN c.cap_ok THEN c.scope_evidence ELSE NULL::pg_catalog.bytea END AS scope_evidence,
       CASE WHEN c.cap_ok THEN c.scope_application ELSE NULL::pg_catalog.bytea END AS scope_application,
       CASE WHEN c.cap_ok THEN c.scope_tenant ELSE NULL::pg_catalog.bytea END AS scope_tenant,
       CASE WHEN c.cap_ok THEN c.scope_owner ELSE NULL::pg_catalog.bytea END AS scope_owner,
       CASE WHEN c.cap_ok THEN c.idempotency_key ELSE NULL::pg_catalog.bytea END AS idempotency_key,
       CASE WHEN c.cap_ok THEN c.intent_evidence ELSE NULL::pg_catalog.bytea END AS intent_evidence,
       CASE WHEN c.cap_ok THEN c.semantic_input ELSE NULL::pg_catalog.bytea END AS semantic_input,
       CASE WHEN c.cap_ok THEN c.replay_input ELSE NULL::pg_catalog.bytea END AS replay_input,
       CASE WHEN c.cap_ok THEN c.protected_binding ELSE NULL::pg_catalog.bytea END AS protected_binding,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.replay_policy, 'UTF8') ELSE NULL::pg_catalog.bytea END AS replay_policy,
       c.max_attempts,
       c.deadline,
       c.original_available_at,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS state,
       c.cancellation_requested,
       c.token,
       c.ownership_revision,
       c.lease_until,
       c.available_at,
       c.cycle,
       c.attempt_count,
       c.dispatch_id,
       CASE WHEN c.cap_ok THEN c.result ELSE NULL::pg_catalog.bytea END AS result,
       c.created_at,
       c.updated_at,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.success_origin, 'UTF8') ELSE NULL::pg_catalog.bytea END AS success_origin,
       c.completion_guard_id,
       c.final_fence_at,
       CASE WHEN c.cap_ok THEN c.completion_result_digest ELSE NULL::pg_catalog.bytea END AS completion_result_digest,
       c.resolution_operation_id,
       c.terminal_resolution_operation_id,
       c.resolution_present,
       c.resolution_record_operation_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_operation_kind, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_operation_kind,
       c.resolution_record_work_id,
       c.resolution_record_expected_revision,
       c.resolution_record_cycle,
       c.resolution_record_attempt,
       c.resolution_record_dispatch_id,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_outcome, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_outcome,
       c.resolution_record_retry_at,
       CASE WHEN c.cap_ok THEN c.resolution_record_result ELSE NULL::pg_catalog.bytea END AS resolution_record_result,
       CASE WHEN c.cap_ok THEN c.resolution_record_result_digest ELSE NULL::pg_catalog.bytea END AS resolution_record_result_digest,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.resolution_record_reason, 'UTF8') ELSE NULL::pg_catalog.bytea END AS resolution_record_reason,
       CASE WHEN c.cap_ok THEN c.resolution_record_evidence ELSE NULL::pg_catalog.bytea END AS resolution_record_evidence,
       CASE WHEN c.cap_ok THEN c.resolution_record_binding ELSE NULL::pg_catalog.bytea END AS resolution_record_binding,
       c.resolution_record_resolution_root_xid,
       c.resolution_record_recorded_at,
       c.job_work_id,
       CASE WHEN c.cap_ok THEN c.job_application ELSE NULL::pg_catalog.bytea END AS job_application,
       CASE WHEN c.cap_ok THEN c.job_tenant ELSE NULL::pg_catalog.bytea END AS job_tenant,
       CASE WHEN c.cap_ok THEN c.job_owner ELSE NULL::pg_catalog.bytea END AS job_owner,
       CASE WHEN c.cap_ok THEN c.job_protected_binding ELSE NULL::pg_catalog.bytea END AS job_protected_binding,
       CASE WHEN c.cap_ok THEN c.job_semantic_input ELSE NULL::pg_catalog.bytea END AS job_semantic_input,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.material_state, 'UTF8') ELSE NULL::pg_catalog.bytea END AS material_state,
       CASE WHEN c.cap_ok THEN c.protected_sidecar ELSE NULL::pg_catalog.bytea END AS protected_sidecar,
       CASE WHEN c.cap_ok THEN c.protected_reference ELSE NULL::pg_catalog.bytea END AS protected_reference,
       CASE WHEN c.cap_ok THEN c.protected_codec ELSE NULL::pg_catalog.bytea END AS protected_codec,
       CASE WHEN c.cap_ok THEN c.protected_key_version ELSE NULL::pg_catalog.bytea END AS protected_key_version,
       c.protected_expires_at,
       CASE WHEN c.cap_ok THEN c.protected_recovery_metadata ELSE NULL::pg_catalog.bytea END AS protected_recovery_metadata,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.protected_cleanup_policy, 'UTF8') ELSE NULL::pg_catalog.bytea END AS protected_cleanup_policy,
       CASE WHEN c.cap_ok THEN c.projection_metadata ELSE NULL::pg_catalog.bytea END AS projection_metadata
FROM checked AS c
ORDER BY c.record_type, c.work_id"""

_W05_COLUMNS = (
    _W02_COLUMNS[0],
    _TransportColumn(
        name="record_type", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=6
    ),
    _TransportColumn(
        name="visited", wire_type=WireType.INT4, oid=23, nullable=True, max_payload_bytes=4
    ),
    _TransportColumn(
        name="next_cursor", wire_type=WireType.UUID, oid=2950, nullable=True, max_payload_bytes=16
    ),
    _TransportColumn(
        name="pass_exhausted", wire_type=WireType.BOOL, oid=16, nullable=True, max_payload_bytes=1
    ),
) + tuple(
    _TransportColumn(
        name=c.name,
        wire_type=c.wire_type,
        oid=c.oid,
        nullable=True,
        max_payload_bytes=c.max_payload_bytes,
    )
    for c in _W02_COLUMNS[1:]
)


# Fixed E32 transport: cap variable cells before PGresult materialization.
_E32_SQL = b"""WITH source AS MATERIALIZED (
    SELECT s.operation_id, s.work_id, s.token, s.expected_revision, s.cycle, s.attempt, s.dispatch_id, s.failed_business_root, s.reason, s.evidence, s.binding, s.resulting_revision, s.recorded_at
    FROM modkit_events.e32($1::pg_catalog.uuid, $2::pg_catalog.uuid, $3::pg_catalog.int8, $4::pg_catalog.int4, $5::pg_catalog.int4, $6::pg_catalog.text::pg_catalog.xid8, $7::pg_catalog.uuid, $8::pg_catalog.text, $9::pg_catalog.bytea, $10::pg_catalog.bytea) AS s
), checked AS (
    SELECT s.*, (
        (s.reason IS NOT NULL AND pg_catalog.octet_length(pg_catalog.convert_to(s.reason, 'UTF8')) OPERATOR(pg_catalog.<=) 256)
        AND (s.evidence IS NOT NULL AND pg_catalog.octet_length(s.evidence) OPERATOR(pg_catalog.<=) 1048576)
        AND (s.binding IS NOT NULL AND pg_catalog.octet_length(s.binding) OPERATOR(pg_catalog.<=) 1048576)
    ) IS TRUE AS cap_ok
    FROM source AS s
)
SELECT c.cap_ok, c.operation_id, c.work_id, c.token, c.expected_revision,
       c.cycle, c.attempt, c.dispatch_id, c.failed_business_root,
       CASE WHEN c.cap_ok THEN pg_catalog.convert_to(c.reason, 'UTF8') ELSE NULL::pg_catalog.bytea END AS reason,
       CASE WHEN c.cap_ok THEN c.evidence ELSE NULL::pg_catalog.bytea END AS evidence,
       CASE WHEN c.cap_ok THEN c.binding ELSE NULL::pg_catalog.bytea END AS binding,
       c.resulting_revision, c.recorded_at
FROM checked AS c
LIMIT 2"""

_E32_COLUMNS = (
    _E14.transport_columns[0],
    _TransportColumn(name="operation_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16),
    _TransportColumn(name="work_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16),
    _TransportColumn(name="token", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16),
    _TransportColumn(name="expected_revision", wire_type=WireType.INT8, oid=20, nullable=False, max_payload_bytes=8),
    _TransportColumn(name="cycle", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4),
    _TransportColumn(name="attempt", wire_type=WireType.INT4, oid=23, nullable=False, max_payload_bytes=4),
    _TransportColumn(name="dispatch_id", wire_type=WireType.UUID, oid=2950, nullable=False, max_payload_bytes=16),
    _TransportColumn(name="failed_business_root", wire_type=WireType.XID8, oid=5069, nullable=False, max_payload_bytes=8),
    _TransportColumn(name="reason", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=256),
    _TransportColumn(name="evidence", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=1048576),
    _TransportColumn(name="binding", wire_type=WireType.BYTEA, oid=17, nullable=False, max_payload_bytes=1048576),
    _TransportColumn(name="resulting_revision", wire_type=WireType.INT8, oid=20, nullable=False, max_payload_bytes=8),
    _TransportColumn(name="recorded_at", wire_type=WireType.TIMESTAMPTZ, oid=1184, nullable=False, max_payload_bytes=8),
)
_E32 = _SqlDescriptor(
    sql=_E32_SQL,
    parameter_casts=("pg_catalog.uuid", "pg_catalog.uuid", "pg_catalog.int8",
                    "pg_catalog.int4", "pg_catalog.int4", "pg_catalog.text",
                    "pg_catalog.uuid", "pg_catalog.text", "pg_catalog.bytea", "pg_catalog.bytea"),
    canonical_columns=get_statement("E32").result.columns,
    transport_columns=_E32_COLUMNS,
    cardinality=CardinalityKind.EXACT_ONE,
    sentinel_limit=2,
    max_admitted_cell_payload_bytes=sum(c.max_payload_bytes for c in _E32_COLUMNS),
)


def _selected_sql_descriptor(
    spec: StatementSpec, operation=None, *, request=None, max_page_payload_bytes=None
) -> _SqlDescriptor:
    """Select one fixed plan after exact canonical raw metadata validation."""
    if operation is not None:
        from .native_profile import _validate_operation

        _validate_operation(operation)
        if spec is not operation.statement:
            _reject_validation()
        if spec.key == "W05":
            from .native_profile import _result_row_limit, _validate_acquire_max_page_payload_bytes

            _validate_acquire_max_page_payload_bytes(max_page_payload_bytes)
            limit = _result_row_limit(request, operation)
            return _SqlDescriptor(
                sql=_W05_SQL,
                parameter_casts=(
                    "pg_catalog.bytea",
                    "pg_catalog.bytea[]",
                    "pg_catalog.int4[]",
                    "pg_catalog.int4",
                    "pg_catalog.float8",
                    "pg_catalog.uuid",
                    "pg_catalog.int4",
                    "pg_catalog.int8",
                ),
                canonical_columns=spec.result.columns,
                transport_columns=_W05_COLUMNS,
                cardinality=CardinalityKind.SCAN,
                sentinel_limit=limit + 2,
                max_admitted_cell_payload_bytes=sum(c.max_payload_bytes for c in _W05_COLUMNS),
            )
        if spec.key == "W03":
            from .native_profile import _result_row_limit, _validate_max_page_payload_bytes

            _validate_max_page_payload_bytes(max_page_payload_bytes)
            limit = _result_row_limit(request, operation)
            return _SqlDescriptor(
                sql=_W03_SQL,
                parameter_casts=(
                    "pg_catalog.bytea",
                    "pg_catalog.timestamptz",
                    "pg_catalog.uuid",
                    "pg_catalog.int4",
                    "pg_catalog.int8",
                ),
                canonical_columns=spec.result.columns,
                transport_columns=_W02_COLUMNS,
                cardinality=CardinalityKind.LIMIT,
                sentinel_limit=limit + 1,
                max_admitted_cell_payload_bytes=14688732,
            )
        if max_page_payload_bytes is not None:
            _reject_validation()
        if spec.key == "W04":
            return _SqlDescriptor(
                sql=_W04_SQL,
                parameter_casts=(
                    "pg_catalog.uuid",
                    "pg_catalog.text",
                    "pg_catalog.bytea",
                    "pg_catalog.bytea",
                    "pg_catalog.bytea",
                    "pg_catalog.bytea",
                    "pg_catalog.bytea",
                ),
                canonical_columns=spec.result.columns,
                transport_columns=_W04_COLUMNS,
                cardinality=CardinalityKind.FIND_TWO,
                sentinel_limit=3,
                max_admitted_cell_payload_bytes=14688735,
            )
        submit = spec.key == "W01"
        return _SqlDescriptor(
            sql=_W01_SQL if submit else _W02_SQL,
            parameter_casts=_W01_CASTS if submit else ("pg_catalog.uuid",),
            canonical_columns=spec.result.columns,
            transport_columns=_W01_COLUMNS if submit else _W02_COLUMNS,
            cardinality=CardinalityKind.EXACT_ONE if submit else CardinalityKind.OPTIONAL_ONE,
            sentinel_limit=2,
            max_admitted_cell_payload_bytes=18 if submit else 14688732,
        )
    _statement_shape_raw(spec)
    if max_page_payload_bytes is not None:
        _reject_validation()
    if spec is get_statement("E05"):
        return _E05
    if spec is get_statement("E14"):
        return _E14
    if spec is get_statement("E28"):
        return _E28
    if spec is get_statement("E06"):
        return _E06
    if spec is get_statement("E08"):
        return _E08
    if spec is get_statement("E09"):
        return _E09
    if spec is get_statement("E10"):
        return _E10
    if spec is get_statement("E11"):
        return _E11
    if spec is get_statement("E32"):
        return _E32
    _reject_validation()


_PG_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
_MIN_UTC_MICROSECONDS = -63082281600000000
_MAX_UTC_MICROSECONDS = 252455615999999999


def _decode_binary_transport_row(
    spec: StatementSpec, values: tuple, operation=None, *, request=None, max_page_payload_bytes=None
) -> tuple:
    """Convert one copied fixed transport row, without driver authority.

    Result metadata/cardinality and capacity must be proved before copying.
    Full request/record validation and result ownership remain separate gates.
    """
    descriptor = _selected_sql_descriptor(
        spec, operation, request=request, max_page_payload_bytes=max_page_payload_bytes
    )
    if type(values) is not tuple or len(values) != len(descriptor.transport_columns):
        _reject_validation()
    if type(values[0]) is not bytes or values[0] != b"\x01":
        _reject_validation()

    # Inspect the complete bounded row before constructing any typed values.
    for index in range(1, len(values)):
        value = values[index]
        column = descriptor.transport_columns[index]
        if value is None:
            if not column.nullable:
                _reject_validation()
            continue
        if type(value) is not bytes or len(value) > column.max_payload_bytes:
            _reject_validation()
        if column.wire_type is not WireType.BYTEA and len(value) != column.max_payload_bytes:
            _reject_validation()
        if column.wire_type is WireType.BOOL and value not in (b"\x00", b"\x01"):
            _reject_validation()

    converted = []
    for index, column in enumerate(descriptor.canonical_columns, start=1):
        value = values[index]
        if value is None:
            converted.append(None)
            continue
        kind = column.wire_type
        if kind is WireType.BYTEA:
            decoded = value
        elif kind is WireType.BOOL:
            decoded = value == b"\x01"
        elif kind is WireType.INT4 or kind is WireType.INT8:
            decoded = int.from_bytes(value, "big", signed=True)
        elif kind is WireType.XID8:
            decoded = int.from_bytes(value, "big", signed=False)
        elif kind is WireType.UUID:
            decoded = UUID(bytes=value)
        elif kind is WireType.TEXT:
            decoded = _decode_utf8(value, _reject=_reject_validation)
        elif kind is WireType.TIMESTAMPTZ:
            micros = int.from_bytes(value, "big", signed=True)
            if not _MIN_UTC_MICROSECONDS <= micros <= _MAX_UTC_MICROSECONDS:
                _reject_validation()
            decoded = _PG_EPOCH + timedelta(microseconds=micros)
        else:
            _reject_validation()
        converted.append(decoded)
    if operation is not None:
        from .native_profile import decode_columns

        return decode_columns(spec, tuple(converted))
    return _decode_columns_raw(descriptor.canonical_columns, tuple(converted))

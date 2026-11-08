"""Pure fixed SQL plans for the fixed E14/E28 and W01/W02/W03 native transport.

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


def _selected_sql_descriptor(
    spec: StatementSpec, operation=None, *, request=None, max_page_payload_bytes=None
) -> _SqlDescriptor:
    """Select one fixed plan after exact canonical raw metadata validation."""
    if operation is not None:
        from .native_profile import _validate_operation

        _validate_operation(operation)
        if spec is not operation.statement:
            _reject_validation()
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
    if spec is get_statement("E14"):
        return _E14
    return _E28


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

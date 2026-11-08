"""Pure fixed SQL plans for the proposed E14/E28 native transport.

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


def _selected_sql_descriptor(spec: StatementSpec) -> _SqlDescriptor:
    """Select one fixed plan after exact canonical raw metadata validation."""
    _statement_shape_raw(spec)
    if spec is get_statement("E14"):
        return _E14
    return _E28


_PG_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
_MIN_UTC_MICROSECONDS = -63082281600000000
_MAX_UTC_MICROSECONDS = 252455615999999999


def _decode_binary_transport_row(spec: StatementSpec, values: tuple) -> tuple:
    """Convert one copied E14/E28 transport row, without driver authority.

    Result metadata/cardinality and capacity must be proved before copying.
    Full request/record validation and result ownership remain separate gates.
    """
    descriptor = _selected_sql_descriptor(spec)
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

    converted = []
    for index, column in enumerate(descriptor.canonical_columns, start=1):
        value = values[index]
        if value is None:
            converted.append(None)
            continue
        kind = column.wire_type
        if kind is WireType.BYTEA:
            decoded = value
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
    return _decode_columns_raw(descriptor.canonical_columns, tuple(converted))

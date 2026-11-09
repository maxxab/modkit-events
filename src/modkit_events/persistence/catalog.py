"""Closed, driver-neutral PostgreSQL statement metadata. No SQL or resource I/O.

Keys are protocol identities, not caller-provided SQL. Adapters must accept only
canonical instances returned by get_statement, not structurally equal copies.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class WireType(str, Enum):
    UUID = "uuid"
    BYTEA = "bytea"
    TEXT = "text"
    INT4 = "int4"
    INT8 = "int8"
    XID8 = "xid8"
    FLOAT8 = "float8"
    BOOL = "bool"
    TIMESTAMPTZ = "timestamptz"
    BYTEA_ARRAY = "bytea_array"
    INT4_ARRAY = "int4_array"


class CardinalityKind(str, Enum):
    EXACT_ONE = "exact_one"
    OPTIONAL_ONE = "optional_one"
    LIMIT = "limit"
    FIND_TWO = "find_two"
    FIND_THREE = "find_three"
    SCAN = "scan"
    READINESS = "readiness"


class RecordKind(str, Enum):
    UNIT = "unit"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    ATTEMPT_NUMBER = "attempt_number"
    XID = "xid"
    STATE = "state"
    ADMISSION = "admission"
    WORK = "work"
    GUARD = "guard"
    SUBSCRIPTION = "subscription"
    OUTBOX = "outbox"
    WORK_HISTORY = "work_history"
    DELIVERY = "delivery"
    PUBLICATION = "publication"
    ATTEMPT = "attempt"
    RESOLUTION = "resolution"
    SETTLEMENT = "settlement"
    REPAIR = "repair"
    SCHEMA_STATUS = "schema_status"
    INBOX = "inbox"
    INBOX_CANDIDATE = "inbox_candidate"
    JOB = "job"
    JOB_CANDIDATE = "job_candidate"
    WORK_SCAN = "work_scan"
    OUTBOX_SCAN = "outbox_scan"
    JOB_SCAN = "job_scan"


class ConstraintId(str, Enum):
    WORK_ID = "work_id"
    KIND = "kind"
    SUBSCRIPTION_ID = "subscription_id"
    NAMESPACE = "namespace"
    COMMAND_TYPE = "command_type"
    SCOPE_EVIDENCE = "scope_evidence"
    IDEMPOTENCY_KEY = "idempotency_key"
    CANONICAL_VERSION = "canonical_version"
    SCHEMA_VERSION_DECIMAL = "schema_version_decimal"
    SCOPE_APPLICATION = "scope_application"
    SCOPE_TENANT = "scope_tenant"
    SCOPE_OWNER = "scope_owner"
    INTENT_EVIDENCE = "intent_evidence"
    SEMANTIC_INPUT = "semantic_input"
    REPLAY_INPUT = "replay_input"
    PROTECTED_BINDING = "protected_binding"
    REPLAY_POLICY = "replay_policy"
    MAX_ATTEMPTS = "max_attempts"
    DEADLINE = "deadline"
    ORIGINAL_AVAILABLE_AT = "original_available_at"
    EVENT_ID = "event_id"
    ENVELOPE_EVIDENCE = "envelope_evidence"
    SUPPORTED = "supported"
    BROKER_REFERENCE = "broker_reference"
    TRANSPORT_OBSERVATION = "transport_observation"
    MANIFEST = "manifest"
    CONSUMER_GROUP = "consumer_group"
    CAPACITY = "capacity"
    COMMAND_TYPES = "command_types"
    SCHEMA_VERSIONS = "schema_versions"
    LIMIT = "limit"
    LEASE_SECONDS = "lease_seconds"
    WORK_CURSOR = "work_cursor"
    OUTBOX_CURSOR = "outbox_cursor"
    DISCOVERY_BUDGET = "discovery_budget"
    TOKEN = "token"
    OWNERSHIP_REVISION = "ownership_revision"
    CYCLE = "cycle"
    EXPECTED_ATTEMPT = "expected_attempt"
    DISPATCH_ID = "dispatch_id"
    EFFECT_ID = "effect_id"
    REQUEST_EVIDENCE = "request_evidence"
    PROVIDER_KEY_REFERENCE = "provider_key_reference"
    AVAILABLE_AT = "available_at"
    GUARD_ID = "guard_id"
    ROOT_XID = "root_xid"
    RESULT = "result"
    FAILED_BUSINESS_ROOT = "failed_business_root"
    FAILURE_OUTCOME = "failure_outcome"
    RETRY_AT = "retry_at"
    REASON = "reason"
    EVIDENCE = "evidence"
    RECEIPT = "receipt"
    EXPECTED_TOKEN = "expected_token"
    EXPECTED_REVISION = "expected_revision"
    AFTER_ID = "after_id"
    AFTER_CYCLE = "after_cycle"
    AFTER_ATTEMPT = "after_attempt"
    INTENT_ID = "intent_id"
    PUBLICATION_STATUS = "publication_status"
    REPAIR_STATUS = "repair_status"
    OPERATION_ID = "operation_id"
    BINDING = "binding"
    AFTER_CREATED_AT = "after_created_at"
    AFTER_WORK_ID = "after_work_id"
    RESOLUTION_OUTCOME = "resolution_outcome"
    ATTEMPT = "attempt"
    REQUIRED_PROFILE = "required_profile"
    MATERIAL_STATE = "material_state"
    PROTECTED_SIDECAR = "protected_sidecar"
    PROTECTED_REFERENCE = "protected_reference"
    PROTECTED_CODEC = "protected_codec"
    PROTECTED_KEY_VERSION = "protected_key_version"
    PROTECTED_EXPIRES_AT = "protected_expires_at"
    PROTECTED_RECOVERY_METADATA = "protected_recovery_metadata"
    PROTECTED_CLEANUP_POLICY = "protected_cleanup_policy"
    PROJECTION_METADATA = "projection_metadata"


def _metadata_reject(error_type, message, reject):
    if reject is not None:
        reject()
    raise error_type(message)


def _name(value: str, *, _reject=None) -> None:
    if type(value) is not str or not value.isascii() or not value.isidentifier():
        _metadata_reject(ValueError, "invalid metadata name", _reject)


def _tuple(value: tuple, cls: type, *, nonempty: bool = False, _reject=None) -> None:
    if (
        type(value) is not tuple
        or (nonempty and not value)
        or any(type(item) is not cls for item in value)
    ):
        _metadata_reject(TypeError, "invalid metadata sequence", _reject)
    if len({item.name for item in value}) != len(value):
        _metadata_reject(ValueError, "duplicate metadata name", _reject)


@dataclass(frozen=True, slots=True, kw_only=True)
class ParameterSpec:
    name: str
    wire_type: WireType
    nullable: bool
    constraint: ConstraintId

    def __post_init__(self) -> None:
        _validate_parameter_spec(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class ColumnSpec:
    name: str
    wire_type: WireType
    nullable: bool

    def __post_init__(self) -> None:
        _validate_column_spec(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultSpec:
    record: RecordKind
    cardinality: CardinalityKind
    columns: tuple[ColumnSpec, ...]

    def __post_init__(self) -> None:
        _validate_result_spec(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class StatementSpec:
    key: str
    contract_id: str
    parameters: tuple[ParameterSpec, ...]
    result: ResultSpec
    mutation: bool

    def __post_init__(self) -> None:
        _validate_statement_spec(self)


def _validate_parameter_spec(value: ParameterSpec, *, _reject=None) -> None:
    _name(value.name, _reject=_reject)
    if (
        type(value.wire_type) is not WireType
        or type(value.nullable) is not bool
        or type(value.constraint) is not ConstraintId
    ):
        _metadata_reject(TypeError, "invalid parameter metadata", _reject)


def _validate_column_spec(value: ColumnSpec, *, _reject=None) -> None:
    _name(value.name, _reject=_reject)
    if type(value.wire_type) is not WireType or type(value.nullable) is not bool:
        _metadata_reject(TypeError, "invalid column metadata", _reject)


def _validate_result_spec(value: ResultSpec, *, _reject=None) -> None:
    if type(value.record) is not RecordKind or type(value.cardinality) is not CardinalityKind:
        _metadata_reject(TypeError, "invalid result metadata", _reject)
    _tuple(value.columns, ColumnSpec, nonempty=True, _reject=_reject)


def _validate_statement_spec(value: StatementSpec, *, _reject=None) -> None:
    if (
        type(value.key) is not str
        or len(value.key) != 3
        or value.key[0] not in ("E", "W")
        or not value.key[1:].isascii()
        or not value.key[1:].isdigit()
    ):
        _metadata_reject(ValueError, "invalid statement key", _reject)
    if not 1 <= int(value.key[1:]) <= (34 if value.key[0] == "E" else 5):
        _metadata_reject(ValueError, "invalid statement key", _reject)
    if type(value.contract_id) is not str or value.contract_id != "modkit-pg-ab-2":
        _metadata_reject(ValueError, "invalid contract identifier", _reject)
    _tuple(value.parameters, ParameterSpec, _reject=_reject)
    if type(value.result) is not ResultSpec or type(value.mutation) is not bool:
        _metadata_reject(TypeError, "invalid statement metadata", _reject)


_TYPES = MappingProxyType(
    dict(
        U=WireType.UUID,
        B=WireType.BYTEA,
        T=WireType.TEXT,
        I=WireType.INT4,
        L=WireType.INT8,
        X=WireType.XID8,
        F=WireType.FLOAT8,
        O=WireType.BOOL,
        Z=WireType.TIMESTAMPTZ,
        BA=WireType.BYTEA_ARRAY,
        IA=WireType.INT4_ARRAY,
    )
)


def _columns(text: str) -> tuple[ColumnSpec, ...]:
    result = []
    for field in text.split():
        name, kind = field.split(":")
        result.append(
            ColumnSpec(name=name, wire_type=_TYPES[kind.rstrip("?")], nullable=kind.endswith("?"))
        )
    return tuple(result)


def _params(text: str) -> tuple[ParameterSpec, ...]:
    result = []
    for field in text.split():
        # Optional @suffix supplies a semantic validator for a contextual label.
        descriptor, *override = field.split("@")
        name, kind = descriptor.split(":")
        result.append(
            ParameterSpec(
                name=name,
                wire_type=_TYPES[kind.rstrip("?")],
                nullable=kind.endswith("?"),
                constraint=ConstraintId(override[0] if override else name),
            )
        )
    return tuple(result)


def _optional(columns: tuple[ColumnSpec, ...], prefix: str = "") -> tuple[ColumnSpec, ...]:
    return tuple(
        ColumnSpec(name=prefix + c.name, wire_type=c.wire_type, nullable=True) for c in columns
    )


_IDENTITY = _params(
    "work_id:U kind:T subscription_id:B? namespace:B command_type:B scope_evidence:B idempotency_key:B?"
)
_ADMISSION = _IDENTITY + _params(
    "canonical_version:I schema_version_decimal:B scope_application:B scope_tenant:B? scope_owner:B? intent_evidence:B semantic_input:B replay_input:B protected_binding:B replay_policy:T max_attempts:I deadline:Z? original_available_at:Z"
)
_EVENT = _params("event_id:B canonical_version:I envelope_evidence:B replay_input:B")
_INTAKE_EVENT = _params(
    "event_id:B event_canonical_version:I@canonical_version envelope_evidence:B event_replay_input:B@replay_input"
)
_FENCE = _params("work_id:U token:U ownership_revision:L cycle:I expected_attempt:I")
_PUB_FENCE = _params("event_id:B token:U ownership_revision:L")
_GUARD_REF = _params(
    "guard_id:U work_id:U root_xid:X token:U ownership_revision:L cycle:I expected_attempt:I"
)
_SCAN_WORK = _params("scan_after:U?@work_cursor discovery_budget:I")
_SCAN_OUTBOX = _params("scan_after:B?@outbox_cursor discovery_budget:I")

_RESOLUTION = _columns(
    "operation_id:U operation_kind:T work_id:U expected_revision:L cycle:I attempt:I dispatch_id:U outcome:T retry_at:Z? result:B? result_digest:B? reason:T? evidence:B binding:B resolution_root_xid:X recorded_at:Z"
)
_WORK_BASE = _columns(
    "work_id:U kind:T subscription_id:B? namespace:B command_type:B schema_version_decimal:B runnable_version:I? canonical_version:I scope_evidence:B scope_application:B scope_tenant:B? scope_owner:B? idempotency_key:B? intent_evidence:B semantic_input:B replay_input:B protected_binding:B replay_policy:T max_attempts:I deadline:Z? original_available_at:Z state:T cancellation_requested:O token:U? ownership_revision:L lease_until:Z? available_at:Z cycle:I attempt_count:I dispatch_id:U? result:B? created_at:Z updated_at:Z success_origin:T? completion_guard_id:U? final_fence_at:Z? completion_result_digest:B? resolution_operation_id:U? terminal_resolution_operation_id:U?"
)
_WORK = _WORK_BASE + _columns("resolution_present:O") + _optional(_RESOLUTION, "resolution_record_")
_GUARD = _columns(
    "guard_id:U work_id:U root_xid:X token:U ownership_revision:L cycle:I expected_attempt:I satisfied:O final_fence_at:Z? terminal_state:T? result_digest:B?"
)
_SUBSCRIPTION = _columns(
    "subscription_id:B manifest:B consumer_group:B capacity:I nonterminal_count:L created_at:Z"
)
_OUTBOX = _columns(
    "event_id:B canonical_version:I envelope_evidence:B replay_input:B state:T token:U? ownership_revision:L lease_until:Z? intent_id:U? receipt:B? outcome_evidence:B? created_at:Z updated_at:Z"
)
_WORK_HISTORY = _columns(
    "history_id:L work_id:U cycle:I attempt:I transition:T reason:T token:U? ownership_revision:L evidence:B recorded_at:Z"
)
_DELIVERY = _columns(
    "history_id:L work_id:U broker_reference:B transport_observation:B recorded_at:Z"
)
_PUBLICATION = _columns(
    "history_id:L event_id:B intent_id:U? operation_id:U? status:T receipt:B? evidence:B binding:B recorded_at:Z"
)
_ATTEMPT = _columns(
    "work_id:U cycle:I attempt:I dispatch_id:U effect_id:B request_evidence:B provider_key_reference:B? dispatch_root_xid:X outcome:T evidence:B recorded_at:Z"
)
_INBOX_HALF = _columns(
    "inbox_subscription_id:B original_event_id:B envelope_evidence:B original_replay_input:B"
)
_INBOX = _WORK + _INBOX_HALF
_INBOX_CANDIDATE = _WORK + _columns("inbox_half_present:O") + _optional(_INBOX_HALF)
_REPAIR = _columns(
    "operation_id:U event_id:B expected_revision:L status:T receipt:B? evidence:B binding:B resulting_revision:L recorded_at:Z"
)
_SETTLEMENT = _columns(
    "operation_id:U work_id:U token:U expected_revision:L cycle:I attempt:I dispatch_id:U failed_business_root:X reason:T evidence:B binding:B resulting_revision:L recorded_at:Z"
)
_WORK_SCAN_ROW = _columns("record_type:T visited:I? next_cursor:U? pass_exhausted:O?") + _optional(
    _WORK
)
_OUTBOX_SCAN_ROW = _columns(
    "record_type:T visited:I? next_cursor:B? pass_exhausted:O?"
) + _optional(_OUTBOX)


def _statement(
    key: str,
    parameters: tuple[ParameterSpec, ...],
    record: RecordKind,
    cardinality: CardinalityKind,
    columns: tuple[ColumnSpec, ...],
    *,
    mutation: bool,
) -> StatementSpec:
    return StatementSpec(
        key=key,
        contract_id="modkit-pg-ab-2",
        parameters=parameters,
        result=ResultSpec(record=record, cardinality=cardinality, columns=columns),
        mutation=mutation,
    )


_R = RecordKind
_C = CardinalityKind
_UNIT = _columns("ok:O")
_ITEMS = (
    _statement(
        "E01",
        _params("subscription_id:B manifest:B consumer_group:B capacity:I"),
        _R.UNIT,
        _C.EXACT_ONE,
        _UNIT,
        mutation=True,
    ),
    _statement("E02", _EVENT, _R.BOOLEAN, _C.EXACT_ONE, _columns("inserted:O"), mutation=True),
    _statement(
        "E03",
        _ADMISSION
        + _INTAKE_EVENT
        + _params("supported:O broker_reference:B transport_observation:B"),
        _R.ADMISSION,
        _C.EXACT_ONE,
        _columns("work_id:U inserted:O"),
        mutation=True,
    ),
    _statement(
        "E04",
        _params("namespace:B kind:T command_types:BA schema_versions:IA limit:I lease_seconds:F")
        + _SCAN_WORK,
        _R.WORK_SCAN,
        _C.SCAN,
        _WORK_SCAN_ROW,
        mutation=True,
    ),
    _statement(
        "E05",
        _FENCE + _params("lease_seconds:F"),
        _R.TIMESTAMP,
        _C.EXACT_ONE,
        _columns("lease_until:Z"),
        mutation=True,
    ),
    _statement(
        "E06",
        _FENCE + _params("dispatch_id:U effect_id:B request_evidence:B provider_key_reference:B?"),
        _R.ATTEMPT_NUMBER,
        _C.EXACT_ONE,
        _columns("attempt:I"),
        mutation=True,
    ),
    _statement(
        "E07", _FENCE + _params("available_at:Z"), _R.UNIT, _C.EXACT_ONE, _UNIT, mutation=True
    ),
    _statement("E08", _FENCE, _R.GUARD, _C.EXACT_ONE, _GUARD, mutation=True),
    _statement("E09", _FENCE, _R.GUARD, _C.OPTIONAL_ONE, _GUARD, mutation=False),
    _statement(
        "E10", _GUARD_REF + _params("result:B"), _R.UNIT, _C.EXACT_ONE, _UNIT, mutation=True
    ),
    _statement(
        "E11",
        _FENCE
        + _params(
            "failed_business_root:X outcome:T@failure_outcome retry_at:Z? reason:T evidence:B"
        ),
        _R.UNIT,
        _C.EXACT_ONE,
        _UNIT,
        mutation=True,
    ),
    _statement(
        "E12",
        _params("work_id:U expected_token:U? expected_revision:L? reason:T"),
        _R.STATE,
        _C.EXACT_ONE,
        _columns("state:T"),
        mutation=True,
    ),
    _statement(
        "E13",
        _params("namespace:B kind:T limit:I") + _SCAN_WORK,
        _R.WORK_SCAN,
        _C.SCAN,
        _WORK_SCAN_ROW,
        mutation=True,
    ),
    _statement("E14", (), _R.XID, _C.EXACT_ONE, _columns("root_xid:X"), mutation=True),
    _statement("E15", _params("work_id:U"), _R.WORK, _C.OPTIONAL_ONE, _WORK, mutation=False),
    _statement(
        "E16",
        _params("subscription_id:B event_id:B"),
        _R.INBOX,
        _C.OPTIONAL_ONE,
        _INBOX,
        mutation=False,
    ),
    _statement("E17", _IDENTITY, _R.WORK, _C.FIND_TWO, _WORK, mutation=False),
    _statement(
        "E18",
        _params("subscription_id:B"),
        _R.SUBSCRIPTION,
        _C.OPTIONAL_ONE,
        _SUBSCRIPTION,
        mutation=False,
    ),
    _statement(
        "E19",
        _params("work_id:U after_id:L limit:I"),
        _R.WORK_HISTORY,
        _C.LIMIT,
        _WORK_HISTORY,
        mutation=False,
    ),
    _statement(
        "E20",
        _params("work_id:U after_id:L limit:I"),
        _R.DELIVERY,
        _C.LIMIT,
        _DELIVERY,
        mutation=False,
    ),
    _statement(
        "E21",
        _params("work_id:U after_cycle:I after_attempt:I limit:I"),
        _R.ATTEMPT,
        _C.LIMIT,
        _ATTEMPT,
        mutation=False,
    ),
    _statement(
        "E22",
        _params("limit:I lease_seconds:F") + _SCAN_OUTBOX,
        _R.OUTBOX_SCAN,
        _C.SCAN,
        _OUTBOX_SCAN_ROW,
        mutation=True,
    ),
    _statement(
        "E23",
        _PUB_FENCE + _params("lease_seconds:F"),
        _R.TIMESTAMP,
        _C.EXACT_ONE,
        _columns("lease_until:Z"),
        mutation=True,
    ),
    _statement(
        "E24", _PUB_FENCE + _params("intent_id:U"), _R.UNIT, _C.EXACT_ONE, _UNIT, mutation=True
    ),
    _statement(
        "E25",
        _PUB_FENCE + _params("intent_id:U status:T@publication_status receipt:B? evidence:B"),
        _R.UNIT,
        _C.EXACT_ONE,
        _UNIT,
        mutation=True,
    ),
    _statement(
        "E26",
        _params("limit:I") + _SCAN_OUTBOX,
        _R.OUTBOX_SCAN,
        _C.SCAN,
        _OUTBOX_SCAN_ROW,
        mutation=True,
    ),
    _statement(
        "E27",
        _params(
            "event_id:B expected_revision:L operation_id:U status:T@repair_status receipt:B? evidence:B binding:B"
        ),
        _R.REPAIR,
        _C.EXACT_ONE,
        _REPAIR,
        mutation=True,
    ),
    _statement("E28", _params("event_id:B"), _R.OUTBOX, _C.OPTIONAL_ONE, _OUTBOX, mutation=False),
    _statement(
        "E29",
        _params("event_id:B after_id:L limit:I"),
        _R.PUBLICATION,
        _C.LIMIT,
        _PUBLICATION,
        mutation=False,
    ),
    _statement(
        "E30",
        _params("namespace:B after_created_at:Z? after_work_id:U? limit:I"),
        _R.WORK,
        _C.LIMIT,
        _WORK,
        mutation=False,
    ),
    _statement(
        "E31",
        _params(
            "work_id:U expected_revision:L cycle:I attempt:I dispatch_id:U operation_id:U outcome:T@resolution_outcome retry_at:Z? result:B? evidence:B binding:B"
        ),
        _R.RESOLUTION,
        _C.EXACT_ONE,
        _RESOLUTION,
        mutation=True,
    ),
    _statement(
        "E32",
        _FENCE + _params("failed_business_root:X operation_id:U reason:T evidence:B binding:B"),
        _R.SETTLEMENT,
        _C.EXACT_ONE,
        _SETTLEMENT,
        mutation=True,
    ),
    _statement(
        "E33",
        _params("required_profile:T"),
        _R.SCHEMA_STATUS,
        _C.READINESS,
        _columns(
            "component:T version:I migration_digest:B catalog_contract_id:T scope_format_id:T intent_format_id:T"
        ),
        mutation=False,
    ),
    _statement(
        "E34",
        _IDENTITY + _params("original_event_id:B@event_id"),
        _R.INBOX_CANDIDATE,
        _C.FIND_THREE,
        _INBOX_CANDIDATE,
        mutation=False,
    ),
)
_STATEMENTS = MappingProxyType({s.key: s for s in _ITEMS})


def get_statement(key: str) -> StatementSpec:
    """Return one canonical E descriptor; never register or synthesize SQL."""
    if type(key) is not str or key not in _STATEMENTS:
        raise ValueError("unknown event statement key")
    return _STATEMENTS[key]


__all__ = (
    "WireType",
    "CardinalityKind",
    "RecordKind",
    "ConstraintId",
    "ParameterSpec",
    "ColumnSpec",
    "ResultSpec",
    "StatementSpec",
    "get_statement",
)  # type: tuple[str, ...]


class OperationKind(str, Enum):
    """Exact immutable registry discriminators, not new SQL operations."""

    REPAIR_PUBLICATION = "repair_publication"
    RECONCILE_WORK = "reconcile_work"
    HOLD_UNCERTAIN = "hold_uncertain"


MUTATION_OPERATION_KINDS = MappingProxyType(
    {
        "E27": OperationKind.REPAIR_PUBLICATION,
        "E31": OperationKind.RECONCILE_WORK,
        "E32": OperationKind.HOLD_UNCERTAIN,
    }
)
__all__ += ("OperationKind", "MUTATION_OPERATION_KINDS")

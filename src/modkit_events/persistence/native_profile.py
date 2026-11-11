"""Fixed import-neutral Workers W01/W02/W03/W04 semantic and retained graph profile.

No Workers import, driver, I/O, registration, or arbitrary graph traversal.
Startup component provenance is cooperative, not authentication of Python code.
"""

from dataclasses import Field, dataclass, fields
from datetime import datetime, timezone
from enum import Enum, EnumType
from math import isfinite
from sys import getsizeof
from types import FunctionType
from uuid import UUID

from . import bindings as B
from . import catalog as C
from . import models as M
from . import observations as O
from .errors import _reject_validation as reject

_MAX = 1048576
# Fourteen distinct large BYTEA output occurrences, not distinct objects.
_LIST_ROW_PAYLOAD_MAX = 14 * _MAX
DEFAULT_LIST_PAGE_PAYLOAD_BYTES = 16 * _MAX
MAX_LIST_PAGE_PAYLOAD_BYTES = 256 * _LIST_ROW_PAYLOAD_MAX
DEFAULT_ACQUIRE_PAGE_PAYLOAD_BYTES = 16 * _MAX
MAX_ACQUIRE_PAGE_PAYLOAD_BYTES = 2**32
_MATERIAL = (
    ("material_state", C.WireType.TEXT, False),
    ("protected_sidecar", C.WireType.BYTEA, True),
    ("protected_reference", C.WireType.BYTEA, True),
    ("protected_codec", C.WireType.BYTEA, True),
    ("protected_key_version", C.WireType.BYTEA, True),
    ("protected_expires_at", C.WireType.TIMESTAMPTZ, True),
    ("protected_recovery_metadata", C.WireType.BYTEA, False),
    ("protected_cleanup_policy", C.WireType.TEXT, False),
    ("projection_metadata", C.WireType.BYTEA, False),
)
_JOB = (
    ("job_work_id", C.WireType.UUID, False),
    ("job_application", C.WireType.BYTEA, False),
    ("job_tenant", C.WireType.BYTEA, True),
    ("job_owner", C.WireType.BYTEA, True),
    ("job_protected_binding", C.WireType.BYTEA, False),
    ("job_semantic_input", C.WireType.BYTEA, False),
) + _MATERIAL
_DETAILS = ("work_id", "application", "tenant", "owner", "protected_binding")
_PAYLOAD = (
    "semantic_input",
    "material_state",
    "sidecar",
    "reference",
    "codec",
    "key_version",
    "expires_at",
    "recovery_metadata",
    "cleanup_policy",
    "projection_metadata",
)


def _shape(statement):
    if type(statement) is not C.StatementSpec:
        reject()
    if (
        type(statement.parameters) is not tuple
        or len(statement.parameters) not in (1, 4, 7, 29)
        or type(statement.result) is not C.ResultSpec
        or type(statement.result.columns) is not tuple
        or len(statement.result.columns) not in (2, 71, 72, 75)
    ):
        reject()
    C._validate_statement_spec(statement, _reject=reject)
    C._validate_result_spec(statement.result, _reject=reject)
    if statement.key not in ("W01", "W02", "W03", "W04", "W05"):
        reject()
    for value in statement.parameters:
        C._validate_parameter_spec(value, _reject=reject)
    for value in statement.result.columns:
        C._validate_column_spec(value, _reject=reject)
    if statement.key == "W01":
        params = (
            tuple((p.name, p.wire_type, p.nullable) for p in C.get_statement("E03").parameters[:20])
            + _MATERIAL
        )
        cols = tuple(
            (c.name, c.wire_type, c.nullable) for c in C.get_statement("E03").result.columns
        )
        record, cardinality, mutation = C.RecordKind.ADMISSION, C.CardinalityKind.EXACT_ONE, True
    elif statement.key == "W05":
        params = tuple(
            (p.name, p.wire_type, p.nullable)
            for p in C.get_statement("E04").parameters
            if p.name != "kind"
        )
        cols = (
            tuple(
                (c.name, c.wire_type, c.nullable) for c in C.get_statement("E04").result.columns[:4]
            )
            + tuple((c.name, c.wire_type, True) for c in C.get_statement("E15").result.columns)
            + tuple((name, wire, True) for name, wire, _ in _JOB)
        )
        record, cardinality, mutation = C.RecordKind.JOB_SCAN, C.CardinalityKind.SCAN, True
    elif statement.key == "W04":
        params = tuple((p.name, p.wire_type, p.nullable) for p in C.get_statement("E17").parameters)
        cols = (
            tuple((c.name, c.wire_type, c.nullable) for c in C.get_statement("E15").result.columns)
            + (("job_half_present", C.WireType.BOOL, False),)
            + tuple((name, wire, True) for name, wire, _ in _JOB)
        )
        record, cardinality, mutation = (
            C.RecordKind.JOB_CANDIDATE,
            C.CardinalityKind.FIND_TWO,
            False,
        )
    else:
        params = (
            (("work_id", C.WireType.UUID, False),)
            if statement.key == "W02"
            else tuple((p.name, p.wire_type, p.nullable) for p in C.get_statement("E30").parameters)
        )
        cols = (
            tuple((c.name, c.wire_type, c.nullable) for c in C.get_statement("E15").result.columns)
            + _JOB
        )
        record, mutation = C.RecordKind.JOB, False
        cardinality = (
            C.CardinalityKind.OPTIONAL_ONE if statement.key == "W02" else C.CardinalityKind.LIMIT
        )
    if (
        tuple((p.name, p.wire_type, p.nullable) for p in statement.parameters) != params
        or tuple((c.name, c.wire_type, c.nullable) for c in statement.result.columns) != cols
        or any(
            p.constraint.value
            != ("work_cursor" if statement.key == "W05" and p.name == "scan_after" else p.name)
            for p in statement.parameters
        )
        or statement.result.record is not record
        or statement.result.cardinality is not cardinality
        or statement.mutation is not mutation
    ):
        reject()


def _carrier(cls, module, name, names):
    if type(cls) is not type:
        reject()
    namespace = vars(cls)
    slots = namespace.get("__slots__")
    declared = namespace.get("__dataclass_fields__")
    params = namespace.get("__dataclass_params__")
    if (
        type(cls.__module__) is not str
        or cls.__module__ != module
        or cls.__name__ != name
        or cls.__bases__ != (object,)
        or cls.__sizeof__ is not object.__sizeof__
        or cls.__dictoffset__ != 0
        or type(slots) is not tuple
        or slots != names
        or type(declared) is not dict
        or tuple(declared) != names
        or any(
            type(field) is not Field or type(field.name) is not str for field in declared.values()
        )
        or type(params) is not type(WorkersNativeOperation.__dataclass_params__)
        or params.frozen is not True
    ):
        reject()
    if tuple(field.name for field in fields(cls)) != names:
        reject()


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class WorkersNativeOperation:
    statement: C.StatementSpec
    request_type: type
    build_request: object
    decode_rows: object
    validate_result: object
    result_types: tuple

    def __post_init__(self):
        _validate_operation(self)


def _validate_operation(operation):
    if type(operation) is not WorkersNativeOperation:
        reject()
    _shape(operation.statement)
    submit = operation.statement.key == "W01"
    listing = operation.statement.key == "W03"
    finding = operation.statement.key == "W04"
    acquiring = operation.statement.key == "W05"
    _carrier(
        operation.request_type,
        "modkit_workers.persistence.models",
        "JobAcquireRequest"
        if acquiring
        else "JobSubmitRequest"
        if submit
        else "JobFindRequest"
        if finding
        else "JobListRequest"
        if listing
        else "JobReadRequest",
        ("capabilities", "limit", "lease_seconds", "scan_after", "discovery_budget")
        if acquiring
        else ("job",)
        if submit or finding
        else ("after", "limit")
        if listing
        else ("work_id",),
    )
    if type(operation.result_types) is not tuple or len(operation.result_types) != (
        1 if submit else 6 if finding else 4 if acquiring else 3
    ):
        reject()
    result_shapes = (
        (("JobAdmissionObservation", ("work_id", "inserted")),)
        if submit
        else (
            ("JobRecord", ("work", "details", "payload")),
            ("JobDetails", _DETAILS),
            ("JobPayload", _PAYLOAD),
        )
    )
    if acquiring:
        result_shapes += (("JobClaimObservation", ("record", "fence")),)
    if finding:
        result_shapes += (
            ("JobCandidate", ("work", "job")),
            ("JobIdentityObservation", ("decision", "candidates", "original_work_id")),
        )
        _decision_enum(operation.result_types[5])
    for cls, (name, names) in zip(operation.result_types, result_shapes):
        _carrier(cls, "modkit_workers.persistence.observations", name, names)
    suffix = (
        "acquire"
        if acquiring
        else "submit"
        if submit
        else "find"
        if finding
        else "list"
        if listing
        else "read"
    )
    callbacks = (
        (
            operation.build_request,
            "bindings",
            "_acquire_raw"
            if acquiring
            else "_submit_raw"
            if submit
            else "_find_jobs_raw"
            if finding
            else "_list_jobs_raw"
            if listing
            else "_read_job_raw",
        ),
        (operation.decode_rows, "rows", "_decode_" + suffix + "_raw"),
        (operation.validate_result, "rows", "_validate_" + suffix + "_result_raw"),
    )
    for callback, leaf, name in callbacks:
        module = "modkit_workers.persistence." + leaf
        if (
            type(callback) is not FunctionType
            or callback.__closure__ is not None
            or type(callback.__module__) is not str
            or callback.__module__ != module
            or callback.__name__ != name
            or callback.__defaults__ is not None
            or callback.__kwdefaults__ is not None
        ):
            reject()


def _decision_enum(cls):
    """Fixed cooperative enum provenance, without calling enum/user hooks."""
    if type(cls) is not EnumType:
        reject()
    namespace = vars(cls)
    members = namespace.get("_member_map_")
    if (
        cls.__bases__ != (Enum,)
        or type(cls.__module__) is not str
        or type(cls.__name__) is not str
        or cls.__module__ != "modkit_workers.persistence.observations"
        or cls.__name__ != "JobIdentityDecision"
        or cls.__sizeof__ is not object.__sizeof__
        or cls.__getattribute__ is not object.__getattribute__
        or type(members) is not dict
        or any(type(name) is not str for name in members)
        or tuple(members) != ("NEW", "MATCH", "CONFLICT")
    ):
        reject()
    for name, expected in (("NEW", "new"), ("MATCH", "match"), ("CONFLICT", "conflict")):
        member = members[name]
        if type(member) is not cls:
            reject()
        value = object.__getattribute__(member, "_value_")
        member_name = object.__getattribute__(member, "_name_")
        if (
            type(value) is not str
            or value != expected
            or type(member_name) is not str
            or member_name != name
            or namespace.get(name) is not member
        ):
            reject()


def _cap(name, wire):
    if name.startswith("resolution_record_"):
        name = name[len("resolution_record_") :]
    if wire is C.WireType.TEXT:
        return 256 if name == "reason" else 32
    if name in ("scope_evidence",):
        return 781
    if name == "schema_version_decimal":
        return 4096
    if name in ("result_digest", "completion_result_digest"):
        return 32
    if name in (
        "subscription_id",
        "namespace",
        "command_type",
        "scope_application",
        "scope_tenant",
        "scope_owner",
        "idempotency_key",
        "job_application",
        "job_tenant",
        "job_owner",
        "protected_codec",
        "protected_key_version",
    ):
        return 256
    return _MAX


def _scalar(value, wire, nullable, name):
    if value is not None and wire in (C.WireType.BYTEA, C.WireType.TEXT):
        expected = bytes if wire is C.WireType.BYTEA else str
        if type(value) is not expected or len(value) > _cap(name, wire):
            reject()
    if wire is C.WireType.FLOAT8:
        if type(value) is not float or not isfinite(value):
            reject()
        return value
    if wire in (C.WireType.BYTEA_ARRAY, C.WireType.INT4_ARRAY):
        if type(value) is not tuple or not 1 <= len(value) <= 256:
            reject()
        for item in value:
            if wire is C.WireType.BYTEA_ARRAY:
                if type(item) is not bytes or not 1 <= len(item) <= 256:
                    reject()
                try:
                    text = item.decode("utf-8")
                except UnicodeDecodeError:
                    reject()
                B._identifier_raw(text)
            else:
                B._integer_raw(item, 1, 2**31 - 1)
        return value
    return B._scalar_raw(value, wire, nullable)


def _parameters(statement, parameters, context):
    _shape(statement)
    if (
        type(parameters) is not tuple
        or len(parameters) != len(statement.parameters)
        or type(context) is not B.ReturnContext
    ):
        reject()
    B._validate_return_context(context, _reject=reject)
    for value, spec in zip(parameters, statement.parameters):
        if _scalar(value, spec.wire_type, spec.nullable, spec.name) is not value:
            reject()
    if statement.key == "W05":
        namespace, commands, versions, limit, lease, cursor, discovery = parameters
        if namespace != b"jobs" or context.expected or context.readiness is not None:
            reject()
        if len(commands) != len(versions) or not 0 < lease <= 3600:
            reject()
        B._integer_raw(limit, 1, 256)
        B._integer_raw(discovery, limit, 4096)
        previous = None
        for command, version in zip(commands, versions):
            pair = (command, version)
            if previous is not None and pair <= previous:
                reject()
            previous = pair
        return
    if statement.key in ("W02", "W03"):
        if context.expected:
            reject()
        if statement.key == "W03":
            namespace, created_at, work_id, limit = parameters
            if namespace != b"jobs" or (created_at is None) != (work_id is None):
                reject()
            B._integer_raw(limit, 1, 256)
        return
    if len(context.expected) != 1:
        reject()
    expected = context.expected[0]
    projected = B._admission_values_raw(expected)
    if expected.identity.kind is not M.WorkKind.JOB or expected.identity.namespace != "jobs":
        reject()
    if statement.key == "W04":
        if expected.identity.subscription_id is not None or context.readiness is not None:
            reject()
        if any(
            projected[spec.name] != value for spec, value in zip(statement.parameters, parameters)
        ):
            reject()
        return
    material = B._decode_protected_binding_raw(expected.protected_binding)
    projected.update(
        material_state=material.material_state.value,
        protected_sidecar=material.sidecar,
        protected_reference=material.reference,
        protected_codec=None if material.codec is None else B._identifier_raw(material.codec),
        protected_key_version=None
        if material.key_version is None
        else B._identifier_raw(material.key_version),
        protected_expires_at=material.expires_at,
        protected_recovery_metadata=material.recovery_metadata,
        protected_cleanup_policy=material.cleanup_policy.value,
        projection_metadata=material.projection_metadata,
    )
    if any(projected[spec.name] != value for spec, value in zip(statement.parameters, parameters)):
        reject()


def freeze_request(
    statement: C.StatementSpec, parameters: tuple, /, *, context: B.ReturnContext
) -> B.FrozenRequest:
    _parameters(statement, parameters, context)
    result = object.__new__(B.FrozenRequest)
    object.__setattr__(result, "statement", statement)
    object.__setattr__(result, "parameters", parameters)
    object.__setattr__(result, "context", context)
    return result


def validate_request(request: B.FrozenRequest, statement: C.StatementSpec, /) -> None:
    if type(request) is not B.FrozenRequest or request.statement is not statement:
        reject()
    _parameters(statement, request.parameters, request.context)


def decode_columns(statement: C.StatementSpec, values: tuple, /) -> tuple:
    _shape(statement)
    if type(values) is not tuple or len(values) != len(statement.result.columns):
        reject()
    from .rows import _wire_scalar_raw

    result = []
    for value, col in zip(values, statement.result.columns):
        # Native transport uses already typed scalars; pure helper also accepts
        # the established bounded UUID/XID spelling conversion.
        if col.wire_type in (C.WireType.BYTEA, C.WireType.TEXT):
            value = _scalar(value, col.wire_type, col.nullable, col.name)
        else:
            value = _wire_scalar_raw(value, col.wire_type, col.nullable)
        result.append(_scalar(value, col.wire_type, col.nullable, col.name))
    return tuple(result)


def _storage(value):
    """One exact immutable scalar, never recursively walking an object."""
    if value is None or type(value) in (bytes, str, bool, int, float):
        return getsizeof(value)
    if type(value) is UUID:
        B._uuid_raw(value)
        return getsizeof(value) + getsizeof(value.int)
    if type(value) is datetime:
        B._instant_raw(value)
        return getsizeof(value)
    if type(value) in (M.MaterialState, M.CleanupPolicy, M.WorkKind, M.ReplayPolicy):
        return getsizeof(value)
    reject()


def _validate_max_page_payload_bytes(value, /):
    """Return the same exact bounded budget integer, without a default."""
    return B._integer_raw(value, 1, MAX_LIST_PAGE_PAYLOAD_BYTES)


def _validate_acquire_max_page_payload_bytes(value, /):
    return B._integer_raw(value, 1, MAX_ACQUIRE_PAGE_PAYLOAD_BYTES)


def _validate_operation_budget(operation, value):
    if operation.statement.key == "W05":
        return _validate_acquire_max_page_payload_bytes(value)
    if operation.statement.key == "W03":
        return _validate_max_page_payload_bytes(value)
    if value is not None:
        reject()
    return None


def _budget_metadata_growth():
    # Mirror the existing seven-key A record and its one W03-only insertion.
    metadata = dict.fromkeys(("token", "capacity", "data", "borrows", "x", "builder", "profile"))
    before = getsizeof(metadata)
    metadata["max_page_payload_bytes"] = None
    return max(0, getsizeof(metadata) - before)


def _request_size(request, operation, *, max_page_payload_bytes=None):
    _validate_operation(operation)
    validate_request(request, operation.statement)
    _validate_operation_budget(operation, max_page_payload_bytes)
    size = (
        getsizeof(request)
        + getsizeof(request.parameters)
        + sum(
            getsizeof(v) + sum(_storage(item) for item in v) if type(v) is tuple else _storage(v)
            for v in request.parameters
        )
    )
    size += (
        getsizeof(request.context)
        + getsizeof(request.context.expected)
        + getsizeof(request.context.readiness)
    )
    if request.context.expected:
        admission = request.context.expected[0]
        identity, scope = admission.identity, admission.identity.scope
        size += getsizeof(admission) + getsizeof(identity) + getsizeof(scope)
        size += sum(
            _storage(getattr(admission, n))
            for n in (
                "schema_version",
                "semantic_input",
                "replay_input",
                "protected_binding",
                "replay_policy",
                "max_attempts",
                "deadline",
                "original_available_at",
            )
        )
        size += sum(
            _storage(getattr(identity, n))
            for n in (
                "work_id",
                "kind",
                "subscription_id",
                "namespace",
                "command_type",
                "idempotency_key",
            )
        )
        size += sum(
            _storage(getattr(scope, n))
            for n in ("canonical_version", "canonical", "application", "tenant", "owner")
        )
    if operation.statement.key in ("W03", "W05"):
        size += getsizeof(max_page_payload_bytes) + _budget_metadata_growth()
    return size


def _result_size(request, value, operation, *, max_page_payload_bytes=None):
    _validate_operation(operation)
    validate_request(request, operation.statement)
    _validate_operation_budget(operation, max_page_payload_bytes)
    if operation.statement.key == "W01":
        if (
            type(value) is not operation.result_types[0]
            or type(value.work_id) is not str
            or len(value.work_id) != 36
            or type(value.inserted) is not bool
        ):
            reject()
        size = getsizeof(value) + _storage(value.work_id) + _storage(value.inserted)
    elif operation.statement.key == "W05":
        size = _acquire_result_size(request, value, operation, max_page_payload_bytes)
    elif operation.statement.key == "W03":
        if type(value) is not tuple or len(value) > request.parameters[3]:
            reject()
        size = getsizeof(value)
        payload_bytes = 0
        for record in value:
            size += _job_result_size(record, operation)
            # The fixed graph preflight above rejects hooks before len().
            payload_bytes += _job_payload_size(record)
            if payload_bytes > max_page_payload_bytes:
                reject()
    elif operation.statement.key == "W04":
        size = _find_result_size(value, operation)
    elif value is None:
        size = getsizeof(None)
    else:
        size = _job_result_size(value, operation)
    operation.validate_result(request, value)
    return size


def _find_result_size(value, operation):
    """Only the fixed W04 observation/candidate graph, including work aliases."""
    if (
        type(value) is not operation.result_types[4]
        or type(value.decision) is not operation.result_types[5]
        or type(value.candidates) is not tuple
        or len(value.candidates) > 2
        or (
            value.original_work_id is not None
            and (type(value.original_work_id) is not str or len(value.original_work_id) != 36)
        )
    ):
        reject()
    members = vars(operation.result_types[5])["_member_map_"]
    if not any(value.decision is member for member in members.values()):
        reject()
    size = (
        getsizeof(value)
        + getsizeof(value.decision)
        + getsizeof(value.candidates)
        + _storage(value.original_work_id)
    )
    for candidate in value.candidates:
        if type(candidate) is not operation.result_types[3]:
            reject()
        size += getsizeof(candidate) + _work_result_size(candidate.work)
        size += (
            getsizeof(None) if candidate.job is None else _job_result_size(candidate.job, operation)
        )
    return size


def _work_result_size(work):
    """Preflight a fixed work-only candidate, including its full resolution."""
    if type(work) is not O.WorkObservation:
        reject()
    columns = C.get_statement("E15").result.columns
    scalars = []
    for col in columns[:39]:
        scalar = getattr(work, col.name)
        _scalar(scalar, col.wire_type, col.nullable, col.name)
        scalars.append(scalar)
    resolution = work.resolution
    if resolution is not None:
        if type(resolution) is not O.ResolutionObservation:
            reject()
        for col in columns[40:]:
            scalar = getattr(resolution, col.name[len("resolution_record_") :])
            _scalar(scalar, col.wire_type, col.nullable, col.name)
            scalars.append(scalar)
    size = getsizeof(work) + getsizeof(resolution) + sum(_storage(v) for v in scalars)
    # The consumer validates W04 semantics after this complete fixed preflight.
    return size


def _job_payload_size(record):
    """Fourteen finite output occurrences; equal/shared bytes count again."""
    work, details, payload = record.work, record.details, record.payload
    size = sum(
        len(value) if value is not None else 0
        for value in (
            work.intent_evidence,
            work.semantic_input,
            work.replay_input,
            work.protected_binding,
            work.result,
            details.protected_binding,
            payload.semantic_input,
            payload.sidecar,
            payload.reference,
            payload.recovery_metadata,
            payload.projection_metadata,
        )
    )
    if work.resolution is not None:
        resolution = work.resolution
        size += sum(
            len(value) if value is not None else 0
            for value in (resolution.result, resolution.evidence, resolution.binding)
        )
    return size


def _job_result_size(value, operation):
    """Preflight and measure one fixed graph, with no page-sized scratch."""
    if (
        type(value) is not operation.result_types[0]
        or type(value.work) is not O.WorkObservation
        or type(value.details) is not operation.result_types[1]
        or type(value.payload) is not operation.result_types[2]
    ):
        reject()
    work, details, payload = value.work, value.details, value.payload
    # Preflight full graph scalar fields before semantic helpers/getsizeof.
    columns = C.get_statement("E15").result.columns
    scalars = []
    for col in columns[:39]:
        scalar = getattr(work, col.name)
        _scalar(scalar, col.wire_type, col.nullable, col.name)
        scalars.append(scalar)
    resolution = work.resolution
    if resolution is not None:
        if type(resolution) is not O.ResolutionObservation:
            reject()
        for col in columns[40:]:
            name = col.name[len("resolution_record_") :]
            scalar = getattr(resolution, name)
            _scalar(scalar, col.wire_type, col.nullable, col.name)
            scalars.append(scalar)
    for name in _DETAILS:
        scalar = getattr(details, name)
        if name == "protected_binding":
            B._bytes_raw(scalar)
        elif scalar is None and name in ("tenant", "owner"):
            pass
        elif name == "work_id":
            if type(scalar) is not str or len(scalar) != 36:
                reject()
        else:
            B._identifier_raw(scalar)
        scalars.append(scalar)
    for name in _PAYLOAD:
        scalar = getattr(payload, name)
        if name == "material_state":
            if type(scalar) is not M.MaterialState:
                reject()
        elif name == "cleanup_policy":
            if type(scalar) is not M.CleanupPolicy:
                reject()
        elif scalar is None and name in (
            "sidecar",
            "reference",
            "codec",
            "key_version",
            "expires_at",
        ):
            pass
        elif name in ("codec", "key_version"):
            B._identifier_raw(scalar)
        elif name == "expires_at":
            B._instant_raw(scalar)
        else:
            B._bytes_raw(scalar)
        scalars.append(scalar)
    size = sum(getsizeof(v) for v in (value, work, details, payload))
    size += getsizeof(resolution) + sum(_storage(v) for v in scalars)
    O._validate_work_observation_raw(work)
    return size


# Conservative interpreter-derived storage upper bounds. References appearing
# repeatedly are charged repeatedly; no deduplication underestimates retention.
def _upper(wire, cap=0):
    if wire in (C.WireType.BYTEA_ARRAY, C.WireType.INT4_ARRAY):
        base = C.WireType.BYTEA if wire is C.WireType.BYTEA_ARRAY else C.WireType.INT4
        return getsizeof((None,) * 256) + 256 * _upper(base, 256)
    if wire is C.WireType.FLOAT8:
        return getsizeof(0.0)
    if wire is C.WireType.BYTEA:
        return getsizeof(b"") + cap
    if wire is C.WireType.TEXT:
        return getsizeof(chr(0x10FFFF)) + 4 * cap
    if wire is C.WireType.UUID:
        return getsizeof(UUID(int=0)) + getsizeof(2**128 - 1)
    if wire is C.WireType.TIMESTAMPTZ:
        return getsizeof(datetime(2026, 1, 1, tzinfo=timezone.utc))
    if wire is C.WireType.BOOL:
        return getsizeof(True)
    return getsizeof(2**64 - 1)


def _column_upper(columns):
    return sum(
        max(getsizeof(None), _upper(c.wire_type, _cap(c.name, c.wire_type))) for c in columns
    )


def _carrier_upper(cls):
    return getsizeof(object.__new__(cls))


def _preparation_capacity(operation, *, max_page_payload_bytes=None):
    _validate_operation(operation)
    _validate_operation_budget(operation, max_page_payload_bytes)
    size = (
        _carrier_upper(B.FrozenRequest)
        + getsizeof((None,) * len(operation.statement.parameters))
        + _column_upper(operation.statement.parameters)
        + _carrier_upper(B.ReturnContext)
        + getsizeof((None,) if operation.statement.key in ("W01", "W04") else ())
        + getsizeof(None)  # The retained ReturnContext.readiness referent.
    )
    if operation.statement.key in ("W01", "W04"):
        size += sum(
            _carrier_upper(cls) for cls in (M.AdmissionInput, M.WorkIdentity, M.ScopeEvidence)
        )
        size += (
            getsizeof(10**4096 - 1)
            + 3 * _upper(C.WireType.BYTEA, _MAX)
            + getsizeof(M.ReplayPolicy.DISABLED)
        )
        size += _upper(C.WireType.INT4) + 2 * _upper(C.WireType.TIMESTAMPTZ)
        size += (
            _upper(C.WireType.UUID) + getsizeof(M.WorkKind.JOB) + 4 * _upper(C.WireType.TEXT, 256)
        )
        size += (
            _upper(C.WireType.INT4)
            + _upper(C.WireType.BYTEA, 781)
            + 3 * _upper(C.WireType.BYTEA, 256)
        )
    if operation.statement.key in ("W03", "W05"):
        maximum = (
            MAX_ACQUIRE_PAGE_PAYLOAD_BYTES
            if operation.statement.key == "W05"
            else MAX_LIST_PAGE_PAYLOAD_BYTES
        )
        size += getsizeof(maximum) + _budget_metadata_growth()
    return size


def result_capacity(
    operation: WorkersNativeOperation, /, *, request=None, max_page_payload_bytes=None
) -> int:
    _validate_operation(operation)
    _validate_operation_budget(operation, max_page_payload_bytes)
    if operation.statement.key == "W01":
        return (
            _carrier_upper(operation.result_types[0])
            + _upper(C.WireType.TEXT, 36)
            + _upper(C.WireType.BOOL)
        )
    if operation.statement.key == "W02":
        return _job_result_capacity(operation)
    if operation.statement.key == "W04":
        return _find_result_capacity(operation)
    if operation.statement.key == "W05":
        return _acquire_result_capacity(request, operation, max_page_payload_bytes)
    n = _result_row_limit(request, operation)
    # Exact preallocated page lists coexist with their one tuple conversion.
    page_containers = getsizeof((None,) * n) + getsizeof([None] * n)
    final_page = (
        page_containers
        + n * (_job_result_capacity(operation) - _LIST_ROW_PAYLOAD_MAX)
        + min(n * _LIST_ROW_PAYLOAD_MAX, max_page_payload_bytes)
    )
    columns = operation.statement.result.columns
    canonical_row = getsizeof((None,) * len(columns)) + _column_upper(columns)
    canonical_page = (
        page_containers
        + n * (canonical_row - _LIST_ROW_PAYLOAD_MAX)
        + min(n * _LIST_ROW_PAYLOAD_MAX, max_page_payload_bytes)
    )
    transport_row = getsizeof((None,) * (len(columns) + 1)) + getsizeof(b"") + 1
    for column in columns:
        cell = _binary_upper(column)
        transport_row += max(getsizeof(None), cell) if column.nullable else cell
    sentinel_backing = (
        getsizeof((None,) * (n + 1))
        + (n + 1) * (transport_row - _LIST_ROW_PAYLOAD_MAX)
        + min((n + 1) * _LIST_ROW_PAYLOAD_MAX, max_page_payload_bytes)
    )
    return final_page + canonical_page + sentinel_backing


def _result_row_limit(request, operation, /):
    """Use the retained validated request, never an independent caller count."""
    _validate_operation(operation)
    validate_request(request, operation.statement)
    return (
        request.parameters[3]
        if operation.statement.key in ("W03", "W05")
        else 2
        if operation.statement.key == "W04"
        else 1
    )


def _binary_upper(column):
    wire = column.wire_type
    if wire is C.WireType.BYTEA:
        width = _cap(column.name, wire)
    elif wire is C.WireType.TEXT:
        width = 4 * _cap(column.name, wire)
    elif wire is C.WireType.BOOL:
        width = 1
    elif wire is C.WireType.INT4:
        width = 4
    elif wire is C.WireType.UUID:
        width = 16
    else:  # INT8, XID8 and TIMESTAMPTZ have fixed eight-byte binary values.
        width = 8
    return getsizeof(b"") + width


def _job_result_capacity(operation):
    # R: unchanged W02 finite JobRecord graph upper bound.
    size = sum(_carrier_upper(cls) for cls in operation.result_types[:3])
    size += _carrier_upper(O.WorkObservation) + _carrier_upper(O.ResolutionObservation)
    size += _column_upper(C.get_statement("E15").result.columns[:39]) + _column_upper(
        C.get_statement("E15").result.columns[40:]
    )
    size += (
        _upper(C.WireType.TEXT, 36)
        + 3 * _upper(C.WireType.TEXT, 256)
        + _upper(C.WireType.BYTEA, _MAX)
    )
    size += (
        5 * _upper(C.WireType.BYTEA, _MAX)
        + 2 * _upper(C.WireType.TEXT, 256)
        + _upper(C.WireType.TIMESTAMPTZ)
    )
    size += getsizeof(M.MaterialState.PRESENT) + getsizeof(M.CleanupPolicy.RETAIN)
    return size


def _work_result_capacity():
    columns = C.get_statement("E15").result.columns
    return (
        _carrier_upper(O.WorkObservation)
        + _carrier_upper(O.ResolutionObservation)
        + _column_upper(columns[:39])
        + _column_upper(columns[40:])
    )


def _find_result_capacity(operation):
    # Fixed two-candidate graph; work is charged again even when aliased by job.
    containers = getsizeof((None,) * 2) + getsizeof([None] * 2)
    typed = (
        _carrier_upper(operation.result_types[4])
        + getsizeof(operation.result_types[5].NEW)
        + _upper(C.WireType.TEXT, 36)
        + containers
        + 2
        * (
            _carrier_upper(operation.result_types[3])
            + _work_result_capacity()
            + _job_result_capacity(operation)
        )
    )
    columns = operation.statement.result.columns
    canonical = containers + 2 * (getsizeof((None,) * len(columns)) + _column_upper(columns))
    transport = getsizeof((None,) * (len(columns) + 1)) + getsizeof(b"") + 1
    transport += sum(max(getsizeof(None), _binary_upper(col)) for col in columns)
    sentinel = getsizeof((None,) * 3) + 3 * transport
    return typed + canonical + sentinel


def _fence_size(value):
    M._validate_fence_raw(value)
    return getsizeof(value) + sum(_storage(getattr(value, name)) for name in M.Fence.__slots__)


def _acquire_result_size(request, value, operation, budget):
    O._validate_scan_page_raw(value)
    if len(value.items) > request.parameters[3] or type(value.next_cursor) not in (
        UUID,
        type(None),
    ):
        reject()
    size = (
        getsizeof(value)
        + getsizeof(value.items)
        + _storage(value.visited)
        + _storage(value.next_cursor)
        + _storage(value.pass_exhausted)
    )
    # Canonical framing tags occur once per emitted row, even when interned.
    payload_bytes = len(b"header")
    columns = C.get_statement("E15").result.columns
    for claim in value.items:
        if type(claim) is not operation.result_types[3]:
            reject()
        size += (
            getsizeof(claim) + _job_result_size(claim.record, operation) + _fence_size(claim.fence)
        )
        work, details, payload = claim.record.work, claim.record.details, claim.record.payload
        if work.resolution is not None:
            reject()
        if (
            claim.fence.work_id != work.work_id
            or claim.fence.token != work.token
            or claim.fence.ownership_revision != work.ownership_revision
            or claim.fence.cycle != work.cycle
            or claim.fence.expected_attempt != work.attempt_count
        ):
            reject()
        payload_bytes += len(b"item")
        for col in columns[:39]:
            scalar = getattr(work, col.name)
            if scalar is not None and col.wire_type in (C.WireType.BYTEA, C.WireType.TEXT):
                payload_bytes += (
                    len(scalar) if type(scalar) is bytes else len(scalar.encode("utf-8"))
                )
        for name in ("application", "tenant", "owner", "protected_binding"):
            scalar = getattr(details, name)
            if scalar is not None:
                payload_bytes += (
                    len(scalar) if type(scalar) is bytes else len(scalar.encode("utf-8"))
                )
        for name in _PAYLOAD:
            scalar = getattr(payload, name)
            if type(scalar) in (M.MaterialState, M.CleanupPolicy):
                payload_bytes += len(scalar.value.encode("utf-8"))
            elif type(scalar) is bytes:
                payload_bytes += len(scalar)
            elif type(scalar) is str:
                payload_bytes += len(scalar.encode("utf-8"))
        if payload_bytes > budget:
            reject()
    if payload_bytes > budget:
        reject()
    return size


def _acquire_result_capacity(request, operation, budget):
    n = _result_row_limit(request, operation)
    variable = min(budget, n * _LIST_ROW_PAYLOAD_MAX)
    fence = _carrier_upper(M.Fence) + 2 * _upper(C.WireType.UUID) + 3 * _upper(C.WireType.INT8)
    typed = (
        _carrier_upper(O.ScanPage)
        + getsizeof([None] * n)
        + getsizeof((None,) * n)
        + _upper(C.WireType.INT4)
        + _upper(C.WireType.UUID)
        + _upper(C.WireType.BOOL)
        + n
        * (
            _carrier_upper(operation.result_types[3])
            + fence
            + _job_result_capacity(operation)
            - _LIST_ROW_PAYLOAD_MAX
        )
    )
    columns = operation.statement.result.columns
    canonical_row = (
        getsizeof((None,) * len(columns)) + _column_upper(columns) - _LIST_ROW_PAYLOAD_MAX
    )
    canonical = getsizeof([None] * (n + 1)) + getsizeof((None,) * (n + 1)) + (n + 1) * canonical_row
    wire_row = getsizeof((None,) * (len(columns) + 1)) + getsizeof(b"") + 1
    wire_row += sum(max(getsizeof(None), _binary_upper(col)) for col in columns)
    wire_row -= _LIST_ROW_PAYLOAD_MAX
    wire = getsizeof((None,) * (n + 2)) + (n + 2) * wire_row
    return typed + canonical + wire + 3 * variable

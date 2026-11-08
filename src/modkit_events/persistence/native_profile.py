"""Fixed import-neutral Workers W01/W02 semantic and retained graph profile.

No Workers import, driver, I/O, registration, or arbitrary graph traversal.
Startup component provenance is cooperative, not authentication of Python code.
"""

from dataclasses import Field, dataclass, fields
from datetime import datetime, timezone
from sys import getsizeof
from types import FunctionType
from uuid import UUID

from . import bindings as B
from . import catalog as C
from . import models as M
from . import observations as O
from .errors import _reject_validation as reject

_MAX = 1048576
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
        or len(statement.parameters) not in (1, 29)
        or type(statement.result) is not C.ResultSpec
        or type(statement.result.columns) is not tuple
        or len(statement.result.columns) not in (2, 71)
    ):
        reject()
    C._validate_statement_spec(statement, _reject=reject)
    C._validate_result_spec(statement.result, _reject=reject)
    if statement.key not in ("W01", "W02"):
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
    else:
        params = (("work_id", C.WireType.UUID, False),)
        cols = (
            tuple((c.name, c.wire_type, c.nullable) for c in C.get_statement("E15").result.columns)
            + _JOB
        )
        record, cardinality, mutation = C.RecordKind.JOB, C.CardinalityKind.OPTIONAL_ONE, False
    if (
        tuple((p.name, p.wire_type, p.nullable) for p in statement.parameters) != params
        or tuple((c.name, c.wire_type, c.nullable) for c in statement.result.columns) != cols
        or any(p.constraint.value != p.name for p in statement.parameters)
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
    _carrier(
        operation.request_type,
        "modkit_workers.persistence.models",
        "JobSubmitRequest" if submit else "JobReadRequest",
        ("job",) if submit else ("work_id",),
    )
    if type(operation.result_types) is not tuple or len(operation.result_types) != (
        1 if submit else 3
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
    for cls, (name, names) in zip(operation.result_types, result_shapes):
        _carrier(cls, "modkit_workers.persistence.observations", name, names)
    suffix = "submit" if submit else "read"
    callbacks = (
        (operation.build_request, "bindings", "_submit_raw" if submit else "_read_job_raw"),
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
    if statement.key == "W02":
        if context.expected:
            reject()
        return
    if len(context.expected) != 1:
        reject()
    expected = context.expected[0]
    projected = B._admission_values_raw(expected)
    if expected.identity.kind is not M.WorkKind.JOB or expected.identity.namespace != "jobs":
        reject()
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
    if value is None or type(value) in (bytes, str, bool, int):
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


def _request_size(request, operation):
    _validate_operation(operation)
    validate_request(request, operation.statement)
    size = (
        getsizeof(request)
        + getsizeof(request.parameters)
        + sum(_storage(v) for v in request.parameters)
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
    return size


def _result_size(request, value, operation):
    _validate_operation(operation)
    validate_request(request, operation.statement)
    if operation.statement.key == "W01":
        if (
            type(value) is not operation.result_types[0]
            or type(value.work_id) is not str
            or len(value.work_id) != 36
            or type(value.inserted) is not bool
        ):
            reject()
        size = getsizeof(value) + _storage(value.work_id) + _storage(value.inserted)
    elif value is None:
        size = getsizeof(None)
    else:
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
    operation.validate_result(request, value)
    return size


# Conservative interpreter-derived storage upper bounds. References appearing
# repeatedly are charged repeatedly; no deduplication underestimates retention.
def _upper(wire, cap=0):
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


def _preparation_capacity(operation):
    _validate_operation(operation)
    size = (
        _carrier_upper(B.FrozenRequest)
        + getsizeof((None,) * len(operation.statement.parameters))
        + _column_upper(operation.statement.parameters)
        + _carrier_upper(B.ReturnContext)
        + getsizeof((None,) if operation.statement.key == "W01" else ())
        + getsizeof(None)  # The retained ReturnContext.readiness referent.
    )
    if operation.statement.key == "W01":
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
    return size


def result_capacity(operation: WorkersNativeOperation, /) -> int:
    _validate_operation(operation)
    if operation.statement.key == "W01":
        return (
            _carrier_upper(operation.result_types[0])
            + _upper(C.WireType.TEXT, 36)
            + _upper(C.WireType.BOOL)
        )
    size = sum(_carrier_upper(cls) for cls in operation.result_types)
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

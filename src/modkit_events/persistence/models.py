"""Immutable managed persistence inputs, independent of drivers and workers."""
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from uuid import UUID
from hashlib import sha256
from .errors import _boundary, _reject_validation
from ..models import Event


class WorkKind(Enum):
    JOB = 'job'
    INBOX = 'inbox'


class ReplayPolicy(Enum):
    DISABLED = 'disabled'
    APPLICATION_SAFE = 'application_safe'


class MaterialState(Enum):
    ABSENT = 'absent'
    PRESENT = 'present'
    ERASED = 'erased'


class CleanupPolicy(Enum):
    RETAIN = 'retain'
    ERASE_AFTER_TERMINAL = 'erase_after_terminal'


def _validate_canonical_evidence(value, *, _reject=None):
    if (
        type(value.version) is not int
        or value.version != 1
        or type(value.content) is not bytes
        or len(value.content) > 1048576
        or type(value.digest) is not bytes
        or len(value.digest) != 32
        or sha256(value.content).digest() != value.digest
    ):
        if _reject is not None:
            _reject()
        raise ValueError


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CanonicalEvidence:
    version: int
    content: bytes
    digest: bytes

    @_boundary
    def __post_init__(self):
        _validate_canonical_evidence(self)


@dataclass(slots=True)
class _CanonicalEvidenceDraft:
    version: object
    content: object
    digest: object


def _canonical_evidence_raw(version, content, digest):
    """Validate the shared evidence contract before creating its exact carrier."""
    draft = _CanonicalEvidenceDraft(version, content, digest)
    _validate_canonical_evidence(draft, _reject=_reject_validation)
    evidence = object.__new__(CanonicalEvidence)
    object.__setattr__(evidence, "version", draft.version)
    object.__setattr__(evidence, "content", draft.content)
    object.__setattr__(evidence, "digest", draft.digest)
    return evidence


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ScopeEvidence:
    canonical_version: int
    canonical: bytes
    application: bytes
    tenant: bytes | None
    owner: bytes | None

    @_boundary
    def __post_init__(self):
        _validate_scope_evidence_core(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ProtectedBindingInput:
    material_state: MaterialState
    codec: str | None
    key_version: str | None
    expires_at: datetime | None
    cleanup_policy: CleanupPolicy
    sidecar: bytes | None
    reference: bytes | None
    content_binding: bytes
    recovery_metadata: object
    projection_metadata: object

    @_boundary
    def __post_init__(self):
        from .bindings import _normalize_material
        for name,value in _normalize_material(self).items():
            object.__setattr__(self,name,value)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EventInput:
    event: Event
    replay_envelope: bytes

    @_boundary
    def __post_init__(self):
        from .bindings import validate_event_replay, canonical_event
        if type(self.event) is not Event or type(self.replay_envelope) is not bytes:
            raise ValueError
        if canonical_event(validate_event_replay(self.replay_envelope)) != canonical_event(self.event):
            raise ValueError

    @property
    def evidence(self):
        from .bindings import canonical_event
        return canonical_event(self.event)

    @property
    def event_id_bytes(self):
        return self.event.event_id.encode('utf-8')


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class WorkIdentity:
    work_id: UUID
    kind: WorkKind
    subscription_id: str | None
    namespace: str
    command_type: str
    scope: ScopeEvidence
    idempotency_key: str | None

    @_boundary
    def __post_init__(self):
        _validate_work_identity_core(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AdmissionInput:
    identity: WorkIdentity
    schema_version: int
    semantic_input: bytes
    replay_input: bytes
    protected_binding: bytes
    replay_policy: ReplayPolicy
    max_attempts: int
    deadline: datetime | None
    original_available_at: datetime

    @_boundary
    def __post_init__(self):
        _validate_admission_input_core(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Fence:
    work_id: UUID
    token: UUID
    ownership_revision: int
    cycle: int
    expected_attempt: int

    @_boundary
    def __post_init__(self):
        from .bindings import _integer
        if type(self.work_id) is not UUID or type(self.token) is not UUID:raise ValueError
        _integer(self.ownership_revision,1,2**63-1);_integer(self.cycle,1,1);_integer(self.expected_attempt,0,1000)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class PublicationFence:
    event_id: str
    token: UUID
    ownership_revision: int

    @_boundary
    def __post_init__(self):
        from .bindings import _integer,_identifier
        _identifier(self.event_id);_integer(self.ownership_revision,1,2**63-1)
        if type(self.token) is not UUID:raise ValueError


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class GuardRef:
    guard_id: UUID
    work_id: UUID
    root_xid: int
    token: UUID
    ownership_revision: int
    cycle: int
    expected_attempt: int

    @_boundary
    def __post_init__(self):
        from .bindings import _integer
        if type(self.guard_id) is not UUID:raise ValueError
        _integer(self.root_xid,1,2**64-1)
        Fence(work_id=self.work_id,token=self.token,ownership_revision=self.ownership_revision,cycle=self.cycle,expected_attempt=self.expected_attempt)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Capability:
    command_type: str
    schema_version: int

    @_boundary
    def __post_init__(self):
        from .bindings import _integer,_identifier
        _identifier(self.command_type);_integer(self.schema_version,1,2147483647)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class WorkCursor:
    created_at: datetime
    work_id: UUID

    @_boundary
    def __post_init__(self):
        from .bindings import _instant
        if type(self.work_id) is not UUID:raise ValueError
        object.__setattr__(self,'created_at',_instant(self.created_at))


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class HistoryCursor:
    after_id: int

    @_boundary
    def __post_init__(self):
        from .bindings import _integer
        _integer(self.after_id,0,2**63-1)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AttemptCursor:
    after_cycle: int
    after_attempt: int

    @_boundary
    def __post_init__(self):
        from .bindings import _integer
        _integer(self.after_cycle,0,2147483647);_integer(self.after_attempt,0,2147483647)


def _retain_field(value, name, normalized, *, _reject=None):
    if _reject is None:
        object.__setattr__(value, name, normalized)
    elif getattr(value, name) is not normalized:
        _reject_validation()

def _validate_scope_evidence_core(self, *, _reject=None):
    from . import scope as S
    from .bindings import _reject_scalar

    decode_canonical_scope = (
        S.decode_canonical_scope if _reject is None else S._decode_canonical_scope_raw
    )
    decode_scope_fields = (
        S.decode_scope_fields if _reject is None else S._decode_scope_fields_raw
    )
    if (
        type(self.canonical_version) is not int
        or self.canonical_version != 1
        or type(self.canonical) is not bytes
        or type(self.application) is not bytes
        or any(
            x is not None and type(x) is not bytes for x in (self.tenant, self.owner)
        )
    ):
        _reject_scalar(_reject)
    if decode_canonical_scope(self.canonical) != decode_scope_fields(
        self.application, self.tenant, self.owner
    ):
        _reject_scalar(_reject)


def _validate_work_identity_core(self, *, _reject=None):
    from .bindings import _identifier, _identifier_raw, _reject_scalar, _uuid_raw

    if _reject is not None:
        _identifier = _identifier_raw
        _uuid_raw(self.work_id)
    if (
        type(self.work_id) is not UUID
        or type(self.kind) is not WorkKind
        or type(self.scope) is not ScopeEvidence
    ):
        _reject_scalar(_reject)
    _validate_scope_evidence_core(self.scope, _reject=_reject)
    if (self.kind is WorkKind.JOB) != (self.subscription_id is None):
        _reject_scalar(_reject)
    for value in (self.namespace, self.command_type):
        _identifier(value)
    for value in (self.subscription_id, self.idempotency_key):
        if value is not None:
            _identifier(value)


def _validate_admission_input_core(self, *, _reject=None, _intent=True):
    from .bindings import (
        _bytes,
        _instant,
        _integer,
        _reject_scalar,
        canonical_event,
        canonical_intent,
        canonical_json,
        decode_mapping_replay,
        decode_protected_binding,
        validate_event_replay,
        version_to_decimal,
    )

    if _reject is not None:
        from .bindings import (
            _bytes_raw as _bytes,
        )
        from .bindings import (
            _canonical_event_raw as canonical_event,
        )
        from .bindings import (
            _canonical_intent_raw as canonical_intent,
        )
        from .bindings import (
            _canonical_json_raw as canonical_json,
        )
        from .bindings import (
            _decode_mapping_replay_raw as decode_mapping_replay,
        )
        from .bindings import (
            _decode_protected_binding_raw as decode_protected_binding,
        )
        from .bindings import (
            _instant_raw as _instant,
        )
        from .bindings import (
            _integer_raw as _integer,
        )
        from .bindings import (
            _validate_event_replay_raw as validate_event_replay,
        )
        from .bindings import (
            _version_to_decimal_raw as version_to_decimal,
        )
    if (
        type(self.identity) is not WorkIdentity
        or type(self.replay_policy) is not ReplayPolicy
    ):
        _reject_scalar(_reject)
    _validate_work_identity_core(self.identity, _reject=_reject)
    version_to_decimal(self.schema_version)
    _integer(self.max_attempts, 1, 1000)
    for name in ("semantic_input", "replay_input", "protected_binding"):
        _retain_field(self, name, _bytes(getattr(self, name)), _reject=_reject)
    _retain_field(
        self,
        "original_available_at",
        _instant(self.original_available_at),
        _reject=_reject,
    )
    if self.deadline is not None:
        _retain_field(self, "deadline", _instant(self.deadline), _reject=_reject)
    decode_protected_binding(self.protected_binding)
    if self.identity.kind is WorkKind.JOB:
        expected = canonical_json(decode_mapping_replay(self.replay_input))
    else:
        event = validate_event_replay(self.replay_input)
        if (
            event.schema_version != self.schema_version
            or event.name != self.identity.command_type
        ):
            _reject_scalar(_reject)
        expected = canonical_event(event).content
    if expected != self.semantic_input:
        _reject_scalar(_reject)
    if _intent:
        canonical_intent(self)


def _validate_scope_evidence_raw(value, /):
    if type(value) is not ScopeEvidence:
        _reject_validation()
    _validate_scope_evidence_core(value, _reject=_reject_validation)


def _scope_evidence_raw(*, canonical_version, canonical, application, tenant, owner):
    from types import SimpleNamespace

    draft = SimpleNamespace(
        canonical_version=canonical_version,
        canonical=canonical,
        application=application,
        tenant=tenant,
        owner=owner,
    )
    _validate_scope_evidence_core(draft, _reject=_reject_validation)
    value = object.__new__(ScopeEvidence)
    object.__setattr__(value, "canonical_version", canonical_version)
    object.__setattr__(value, "canonical", canonical)
    object.__setattr__(value, "application", application)
    object.__setattr__(value, "tenant", tenant)
    object.__setattr__(value, "owner", owner)
    return value


def _validate_work_identity_raw(value, /):
    if type(value) is not WorkIdentity:
        _reject_validation()
    _validate_work_identity_core(value, _reject=_reject_validation)


def _work_identity_raw(
    *, work_id, kind, subscription_id, namespace, command_type, scope, idempotency_key
):
    from types import SimpleNamespace

    draft = SimpleNamespace(
        work_id=work_id,
        kind=kind,
        subscription_id=subscription_id,
        namespace=namespace,
        command_type=command_type,
        scope=scope,
        idempotency_key=idempotency_key,
    )
    _validate_work_identity_core(draft, _reject=_reject_validation)
    value = object.__new__(WorkIdentity)
    object.__setattr__(value, "work_id", work_id)
    object.__setattr__(value, "kind", kind)
    object.__setattr__(value, "subscription_id", subscription_id)
    object.__setattr__(value, "namespace", namespace)
    object.__setattr__(value, "command_type", command_type)
    object.__setattr__(value, "scope", scope)
    object.__setattr__(value, "idempotency_key", idempotency_key)
    return value


def _validate_admission_input_raw(value, /):
    if type(value) is not AdmissionInput:
        _reject_validation()
    _validate_admission_input_core(value, _reject=_reject_validation)


def _admission_input_raw(
    *,
    identity,
    schema_version,
    semantic_input,
    replay_input,
    protected_binding,
    replay_policy,
    max_attempts,
    deadline,
    original_available_at,
):
    from types import SimpleNamespace

    draft = SimpleNamespace(
        identity=identity,
        schema_version=schema_version,
        semantic_input=semantic_input,
        replay_input=replay_input,
        protected_binding=protected_binding,
        replay_policy=replay_policy,
        max_attempts=max_attempts,
        deadline=deadline,
        original_available_at=original_available_at,
    )
    # Fixed fields are bounded and exact before final carrier construction.
    _validate_admission_input_core(draft, _reject=_reject_validation, _intent=False)
    value = object.__new__(AdmissionInput)
    object.__setattr__(value, "identity", identity)
    object.__setattr__(value, "schema_version", schema_version)
    object.__setattr__(value, "semantic_input", semantic_input)
    object.__setattr__(value, "replay_input", replay_input)
    object.__setattr__(value, "protected_binding", protected_binding)
    object.__setattr__(value, "replay_policy", replay_policy)
    object.__setattr__(value, "max_attempts", max_attempts)
    object.__setattr__(value, "deadline", deadline)
    object.__setattr__(value, "original_available_at", original_available_at)
    from .bindings import _canonical_intent_raw

    _canonical_intent_raw(value)
    return value


def _validate_fence_raw(value, /):
    """Validate the exact shared carrier without a sanitizing boundary."""
    from .bindings import _integer_raw, _uuid_raw

    if type(value) is not Fence:
        _reject_validation()
    _uuid_raw(value.work_id)
    _uuid_raw(value.token)
    _integer_raw(value.ownership_revision, 1, 2**63 - 1)
    _integer_raw(value.cycle, 1, 1)
    _integer_raw(value.expected_attempt, 0, 1000)


def _fence_raw(*, work_id, token, ownership_revision, cycle, expected_attempt):
    value = object.__new__(Fence)
    object.__setattr__(value, "work_id", work_id)
    object.__setattr__(value, "token", token)
    object.__setattr__(value, "ownership_revision", ownership_revision)
    object.__setattr__(value, "cycle", cycle)
    object.__setattr__(value, "expected_attempt", expected_attempt)
    _validate_fence_raw(value)
    return value

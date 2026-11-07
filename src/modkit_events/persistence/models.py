"""Immutable managed persistence inputs, independent of drivers and workers."""
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from uuid import UUID
from hashlib import sha256
from .errors import _boundary, _reject_validation
from .scope import decode_canonical_scope, decode_scope_fields
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
        if type(self.canonical_version) is not int or self.canonical_version != 1 or type(self.canonical) is not bytes or type(self.application) is not bytes or any(x is not None and type(x) is not bytes for x in (self.tenant,self.owner)):
            raise ValueError
        if decode_canonical_scope(self.canonical) != decode_scope_fields(self.application,self.tenant,self.owner):
            raise ValueError


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
        from .bindings import _identifier
        if type(self.work_id) is not UUID or type(self.kind) is not WorkKind or type(self.scope) is not ScopeEvidence:raise ValueError
        self.scope.__post_init__()
        if (self.kind is WorkKind.JOB)!=(self.subscription_id is None):raise ValueError
        for value in (self.namespace,self.command_type):_identifier(value)
        for value in (self.subscription_id,self.idempotency_key):
            if value is not None:_identifier(value)


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
        from .bindings import (_bytes,_instant,_integer,version_to_decimal,canonical_json,
            decode_mapping_replay,validate_event_replay,canonical_event,decode_protected_binding,canonical_intent)
        if type(self.identity) is not WorkIdentity or type(self.replay_policy) is not ReplayPolicy:raise ValueError
        self.identity.__post_init__();version_to_decimal(self.schema_version);_integer(self.max_attempts,1,1000)
        for name in ('semantic_input','replay_input','protected_binding'):object.__setattr__(self,name,_bytes(getattr(self,name)))
        object.__setattr__(self,'original_available_at',_instant(self.original_available_at))
        if self.deadline is not None:object.__setattr__(self,'deadline',_instant(self.deadline))
        decode_protected_binding(self.protected_binding)
        if self.identity.kind is WorkKind.JOB:
            expected=canonical_json(decode_mapping_replay(self.replay_input))
        else:
            event=validate_event_replay(self.replay_input)
            if event.schema_version!=self.schema_version or event.name!=self.identity.command_type:raise ValueError
            expected=canonical_event(event).content
        if expected!=self.semantic_input:raise ValueError
        canonical_intent(self)


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

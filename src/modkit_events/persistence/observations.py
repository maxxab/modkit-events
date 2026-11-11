"""Statement-local observations never clear an existing uncertain incident."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Generic, TypeVar
from uuid import UUID

from .bindings import _bytes, _instant, _integer, canonical_intent, version_from_decimal
from .errors import ErrorCode, _boundary, _observation_boundary
from .models import AdmissionInput, ReplayPolicy, ScopeEvidence, WorkIdentity, WorkKind


class OperationState(Enum):
    NOT_SENT = "not_sent"
    SENT_UNCONFIRMED = "sent_unconfirmed"
    STAGED = "staged"


@dataclass(frozen=True, slots=True, kw_only=True)
class OperationObservation:
    key: str
    state: OperationState
    error_code: ErrorCode | None

    @_boundary
    def __post_init__(self):
        if (
            type(self.key) is not str
            or self.key
            not in tuple(f"E{i:02d}" for i in range(1, 35))
            + tuple(f"W{i:02d}" for i in range(1, 6))
            or type(self.state) is not OperationState
            or self.error_code is not None
            and type(self.error_code) is not ErrorCode
        ):
            raise ValueError


def _valid_uncertainty(value):
    """Unsanitized exact-record predicate; internal failures are not invalid input."""
    if type(value) is not Uncertainty:
        return False
    return _valid_uncertainty_fields(value)


def _valid_uncertainty_fields(value):
    """Retain the public dataclass field-validation contract."""
    present = getattr(value, "present", None)
    categories = getattr(value, "categories", None)
    return (
        type(present) is bool
        and type(categories) is frozenset
        and all(type(code) is ErrorCode for code in categories)
        and present == bool(categories)
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Uncertainty:
    present: bool
    categories: frozenset[ErrorCode]

    @_boundary
    def __post_init__(self):
        if not _valid_uncertainty_fields(self):
            raise ValueError


def _uncertainty_from_categories(categories):
    """Private raw allocation seam, shared by contextual and public boundaries."""
    if type(categories) is not frozenset or any(type(code) is not ErrorCode for code in categories):
        raise ValueError
    result = object.__new__(Uncertainty)
    object.__setattr__(result, "present", bool(categories))
    object.__setattr__(result, "categories", categories)
    return result


def _join_uncertainty(current, incoming):
    """Sole union implementation; callers choose their own error boundary."""
    if not _valid_uncertainty(current) or not _valid_uncertainty(incoming):
        raise ValueError
    return _uncertainty_from_categories(current.categories | incoming.categories)


@_boundary
def join_uncertainty(current, incoming):
    return _join_uncertainty(current, incoming)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ResolutionObservation:
    operation_id: UUID
    operation_kind: str
    work_id: UUID
    expected_revision: int
    cycle: int
    attempt: int
    dispatch_id: UUID
    outcome: str
    retry_at: datetime | None
    result: bytes | None
    result_digest: bytes | None
    reason: str | None
    evidence: bytes
    binding: bytes
    resolution_root_xid: int
    recorded_at: datetime

    @_observation_boundary
    def __post_init__(self):
        _validate_resolution_observation_core(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class WorkObservation:
    work_id: UUID
    kind: str
    subscription_id: bytes | None
    namespace: bytes
    command_type: bytes
    schema_version_decimal: bytes
    runnable_version: int | None
    canonical_version: int
    scope_evidence: bytes
    scope_application: bytes
    scope_tenant: bytes | None
    scope_owner: bytes | None
    idempotency_key: bytes | None
    intent_evidence: bytes
    semantic_input: bytes
    replay_input: bytes
    protected_binding: bytes
    replay_policy: str
    max_attempts: int
    deadline: datetime | None
    original_available_at: datetime
    state: str
    cancellation_requested: bool
    token: UUID | None
    ownership_revision: int
    lease_until: datetime | None
    available_at: datetime
    cycle: int
    attempt_count: int
    dispatch_id: UUID | None
    result: bytes | None
    created_at: datetime
    updated_at: datetime
    success_origin: str | None
    completion_guard_id: UUID | None
    final_fence_at: datetime | None
    completion_result_digest: bytes | None
    resolution_operation_id: UUID | None
    terminal_resolution_operation_id: UUID | None
    resolution: ResolutionObservation | None

    @_observation_boundary
    def __post_init__(self):
        _validate_work_observation_core(self)

    @property
    def schema_version(self):
        return version_from_decimal(self.schema_version_decimal)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AdmissionRow:
    work_id: UUID
    inserted: bool

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class GuardRow:
    guard_id: UUID
    work_id: UUID
    root_xid: int
    token: UUID
    ownership_revision: int
    cycle: int
    expected_attempt: int
    satisfied: bool
    final_fence_at: datetime | None
    terminal_state: str | None
    result_digest: bytes | None

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class SubscriptionRow:
    subscription_id: bytes
    manifest: bytes
    consumer_group: bytes
    capacity: int
    nonterminal_count: int
    created_at: datetime

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class OutboxRow:
    event_id: bytes
    canonical_version: int
    envelope_evidence: bytes
    replay_input: bytes
    state: str
    token: UUID | None
    ownership_revision: int
    lease_until: datetime | None
    intent_id: UUID | None
    receipt: bytes | None
    outcome_evidence: bytes | None
    created_at: datetime
    updated_at: datetime

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class WorkHistoryRow:
    history_id: int
    work_id: UUID
    cycle: int
    attempt: int
    transition: str
    reason: str
    token: UUID | None
    ownership_revision: int
    evidence: bytes
    recorded_at: datetime

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DeliveryRow:
    history_id: int
    work_id: UUID
    broker_reference: bytes
    transport_observation: bytes
    recorded_at: datetime

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class PublicationRow:
    history_id: int
    event_id: bytes
    intent_id: UUID | None
    operation_id: UUID | None
    status: str
    receipt: bytes | None
    evidence: bytes
    binding: bytes
    recorded_at: datetime

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AttemptRow:
    work_id: UUID
    cycle: int
    attempt: int
    dispatch_id: UUID
    effect_id: bytes
    request_evidence: bytes
    provider_key_reference: bytes | None
    dispatch_root_xid: int
    outcome: str
    evidence: bytes
    recorded_at: datetime

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class SettlementObservation:
    operation_id: UUID
    work_id: UUID
    token: UUID
    expected_revision: int
    cycle: int
    attempt: int
    dispatch_id: UUID
    failed_business_root: int
    reason: str
    evidence: bytes
    binding: bytes
    resulting_revision: int
    recorded_at: datetime

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class RepairObservation:
    operation_id: UUID
    event_id: bytes
    expected_revision: int
    status: str
    receipt: bytes | None
    evidence: bytes
    binding: bytes
    resulting_revision: int
    recorded_at: datetime

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class SchemaStatus:
    component: str
    version: int
    migration_digest: bytes
    catalog_contract_id: str
    scope_format_id: str
    intent_format_id: str

    @_observation_boundary
    def __post_init__(self):
        from .rows import _validate_record

        _validate_record(self)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class InboxObservation(WorkObservation):
    inbox_subscription_id: bytes
    original_event_id: bytes
    envelope_evidence: bytes
    original_replay_input: bytes

    @_observation_boundary
    def __post_init__(self):
        WorkObservation.__post_init__(self)
        from .rows import _validate_inbox

        _validate_inbox(self, True)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class InboxCandidate(WorkObservation):
    inbox_half_present: bool
    inbox_subscription_id: bytes | None
    original_event_id: bytes | None
    envelope_evidence: bytes | None
    original_replay_input: bytes | None

    @_observation_boundary
    def __post_init__(self):
        WorkObservation.__post_init__(self)
        from .rows import _validate_inbox

        if type(self.inbox_half_present) is not bool:
            raise ValueError
        _validate_inbox(self, self.inbox_half_present)


_T = TypeVar("_T")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ScanFrame:
    visited: int
    next_cursor: UUID | bytes | None
    pass_exhausted: bool
    item_columns: tuple

    @_observation_boundary
    def __post_init__(self):
        _integer(self.visited, 0, 4096)
        if (
            type(self.pass_exhausted) is not bool
            or type(self.item_columns) is not tuple
            or any(type(row) is not tuple for row in self.item_columns)
        ):
            raise ValueError
        if self.next_cursor is not None and type(self.next_cursor) not in (UUID, bytes):
            raise ValueError
        if type(self.next_cursor) is bytes and len(self.next_cursor) != 32:
            raise ValueError
        if len(self.item_columns) > 256 or len(self.item_columns) > self.visited:
            raise ValueError


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ScanPage(Generic[_T]):
    items: tuple[_T, ...]
    visited: int
    next_cursor: UUID | bytes | None
    pass_exhausted: bool

    @_observation_boundary
    def __post_init__(self):
        _integer(self.visited, 0, 4096)
        if (
            type(self.items) is not tuple
            or len(self.items) > 256
            or len(self.items) > self.visited
            or type(self.pass_exhausted) is not bool
        ):
            raise ValueError
        if self.next_cursor is not None and type(self.next_cursor) not in (UUID, bytes):
            raise ValueError
        if type(self.next_cursor) is bytes and len(self.next_cursor) != 32:
            raise ValueError
        # Concrete item ownership/type/identity validation is done by its decoder;
        # the generic page is an observation carrier, never execution authority.


def _validate_resolution_observation_core(self, *, _reject=None):
    from .bindings import _reject_scalar
    from .models import _retain_field

    _bytes_fn, _integer_fn, _instant_fn = _bytes, _integer, _instant
    if _reject is not None:
        from .bindings import _bytes_raw, _instant_raw, _integer_raw, _uuid_raw

        _bytes_fn, _integer_fn, _instant_fn = _bytes_raw, _integer_raw, _instant_raw
        for value in (self.operation_id, self.work_id, self.dispatch_id):
            _uuid_raw(value)
    if any(type(x) is not UUID for x in (self.operation_id, self.work_id, self.dispatch_id)):
        _reject_scalar(_reject)
    from .catalog import MUTATION_OPERATION_KINDS

    if (
        type(self.operation_kind) is not str
        or self.operation_kind != MUTATION_OPERATION_KINDS["E31"].value
    ):
        _reject_scalar(_reject)
    if type(self.outcome) is not str:
        _reject_scalar(_reject)
    _integer_fn(self.expected_revision, 0, 2**63 - 1)
    _integer_fn(self.cycle, 1, 1)
    _integer_fn(self.attempt, 1, 1000)
    _integer_fn(self.resolution_root_xid, 1, 2**64 - 1)
    for name in ("evidence", "binding"):
        _retain_field(self, name, _bytes_fn(getattr(self, name)), _reject=_reject)
    _retain_field(self, "recorded_at", _instant_fn(self.recorded_at), _reject=_reject)
    if self.retry_at is not None:
        _retain_field(self, "retry_at", _instant_fn(self.retry_at), _reject=_reject)
    if self.result is not None:
        _retain_field(self, "result", _bytes_fn(self.result), _reject=_reject)
    if self.result_digest is not None:
        _retain_field(self, "result_digest", _bytes_fn(self.result_digest, 32), _reject=_reject)
    if self.outcome not in (
        "confirmed_success",
        "confirmed_rejection",
        "confirmed_cancelled",
        "safe_retry",
    ):
        _reject_scalar(_reject)
    if (self.outcome == "safe_retry") != (self.retry_at is not None):
        _reject_scalar(_reject)
    if self.outcome == "confirmed_success":
        if self.result is None or self.result_digest != sha256(self.result).digest():
            _reject_scalar(_reject)
    elif self.result is not None or self.result_digest is not None:
        _reject_scalar(_reject)
    # E31 has no submitted reason; reconcile_* reasons belong to work history.
    if self.reason is not None:
        _reject_scalar(_reject)


def _validate_work_observation_core(self, *, _reject=None):
    from .bindings import _reject_scalar
    from .models import _retain_field

    _bytes_fn, _integer_fn, _instant_fn = _bytes, _integer, _instant
    if _reject is not None:
        from .bindings import _bytes_raw, _instant_raw, _integer_raw, _uuid_raw

        _bytes_fn, _integer_fn, _instant_fn = _bytes_raw, _integer_raw, _instant_raw
        for name in (
            "work_id",
            "token",
            "dispatch_id",
            "completion_guard_id",
            "resolution_operation_id",
            "terminal_resolution_operation_id",
        ):
            value = getattr(self, name)
            if value is not None:
                _uuid_raw(value)
    version_fn, scope_fn, identity_fn, admission_fn, intent_fn = (
        version_from_decimal,
        ScopeEvidence,
        WorkIdentity,
        AdmissionInput,
        canonical_intent,
    )

    def decode_text(value):
        return value.decode("utf8")

    if _reject is not None:
        from .bindings import (
            _canonical_intent_raw,
            _decode_utf8,
            _version_from_decimal_raw,
        )
        from .models import (
            _admission_input_raw,
            _scope_evidence_raw,
            _work_identity_raw,
        )

        version_fn, scope_fn, identity_fn, admission_fn, intent_fn = (
            _version_from_decimal_raw,
            _scope_evidence_raw,
            _work_identity_raw,
            _admission_input_raw,
            _canonical_intent_raw,
        )

        def decode_text(value):
            return _decode_utf8(value, _reject=_reject)

        if (
            type(self.kind) is not str
            or self.kind not in ("job", "inbox")
            or type(self.replay_policy) is not str
            or self.replay_policy not in ("disabled", "application_safe")
        ):
            _reject_scalar(_reject)
    if type(self.work_id) is not UUID or type(self.cancellation_requested) is not bool:
        _reject_scalar(_reject)
    if any(type(value) is not str for value in (self.kind, self.state, self.replay_policy)):
        _reject_scalar(_reject)
    if self.success_origin is not None and type(self.success_origin) is not str:
        _reject_scalar(_reject)
    for name in (
        "token",
        "dispatch_id",
        "completion_guard_id",
        "resolution_operation_id",
        "terminal_resolution_operation_id",
    ):
        value = getattr(self, name)
        if value is not None and type(value) is not UUID:
            _reject_scalar(_reject)
    for name in (
        "namespace",
        "command_type",
        "schema_version_decimal",
        "scope_evidence",
        "scope_application",
        "intent_evidence",
        "semantic_input",
        "replay_input",
        "protected_binding",
    ):
        _retain_field(self, name, _bytes_fn(getattr(self, name)), _reject=_reject)
    for name in (
        "subscription_id",
        "scope_tenant",
        "scope_owner",
        "idempotency_key",
        "result",
        "completion_result_digest",
    ):
        value = getattr(self, name)
        if value is not None:
            _retain_field(self, name, _bytes_fn(value), _reject=_reject)
    for name in ("original_available_at", "available_at", "created_at", "updated_at"):
        _retain_field(self, name, _instant_fn(getattr(self, name)), _reject=_reject)
    for name in ("deadline", "lease_until", "final_fence_at"):
        value = getattr(self, name)
        if value is not None:
            _retain_field(self, name, _instant_fn(value), _reject=_reject)
    version = version_fn(self.schema_version_decimal)
    if self.runnable_version is not None:
        _integer_fn(self.runnable_version, 1, 2147483647)
        if self.runnable_version != version:
            _reject_scalar(_reject)
    if version > 2147483647 and self.runnable_version is not None:
        _reject_scalar(_reject)
    scope = scope_fn(
        canonical_version=self.canonical_version,
        canonical=self.scope_evidence,
        application=self.scope_application,
        tenant=self.scope_tenant,
        owner=self.scope_owner,
    )
    identity = identity_fn(
        work_id=self.work_id,
        kind=WorkKind(self.kind),
        subscription_id=None if self.subscription_id is None else decode_text(self.subscription_id),
        namespace=decode_text(self.namespace),
        command_type=decode_text(self.command_type),
        scope=scope,
        idempotency_key=None if self.idempotency_key is None else decode_text(self.idempotency_key),
    )
    admission = admission_fn(
        identity=identity,
        schema_version=version,
        semantic_input=self.semantic_input,
        replay_input=self.replay_input,
        protected_binding=self.protected_binding,
        replay_policy=ReplayPolicy(self.replay_policy),
        max_attempts=self.max_attempts,
        deadline=self.deadline,
        original_available_at=self.original_available_at,
    )
    if intent_fn(admission).content != self.intent_evidence:
        _reject_scalar(_reject)
    _integer_fn(self.ownership_revision, 0, 2**63 - 1)
    _integer_fn(self.cycle, 1, 1)
    _integer_fn(self.attempt_count, 0, self.max_attempts)
    if self.state not in (
        "queued",
        "claimed",
        "running",
        "retry_waiting",
        "succeeded",
        "failed",
        "expired",
        "cancelled",
        "blocked_schema",
        "held",
    ):
        _reject_scalar(_reject)
    owned = self.state in ("claimed", "running")
    # Cancellation terminalizes predispatch work or holds dispatched work.
    if self.cancellation_requested and self.state in (
        "queued",
        "claimed",
        "running",
        "retry_waiting",
        "blocked_schema",
    ):
        _reject_scalar(_reject)
    if self.state == "claimed" and self.attempt_count >= self.max_attempts:
        _reject_scalar(_reject)
    if owned != (self.token is not None) or owned != (self.lease_until is not None):
        _reject_scalar(_reject)
    if owned and self.ownership_revision < 1:
        _reject_scalar(_reject)
    if (
        self.state in ("queued", "claimed", "retry_waiting", "blocked_schema")
        and self.dispatch_id is not None
    ):
        _reject_scalar(_reject)
    if self.state in ("running", "held", "succeeded") and (
        self.dispatch_id is None or self.attempt_count < 1
    ):
        _reject_scalar(_reject)
    if self.dispatch_id is not None and self.attempt_count < 1:
        _reject_scalar(_reject)
    if (
        self.state in ("queued", "claimed", "running", "retry_waiting")
        and self.runnable_version is None
    ):
        _reject_scalar(_reject)
    if (
        self.deadline is not None
        and self.lease_until is not None
        and self.lease_until > self.deadline
    ):
        _reject_scalar(_reject)
    if self.resolution is not None:
        if type(self.resolution) is not ResolutionObservation:
            _reject_scalar(_reject)
        _validate_resolution_observation_core(self.resolution, _reject=_reject)
        r = self.resolution
        if (r.work_id, r.cycle, r.attempt, r.dispatch_id) != (
            self.work_id,
            self.cycle,
            self.attempt_count,
            self.dispatch_id,
        ) or self.terminal_resolution_operation_id != r.operation_id:
            _reject_scalar(_reject)
    if self.state == "succeeded":
        if self.result is None:
            _reject_scalar(_reject)
        if self.success_origin == "guarded":
            if (
                self.completion_guard_id is None
                or self.final_fence_at is None
                or self.completion_result_digest != sha256(self.result).digest()
                or self.resolution_operation_id is not None
                or self.terminal_resolution_operation_id is not None
                or self.resolution is not None
            ):
                _reject_scalar(_reject)
        elif self.success_origin == "reconciled":
            if (
                any(
                    x is not None
                    for x in (
                        self.completion_guard_id,
                        self.final_fence_at,
                        self.completion_result_digest,
                    )
                )
                or self.resolution is None
                or self.resolution.outcome != "confirmed_success"
                or self.resolution_operation_id != self.resolution.operation_id
                or self.resolution.result != self.result
            ):
                _reject_scalar(_reject)
        else:
            _reject_scalar(_reject)
    else:
        if any(
            x is not None
            for x in (
                self.success_origin,
                self.completion_guard_id,
                self.final_fence_at,
                self.completion_result_digest,
                self.resolution_operation_id,
                self.result,
            )
        ):
            _reject_scalar(_reject)
        if self.terminal_resolution_operation_id is not None:
            if self.resolution is None or (self.state, self.resolution.outcome) not in (
                ("failed", "confirmed_rejection"),
                ("cancelled", "confirmed_cancelled"),
            ):
                _reject_scalar(_reject)
        elif self.resolution is not None:
            _reject_scalar(_reject)


def _validate_resolution_observation_raw(value, /):
    from .errors import _reject_validation

    if type(value) is not ResolutionObservation:
        _reject_validation()
    _validate_resolution_observation_core(value, _reject=_reject_validation)


def _resolution_observation_raw(**values):
    from types import SimpleNamespace

    from .errors import _reject_validation

    if set(values) != set(ResolutionObservation.__dataclass_fields__):
        _reject_validation()
    draft = SimpleNamespace(**values)
    _validate_resolution_observation_core(draft, _reject=_reject_validation)
    value = object.__new__(ResolutionObservation)
    for name in ResolutionObservation.__dataclass_fields__:
        object.__setattr__(value, name, values[name])
    return value


def _validate_work_observation_raw(value, /):
    from .errors import _reject_validation

    if type(value) is not WorkObservation:
        _reject_validation()
    _validate_work_observation_core(value, _reject=_reject_validation)


def _work_observation_raw(**values):
    from types import SimpleNamespace

    from .errors import _reject_validation

    if set(values) != set(WorkObservation.__dataclass_fields__):
        _reject_validation()
    draft = SimpleNamespace(**values)
    _validate_work_observation_core(draft, _reject=_reject_validation)
    value = object.__new__(WorkObservation)
    for name in WorkObservation.__dataclass_fields__:
        object.__setattr__(value, name, values[name])
    return value


def _validate_scan_page_raw(value, /):
    """Validate shared framing; concrete item semantics belong to the decoder."""
    from .bindings import _integer_raw, _uuid_raw
    from .errors import _reject_validation

    if type(value) is not ScanPage:
        _reject_validation()
    _integer_raw(value.visited, 0, 4096)
    if (
        type(value.items) is not tuple
        or len(value.items) > 256
        or len(value.items) > value.visited
        or type(value.pass_exhausted) is not bool
    ):
        _reject_validation()
    if value.next_cursor is not None:
        if type(value.next_cursor) is UUID:
            _uuid_raw(value.next_cursor)
        elif type(value.next_cursor) is not bytes or len(value.next_cursor) != 32:
            _reject_validation()


def _scan_page_raw(*, items, visited, next_cursor, pass_exhausted):
    value = object.__new__(ScanPage)
    object.__setattr__(value, "items", items)
    object.__setattr__(value, "visited", visited)
    object.__setattr__(value, "next_cursor", next_cursor)
    object.__setattr__(value, "pass_exhausted", pass_exhausted)
    _validate_scan_page_raw(value)
    return value

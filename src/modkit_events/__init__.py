"""Generic event envelopes and duplicate-aware delivery, with optional adapters."""

from .claims import Claim, ClaimResult, ClaimStore, MemoryClaimStore, OwnershipLost
from .codec import JsonCodec
from .consumer import Consumer
from .contracts import (
    ConflictingRouteError,
    ContractRegistry,
    DuplicateContractError,
    EventContract,
    InvalidContractConfiguration,
    InvalidValidatorResult,
    PayloadValidationError,
    PayloadValidator,
    UnknownEventName,
    UnsupportedSchemaVersion,
)
from .delivery import (
    DeliveryContext,
    DeliveryPhase,
    DeliveryRecord,
    DeliveryRouteMismatch,
    Disposition,
    DispositionKind,
)
from .dispatch import Dispatcher
from .models import Event
from .outbox import OutboxClaim, OutboxPublisher, OutboxStore
from .protocols import Publisher
from .retry import RetryPolicy
from .subscriptions import (
    ConflictingConsumerGroupError,
    DuplicateSubscriptionError,
    InvalidSubscriptionConfiguration,
    StartPosition,
    Subscription,
    UnsupportedCapabilityError,
    validate_subscriptions,
)

__all__ = [
    "Claim",
    "ClaimResult",
    "ClaimStore",
    "Consumer",
    "Dispatcher",
    "Event",
    "JsonCodec",
    "MemoryClaimStore",
    "OwnershipLost",
    "Publisher",
    "RetryPolicy",
]

__all__ += ["OutboxClaim", "OutboxPublisher", "OutboxStore"]


__all__ += [
    "ConflictingRouteError",
    "ContractRegistry",
    "DuplicateContractError",
    "EventContract",
    "InvalidContractConfiguration",
    "InvalidValidatorResult",
    "PayloadValidationError",
    "PayloadValidator",
    "UnknownEventName",
    "UnsupportedSchemaVersion",
    "ConflictingConsumerGroupError",
    "DuplicateSubscriptionError",
    "InvalidSubscriptionConfiguration",
    "StartPosition",
    "Subscription",
    "UnsupportedCapabilityError",
    "validate_subscriptions",
    "DeliveryContext",
    "DeliveryPhase",
    "DeliveryRecord",
    "DeliveryRouteMismatch",
    "Disposition",
    "DispositionKind",
]

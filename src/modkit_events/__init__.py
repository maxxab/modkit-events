"""Generic event envelopes and duplicate-aware delivery, with optional adapters."""

from .claims import Claim, ClaimResult, ClaimStore, MemoryClaimStore, OwnershipLost
from .codec import JsonCodec
from .consumer import Consumer
from .dispatch import Dispatcher
from .models import Event
from .protocols import Publisher
from .retry import RetryPolicy

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
from .outbox import OutboxClaim, OutboxPublisher, OutboxStore

__all__ += ["OutboxClaim", "OutboxPublisher", "OutboxStore"]

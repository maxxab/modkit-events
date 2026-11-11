"""Phase-scoped observations, never ACK, transaction or replay authority."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .subscriptions import Subscription


class DeliveryRouteMismatch(ValueError):
    pass


def _text(value: object, maximum: int) -> bool:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        return False
    try:
        return len(value.encode("utf-8")) <= maximum
    except UnicodeError:
        return False


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Expected timezone-aware datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryContext:
    subscription_id: str
    broker: str
    destination: str
    group: str
    consumer_id: str
    message_id: str
    received_at: datetime
    delivery_count: int | None = None

    def __post_init__(self) -> None:
        if not all(
            _text(value, 256)
            for value in (
                self.subscription_id,
                self.broker,
                self.destination,
                self.group,
                self.consumer_id,
            )
        ) or not _text(self.message_id, 512):
            raise ValueError("Invalid delivery identifiers")
        count = self.delivery_count
        if count is not None and (type(count) is not int or not 1 <= count <= 2**63 - 1):
            raise ValueError("Invalid transport delivery count")
        object.__setattr__(self, "received_at", _utc(self.received_at))

    def validate_subscription(self, subscription: Subscription) -> None:
        if not isinstance(subscription, Subscription):
            raise ValueError("Expected Subscription")
        if (self.subscription_id, self.destination, self.group) != (
            subscription.subscription_id,
            subscription.route,
            subscription.group,
        ):
            raise DeliveryRouteMismatch("Delivery does not match subscription")


class DispositionKind(Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    QUARANTINED = "quarantined"
    UNCERTAIN = "uncertain"


class DeliveryPhase(Enum):
    INTAKE = "intake"
    PUBLICATION = "publication"
    PROCESSING = "processing"


@dataclass(frozen=True, slots=True, kw_only=True)
class Disposition:
    kind: DispositionKind
    reason_code: str | None = None
    retry_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DispositionKind):
            raise ValueError("Invalid disposition kind")
        if self.kind is DispositionKind.CONFIRMED:
            if self.reason_code is not None or self.retry_at is not None:
                raise ValueError("Confirmed disposition has no reason or schedule")
        elif (
            not isinstance(self.reason_code, str)
            or re.fullmatch(
                r"[a-z][a-z0-9_]{0,63}",
                self.reason_code,
                flags=re.ASCII,
            )
            is None
        ):
            raise ValueError("Nonconfirmed disposition requires a reason token")
        if self.retry_at is not None:
            if self.kind is not DispositionKind.DEFERRED:
                raise ValueError("Only deferred disposition may carry a schedule")
            object.__setattr__(self, "retry_at", _utc(self.retry_at))


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryRecord:
    event_id: str
    phase: DeliveryPhase
    disposition: Disposition
    context: DeliveryContext | None = None

    def __post_init__(self) -> None:
        # Intentionally legacy Event identity validity, NOT managed configuration bounds.
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("Event identity must be a nonempty string")
        if not isinstance(self.phase, DeliveryPhase) or not isinstance(
            self.disposition, Disposition
        ):
            raise ValueError("Expected delivery phase and disposition")
        if self.context is not None and not isinstance(self.context, DeliveryContext):
            raise ValueError("Expected DeliveryContext")
        if self.phase is not DeliveryPhase.PUBLICATION and self.context is None:
            raise ValueError("Intake and processing require delivery context")

"""Opt-in sequential publication observations, without retries or settlement."""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncGenerator, Iterable
from dataclasses import dataclass

from .delivery import DeliveryPhase, DeliveryRecord, Disposition, DispositionKind
from .models import Event
from .protocols import Publisher


def _valid_receipt(value: object) -> bool:
    # Reject subclasses before invoking any overridable methods or coercion.
    if type(value) is not str:
        return False
    # A character bound first limits the later UTF-8 allocation to 2048 bytes.
    if len(value) > 512 or not value.strip() or "\0" in value:
        return False
    try:
        return len(value.encode("utf-8")) <= 512
    except UnicodeError:
        return False


class PublicationRejected(Exception):
    """Publisher evidence of nonacceptance; never use for an uncertain send."""

    def __init__(self, reason_code: str) -> None:
        Disposition(kind=DispositionKind.REJECTED, reason_code=reason_code)
        self._reason_code = reason_code
        super().__init__("Publication explicitly rejected")

    @property
    def reason_code(self) -> str:
        return self._reason_code


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicationResult:
    """A receipt-scoped observation, not durability or transaction authority."""

    record: DeliveryRecord
    message_id: str | None

    def __post_init__(self) -> None:
        record = self.record
        if (
            not isinstance(record, DeliveryRecord)
            or record.phase is not DeliveryPhase.PUBLICATION
            or record.context is not None
            or record.disposition.kind
            not in (DispositionKind.CONFIRMED, DispositionKind.REJECTED, DispositionKind.UNCERTAIN)
        ):
            raise ValueError("Expected a supported publication record without intake context")
        if record.disposition.kind is DispositionKind.CONFIRMED:
            if not _valid_receipt(self.message_id):
                raise ValueError("Confirmed publication requires a valid receipt")
        elif self.message_id is not None:
            raise ValueError("Nonconfirmed publication cannot carry a receipt")


def publish_batch(
    publisher: Publisher,
    events: Iterable[Event],
    *,
    timeout: float = 10,
    max_items: int = 1000,
) -> AsyncGenerator[PublicationResult, None]:
    """Snapshot input references now; publish lazily, one item per requested result.

    Validation covers only this batch's contract, not publisher-specific rules.
    The caller owns broker lifetime, durable intent, leases and reconciliation.
    """
    if type(max_items) is not int or not 1 <= max_items <= 1000:
        raise ValueError("max_items must be an integer between 1 and 1000")
    if type(timeout) not in (int, float):
        raise ValueError("timeout must be finite and positive")
    try:
        seconds = float(timeout)
    except OverflowError:
        raise ValueError("timeout must be finite and positive") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("timeout must be finite and positive")

    snapshot: list[Event] = []
    identities: set[str] = set()
    for index, value in enumerate(events):
        if index >= max_items:
            raise ValueError("Batch exceeds max_items")
        if not isinstance(value, Event):
            raise ValueError("Expected Event values")
        identity = value.event_id
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("Event identity must be a nonempty string")
        if identity in identities:
            raise ValueError("Duplicate event identity in batch")
        identities.add(identity)
        snapshot.append(value)
    return _publish(publisher, tuple(snapshot), seconds)


async def _publish(
    publisher: Publisher, events: tuple[Event, ...], timeout: float
) -> AsyncGenerator[PublicationResult, None]:
    for event in events:
        receipt: str | None = None
        try:
            async with asyncio.timeout(timeout):
                receipt = await publisher.publish(event)
        except PublicationRejected as error:
            receipt = None
            disposition = Disposition(kind=DispositionKind.REJECTED, reason_code=error.reason_code)
        except TimeoutError:
            receipt = None
            disposition = Disposition(kind=DispositionKind.UNCERTAIN, reason_code="publish_timeout")
        except Exception:
            receipt = None
            disposition = Disposition(kind=DispositionKind.UNCERTAIN, reason_code="publish_failed")
        else:
            if _valid_receipt(receipt):
                disposition = Disposition(kind=DispositionKind.CONFIRMED)
            else:
                # Do not retain an oversized or otherwise invalid receipt across the yield.
                receipt = None
                disposition = Disposition(
                    kind=DispositionKind.UNCERTAIN, reason_code="invalid_receipt"
                )
        # Outside exception handlers: do not retain transport errors in yielded results.
        # Cancellation and other BaseException values are deliberately not converted.
        yield PublicationResult(
            record=DeliveryRecord(
                event_id=event.event_id,
                phase=DeliveryPhase.PUBLICATION,
                disposition=disposition,
            ),
            message_id=receipt,
        )

"""Broker-neutral publisher for leased durable outbox rows."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from .claims import OwnershipLost, positive_seconds
from .models import Event
from .protocols import Publisher
from .retry import RetryPolicy


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    event: Event
    token: str
    attempt: int


class OutboxStore(Protocol):
    async def claim(self, limit: int) -> list[OutboxClaim]: ...
    async def complete(self, claim: OutboxClaim, message_id: str) -> bool: ...
    async def fail(
        self, claim: OutboxClaim, error: str, delay: float, max_attempts: int
    ) -> bool: ...


class OutboxPublisher:
    """One bounded batch per call; caller owns scheduling and broker lifetime.

    Publish may succeed remotely before timeout or completion-storage failure.
    Recovery can therefore publish the same event more than once.
    """

    def __init__(
        self,
        store: OutboxStore,
        publisher: Publisher,
        *,
        retry: RetryPolicy = RetryPolicy(),
        timeout: float = 10,
        batch_size: int = 100,
    ):
        positive_seconds(timeout)
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        self.store = store
        self.publisher = publisher
        self.retry = retry
        self.timeout = timeout
        self.batch_size = batch_size

    async def process_once(self) -> list[str]:
        results = []
        for _ in range(self.batch_size):
            claims = await self.store.claim(1)
            if not claims:
                break
            claim = claims[0]
            if claim.attempt > self.retry.max_attempts:
                if not await self.store.fail(
                    claim, "Attempt budget exhausted before publish", 0, self.retry.max_attempts
                ):
                    raise OwnershipLost("Exhausted outbox claim lost ownership")
                results.append("dead")
                continue
            try:
                async with asyncio.timeout(self.timeout):
                    message_id = await self.publisher.publish(claim.event)
            except asyncio.CancelledError as original:
                try:
                    await self.store.fail(claim, "cancelled", 0, self.retry.max_attempts)
                except BaseException as cleanup:
                    original.add_note(f"Outbox cleanup failed: {type(cleanup).__name__}: {cleanup}")
                raise
            except Exception as error:
                if not await self.store.fail(
                    claim, str(error), self.retry.delay(claim.attempt), self.retry.max_attempts
                ):
                    raise OwnershipLost("Outbox failure lost ownership") from error
                results.append("dead" if claim.attempt >= self.retry.max_attempts else "retry")
                if results[-1] == "retry":
                    break
            else:
                if not await self.store.complete(claim, message_id):
                    raise OwnershipLost("Published event lost outbox ownership")
                results.append("published")
        return results

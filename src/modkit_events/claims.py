"""Ownership-bearing duplicate claims; leases are not execution locks."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Claim:
    scope: str
    key: str
    token: str


@dataclass(frozen=True, slots=True)
class ClaimResult:
    state: Literal["acquired", "inflight", "completed"]
    claim: Claim | None = None


class ClaimStore(Protocol):
    async def claim(self, scope: str, key: str) -> ClaimResult: ...
    async def complete(self, claim: Claim) -> bool: ...
    async def release(self, claim: Claim) -> bool: ...


class OwnershipLost(RuntimeError):
    """The lease expired or another owner replaced this claim; do not ACK."""


def positive_seconds(value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError("Duration must be finite and positive")


def validate_key(scope: str, key: str) -> None:
    if not all(isinstance(value, str) and value.strip() for value in (scope, key)):
        raise ValueError("scope and key must be nonempty strings")


class MemoryClaimStore:
    """Single-event-loop test/local store. No cross-process durability or retention worker."""

    def __init__(self, *, lease_seconds: float = 60, clock: Callable[[], float] = time.monotonic):
        positive_seconds(lease_seconds)
        self.lease_seconds = lease_seconds
        self.clock = clock
        self._rows: dict[tuple[str, str], tuple[str | None, float]] = {}

    async def claim(self, scope: str, key: str) -> ClaimResult:
        validate_key(scope, key)
        row = self._rows.get((scope, key))
        now = self.clock()
        if row is not None:
            token, deadline = row
            if token is None:
                return ClaimResult("completed")
            if deadline > now:
                return ClaimResult("inflight")
        claim = Claim(scope, key, uuid4().hex)
        self._rows[scope, key] = (claim.token, now + self.lease_seconds)
        return ClaimResult("acquired", claim)

    def _owned(self, claim: Claim) -> bool:
        row = self._rows.get((claim.scope, claim.key))
        return row is not None and row[0] == claim.token and row[1] > self.clock()

    async def complete(self, claim: Claim) -> bool:
        if not self._owned(claim):
            return False
        self._rows[claim.scope, claim.key] = (None, 0)
        return True

    async def release(self, claim: Claim) -> bool:
        if not self._owned(claim):
            return False
        del self._rows[claim.scope, claim.key]
        return True

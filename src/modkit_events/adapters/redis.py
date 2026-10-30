"""Optional standalone Redis Streams adapter. Caller owns the Redis client.

No stream trimming, implicit connection setup, background tasks or hidden logging.
Multi-key scripts require standalone Redis (not Redis Cluster).
"""

import asyncio
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from ..claims import Claim, ClaimResult, OwnershipLost, positive_seconds, validate_key
from ..codec import JsonCodec
from ..consumer import Consumer
from ..models import Event
from ..retry import RetryPolicy

_CLAIM = """
if #KEYS > 1 and redis.call('EXISTS', KEYS[2]) == 1 then return 3 end
local value = redis.call('GET', KEYS[1])
if value == 'completed' then return 2 end
if value then return 0 end
redis.call('SET', KEYS[1], ARGV[1], 'PX', ARGV[2])
return 1
"""
_COMPLETE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], 'completed', 'PX', ARGV[2])
return 1
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""
_FAILURE = """
if redis.call('GET', KEYS[2]) ~= ARGV[3] then return -1 end
local count = redis.call('HINCRBY', KEYS[1], 'count', 1)
local now = redis.call('TIME')
local millis = now[1] * 1000 + math.floor(now[2] / 1000)
local delay = math.min(tonumber(ARGV[2]), tonumber(ARGV[1]) * 2 ^ math.min(count-1, 1023))
redis.call('HSET', KEYS[1], 'due', millis + delay)
if count < tonumber(ARGV[4]) then redis.call('DEL', KEYS[2]) end
return count
"""
_DUE = """
local due = tonumber(redis.call('HGET', KEYS[1], 'due') or '0')
local now = redis.call('TIME')
return due <= now[1] * 1000 + math.floor(now[2] / 1000) and 1 or 0
"""
_ACK = """
local result = redis.call('XACK', KEYS[1], ARGV[1], ARGV[2])
redis.call('DEL', KEYS[2])
return result
"""
_DEAD = """
if #KEYS > 4 and redis.call('GET', KEYS[5]) ~= ARGV[6] then return -1 end
local existing = redis.call('GET', KEYS[4])
if not existing then
  if redis.call('XLEN', KEYS[2]) >= tonumber(ARGV[4]) then return 0 end
  local id = redis.call('XADD', KEYS[2], '*', 'data', ARGV[3],
    'original_id', ARGV[2], 'original_stream', KEYS[1], 'group', ARGV[1], 'reason', ARGV[5])
  redis.call('SET', KEYS[4], id)
end
redis.call('XACK', KEYS[1], ARGV[1], ARGV[2])
redis.call('DEL', KEYS[3])
if #KEYS > 4 then redis.call('DEL', KEYS[5]) end
return 1
"""


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _digest(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()


def _bounded(value: int, name: str, minimum: int = 1, maximum: int = 1000) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


class TerminalEventError(Exception):
    """An application explicitly requests dead-lettering instead of retry."""


@dataclass(frozen=True, slots=True)
class Delivery:
    message_id: str
    raw: bytes


class RedisClaimStore:
    """Atomic token claims. Completed retention expiry permits later duplicates."""

    def __init__(
        self,
        client: Redis,
        *,
        namespace: str,
        lease_seconds: float = 60,
        completed_seconds: float = 86400,
    ):
        validate_key(namespace, "namespace")
        positive_seconds(lease_seconds)
        positive_seconds(completed_seconds)
        self.client = client
        self.namespace = namespace
        self.lease_ms = max(1, math.ceil(lease_seconds * 1000))
        self.completed_ms = max(1, math.ceil(completed_seconds * 1000))

    def _key(self, scope: str, key: str) -> str:
        return f"{self.namespace}:claim:{_digest(scope, key)}"

    async def claim(self, scope: str, key: str) -> ClaimResult:
        validate_key(scope, key)
        claim = Claim(scope, key, uuid4().hex)
        result = await self.client.eval(
            _CLAIM, 1, self._key(scope, key), claim.token, self.lease_ms
        )
        if result == 1:
            return ClaimResult("acquired", claim)
        return ClaimResult("completed" if result == 2 else "inflight")

    async def complete(self, claim: Claim) -> bool:
        return bool(
            await self.client.eval(
                _COMPLETE, 1, self._key(claim.scope, claim.key), claim.token, self.completed_ms
            )
        )

    async def release(self, claim: Claim) -> bool:
        return bool(
            await self.client.eval(_RELEASE, 1, self._key(claim.scope, claim.key), claim.token)
        )


class RedisStreams:
    """Explicit stream/group operations with failure-only retry budgets.

    Use a distinct Consumer scope for each logical stream/group subscription.
    `read` reads new entries; callers must also repeatedly `reclaim` idle pending
    entries, following its returned cursor. Each process call handles one entry.
    Errors from storage/ACK propagate; they are never counted as handler failures.
    """

    def __init__(
        self,
        client: Redis,
        *,
        stream: str,
        group: str,
        consumer: str,
        namespace: str,
        dlq_stream: str | None = None,
        dlq_capacity: int = 10000,
        codec: JsonCodec | None = None,
        retry: RetryPolicy = RetryPolicy(),
        handler_timeout: float = 30,
    ):
        validate_key(stream, group)
        validate_key(consumer, namespace)
        positive_seconds(handler_timeout)
        _bounded(dlq_capacity, "dlq_capacity", maximum=1000000)
        dlq_stream = dlq_stream or stream + ":dlq"
        validate_key(dlq_stream, "dlq_stream")
        if dlq_stream == stream:
            raise ValueError("DLQ stream must differ from source stream")
        self.client = client
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self.namespace = namespace
        self.dlq_stream = dlq_stream
        self.dlq_capacity = dlq_capacity
        self.codec = codec or JsonCodec()
        self.retry = retry
        self.handler_timeout = handler_timeout

    def _retry_key(self, delivery: Delivery) -> str:
        return f"{self.namespace}:retry:{_digest(self.stream, self.group, delivery.message_id)}"

    async def ensure_group(self) -> None:
        """Explicitly create group at 0 (includes existing messages), never reset it."""
        try:
            await self.client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as error:
            if not str(error).startswith("BUSYGROUP "):
                raise

    async def publish(self, event: Event) -> str:
        return _text(await self.client.xadd(self.stream, {"data": self.codec.encode(event)}))

    @staticmethod
    def _deliveries(rows) -> list[Delivery]:
        result = []
        for message_id, fields in rows:
            raw = fields.get(b"data", fields.get("data", b""))
            if isinstance(raw, str):
                raw = raw.encode()
            result.append(Delivery(_text(message_id), raw))
        return result

    async def read(self, *, count: int = 100, block_ms: int | None = None) -> list[Delivery]:
        _bounded(count, "count")
        if block_ms is not None:
            _bounded(block_ms, "block_ms", maximum=60000)
        result = await self.client.xreadgroup(
            self.group, self.consumer, {self.stream: ">"}, count=count, block=block_ms
        )
        groups = result.items() if isinstance(result, Mapping) else result
        deliveries = []
        for _, rows in cast(list[tuple[Any, Any]], groups):
            # redis-py supports unified maps, legacy RESP2 lists and explicit
            # legacy RESP3 maps whose entry list has one extra wrapper.
            if (
                rows
                and isinstance(rows[0], list)
                and (not rows[0] or isinstance(rows[0][0], (list, tuple)))
            ):
                rows = rows[0]
            deliveries.extend(self._deliveries(rows))
        return deliveries

    async def reclaim(
        self, *, min_idle_ms: int, cursor: str = "0-0", count: int = 100
    ) -> tuple[str, list[Delivery]]:
        _bounded(count, "count")
        _bounded(min_idle_ms, "min_idle_ms", minimum=0, maximum=2147483647)
        result = await self.client.xautoclaim(
            self.stream, self.group, self.consumer, min_idle_ms, start_id=cursor, count=count
        )
        return _text(result[0]), self._deliveries(result[1])

    async def ack(self, delivery: Delivery) -> bool:
        return bool(
            await self.client.eval(
                _ACK, 2, self.stream, self._retry_key(delivery), self.group, delivery.message_id
            )
        )

    async def failure_count(self, delivery: Delivery) -> int:
        return int(await self.client.hget(self._retry_key(delivery), "count") or 0)

    def _dead_key(self, delivery: Delivery) -> str:
        return f"{self.namespace}:dead:{_digest(self.stream, self.group, delivery.message_id)}"

    async def _dead_letter(
        self,
        delivery: Delivery,
        reason: str,
        store: RedisClaimStore | None = None,
        claim: Claim | None = None,
    ) -> str:
        marker = self._dead_key(delivery)
        keys = [self.stream, self.dlq_stream, self._retry_key(delivery), marker]
        if store is not None and claim is not None:
            keys.append(store._key(claim.scope, claim.key))
        result = await self.client.eval(
            _DEAD,
            len(keys),
            *keys,
            self.group,
            delivery.message_id,
            delivery.raw,
            self.dlq_capacity,
            reason[:1000],
            claim.token if claim else "",
        )
        if result == -1:
            raise OwnershipLost("Dead-letter disposition lost ownership")
        if not result:
            raise RuntimeError("DLQ capacity exceeded; original left pending")
        return "dead"

    async def process(self, delivery: Delivery, consumer: Consumer) -> str:
        """Handle or leave pending. Cancellation propagates after best-effort release."""
        store = consumer.store
        if not isinstance(store, RedisClaimStore) or store.client is not self.client:
            raise ValueError("Automatic disposition requires RedisClaimStore with the same client")
        try:
            event = self.codec.decode(delivery.raw)
        except ValueError as error:
            return await self._dead_letter(delivery, f"Invalid envelope: {error}")
        # Atomically check per-delivery terminal marker AND acquire the event claim.
        claim = Claim(consumer.scope, event.event_id, uuid4().hex)
        acquired = await self.client.eval(
            _CLAIM,
            2,
            store._key(claim.scope, claim.key),
            self._dead_key(delivery),
            claim.token,
            store.lease_ms,
        )
        if acquired == 3:
            await self.ack(delivery)
            return "dead"
        result = (
            ClaimResult("acquired", claim)
            if acquired == 1
            else ClaimResult("completed" if acquired == 2 else "inflight")
        )
        if result.state == "inflight":
            return "inflight"
        if result.state == "completed":
            await self.ack(delivery)
            return "completed"
        # Storage failures here leave lease to expire; no handler was run.
        if await self.failure_count(delivery) >= self.retry.max_attempts:
            return await self._dead_letter(delivery, "Retry budget exhausted", store, claim)
        if not await self.client.eval(_DUE, 1, self._retry_key(delivery)):
            if not await consumer.store.release(claim):
                raise OwnershipLost("Retry delay lost ownership")
            return "retry"
        try:
            async with asyncio.timeout(self.handler_timeout):
                await consumer.dispatcher.dispatch(event)
        except BaseException as error:
            if not isinstance(error, Exception):
                try:
                    if not await store.release(claim):
                        error.add_note("Claim release lost ownership")
                except BaseException as cleanup:
                    error.add_note(f"Claim cleanup failed: {type(cleanup).__name__}: {cleanup}")
                raise
            if isinstance(error, TerminalEventError):
                return await self._dead_letter(delivery, str(error), store, claim)
            # Fence retry bookkeeping and release in one Redis operation. Keep
            # the claim when exhausted until the fenced DLQ handoff completes.
            count = await self.client.eval(
                _FAILURE,
                2,
                self._retry_key(delivery),
                store._key(claim.scope, claim.key),
                self.retry.base_delay * 1000,
                self.retry.max_delay * 1000,
                claim.token,
                self.retry.max_attempts,
            )
            if count == -1:
                raise OwnershipLost("Handler failure lost ownership") from error
            if count >= self.retry.max_attempts:
                return await self._dead_letter(delivery, str(error), store, claim)
            return "retry"
        if not await consumer.store.complete(claim):
            raise OwnershipLost("Handler finished after claim ownership was lost")
        await self.ack(delivery)
        return "processed"

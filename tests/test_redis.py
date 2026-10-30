"""Real Redis integration. Set MODKIT_REDIS_URL for a disposable test server."""

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio

from modkit_events import Consumer, Dispatcher, Event, JsonCodec, RetryPolicy
from modkit_events.adapters.redis import RedisClaimStore, RedisStreams, TerminalEventError


@pytest_asyncio.fixture(params=[{}, {"protocol": 3}, {"protocol": 3, "legacy_responses": False}])
async def client(request):
    from redis.asyncio import Redis

    url = os.environ.get("MODKIT_REDIS_URL")
    if not url and os.environ.get("MODKIT_REQUIRE_REDIS"):
        pytest.fail("MODKIT_REDIS_URL required by integration gate")
    if not url:
        pytest.skip("MODKIT_REDIS_URL required for real Redis integration")
    client = Redis.from_url(url, **request.param)
    await client.ping()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def stream(client):
    prefix = "test-modkit-" + uuid4().hex
    bus = RedisStreams(
        client,
        stream=prefix,
        group="workers",
        consumer="one",
        namespace=prefix,
        retry=RetryPolicy(max_attempts=2, base_delay=0),
    )
    await bus.ensure_group()
    yield bus
    keys = [key async for key in client.scan_iter(match=prefix + "*")]
    if keys:
        await client.delete(*keys)


def consuming(store, handler):
    dispatcher = Dispatcher()
    dispatcher.subscribe("demo", handler)
    return Consumer(store, dispatcher, scope="workers")


async def test_real_claim_race_has_one_live_owner(stream):
    # Exclusivity applies while the lease is live, not across a 20 ms CI deadline.
    store = RedisClaimStore(stream.client, namespace=stream.namespace, lease_seconds=300)
    results = await asyncio.gather(*(store.claim("g", "id") for _ in range(10)))
    assert await stream.client.pttl(store._key("g", "id")) > 0
    assert sum(result.state == "acquired" for result in results) == 1
    assert sum(result.state == "inflight" for result in results) == 9


async def test_real_expired_claim_rejects_stale_owner_and_completes(stream):
    store = RedisClaimStore(stream.client, namespace=stream.namespace, lease_seconds=300)
    first = await store.claim("g", "id")
    assert first.state == "acquired"
    assert first.claim is not None
    key = store._key("g", "id")
    assert await stream.client.pttl(key) > 0
    # Expire only this test-owned key, synchronously on Redis, without a sleep.
    assert await stream.client.pexpire(key, 0)
    assert await stream.client.exists(key) == 0
    new = await store.claim("g", "id")
    assert new.state == "acquired"
    assert new.claim is not None
    assert new.claim.token != first.claim.token
    assert not await store.complete(first.claim)
    assert not await store.release(first.claim)
    assert await store.complete(new.claim)
    assert (await store.claim("g", "id")).state == "completed"


async def test_publish_consume_ack_and_duplicate(stream):
    calls = []

    async def handler(event):
        calls.append(event)

    store = RedisClaimStore(stream.client, namespace=stream.namespace)
    consumer = consuming(store, handler)
    event = Event("id", "demo", {"n": 1})
    for _ in range(2):
        await stream.publish(event)
        delivery = (await stream.read())[0]
        assert await stream.process(delivery, consumer) in ("processed", "completed")
    assert len(calls) == 1
    assert (await stream.client.xpending(stream.stream, stream.group))["pending"] == 0


async def test_inflight_pending_then_reclaim(stream):
    async def handler(event):
        pass

    store = RedisClaimStore(stream.client, namespace=stream.namespace)
    claim = (await store.claim("workers", "id")).claim
    await stream.publish(Event("id", "demo", {}))
    delivery = (await stream.read())[0]
    consumer = consuming(store, handler)
    assert await stream.process(delivery, consumer) == "inflight"
    assert (await stream.client.xpending(stream.stream, stream.group))["pending"] == 1
    await store.release(claim)
    cursor, deliveries = await stream.reclaim(min_idle_ms=0)
    assert cursor == "0-0"
    assert await stream.process(deliveries[0], consumer) == "processed"


async def test_retry_exhausted_and_poison_to_dlq(stream):
    async def handler(event):
        raise RuntimeError("failed")

    consumer = consuming(RedisClaimStore(stream.client, namespace=stream.namespace), handler)
    await stream.publish(Event("id", "demo", {}))
    delivery = (await stream.read())[0]
    assert await stream.process(delivery, consumer) == "retry"
    assert await stream.process(delivery, consumer) == "dead"
    assert await stream.client.xlen(stream.dlq_stream) == 1
    assert (await stream.client.xpending(stream.stream, stream.group))["pending"] == 0
    await stream.client.xadd(stream.stream, {"data": b"{"})
    poison = (await stream.read())[0]
    assert await stream.process(poison, consumer) == "dead"
    assert await stream.client.xlen(stream.dlq_stream) == 2


async def test_dlq_capacity_failure_leaves_pending(stream):
    stream.dlq_capacity = 1
    await stream.client.xadd(stream.dlq_stream, {"data": "existing"})
    await stream.client.xadd(stream.stream, {"data": b"{"})
    delivery = (await stream.read())[0]

    async def handler(event):
        raise AssertionError()

    consumer = consuming(RedisClaimStore(stream.client, namespace=stream.namespace), handler)
    with pytest.raises(RuntimeError, match="capacity"):
        await stream.process(delivery, consumer)
    assert (await stream.client.xpending(stream.stream, stream.group))["pending"] == 1


async def test_ack_error_redelivery_does_not_repeat_handler(stream, monkeypatch):
    calls = []

    async def handler(event):
        calls.append(event)

    consumer = consuming(RedisClaimStore(stream.client, namespace=stream.namespace), handler)
    await stream.publish(Event("id", "demo", {}))
    delivery = (await stream.read())[0]
    original = stream.ack

    async def broken(delivery):
        raise RuntimeError("ack")

    monkeypatch.setattr(stream, "ack", broken)
    with pytest.raises(RuntimeError, match="ack"):
        await stream.process(delivery, consumer)
    assert await stream.failure_count(delivery) == 0
    monkeypatch.setattr(stream, "ack", original)
    assert await stream.process(delivery, consumer) == "completed"
    assert len(calls) == 1


async def test_cancel_and_terminal_semantics(stream):
    async def cancel(event):
        raise asyncio.CancelledError()

    store = RedisClaimStore(stream.client, namespace=stream.namespace)
    await stream.publish(Event("id", "demo", {}))
    delivery = (await stream.read())[0]
    with pytest.raises(asyncio.CancelledError):
        await stream.process(delivery, consuming(store, cancel))
    assert await stream.failure_count(delivery) == 0
    assert (await stream.client.xpending(stream.stream, stream.group))["pending"] == 1

    async def terminal(event):
        raise TerminalEventError("bad business input")

    assert await stream.process(delivery, consuming(store, terminal)) == "dead"


def test_bad_configuration():
    with pytest.raises(ValueError):
        RedisClaimStore(None, namespace="", lease_seconds=0)
    with pytest.raises(ValueError):
        RedisStreams(None, stream="s", group="g", consumer="c", namespace="n", dlq_stream="s")
    with pytest.raises(ValueError):
        JsonCodec().decode(b'{"event_id":"a","event_id":"b","name":"demo","payload":{}}')


async def test_stale_handler_cannot_record_retry_or_dead_letter(stream):
    from modkit_events import OwnershipLost

    store = RedisClaimStore(stream.client, namespace=stream.namespace, lease_seconds=0.01)

    async def expired(event):
        await asyncio.sleep(0.03)
        raise TerminalEventError("old owner")

    await stream.publish(Event("id", "demo", {}))
    delivery = (await stream.read())[0]
    with pytest.raises(OwnershipLost):
        await stream.process(delivery, consuming(store, expired))
    assert await stream.failure_count(delivery) == 0
    assert await stream.client.xlen(stream.dlq_stream) == 0
    assert (await stream.client.xpending(stream.stream, stream.group))["pending"] == 1

    async def retry_expired(event):
        await asyncio.sleep(0.03)
        raise RuntimeError("old owner")

    with pytest.raises(OwnershipLost):
        await stream.process(delivery, consuming(store, retry_expired))
    assert await stream.failure_count(delivery) == 0


async def test_terminal_delivery_does_not_replay_already_fetched_duplicate(stream):
    calls = []

    async def terminal(event):
        calls.append(event)
        raise TerminalEventError("terminal")

    store = RedisClaimStore(stream.client, namespace=stream.namespace)
    await stream.publish(Event("id", "demo", {}))
    delivery = (await stream.read())[0]
    consumer = consuming(store, terminal)
    assert await stream.process(delivery, consumer) == "dead"
    assert await stream.process(delivery, consumer) == "dead"
    assert len(calls) == 1
    assert await stream.client.xlen(stream.dlq_stream) == 1

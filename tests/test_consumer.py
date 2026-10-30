import asyncio

import pytest

from modkit_events import Consumer, Dispatcher, Event, MemoryClaimStore, OwnershipLost


def setup(store):
    calls = []
    d = Dispatcher()

    async def handler(event):
        calls.append(event)

    d.subscribe("demo", handler)
    return Consumer(store, d, scope="group"), calls


async def test_claim_states_and_stale_token():
    now = [0.0]
    store = MemoryClaimStore(lease_seconds=2, clock=lambda: now[0])
    first = await store.claim("g", "id")
    assert (await store.claim("g", "id")).state == "inflight"
    now[0] = 3
    second = await store.claim("g", "id")
    assert not await store.complete(first.claim)
    assert not await store.release(first.claim)
    assert await store.complete(second.claim)
    assert (await store.claim("g", "id")).state == "completed"
    assert (await store.claim("different", "id")).state == "acquired"


async def test_consumer_completed_and_inflight():
    store = MemoryClaimStore()
    consumer, calls = setup(store)
    event = Event("id", "demo", {})
    claim = (await store.claim("group", "id")).claim
    assert await consumer.consume(event) == "inflight"
    assert calls == []
    await store.release(claim)
    assert await consumer.consume(event) == "processed"
    assert await consumer.consume(event) == "completed"
    assert len(calls) == 1


async def test_failure_release_and_cancel_cleanup_preserves_original():
    class BrokenCleanup(MemoryClaimStore):
        async def release(self, claim):
            raise RuntimeError("cleanup")

    d = Dispatcher()

    async def cancelled(event):
        raise asyncio.CancelledError("original")

    d.subscribe("demo", cancelled)
    consumer = Consumer(BrokenCleanup(), d, scope="g")
    with pytest.raises(asyncio.CancelledError, match="original") as error:
        await consumer.consume(Event("id", "demo", {}))
    assert "cleanup" in error.value.__notes__[0]


async def test_handler_failure_retries():
    store = MemoryClaimStore()
    d = Dispatcher()
    calls = []

    async def fail(event):
        calls.append(event)
        raise RuntimeError("handler")

    d.subscribe("demo", fail)
    consumer = Consumer(store, d, scope="g")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await consumer.consume(Event("id", "demo", {}))
    assert len(calls) == 2


async def test_lease_expiry_allows_overlap_but_old_owner_cannot_finish():
    now = [0.0]
    store = MemoryClaimStore(lease_seconds=1, clock=lambda: now[0])
    entered = asyncio.Event()
    finish = asyncio.Event()
    calls = []
    d = Dispatcher()

    async def handler(event):
        calls.append(event)
        if len(calls) == 1:
            entered.set()
            await finish.wait()

    d.subscribe("demo", handler)
    consumer = Consumer(store, d, scope="g")
    event = Event("id", "demo", {})
    old = asyncio.create_task(consumer.consume(event))
    await entered.wait()
    now[0] = 2
    assert await consumer.consume(event) == "processed"
    finish.set()
    with pytest.raises(OwnershipLost):
        await old
    assert len(calls) == 2

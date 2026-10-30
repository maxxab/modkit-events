"""Local boundary tests; these do not substitute for real Redis script tests."""

import pytest

from modkit_events import Consumer, Dispatcher, Event, JsonCodec, MemoryClaimStore
from modkit_events.adapters import redis as adapter


async def test_failure_disposition_keeps_owner_until_atomic_script():
    class Client:
        async def hget(self, key, field):
            return None

        async def eval(self, script, *args):
            if script == adapter._CLAIM:
                return 1
            if script == adapter._DUE:
                return 1
            if script == adapter._FAILURE:
                assert not store.released, "claim released before failure disposition"
                return 1
            return 1

    client = Client()

    class Store(adapter.RedisClaimStore):
        released = False

        async def release(self, claim):
            self.released = True
            return True

    store = Store(client, namespace="n")
    dispatcher = Dispatcher()

    async def bad(event):
        raise RuntimeError("handler")

    dispatcher.subscribe("demo", bad)
    bus = adapter.RedisStreams(client, stream="s", group="g", consumer="c", namespace="n")
    delivery = adapter.Delivery("1-0", JsonCodec().encode(Event("id", "demo", {})))
    assert await bus.process(delivery, Consumer(store, dispatcher, scope="g")) == "retry"


async def test_automatic_disposition_rejects_cross_store_atomicity_claim():
    bus = adapter.RedisStreams(None, stream="s", group="g", consumer="c", namespace="n")
    consumer = Consumer(MemoryClaimStore(), Dispatcher(), scope="g")
    with pytest.raises(ValueError, match="RedisClaimStore"):
        await bus.process(adapter.Delivery("1-0", b"{}"), consumer)


@pytest.mark.parametrize(
    "response",
    [
        [(b"s", [(b"1-0", {b"data": b"raw"})])],
        {b"s": [(b"1-0", {b"data": b"raw"})]},
        {b"s": [[(b"1-0", {b"data": b"raw"})]]},
    ],
)
async def test_read_accepts_resp2_unified_and_legacy_resp3_shapes(response):
    class Client:
        async def xreadgroup(self, *args, **kwargs):
            return response

    bus = adapter.RedisStreams(Client(), stream="s", group="g", consumer="c", namespace="n")
    assert await bus.read() == [adapter.Delivery("1-0", b"raw")]

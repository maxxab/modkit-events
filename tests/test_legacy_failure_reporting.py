"""Local boundary regressions: diagnostics must not change failure disposition."""

import asyncio

import pytest

from modkit_events import Consumer, Dispatcher, Event, JsonCodec, OwnershipLost, RetryPolicy
from modkit_events.adapters import redis as adapter
from modkit_events.claims import Claim, ClaimResult
from modkit_events.outbox import OutboxClaim, OutboxPublisher


class Unprintable(Exception):
    def __str__(self):
        raise ValueError("rendering failed")


class UnprintableBase(Exception):
    def __str__(self):
        raise KeyboardInterrupt("rendering failed")


class UnprintableTerminal(adapter.TerminalEventError):
    def __str__(self):
        raise ValueError("rendering failed")


class NoNotes(asyncio.CancelledError):
    def add_note(self, note):
        raise KeyboardInterrupt("annotation failed")


EVENT = Event("event-1", "example", {})


class RaisingHandler:
    def __init__(self, error):
        self.error = error
        self.calls = 0
        self.received_tb = None

    async def __call__(self, event):
        assert event == EVENT
        self.calls += 1
        try:
            raise self.error
        except BaseException:
            self.received_tb = self.error.__traceback__
            raise

    publish = __call__


def dispatcher(handler):
    result = Dispatcher()
    result.subscribe(EVENT.name, handler)
    return result


class ClaimStore:
    def __init__(self, cleanup):
        self.cleanup = cleanup
        self.releases = []
        self.claim_value = Claim("scope", EVENT.event_id, "token")

    async def claim(self, scope, key):
        assert (scope, key) == ("scope", EVENT.event_id)
        return ClaimResult("acquired", self.claim_value)

    async def release(self, claim):
        self.releases.append(claim)
        if isinstance(self.cleanup, BaseException):
            raise self.cleanup
        return self.cleanup

    async def complete(self, claim):
        pytest.fail("Failure must not complete")


class OutboxStore:
    def __init__(self, attempt=2, failure=True):
        self.value = OutboxClaim(EVENT, "outbox-token", attempt)
        self.failure = failure
        self.failures = []
        self.claims = 0

    async def claim(self, limit):
        assert limit == 1
        self.claims += 1
        assert self.claims == 1
        return [self.value]

    async def fail(self, claim, error, delay, max_attempts):
        self.failures.append((claim, error, delay, max_attempts))
        if isinstance(self.failure, BaseException):
            raise self.failure
        return self.failure

    async def complete(self, claim, message_id):
        pytest.fail("Failure must not complete")


class RedisBoundary:
    """No client creation: capture real adapter's calls at its I/O boundary."""

    def __init__(self, *, release=True, count=3, dead=1):
        self.release = release
        self.count = count
        self.dead = dead
        self.calls = []
        self.claim_key = None
        self.token = None

    async def hget(self, key, field):
        self.calls.append(("hget", key, field))
        return 0

    async def eval(self, script, number, *args):
        self.calls.append((script, number, *args))
        if script == adapter._CLAIM:
            assert number == 2
            self.claim_key, _, self.token, lease = args
            assert lease == 60000
            return 1
        if script == adapter._DUE:
            assert number == 1
            return 1
        if script == adapter._RELEASE:
            assert (number, args) == (1, (self.claim_key, self.token))
            if isinstance(self.release, BaseException):
                raise self.release
            return self.release
        if script == adapter._FAILURE:
            assert number == 2
            assert args[1:] == (self.claim_key, 2000, 20000, self.token, 3)
            return self.count
        if script == adapter._DEAD:
            assert number == 5
            assert args[4] == self.claim_key
            assert args[5:9] == ("group", "1-0", JsonCodec().encode(EVENT), 10000)
            assert isinstance(args[9], str) and args[9]
            assert args[10] == self.token
            if isinstance(self.dead, BaseException):
                raise self.dead
            return self.dead
        pytest.fail("Unexpected script: completion/ACK/replay forbidden")


def redis_case(handler, **kwargs):
    client = RedisBoundary(**kwargs)
    streams = adapter.RedisStreams(
        client,
        stream="source",
        group="group",
        consumer="worker",
        namespace="ns",
        retry=RetryPolicy(max_attempts=3, base_delay=2, max_delay=20),
    )
    consumer = Consumer(
        adapter.RedisClaimStore(client, namespace="ns"), dispatcher(handler), scope="scope"
    )
    delivery = adapter.Delivery("1-0", JsonCodec().encode(EVENT))
    return client, streams.process(delivery, consumer)


def assert_primary(caught, original, handler, metadata):
    assert caught is original
    assert (caught.__cause__, caught.__context__, caught.__suppress_context__) == metadata
    assert caught.__notes__[0] == "existing note"
    tb = caught.__traceback__
    while tb is not None and tb is not handler.received_tb:
        tb = tb.tb_next
    assert tb is handler.received_tb and tb is not None
    assert handler.calls == 1


@pytest.mark.parametrize("entry", ["consumer", "outbox", "redis"])
@pytest.mark.parametrize(
    "cleanup", [Unprintable(), UnprintableBase(), ValueError("cleanup"), False]
)
@pytest.mark.parametrize("reject_notes", [False, True])
async def test_cleanup_preserves_primary_metadata_traceback_and_once(entry, cleanup, reject_notes):
    original = NoNotes("cancel") if reject_notes else asyncio.CancelledError("cancel")
    original.__cause__ = ValueError("cause")
    original.__context__ = RuntimeError("context")
    original.__suppress_context__ = True
    BaseException.add_note(original, "existing note")
    metadata = (original.__cause__, original.__context__, original.__suppress_context__)
    handler = RaisingHandler(original)
    if entry == "consumer":
        store = ClaimStore(cleanup)
        call = Consumer(store, dispatcher(handler), scope="scope").consume(EVENT)
    elif entry == "outbox":
        store = OutboxStore(failure=cleanup)
        call = OutboxPublisher(store, handler, batch_size=1).process_once()
    else:
        client, call = redis_case(handler, release=cleanup)
    caught = None
    try:
        await call
    except BaseException as error:
        caught = error
    assert_primary(caught, original, handler, metadata)
    if entry == "consumer":
        assert store.releases == [store.claim_value]
    elif entry == "outbox":
        assert store.failures == [(store.value, "cancelled", 0, 3)]
    else:
        assert [call[0] for call in client.calls] == [
            adapter._CLAIM,
            "hget",
            adapter._DUE,
            adapter._RELEASE,
        ]
    if not reject_notes and isinstance(cleanup, ValueError):
        assert original.__notes__[1].endswith("ValueError: cleanup")
    if not reject_notes and cleanup is False and entry != "outbox":
        assert original.__notes__[1] == "Claim release lost ownership"


@pytest.mark.parametrize("attempt,want,delay", [(2, "retry", 4), (3, "dead", 8)])
@pytest.mark.parametrize("error", [Unprintable(), ValueError("printable")])
async def test_outbox_error_text_cannot_prevent_disposition(attempt, want, delay, error):
    handler = RaisingHandler(error)
    store = OutboxStore(attempt)
    result = await OutboxPublisher(
        store, handler, batch_size=1, retry=RetryPolicy(3, 2, 20)
    ).process_once()
    assert result == [want]
    assert handler.calls == store.claims == len(store.failures) == 1
    claim, text, actual_delay, budget = store.failures[0]
    assert (claim, actual_delay, budget) == (store.value, delay, 3)
    assert isinstance(text, str) and text
    if isinstance(error, ValueError):
        assert text == "printable"


@pytest.mark.parametrize("failure", [False, RuntimeError("store failed")])
async def test_outbox_storage_and_fence_errors_still_propagate(failure):
    original = Unprintable()
    handler = RaisingHandler(original)
    store = OutboxStore(failure=failure)
    with pytest.raises((OwnershipLost, RuntimeError)) as caught:
        await OutboxPublisher(store, handler, batch_size=1).process_once()
    if failure is False:
        assert isinstance(caught.value, OwnershipLost)
        assert caught.value.__cause__ is original
    else:
        assert caught.value is failure
    assert handler.calls == len(store.failures) == 1


@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize("printable", [False, True])
@pytest.mark.parametrize("dead", [1, 0, -1, RuntimeError("DLQ storage failed")])
async def test_redis_disposition_reaches_fenced_dlq_once(terminal, printable, dead):
    if terminal:
        error = adapter.TerminalEventError("printable") if printable else UnprintableTerminal()
    else:
        error = ValueError("printable") if printable else Unprintable()
    handler = RaisingHandler(error)
    client, call = redis_case(handler, dead=dead)
    if dead == 1:
        assert await call == "dead"
    else:
        with pytest.raises(RuntimeError) as caught:
            await call
        if dead == -1:
            assert isinstance(caught.value, OwnershipLost)
        elif dead == 0:
            assert "capacity" in str(caught.value)
        else:
            assert caught.value is dead
    expected = [adapter._CLAIM, "hget", adapter._DUE]
    if not terminal:
        expected.append(adapter._FAILURE)
    expected.append(adapter._DEAD)
    assert [call[0] for call in client.calls] == expected
    assert handler.calls == 1
    if printable:
        assert client.calls[-1][-2] == "printable"


@pytest.mark.parametrize("count", [1, -1])
async def test_redis_retry_and_stale_fence_do_not_dead_letter(count):
    error = Unprintable()
    handler = RaisingHandler(error)
    client, call = redis_case(handler, count=count)
    if count == 1:
        assert await call == "retry"
    else:
        with pytest.raises(OwnershipLost) as caught:
            await call
        assert caught.value.__cause__ is error
    assert [call[0] for call in client.calls] == [
        adapter._CLAIM,
        "hget",
        adapter._DUE,
        adapter._FAILURE,
    ]
    assert handler.calls == 1


@pytest.mark.parametrize("broken", [False, True])
async def test_invalid_envelope_text_cannot_prevent_unfenced_dlq(broken):
    class BadEnvelope(ValueError):
        def __str__(self):
            raise ValueError("rendering failed")

    class Codec:
        def decode(self, raw):
            raise BadEnvelope() if broken else ValueError("invalid")

    class Boundary:
        def __init__(self):
            self.calls = []

        async def eval(self, script, number, *args):
            self.calls.append((script, number, args))
            assert script == adapter._DEAD and number == 4
            assert args[4:8] == ("group", "1-0", b"invalid", 10000)
            assert args[-1] == ""
            assert args[-2].startswith("Invalid envelope: ")
            if not broken:
                assert args[-2] == "Invalid envelope: invalid"
            return 1

    client = Boundary()
    streams = adapter.RedisStreams(
        client, stream="source", group="group", consumer="worker", namespace="ns", codec=Codec()
    )
    consumer = Consumer(
        adapter.RedisClaimStore(client, namespace="ns"), Dispatcher(), scope="scope"
    )
    assert await streams.process(adapter.Delivery("1-0", b"invalid"), consumer) == "dead"
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "cleanup", [Unprintable(), UnprintableBase(), ValueError("cleanup"), False]
)
async def test_consumer_ordinary_handler_failure_remains_primary(cleanup):
    original = ValueError("handler")
    original.__cause__ = RuntimeError("cause")
    original.__context__ = RuntimeError("context")
    original.__suppress_context__ = True
    original.add_note("existing note")
    metadata = (original.__cause__, original.__context__, original.__suppress_context__)
    handler = RaisingHandler(original)
    store = ClaimStore(cleanup)
    caught = None
    try:
        await Consumer(store, dispatcher(handler), scope="scope").consume(EVENT)
    except BaseException as error:
        caught = error
    assert_primary(caught, original, handler, metadata)
    assert store.releases == [store.claim_value]

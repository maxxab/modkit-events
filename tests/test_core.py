import math

import pytest

from modkit_events import Dispatcher, Event, JsonCodec, RetryPolicy


def test_event_snapshot_and_roundtrip():
    payload = {"nested": [1, {"ok": True}]}
    event = Event("1", "demo", payload, metadata={"trace": "x"})
    payload["nested"].append(2)
    assert event.payload == {"nested": (1, {"ok": True})}
    with pytest.raises(TypeError):
        event.payload["x"] = 3
    assert JsonCodec().decode(JsonCodec().encode(event)) == event


@pytest.mark.parametrize(
    "args", [("", "a", {}), ("a", "", {}), ("a", "b", {}, 0), ("a", "b", {}, True)]
)
def test_invalid_identity(args):
    with pytest.raises(ValueError):
        Event(*args)


@pytest.mark.parametrize("payload", [{"n": math.nan}, {1: "a"}, {"x": object()}])
def test_non_json_rejected(payload):
    with pytest.raises((ValueError, TypeError)):
        Event("a", "b", payload)


def test_codec_rejects_size_depth_and_bad_schema():
    with pytest.raises(ValueError):
        JsonCodec(max_bytes=8).encode(Event("a", "b", {}))
    with pytest.raises(ValueError):
        JsonCodec(max_bytes=8).decode(b"x" * 9)
    with pytest.raises(ValueError):
        JsonCodec(max_depth=2).encode(Event("a", "b", {"x": {"y": {"z": 1}}}))
    for raw in [b"{}", b"[]", b"{", b'{"event_id":"a","name":"b","payload":{"x":NaN}}']:
        with pytest.raises(ValueError):
            JsonCodec().decode(raw)


async def test_ordered_dispatch_partial_retry():
    calls = []
    dispatcher = Dispatcher()

    async def first(event):
        calls.append(event.event_id)

    async def bad(event):
        raise RuntimeError("handler")

    dispatcher.subscribe("demo", first)
    dispatcher.subscribe("demo", bad)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="handler"):
            await dispatcher.dispatch(Event("1", "demo", {}))
    assert calls == ["1", "1"]
    with pytest.raises(LookupError):
        await dispatcher.dispatch(Event("2", "unhandled", {}))


def test_retry_bounds():
    policy = RetryPolicy(max_attempts=3, base_delay=2, max_delay=5)
    assert [policy.delay(n) for n in (1, 2, 3, 100000)] == [2, 4, 5, 5]
    for kwargs in [{"max_attempts": 0}, {"base_delay": -1}, {"max_delay": math.inf}]:
        with pytest.raises(ValueError):
            RetryPolicy(**kwargs)

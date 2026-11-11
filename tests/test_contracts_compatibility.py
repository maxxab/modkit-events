"""Pure controls plus explicit async cases excluded from the synchronous runner."""

import unittest

from test_contracts import Validator

from modkit_events import Dispatcher, Event, JsonCodec
from modkit_events.contracts import EventContract, InvalidContractConfiguration
from modkit_events.delivery import DeliveryPhase, DeliveryRecord, Disposition, DispositionKind
from modkit_events.subscriptions import InvalidSubscriptionConfiguration, Subscription


class CompatibilityTests(unittest.TestCase):
    def test_long_nul_inputs_remain_legacy_valid(self):
        for value in ("x" * 257, "é" * 129, "x\0"):
            event = Event(value, value, {}, metadata={"trace": value, "message_id": value})
            self.assertEqual(JsonCodec().decode(JsonCodec().encode(event)), event)
            d = Dispatcher()

            async def handler(event):
                pass

            d.subscribe(value, handler)
            d.subscribe(value, handler)
            DeliveryRecord(
                event_id=value,
                phase=DeliveryPhase.PUBLICATION,
                disposition=Disposition(kind=DispositionKind.CONFIRMED),
            )
            with self.assertRaises(InvalidContractConfiguration):
                EventContract(name=value, schema_version=1, route="stream", validator=Validator())
            with self.assertRaises(InvalidSubscriptionConfiguration):
                Subscription(subscription_id="s", group="g", route="stream", event_names=[value])

    def test_golden_envelope(self):
        event = Event("id", "event", {"x": [1]}, metadata={"trace": "z"})
        self.assertEqual(
            JsonCodec().encode(event),
            b'{"event_id":"id","name":"event","schema_version":1,"payload":{"x":[1]},"metadata":{"trace":"z"}}',
        )
        for raw in (
            b'{"event_id":"a","event_id":"b","name":"x","payload":{}}',
            b'{"event_id":"a","name":"x","payload":{"x":NaN}}',
        ):
            with self.assertRaises(ValueError):
                JsonCodec().decode(raw)
        with self.assertRaises(ValueError):
            JsonCodec(max_bytes=2).encode(event)


async def test_legacy_order_partial_failure():
    calls = []
    d = Dispatcher()

    async def first(event):
        calls.append(event.event_id)

    async def bad(event):
        raise RuntimeError("handler")

    d.subscribe("long" * 100, first)
    d.subscribe("long" * 100, bad)
    for _ in range(2):
        try:
            await d.dispatch(Event("id", "long" * 100, {}))
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected failure")
    assert calls == ["id", "id"]

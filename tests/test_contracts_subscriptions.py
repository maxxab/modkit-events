import unittest
from collections import namedtuple

from test_contracts import contract

from modkit_events.contracts import ContractRegistry
from modkit_events.models import Event
from modkit_events.subscriptions import (
    ConflictingConsumerGroupError,
    DuplicateSubscriptionError,
    InvalidSubscriptionConfiguration,
    StartPosition,
    Subscription,
    UnsupportedCapabilityError,
    validate_subscriptions,
)


def subscription(**kwargs):
    values = dict(subscription_id="sub", group="group", route="stream", event_names=["event"])
    values.update(kwargs)
    return Subscription(**values)


class SubscriptionTests(unittest.TestCase):
    def test_manifest_and_filters(self):
        names = ["event"]
        sub = subscription(event_names=names)
        names.append("other")
        self.assertEqual(sub.event_names, frozenset({"event"}))
        self.assertIs(sub.start_position, StartPosition.BEGINNING)
        self.assertIs(
            subscription(start_position=StartPosition.LATEST).start_position, StartPosition.LATEST
        )
        self.assertTrue(sub.matches(Event("id", "event", {}, 2**20000)))
        self.assertFalse(sub.matches(Event("id", "other", {})))
        self.assertEqual(validate_subscriptions([sub]), (sub,))
        with self.assertRaises(DuplicateSubscriptionError):
            validate_subscriptions([sub, sub])
        with self.assertRaises(ConflictingConsumerGroupError):
            validate_subscriptions([sub, subscription(subscription_id="other")])
        self.assertEqual(
            len(
                validate_subscriptions([sub, subscription(subscription_id="other", route="other")])
            ),
            2,
        )
        for names in ([], ["event", "event"], ["x" * 257], ["x\0"], [None]):
            with self.assertRaises(InvalidSubscriptionConfiguration):
                subscription(event_names=names)
        for position in ("beginning", True, 1, None):
            with self.assertRaises(InvalidSubscriptionConfiguration):
                subscription(start_position=position)
        with self.assertRaises(InvalidSubscriptionConfiguration):
            validate_subscriptions([{}])
        with self.assertRaises(InvalidSubscriptionConfiguration):
            sub.matches({})

    def test_exact_capabilities_and_shapes(self):
        sub = subscription()
        registry = ContractRegistry([contract(), contract(version=3), contract(name="other")])
        sub.validate(registry, handler_capabilities=[("event", 1)])
        Pair = namedtuple("Pair", "name version")
        malformed = [
            "ab",
            b"ab",
            ["event", 1],
            (),
            ("event",),
            ("event", 1, 2),
            {"event": 1},
            iter(["event", 1]),
            Pair("event", 1),
            ([], 1),
            ("event", {}),
            (1, 1),
            ("event", True),
            ("event", 1.0),
            ("event", "1"),
        ]
        for entry in malformed:
            with self.subTest(kind=type(entry).__name__):
                with self.assertRaises(UnsupportedCapabilityError):
                    sub.validate(registry, handler_capabilities=[entry])
        for entries in ([], [("event", 2)], [("other", 1)], [("event", 1), ("event", 1)]):
            with self.assertRaises(UnsupportedCapabilityError):
                sub.validate(registry, handler_capabilities=entries)
        with self.assertRaises(UnsupportedCapabilityError):
            sub.validate(
                ContractRegistry([contract(route="wrong")]), handler_capabilities=[("event", 1)]
            )
        with self.assertRaises(UnsupportedCapabilityError):
            sub.validate({}, handler_capabilities=[])
        error = RuntimeError("iterator")

        def broken():
            yield ("event", 1)
            raise error

        try:
            sub.validate(registry, handler_capabilities=broken())
        except RuntimeError as actual:
            self.assertIs(actual, error)
        else:
            self.fail("iterator error hidden")

    def test_collection_bounds(self):
        self.assertEqual(
            len(subscription(event_names=[f"n{i}" for i in range(1024)]).event_names), 1024
        )

        def excess_names():
            for i in range(1025):
                yield f"n{i}"
            self.fail("read past filter limit")

        with self.assertRaises(InvalidSubscriptionConfiguration):
            subscription(event_names=excess_names())

        def subs(count):
            for i in range(count):
                yield subscription(subscription_id=f"s{i}", group=f"g{i}")

        self.assertEqual(len(validate_subscriptions(subs(4096))), 4096)

        def excess_manifest():
            yield from subs(4097)
            self.fail("read past manifest limit")

        with self.assertRaises(InvalidSubscriptionConfiguration):
            validate_subscriptions(excess_manifest())
        registry = ContractRegistry(contract(version=i + 1) for i in range(4096))
        subscription().validate(
            registry, handler_capabilities=(("event", i + 1) for i in range(4096))
        )

        def excess_caps():
            for i in range(4097):
                yield ("event", i + 1)
            self.fail("read past capability limit")

        with self.assertRaises(UnsupportedCapabilityError):
            subscription().validate(registry, handler_capabilities=excess_caps())

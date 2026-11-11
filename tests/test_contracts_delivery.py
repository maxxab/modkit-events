import unittest
from datetime import datetime, timedelta, timezone

from test_contracts_subscriptions import subscription

from modkit_events.delivery import (
    DeliveryContext,
    DeliveryPhase,
    DeliveryRecord,
    DeliveryRouteMismatch,
    Disposition,
    DispositionKind,
)


def context(**kwargs):
    values = dict(
        subscription_id="sub",
        broker="redis",
        destination="stream",
        group="group",
        consumer_id="replica",
        message_id="1-0",
        received_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    values.update(kwargs)
    return DeliveryContext(**values)


class DeliveryTests(unittest.TestCase):
    def test_context(self):
        c = context()
        c.validate_subscription(subscription())
        for kwargs in ({"subscription_id": "wrong"}, {"group": "wrong"}, {"destination": "wrong"}):
            with self.assertRaises(DeliveryRouteMismatch):
                context(**kwargs).validate_subscription(subscription())
        with self.assertRaises(ValueError):
            c.validate_subscription({})
        for count in (None, 1, 2**63 - 1):
            context(delivery_count=count)
        for count in (0, -1, True, 1.0, "1", 2**63):
            with self.assertRaises(ValueError):
                context(delivery_count=count)
        context(message_id="18446744073709551615-18446744073709551615")
        context(message_id="x" * 512)
        for message_id in ("x" * 513, "x\0", "\ud800", " "):
            with self.assertRaises(ValueError):
                context(message_id=message_id)
        with self.assertRaises(ValueError):
            context(received_at=datetime(2026, 1, 1))
        offset = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(context(received_at=offset).received_at, offset)
        self.assertIs(context(received_at=offset).received_at.tzinfo, timezone.utc)
        with self.assertRaises(AttributeError):
            c.message_id = "changed"

    def test_dispositions_and_records(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        confirmed = Disposition(kind=DispositionKind.CONFIRMED)
        for kind in DispositionKind:
            reason = None if kind is DispositionKind.CONFIRMED else "category"
            d = Disposition(kind=kind, reason_code=reason)
            for phase in DeliveryPhase:
                record = DeliveryRecord(
                    event_id="id", phase=phase, disposition=d, context=context()
                )
                self.assertIs(record.disposition, d)
            if kind is not DispositionKind.CONFIRMED:
                with self.assertRaises(ValueError):
                    Disposition(kind=kind)
            if kind is DispositionKind.DEFERRED:
                Disposition(kind=kind, reason_code=reason, retry_at=now)
            else:
                with self.assertRaises(ValueError):
                    Disposition(kind=kind, reason_code=reason, retry_at=now)
        with self.assertRaises(ValueError):
            Disposition(kind=DispositionKind.CONFIRMED, reason_code="category")
        for reason in ("", "A", "secret text", "a" * 65, "é", 1):
            with self.assertRaises(ValueError):
                Disposition(kind=DispositionKind.REJECTED, reason_code=reason)
        for kind in ("confirmed", DeliveryPhase.INTAKE, True, None):
            with self.assertRaises(ValueError):
                Disposition(kind=kind)
        for phase in ("intake", DispositionKind.CONFIRMED, True, None):
            with self.assertRaises(ValueError):
                DeliveryRecord(event_id="id", phase=phase, disposition=confirmed)
        for phase in (DeliveryPhase.INTAKE, DeliveryPhase.PROCESSING):
            with self.assertRaises(ValueError):
                DeliveryRecord(event_id="id", phase=phase, disposition=confirmed)
        DeliveryRecord(event_id="id", phase=DeliveryPhase.PUBLICATION, disposition=confirmed)
        for kwargs in ({"disposition": {}}, {"context": {}}, {"event_id": " "}):
            values = dict(event_id="id", phase=DeliveryPhase.PUBLICATION, disposition=confirmed)
            values.update(kwargs)
            with self.assertRaises(ValueError):
                DeliveryRecord(**values)
        self.assertFalse(hasattr(confirmed, "ack"))
        self.assertFalse(hasattr(confirmed, "commit"))

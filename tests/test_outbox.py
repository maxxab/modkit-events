import asyncio

import pytest

from modkit_events import Event, RetryPolicy
from modkit_events.outbox import OutboxClaim, OutboxPublisher


class Store:
    def __init__(self):
        self.rows = [OutboxClaim(Event("id", "demo", {}), "token", 1)]
        self.done = []
        self.failed = []

    async def claim(self, limit):
        rows, self.rows = self.rows[:limit], self.rows[limit:]
        return rows

    async def complete(self, claim, message_id):
        self.done.append(message_id)
        return True

    async def fail(self, claim, error, delay, max_attempts):
        self.failed.append((error, delay, max_attempts))
        return True


async def test_outbox_success_failure_timeout_and_cancel():
    class Broker:
        async def publish(self, event):
            return "1-0"

    store = Store()
    worker = OutboxPublisher(store, Broker())
    assert await worker.process_once() == ["published"]
    assert store.done == ["1-0"]

    class Failing:
        async def publish(self, event):
            raise RuntimeError("publish failed")

    store.rows = [OutboxClaim(Event("id", "demo", {}), "token", 1)]
    worker = OutboxPublisher(store, Failing(), retry=RetryPolicy(base_delay=2))
    assert await worker.process_once() == ["retry"]
    assert store.failed[-1] == ("publish failed", 2, 3)

    class Slow:
        async def publish(self, event):
            await asyncio.sleep(10)

    store.rows = [OutboxClaim(Event("id", "demo", {}), "token", 1)]
    worker = OutboxPublisher(store, Slow(), timeout=0.001)
    assert await worker.process_once() == ["retry"]

    class Cancel:
        async def publish(self, event):
            raise asyncio.CancelledError()

    store.rows = [OutboxClaim(Event("id", "demo", {}), "token", 1)]
    worker = OutboxPublisher(store, Cancel())
    with pytest.raises(asyncio.CancelledError):
        await worker.process_once()
    assert len(store.done) == 1


async def test_completion_storage_error_not_publish_retry():
    class Broken(Store):
        async def complete(self, claim, message_id):
            raise RuntimeError("database")

    class Broker:
        async def publish(self, event):
            return "1-0"

    store = Broken()
    with pytest.raises(RuntimeError, match="database"):
        await OutboxPublisher(store, Broker()).process_once()
    assert store.failed == []


async def test_claims_one_immediately_before_each_publish_not_queued_batch():
    class Leases(Store):
        def __init__(self):
            super().__init__()
            self.rows.append(OutboxClaim(Event("second", "demo", {}), "second-token", 1))
            self.calls = []

        async def claim(self, limit):
            self.calls.append(("claim", limit))
            rows, self.rows = self.rows[:limit], self.rows[limit:]
            return rows

    store = Leases()

    class Broker:
        async def publish(self, event):
            store.calls.append(("publish", event.event_id))
            return "receipt"

    await OutboxPublisher(store, Broker(), batch_size=2).process_once()
    assert store.calls == [("claim", 1), ("publish", "id"), ("claim", 1), ("publish", "second")]


async def test_recovered_claim_over_budget_is_dead_without_another_publish():
    store = Store()
    store.rows = [OutboxClaim(Event("id", "demo", {}), "recovered", 4)]

    class Broker:
        async def publish(self, event):
            raise AssertionError("exhausted recovered claim must not publish")

    assert await OutboxPublisher(store, Broker()).process_once() == ["dead"]
    assert store.failed == [("Attempt budget exhausted before publish", 0, 3)]

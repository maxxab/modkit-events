"""Behavior controls for the opt-in batch helper, not broker qualification."""

import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from itertools import count

import pytest

from modkit_events.batch_publication import PublicationRejected, PublicationResult, publish_batch
from modkit_events.delivery import (
    DeliveryContext,
    DeliveryPhase,
    DeliveryRecord,
    Disposition,
    DispositionKind,
)
from modkit_events.models import Event


class RecordingPublisher:
    """In-memory transport boundary; the real batch helper owns all decisions."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.events = []

    async def publish(self, event):
        self.events.append(event)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


async def collect(batch):
    return [result async for result in batch]


def event(identity="one"):
    return Event(identity, "garden.reading", {"values": [1, {"temperature": 21}]})


def publication_record(kind=DispositionKind.CONFIRMED):
    return DeliveryRecord(
        event_id="one",
        phase=DeliveryPhase.PUBLICATION,
        disposition=Disposition(
            kind=kind, reason_code=None if kind is DispositionKind.CONFIRMED else "test_reason"
        ),
    )


async def test_success_yields_publication_observation_and_preserves_receipt():
    original = event()
    publisher = RecordingPublisher(" 1700-0 ")

    results = await collect(publish_batch(publisher, [original]))

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, PublicationResult)
    assert result.record.event_id == "one"
    assert result.record.phase is DeliveryPhase.PUBLICATION
    assert result.record.disposition.kind is DispositionKind.CONFIRMED
    assert result.record.disposition.reason_code is None
    assert result.record.disposition.retry_at is None
    assert result.record.context is None
    assert result.message_id == " 1700-0 "
    assert publisher.events == [original]
    assert publisher.events[0] is original
    with pytest.raises(FrozenInstanceError):
        result.message_id = "replacement"


async def test_snapshot_is_membership_order_and_references_not_event_copy():
    payload = {"nested": [{"value": 1}]}
    first = Event("one", "garden.reading", payload)
    second = event("two")
    source = [first, second]
    publisher = RecordingPublisher("1-0", "2-0")
    batch = publish_batch(publisher, source)
    source[:] = [event("replacement")]
    payload["nested"][0]["value"] = 999

    results = await collect(batch)

    assert [item.record.event_id for item in results] == ["one", "two"]
    assert publisher.events[0] is first
    assert publisher.events[1] is second
    # Event construction, not publish_batch, snapshots standard JSON containers.
    assert publisher.events[0].payload["nested"][0]["value"] == 1


async def test_lazy_iteration_never_prefetches_or_publishes_after_early_close():
    first, second = event(), event("two")
    publisher = RecordingPublisher("1-0", "2-0")
    batch = publish_batch(publisher, [first, second])
    assert publisher.events == []

    result = await anext(batch)
    assert result.record.event_id == "one"
    await asyncio.sleep(0)
    assert publisher.events == [first]

    await batch.aclose()
    assert publisher.events == [first]


async def test_empty_batch_is_lazy_and_has_no_publication():
    publisher = RecordingPublisher()
    assert await collect(publish_batch(publisher, [])) == []
    assert publisher.events == []


@pytest.mark.parametrize("bad", [None, {}, "event", 1, object()])
def test_invalid_late_event_prevents_all_broker_calls(bad):
    publisher = RecordingPublisher("1-0")
    with pytest.raises((TypeError, ValueError)):
        publish_batch(publisher, [event(), bad])
    assert publisher.events == []


def test_duplicate_identity_with_different_payload_is_rejected_before_io():
    publisher = RecordingPublisher("1-0", "2-0")
    conflict = Event("one", "another.name", {"value": "different"})
    with pytest.raises(ValueError):
        publish_batch(publisher, [event(), conflict])
    assert publisher.events == []


async def test_distinct_legacy_event_ids_are_preserved_without_new_profile_bounds():
    originals = [event(" a "), event("a"), event("x" * 1025)]
    publisher = RecordingPublisher("1-0", "2-0", "3-0")
    results = await collect(publish_batch(publisher, originals))
    assert [item.record.event_id for item in results] == [" a ", "a", "x" * 1025]
    assert all(actual is original for actual, original in zip(publisher.events, originals))


@pytest.mark.parametrize("limit", [1, 1000])
async def test_exact_item_limit_is_supported(limit):
    originals = [event(str(index)) for index in range(limit)]
    publisher = RecordingPublisher(*[f"{index}-0" for index in range(limit)])
    results = await collect(publish_batch(publisher, originals, max_items=limit))
    assert len(results) == limit
    assert [item.record.event_id for item in results] == [str(index) for index in range(limit)]
    assert len(publisher.events) == limit


def test_excess_input_is_bounded_and_rejected_before_any_publish():
    pulled = []

    def endless():
        for index in count():
            pulled.append(index)
            yield event(str(index))

    publisher = RecordingPublisher()
    with pytest.raises(ValueError):
        publish_batch(publisher, endless(), max_items=2)
    assert pulled == [0, 1, 2]
    assert publisher.events == []


def test_default_input_limit_stops_at_1001_without_io():
    pulled = []

    def endless():
        for index in count():
            pulled.append(index)
            yield event(str(index))

    publisher = RecordingPublisher()
    with pytest.raises(ValueError):
        publish_batch(publisher, endless())
    assert len(pulled) == 1001
    assert publisher.events == []


def test_input_iterator_failure_propagates_before_broker_io():
    failure = RuntimeError("application iterator failed")

    def broken():
        yield event()
        raise failure

    publisher = RecordingPublisher("1-0")
    with pytest.raises(RuntimeError) as caught:
        publish_batch(publisher, broken())
    assert caught.value is failure
    assert publisher.events == []


@pytest.mark.parametrize("limit", [0, -1, 1001, True, False, 1.5, "1", None])
def test_invalid_limit_fails_before_consuming_events(limit):
    def must_not_iterate():
        raise AssertionError("invalid configuration consumed application input")
        yield

    with pytest.raises(ValueError):
        publish_batch(RecordingPublisher(), must_not_iterate(), max_items=limit)


@pytest.mark.parametrize(
    "timeout", [0, -1, True, False, float("inf"), float("nan"), "1", None, 10**1000]
)
def test_invalid_timeout_fails_before_consuming_events(timeout):
    def must_not_iterate():
        raise AssertionError("invalid configuration consumed application input")
        yield

    with pytest.raises(ValueError):
        publish_batch(RecordingPublisher(), must_not_iterate(), timeout=timeout)


async def test_explicit_rejection_is_distinct_from_uncertainty_and_never_retried():
    originals = [event("one"), event("two"), event("three")]
    publisher = RecordingPublisher(
        PublicationRejected("policy_rejected"), RuntimeError("secret provider detail"), "3-0"
    )

    results = await collect(publish_batch(publisher, originals))

    assert [item.record.disposition.kind for item in results] == [
        DispositionKind.REJECTED,
        DispositionKind.UNCERTAIN,
        DispositionKind.CONFIRMED,
    ]
    assert [item.record.disposition.reason_code for item in results] == [
        "policy_rejected",
        "publish_failed",
        None,
    ]
    assert [item.message_id for item in results] == [None, None, "3-0"]
    assert [item.record.event_id for item in results] == ["one", "two", "three"]
    assert publisher.events == originals
    assert "secret provider detail" not in repr(results)


@pytest.mark.parametrize("reason", ["", "Upper", "reason with spaces", "x" * 65, None])
def test_explicit_rejection_requires_a_valid_reason_token(reason):
    with pytest.raises(ValueError):
        PublicationRejected(reason)


async def test_publisher_local_validation_error_is_uncertain_not_inferred_rejection():
    publisher = RecordingPublisher(ValueError("unknown publisher-specific validation"))
    result = (await collect(publish_batch(publisher, [event()])))[0]
    assert result.record.disposition.kind is DispositionKind.UNCERTAIN
    assert result.record.disposition.reason_code == "publish_failed"
    assert result.message_id is None


async def test_cooperative_timeout_is_uncertain_and_does_not_retry():
    originals = [event(), event("two")]

    class WaitingPublisher:
        def __init__(self):
            self.events = []
            self.first_ended = False

        async def publish(self, value):
            self.events.append(value)
            if value.event_id == "one":
                try:
                    await asyncio.Event().wait()
                finally:
                    self.first_ended = True
            return "2-0"

    publisher = WaitingPublisher()
    results = await collect(publish_batch(publisher, originals, timeout=0.01))
    assert results[0].record.disposition.kind is DispositionKind.UNCERTAIN
    assert results[0].record.disposition.reason_code == "publish_timeout"
    assert results[0].message_id is None
    assert results[1].message_id == "2-0"
    assert publisher.first_ended
    assert publisher.events == originals


async def test_cancellation_preserves_yielded_result_and_never_sends_later_event():
    originals = [event(), event("two"), event("three")]
    entered = asyncio.Event()
    ended = asyncio.Event()
    seen = []

    class Publisher:
        async def publish(self, value):
            seen.append(value)
            if value.event_id == "two":
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    ended.set()
            return "1-0"

    batch = publish_batch(Publisher(), originals)
    first = await anext(batch)
    pending = asyncio.create_task(anext(batch))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert first.message_id == "1-0"
        assert first.record.disposition.kind is DispositionKind.CONFIRMED
        assert ended.is_set()
        assert seen == originals[:2]
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await batch.aclose()


@pytest.mark.parametrize("failure", [asyncio.CancelledError("cancel"), BaseException("stop")])
async def test_base_exception_propagates_by_identity_without_later_send(failure):
    publisher = RecordingPublisher(failure, "2-0")
    batch = publish_batch(publisher, [event(), event("two")])
    with pytest.raises(type(failure)) as caught:
        await anext(batch)
    assert caught.value is failure
    assert [item.event_id for item in publisher.events] == ["one"]


@pytest.mark.parametrize(
    "receipt", [None, b"1-0", 1, True, "", " \t", "has\x00nul", "\ud800", "a" * 513, "é" * 257]
)
async def test_invalid_receipt_is_uncertain_under_local_result_policy(receipt):
    publisher = RecordingPublisher(receipt)
    result = (await collect(publish_batch(publisher, [event()])))[0]
    assert result.record.disposition.kind is DispositionKind.UNCERTAIN
    assert result.record.disposition.reason_code == "invalid_receipt"
    assert result.message_id is None
    assert len(publisher.events) == 1


@pytest.mark.parametrize("receipt", ["1-0", " a ", "a" * 512, "é" * 256])
async def test_local_receipt_boundary_preserves_exact_value(receipt):
    result = (await collect(publish_batch(RecordingPublisher(receipt), [event()])))[0]
    assert result.record.disposition.kind is DispositionKind.CONFIRMED
    assert result.message_id == receipt


@pytest.mark.parametrize("receipt", [None, "", "a" * 513, b"1-0"])
def test_result_cannot_claim_confirmation_without_a_valid_receipt(receipt):
    with pytest.raises(ValueError):
        PublicationResult(record=publication_record(), message_id=receipt)


@pytest.mark.parametrize("kind", [DispositionKind.REJECTED, DispositionKind.UNCERTAIN])
def test_nonconfirmed_result_cannot_carry_a_receipt(kind):
    with pytest.raises(ValueError):
        PublicationResult(record=publication_record(kind), message_id="1-0")


@pytest.mark.parametrize("kind", [DispositionKind.DEFERRED, DispositionKind.QUARANTINED])
def test_result_rejects_outcomes_not_supported_by_publication_helper(kind):
    with pytest.raises(ValueError):
        PublicationResult(record=publication_record(kind), message_id=None)


@pytest.mark.parametrize(
    "phase", [DeliveryPhase.INTAKE, DeliveryPhase.PROCESSING, DeliveryPhase.PUBLICATION]
)
def test_result_rejects_nonpublication_phase_or_subscription_context(phase):
    context = DeliveryContext(
        subscription_id="archive",
        broker="redis",
        destination="garden",
        group="archive",
        consumer_id="replica",
        message_id="1-0",
        received_at=datetime(2026, 11, 8, tzinfo=timezone.utc),
    )
    record = DeliveryRecord(
        event_id="one",
        phase=phase,
        disposition=Disposition(kind=DispositionKind.CONFIRMED),
        context=context,
    )
    with pytest.raises(ValueError):
        PublicationResult(record=record, message_id="1-0")


def test_result_rejects_non_record_values():
    with pytest.raises(ValueError):
        PublicationResult(record=None, message_id="1-0")


async def test_oversized_receipt_is_rejected_before_utf8_encoding():
    class OversizedReceipt(str):
        def encode(self, *args, **kwargs):
            raise AssertionError("oversized receipt must not be encoded")

    publisher = RecordingPublisher(OversizedReceipt("x" * 513))
    result = (await collect(publish_batch(publisher, [event()])))[0]
    assert result.record.disposition.kind is DispositionKind.UNCERTAIN
    assert result.record.disposition.reason_code == "invalid_receipt"
    assert result.message_id is None


@pytest.mark.parametrize("text", ["1-0", "\ud800", "é" * 257, "   ", "a\0b", "x" * 513])
async def test_string_subclasses_are_uncertain_under_exact_builtin_receipt_policy(text):
    class ReceiptSubclass(str):
        pass

    result = (await collect(publish_batch(RecordingPublisher(ReceiptSubclass(text)), [event()])))[0]
    assert result.record.disposition.kind is DispositionKind.UNCERTAIN
    assert result.record.disposition.reason_code == "invalid_receipt"
    assert result.message_id is None


@pytest.mark.parametrize("text", ["1-0", "\ud800", "é" * 257, "   ", "a\0b", "x" * 513])
def test_result_constructor_rejects_every_string_subclass(text):
    class ReceiptSubclass(str):
        pass

    with pytest.raises(ValueError):
        PublicationResult(record=publication_record(), message_id=ReceiptSubclass(text))


async def test_receipt_subclass_hooks_are_never_called_or_coerced():
    hooks = []

    class HostileReceipt(str):
        def _unexpected(self, name):
            hooks.append(name)
            raise AssertionError("Receipt subclass hook must not run")

        def __len__(self):
            return self._unexpected("len")

        def strip(self, *args, **kwargs):
            return self._unexpected("strip")

        def __contains__(self, value):
            return self._unexpected("contains")

        def encode(self, *args, **kwargs):
            return self._unexpected("encode")

        def __str__(self):
            return self._unexpected("str")

        def __repr__(self):
            return self._unexpected("repr")

    receipt = HostileReceipt("a\0b" * 200)
    result = (await collect(publish_batch(RecordingPublisher(receipt), [event()])))[0]
    assert result.record.disposition.kind is DispositionKind.UNCERTAIN
    assert result.message_id is None
    with pytest.raises(ValueError):
        PublicationResult(record=publication_record(), message_id=receipt)
    assert hooks == []


@pytest.mark.parametrize("text", ["\ud800", "é" * 257, "   ", "a\0b", "x" * 513])
async def test_forged_string_operations_cannot_confirm_invalid_receipts(text):
    class ForgedReceipt(str):
        def __len__(self):
            return 1

        def strip(self, *args, **kwargs):
            return "safe"

        def __contains__(self, value):
            return False

        def encode(self, *args, **kwargs):
            return b"safe"

    receipt = ForgedReceipt(text)
    result = (await collect(publish_batch(RecordingPublisher(receipt), [event()])))[0]
    assert result.record.disposition.kind is DispositionKind.UNCERTAIN
    assert result.record.disposition.reason_code == "invalid_receipt"
    assert result.message_id is None
    with pytest.raises(ValueError):
        PublicationResult(record=publication_record(), message_id=receipt)

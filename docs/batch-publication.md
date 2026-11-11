# Opt-in per-item batch publication

This source implementation is opt-in. The existing Publisher, RedisStreams and OutboxPublisher APIs remain unchanged. Focused behavioral checks do not qualify a broker, managed outbox, installed distribution or stronger durability profile.

The explicit import is `modkit_events.batch_publication`. The helper publishes a bounded input sequentially and yields a result for each attempted event. It adds no dependency on Workers, optional drivers, persistence or a runtime controller.

```python
from modkit_events.batch_publication import publish_batch
from modkit_events.delivery import DispositionKind

# publisher implements async publish(event) -> str.
# events contains already-constructed Event values.
batch = publish_batch(publisher, events, timeout=10, max_items=100)
try:
    async for result in batch:
        record = result.record  # Existing DeliveryRecord, phase PUBLICATION.
        if record.disposition.kind is DispositionKind.CONFIRMED:
            receipt = result.message_id
        # Application-owned handling may save or reconcile this observation.
        # Nothing automatically settles an outbox, commits, retries or ACKs.
finally:
    await batch.aclose()
```

## Input and sequencing

`publish_batch(publisher, events, *, timeout=10, max_items=1000)` is a synchronous factory returning an async generator with explicit `aclose()` support. Before returning it, the factory snapshots the iterable's membership, order and Event references. Replacing or reordering the input collection afterward does not change the batch. No event deep copy or payload serialization is added.

The current Event constructor recursively snapshots ordinary JSON mappings into mapping proxies and sequences into tuples. That behavior belongs to Event; the batch helper does not establish stronger deep immutability, revalidate arbitrary internals, or defend against deliberate object-internals mutation. The exact existing Event objects are passed to the Publisher.

The batch validates Event membership, nonempty string event identities, duplicate identities and count. Identical IDs are rejected even when their payloads match. Event IDs retain legacy bounds and exact spelling, with no trimming or new managed-profile length limit. An invalid later entry rejects the entire input before any publish starts.

`max_items` is an exact integer from 1 through 1000, default 1000. Empty batches are valid. Reading stops at the first invalid entry or the first excess entry; at most `max_items + 1` entries are obtained for the count check. This bounds retained item references, not payload bytes or process memory. An application iterable can still block or raise while being consumed. Its exceptions propagate before broker I/O.

Pre-I/O validation covers only this batch's input contract. It does not prevalidate a Publisher's encoding rules, broker-specific admission, routing, permissions or durability requirements. A Publisher may fail later even after batch validation succeeds.

No broker call occurs until iteration begins. At most one `publish` call is awaited at a time, and the next event starts only when the caller requests another result. After each yield the caller can save its observation, stop, or continue. Closing after a yield sends no later event. There is no background task, prefetch, automatic retry or parallel publication.

## Results and the meaning of confirmation

`PublicationResult(record=..., message_id=...)` is frozen and reuses the existing DeliveryRecord and Disposition types. The record is PUBLICATION, with no fabricated subscription context. Only CONFIRMED, REJECTED and UNCERTAIN are allowed.

- **CONFIRMED:** the Publisher returned a receipt satisfying this helper's local result policy. `message_id` contains that exact receipt. The disposition has no reason or schedule.
- **REJECTED:** the Publisher explicitly raised `PublicationRejected(reason_code)`, meaning the adapter has established that this event was not accepted. The reason is the validated application-selected category and `message_id` is None.
- **UNCERTAIN:** another ordinary exception, a cooperative timeout, or an invalid receipt prevented a usable observation. Fixed reason tokens are `publish_failed`, `publish_timeout` and `invalid_receipt`; `message_id` is None.

Generic errors, including encoding/validation-looking exceptions, do not imply rejection: this helper cannot prove which operation an arbitrary Publisher performed before raising. Existing handler exceptions such as TerminalEventError are not reinterpreted as broker rejection. Only an explicit PublicationRejected signal has that meaning. Applications must not raise it for a connection loss or other uncertain acceptance.

The receipt policy is local to PublicationResult, not an added requirement on the existing Publisher protocol or Redis server: an exact builtin `str` (`type(receipt) is str`), nonblank, strict UTF-8, no NUL, at most 512 encoded bytes. String subclasses are rejected even when their underlying text looks valid; the helper does not call their overridable length, whitespace, containment, encoding, string-conversion or representation methods. They produce UNCERTAIN / invalid_receipt, and direct confirmed PublicationResult construction rejects them. An initial character-length check bounds the later encoding allocation. Values are not trimmed, normalized, coerced or truncated. A returned receipt outside that policy becomes UNCERTAIN even if the broker accepted the event. Reconcile it using application-owned evidence; do not assume it is safe to resend.

Confirmation is only as strong as the selected Publisher's actual guarantee. In particular, the existing RedisStreams.publish returns after XADD. This helper does not add WAITAOF, AOF verification, replication acknowledgement, exactly-once delivery or proof of durable retention. A confirmed record alone does not authorize PostgreSQL E25 settlement or establish commit acknowledgement, replay safety, transaction fencing or external-effect certainty.

After rejection or uncertainty, the next independent event is attempted only if the caller requests another result. Already yielded observations remain available to the caller. The helper does not retry any item or decide whether a failed item may be replayed.

## Timeouts, cancellation and diagnostics

`timeout` must be finite and positive and applies separately to each awaited publish. It uses cooperative asyncio cancellation, not a hard execution or wall-clock bound. Publishers must not swallow cancellation. Cancellation does not prove that a broker operation, underlying thread or remote side effect stopped.

Cancellation and other BaseException values propagate rather than becoming a successful batch result. If cancellation interrupts a publish, treat the current item as potentially accepted and retain the observations already yielded. Later items were not started. The helper produces no fabricated rejection, clean-stop proof or persisted uncertainty record for that interrupted item. The caller owns durable intent, reconciliation and shutdown supervision.

Results never retain ordinary transport exception objects or copy their message text. Fixed reason tokens prevent that particular diagnostic leak. PublicationRejected accepts only the existing lowercase ASCII reason-token format, but the application must still select a nonsecret category. These boundaries do not erase exception traceback locals, application-held inputs or user-provided identifiers/receipts. Do not expose raw exception tracebacks or frame locals as safe public diagnostics.

## Integration and verification boundaries

This is a publication helper, not a managed outbox executor. It does not claim work, persist intent, renew leases, enforce fences, settle transactions, schedule retries or start supervised loops. The existing OutboxPublisher retains its one-claim-before-one-send behavior and is not silently routed through this API. Applications supplying already-claimed work must independently satisfy lease and durable-intent requirements before I/O; this helper does not make an expiring preclaimed batch safe.

The focused tests use real Event/DeliveryRecord/Disposition values and an in-memory async Publisher at the external transport boundary. They cover ordering, lazy execution, validation, exact limits, outcome classification, cancellation, cooperative timeout and sanitized result fields. These local source checks do not qualify Redis, PostgreSQL, installed distributions, the full suite, throughput, memory or any stronger durability profile.

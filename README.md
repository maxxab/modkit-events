# modkit-events

Application-neutral event envelopes, ordered async dispatch, duplicate-aware
consumption, and optional Redis Streams / SQLAlchemy inbox-outbox adapters.
MIT licensed. Python 3.12+; CI targets 3.12–3.15 on Linux, Windows and macOS.

**Pre-release validation:** core and real SQLite tests run locally. Real Redis
integration and the cross-platform matrix are release gates in hosted CI, not
claims established by the local test run.

## Install

```sh
pip install modkit-events
pip install 'modkit-events[redis]'
pip install 'modkit-events[sqlalchemy]' aiosqlite
```

The base package has no runtime dependencies. Adapters import only when explicitly
requested. SQLAlchemy currently supports **SQLite 3.35+ only**; other dialects
are rejected rather than claiming untested locking semantics. Redis requires a
standalone server supporting `XAUTOCLAIM` (Redis 7+); CI uses Redis 8.10.3.
Redis Cluster is not supported by the multi-key disposition scripts.

## Core example

```python
from modkit_events import Consumer, Dispatcher, Event, MemoryClaimStore

async def handle(event):
    print(event.payload["temperature"])

dispatcher = Dispatcher()
dispatcher.subscribe("greenhouse.reading", handle)
consumer = Consumer(MemoryClaimStore(), dispatcher, scope="readings")
event = Event("reading-42", "greenhouse.reading", {"temperature": 21.5})
# In an async function:
# await consumer.consume(event)  # "processed", "inflight", or "completed"
```

`Event(event_id, name, payload, schema_version=1, metadata={})` snapshots strict
JSON values: nested mappings become read-only and lists become tuples. Non-string
keys, non-finite numbers, unsupported objects, cycles/deep structures are rejected.
The application owns payload validation, schema evolution, event names, routing,
metadata (including tracing), handler business rules and error classification.
No implicit catalogs, service names, actor models or environment config are used.

`JsonCodec(max_bytes=1048576, max_depth=32)` encodes UTF-8 JSON and checks both
inbound and outbound size/depth. Duplicate JSON keys are rejected. Use application
code to convert dates, enums, models or bytes before constructing an event.

`Dispatcher.subscribe(name, async_handler)` invokes matching handlers in order.
An unhandled name raises `LookupError`; nothing is silently acknowledged.
A later handler's failure does not undo earlier side effects: retry repeats them.
There is no speculative per-handler completion ledger or automatic logging.

## Duplicate and failure semantics

A `ClaimStore` implements async `claim(scope, key)`, `complete(claim)` and
`release(claim)`. `ClaimResult` distinguishes **acquired**, **inflight** and
**completed**. An acquired `Claim` carries an opaque token; completion/release
must compare that token and require a live lease. `False` means ownership lost.
`Consumer` raises `OwnershipLost` if successful handler work cannot be completed
by its original owner. It releases after a handler exception/cancellation,
preserving the original exception; cleanup failures are attached as exception
notes. Storage completion failures are not mistaken for handler failures.

Choose a separate scope per logical consumer group/stream; the same event ID
within one scope means the same logical work. Reusing an ID with a different
payload is an application error (claims do not compare payload hashes).

**Not exactly-once.** A process can fail after its external side effect but before
completion; a lease can expire while a handler still runs. Replacement handlers
may overlap. Token checks fence bookkeeping, not business side effects. Handlers
must tolerate duplicates, ideally with application transaction/idempotency rules.
No unconditional delivery or single-active-handler guarantee is made. Store/broker
persistence, retention, clocks, retry scheduling and recovery are operational
responsibilities. `MemoryClaimStore` is single-event-loop, non-durable and keeps
completed rows indefinitely; it is primarily for tests and small local flows.

## Redis Streams

```python
from redis.asyncio import Redis
from modkit_events import Consumer, Dispatcher
from modkit_events.adapters.redis import RedisClaimStore, RedisStreams

client = Redis.from_url("redis://localhost:6379/0")  # application owns close()
bus = RedisStreams(client, stream="readings", group="archive", consumer="worker-1",
                   namespace="greenhouse")
claims = RedisClaimStore(client, namespace="greenhouse", lease_seconds=60,
                         completed_seconds=86400)
dispatcher = Dispatcher()
# dispatcher.subscribe("greenhouse.reading", your_async_handler)
consumer = Consumer(claims, dispatcher, scope="readings/archive")
# await bus.ensure_group()  # explicit creation at ID 0, includes existing entries
# await bus.publish(event)
# for delivery in await bus.read(count=100, block_ms=1000):
#     await bus.process(delivery, consumer)
# cursor, pending = await bus.reclaim(min_idle_ms=60000, cursor="0-0")
# for delivery in pending: await bus.process(delivery, consumer)
# await client.aclose()
```

Applications schedule both new reads **and pending recovery** and follow the
`reclaim` cursor until `0-0`, then repeat periodically. No background tasks are
started. Configure idle recovery above normal processing time; this reduces but
does not eliminate overlaps. `handler_timeout` defaults to 30 seconds. Cancellation
propagates and leaves the broker entry pending; release is best effort.

`process` uses a **RedisClaimStore backed by the exact same Redis client** so
retry/DLQ bookkeeping and owner checks can be atomic. Other claim stores remain
usable through broker-neutral `Consumer`; coordinate their broker ACK/retry policy
in application code, without assuming a cross-database atomic transaction.

Outcomes are `processed`, `completed`, `inflight`, `retry`, or `dead`:

- Completed work is ACKed without replay. In-flight work stays pending.
- Only handler failures spend the retry budget. Storage/ACK errors propagate.
- `RetryPolicy(max_attempts=3, base_delay=1, max_delay=60)` counts the initial
  failure and applies bounded exponential delay. Early redelivery stays pending.
- Malformed envelopes and explicit `TerminalEventError` bypass retry. Unknown
  names are ordinary retryable handler errors unless the application classifies
  them differently.
- Exhausted/terminal messages are written to DLQ before ACK. DLQ capacity defaults
  to 10,000; full/unavailable DLQ leaves the original pending. No source stream
  is trimmed. Owner-checked scripts prevent stale retry/terminal disposition.
- Durable per-delivery DLQ markers suppress repeated writes and already-fetched
  duplicate delivery handling. Markers have no automatic TTL. The application
  owns DLQ inspection, redrive and marker retention; retaining a marker after
  deleting a DLQ entry still records terminal disposition of that original ID.
- A failed Lua command does not roll back earlier commands. An interrupted DLQ
  handoff is retried using its marker; only a confirmed successful disposition is
  reported. Infrastructure outages can still require operator recovery.

Completed event claims expire after `completed_seconds`; later redelivery can run
again. Retry counters persist until ACK. Set Redis persistence/retention to your
requirements. Avoid externally deleting or changing adapter-owned keys mid-flight.

## Durable SQL inbox and transactional outbox

```python
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from modkit_events import OutboxPublisher
from modkit_events.adapters.sqlalchemy import (
    create_tables, SQLAlchemyInbox, SQLAlchemyOutbox,
)

engine = create_async_engine("sqlite+aiosqlite:///events.db")
sessions = async_sessionmaker(engine)
metadata = MetaData()
tables = create_tables(metadata, prefix="garden")  # definitions only, NO DDL
inbox = SQLAlchemyInbox(sessions, tables.inbox, lease_seconds=60)
outbox = SQLAlchemyOutbox(sessions, tables.outbox, lease_seconds=60)
# App migration: async with engine.begin() as connection:
#     await connection.run_sync(metadata.create_all)
# Atomic business write + enqueue in the app's own transaction:
# async with sessions.begin() as session:
#     ... application database updates ...
#     await outbox.enqueue(session, event)
# publisher = OutboxPublisher(outbox, bus, timeout=10, batch_size=100)
# await publisher.process_once()
# await engine.dispose()
```

The application owns migrations, schema/table naming, database/engine lifetime,
session factory configuration and retention. `enqueue(session, event)` never
commits/closes the application session. Duplicate IDs raise `IntegrityError`; no
silent payload substitution. Inbox and publisher bookkeeping each use separate
factory-created sessions/transactions which they commit and close. Inbox claims
are **not** atomic with handler business transactions by default.

SQL inbox completion persists indefinitely. Outbox states are `pending`,
`publishing`, `published`, `dead`; inspect the supplied SQLAlchemy tables directly.
Atomic conditional updates and uniqueness arbitrate concurrent SQLite claims.
Worker wall clocks must be synchronized; injectable clocks are for tests. Expired
claims can be acquired after a crash; attempts increment on every acquisition.
Recovered claims already beyond the configured attempt budget become dead without
another broker publish.

`OutboxPublisher` claims one row immediately before each publish, up to
`batch_size` attempts per call, stopping early on a retryable failure. It never
preclaims a batch whose leases expire while queued. A timeout or publish error
records backoff/dead status; cancellation attempts cleanup and propagates.
Completion-storage failure propagates without being counted as broker failure.
A broker may have accepted a publish even if its response was lost: recovery can
republish. Choose a lease longer than normal operation and still design for that
crash window. Lease expiry during publish can overlap another owner. There is no
cross-broker/database transaction and no implicit lease-renewal service.

## Development and verification

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check src tests examples scripts
python -m ruff format --check src tests examples scripts
python -m mypy src/modkit_events --ignore-missing-imports
python -m build
python -m twine check dist/*
python scripts/check_wheel.py dist/modkit_events-0.1.0-py3-none-any.whl
```

Real Redis tests require a disposable standalone server. Set `MODKIT_REDIS_URL`
and `MODKIT_REQUIRE_REDIS=1` to make missing service configuration a failure.
Tests use random namespaced keys and clean those keys only, never `FLUSHDB`.
Hosted Redis CI sets both variables and tests source, installed wheel and rebuilt
sdist. Locally unavailable Redis produces explicit skips, not an integration pass.
The wheel checker creates fresh environments outside checkout, verifies import
origin/version/no sibling distributions, base-without-extras, sample behavior,
real SQLite and (when configured) Redis tests. Keep hosted CI green for the exact
release SHA before publication.

The MIT license retains the original source copyright notice.

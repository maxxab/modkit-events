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

`modkit-events` works independently, with or without `modkit-workers` installed.
These are separate, generic packages for any application. The dependency is
one-way: Workers requires Events; Events never requires Workers, including for
its supported optional adapters, default tests and Events-only migration path.
The reference application is not a package dependency.
Workers owns its consumer integration tests. Events also has explicitly selected
Workers companion tests; its default tests remain Workers-independent. Native
PostgreSQL migrations and adapters remain unqualified for release.

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

## Native PostgreSQL transport status

**Bounded W01/W02/W03 native, helper and W05 dependency checks passed; full
native qualification remains incomplete (NOT_READY).** The W01 submission and W02 status
extension has passed independent source review and focused source validation. It uses the existing Events
controller and the caller's original READ COMMITTED root, with fixed statement
profiles, bounded request/context retention, and fully validated typed results.
It adds no second controller or Events dependency on Workers. This does not
qualify W04/W05 native profiles or a generic native transport.

Workers selects the extension through its `prepare_submit` and `prepare_read_job`
wrappers. Admission, result reservation, execution and release remain explicit.
`read_result` borrows a still-charged value; the caller must end all borrowed
references before releasing the result. Successful statement execution is not
commit acknowledgement.

The W03 complete-page listing extension has passed independent source review
and bounded native qualification, including its private five-argument SQL
overload.
Workers `prepare_list_jobs` defaults `max_page_payload_bytes` to 16 MiB across 14
large BYTEA occurrences, counting repeated fields separately. Explicit budgets
from 1 through 3,758,096,384 bytes preserve larger complete pages and limit 1..256.
The four-argument business request stays unchanged. After admission, use the
common `result_capacity(ticket, execution_ledger=...)` quote before reservation.
At the default budget and limit 256, the conservative result charge is 62,052,884
bytes on the measured Python interpreter, plus request and other controller
backing; it is not a process-memory limit. Oversized pages fail entirely without
truncation or retry. Received `PZ013` retains the existing HELD/UNKNOWN recovery
rules. The private bounded SQL overload must be installed separately; there is
no fallback to unbounded SQL or automatic installation.

Accepted W03 checks include empty and 256-row full-record pages, non-null
cursors, exact-budget success and the original late `PZ013` without a returned
prefix. Catalog and access-control checks passed. A concurrent lawful E04 claim
preserved the complete historical two-row snapshot; cancellation on the original
connection preserved `57014`, exception identity and HELD/UNKNOWN without refund.
Owner-only rollback controls covered projection caps and sentinels, not native
execution against faulted SQL definitions.

The original W03 run failed when its Docker observer could not start. A separate
diagnostic reproduced Docker initialization failing under the inherited native
address-space limit. A corrected remaining-only continuation passed snapshot
and cancellation checks without replaying successful cases; the original failure
and missing original stderr remain preserved. Bounded query-plan and complete
original-window server-log checks passed. This does not qualify a genuine
resolved lifecycle, direct wire capture, exact total memory/RSS, an SLA or all
possible sensitive log values.

A separately accepted disposition confirms graceful shutdown and non-force
removal of the W03 fixture, with container and owned socket directory absence
verified.

The first real W01/W02 qualification attempt did **not** pass. Initial submission,
a complete protected-record read and a missing read returned before an identical
duplicate submission hit the 20-second statement timeout with a 256 KiB payload
string. The server trace reached the existing `_json_string_chunks` path through
E15 during W01. That failed attempt and its read-only empty aftermath remain
historical evidence, not a passed transaction test or cleanup/refund receipt.

The [bounded replay materialization fix](docs/sql-candidates/json-replay-materialization/README.md)
retains one size-checked bytea value in `_json_to_j` before scanning. At the exact
fix snapshot, a fresh independently reviewed invocation of the unchanged native
test passed its normal, key-conflict and ID-conflict phases with the same 256 KiB
payload string, 20-second statement timeout and one-CPU limit. This includes
identical duplicate submission, caller rollback and commit, typed reads, tested
result lifetimes and client diagnostic checks. It closes the observed regression
for this invocation and profile; it is not a latency, throughput or memory
guarantee. Closing a held conflict connection is not a managed cleanup/refund
receipt.

That continuation later stopped at a fixture observation-permission error.
This attempt and an earlier incorrect integer-oracle attempt remain historical
failures; completed native phases were preserved without replay.

A separately reviewed continuation passed the corrected 43-case helper corpus
and the targeted current-helper W05 SQL dependency checks. W05 passed exact
named-value and claim/history comparisons, both full transactional rollback
checks, and the expected late-corrupt-replay error with evidence of the earlier
real claim allocation. This is not W05 native binary-profile or broad
concurrency qualification.

Final observations matched the expected committed baseline, with no prepared
transactions or other database clients. The bounded 250-line server-log privacy
check, containment and input-pin checks passed. These checks do not certify all
logs. A separate disposition receipt confirms clean shutdown and non-force
removal of the isolated fixture, with container and owned socket absence verified.

Existing E14/E28 qualification remains separate. Production installation, final
grants/manifests, installed artifacts, other drivers/platforms, broader native
and scaling qualification, and release readiness remain unqualified.

Companion source checks require `MODKIT_EVENTS_WORKERS_TESTS=1` and an installed
Workers package or an explicit Workers source `PYTHONPATH`. Unselected companion
cases skip; selected missing or broken imports fail. Events-only checks remain
active. Source tests do not substitute for the remaining real-driver proof.

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

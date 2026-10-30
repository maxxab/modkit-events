"""Real SQLite integration: transactions, contention, leases and restart."""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import MetaData, insert, inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modkit_events.adapters.sqlalchemy import SQLAlchemyInbox, SQLAlchemyOutbox, create_tables
from modkit_events.models import Event


@pytest_asyncio.fixture
async def database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'events.db'}")
    metadata = MetaData()
    tables = create_tables(metadata)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    now = [1000.0]
    yield engine, sessions, tables, now
    await engine.dispose()


def inbox(database):
    _, sessions, tables, now = database
    return SQLAlchemyInbox(sessions, tables.inbox, lease_seconds=10, clock=lambda: now[0])


def outbox(database):
    _, sessions, tables, now = database
    return SQLAlchemyOutbox(sessions, tables.outbox, lease_seconds=10, clock=lambda: now[0])


@pytest.mark.asyncio
async def test_schema_is_explicit(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    tables = create_tables(MetaData(), prefix="custom")
    store = SQLAlchemyInbox(async_sessionmaker(engine), tables.inbox)
    async with engine.connect() as connection:
        assert await connection.run_sync(lambda sync: inspect(sync).get_table_names()) == []
    with pytest.raises(OperationalError, match="no such table"):
        await store.claim("scope", "key")
    await engine.dispose()


@pytest.mark.parametrize("prefix", ["", "bad-name", "x;DROP TABLE", "a" * 49])
def test_table_prefix_validation(prefix):
    with pytest.raises(ValueError):
        create_tables(MetaData(), prefix=prefix)


@pytest.mark.asyncio
async def test_inbox_competing_claims_acquire_once_and_survive_restart(database):
    stores = [inbox(database) for _ in range(8)]
    results = await asyncio.gather(*(store.claim("group", "evt") for store in stores))
    assert [result.state for result in results].count("acquired") == 1
    assert [result.state for result in results].count("inflight") == 7
    winner = next(result.claim for result in results if result.claim is not None)
    assert await stores[0].complete(winner)
    assert (await inbox(database).claim("group", "evt")).state == "completed"
    assert (await inbox(database).claim("another", "evt")).state == "acquired"


@pytest.mark.asyncio
async def test_inbox_stale_owner_cannot_mutate_replacement(database):
    store = inbox(database)
    old = (await store.claim("g", "k")).claim
    database[3][0] += 10
    assert not await store.complete(old)
    assert not await store.release(old)
    new = (await store.claim("g", "k")).claim
    assert old.token != new.token
    assert not await store.complete(old)
    assert not await store.release(old)
    assert (await store.claim("g", "k")).state == "inflight"
    assert await store.complete(new)
    assert not await store.release(new)


@pytest.mark.asyncio
async def test_inbox_release_allows_retry(database):
    store = inbox(database)
    claim = (await store.claim("g", "k")).claim
    assert await store.release(claim)
    assert not await store.release(claim)
    assert (await store.claim("g", "k")).state == "acquired"


@pytest.mark.asyncio
async def test_enqueue_joins_business_transaction_and_rollback(database):
    _, sessions, tables, _ = database
    store = outbox(database)
    async with sessions() as session:
        await store.enqueue(session, Event("rollback", "created", {}))
        assert session.in_transaction()
        await session.rollback()
        await session.execute(select(tables.outbox))  # Caller still owns usable session.
    assert await store.claim(10) == []
    async with sessions.begin() as session:
        await store.enqueue(session, Event("committed", "created", {"item": 3}))
    assert [claim.event.event_id for claim in await store.claim(10)] == ["committed"]


@pytest.mark.asyncio
async def test_enqueue_duplicate_is_not_silently_accepted(database):
    _, sessions, _, _ = database
    store = outbox(database)
    async with sessions.begin() as session:
        await store.enqueue(session, Event("same", "created", {"item": 1}))
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            await store.enqueue(session, Event("same", "created", {"item": 2}))
    assert (await store.claim(1))[0].event.payload == {"item": 1}


@pytest.mark.asyncio
async def test_outbox_competing_batches_do_not_share_live_claims(database):
    _, sessions, _, _ = database
    store = outbox(database)
    async with sessions.begin() as session:
        for index in range(12):
            await store.enqueue(session, Event(str(index), "created", {}))
    batches = await asyncio.gather(*(outbox(database).claim(4) for _ in range(5)))
    ids = [claim.event.event_id for batch in batches for claim in batch]
    assert len(ids) == len(set(ids)) == 12


@pytest.mark.asyncio
async def test_outbox_recovery_fences_stale_success_and_failure(database):
    _, sessions, tables, now = database
    store = outbox(database)
    async with sessions.begin() as session:
        await store.enqueue(session, Event("e", "created", {}))
    old = (await store.claim(1))[0]
    now[0] += 10
    assert not await store.complete(old, "old-message")
    assert not await store.fail(old, "old-error", 0, 3)
    new = (await outbox(database).claim(1))[0]
    assert (old.attempt, new.attempt) == (1, 2)
    assert old.token != new.token
    assert not await store.complete(old, "old-message")
    assert not await store.fail(old, "old-error", 0, 3)
    assert await store.complete(new, "new-message")
    assert await outbox(database).claim(1) == []
    async with sessions() as session:
        row = (await session.execute(select(tables.outbox))).mappings().one()
        assert row["state"] == "published"
        assert row["message_id"] == "new-message"


@pytest.mark.asyncio
async def test_outbox_backoff_exhaustion_and_durable_dead_state(database):
    _, sessions, tables, now = database
    store = outbox(database)
    async with sessions.begin() as session:
        await store.enqueue(session, Event("e", "created", {}))
    first = (await store.claim(1))[0]
    assert await store.fail(first, "broker down", 5, 2)
    assert await store.claim(1) == []
    now[0] += 5
    second = (await store.claim(1))[0]
    assert second.attempt == 2
    assert await store.fail(second, "still down", 5, 2)
    now[0] += 100
    assert await outbox(database).claim(1) == []
    async with sessions() as session:
        row = (await session.execute(select(tables.outbox))).mappings().one()
        assert row["state"] == "dead"
        assert row["last_error"] == "still down"


@pytest.mark.asyncio
async def test_failed_claim_decode_rolls_back_the_entire_batch(database):
    _, sessions, tables, _ = database
    store = outbox(database)
    async with sessions.begin() as session:
        await store.enqueue(session, Event("a", "created", {}))
        await session.execute(
            insert(tables.outbox).values(
                event_id="z",
                data=b"not-json",
                state="pending",
                attempt=0,
                available_at=0,
                token=None,
                lease_until=None,
            )
        )
    with pytest.raises(ValueError):
        await store.claim(10)
    async with sessions() as session:
        rows = (await session.execute(select(tables.outbox))).mappings().all()
        assert all(row["state"] == "pending" and row["attempt"] == 0 for row in rows)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_leases_rejected(value):
    # Constructor validation needs no connection and owns no schema.
    tables = create_tables(MetaData())
    for adapter, table in [(SQLAlchemyInbox, tables.inbox), (SQLAlchemyOutbox, tables.outbox)]:
        with pytest.raises(ValueError):
            adapter(None, table, lease_seconds=value)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 1001, True, 1.5])
async def test_outbox_rejects_invalid_batch_limits(database, limit):
    with pytest.raises(ValueError):
        await outbox(database).claim(limit)


@pytest.mark.asyncio
async def test_corrupt_envelope_identity_rolls_back_claim(database):
    _, sessions, tables, _ = database
    store = outbox(database)
    async with sessions.begin() as session:
        await store.enqueue(session, Event("expected", "created", {}))
        await session.execute(
            tables.outbox.update().values(data=store.codec.encode(Event("wrong", "created", {})))
        )
    with pytest.raises(ValueError, match="identity"):
        await store.claim(1)
    async with sessions() as session:
        row = (await session.execute(select(tables.outbox))).mappings().one()
        assert row["state"] == "pending" and row["attempt"] == 0


@pytest.mark.asyncio
async def test_completion_database_failure_does_not_record_success(database):
    from sqlalchemy import text

    _, sessions, tables, _ = database
    store = inbox(database)
    claim = (await store.claim("g", "k")).claim
    async with sessions.begin() as session:
        await session.execute(
            text(
                f"CREATE TRIGGER reject_completion BEFORE UPDATE ON {tables.inbox.name} "
                "WHEN NEW.state = 'completed' BEGIN SELECT RAISE(ABORT, 'unavailable'); END"
            )
        )
    with pytest.raises(IntegrityError, match="unavailable"):
        await store.complete(claim)
    assert (await inbox(database).claim("g", "k")).state == "inflight"
    async with sessions.begin() as session:
        await session.execute(text("DROP TRIGGER reject_completion"))
    assert await store.complete(claim)


@pytest.mark.asyncio
async def test_cancellation_after_claim_write_rolls_back_owned_transaction(database):
    from sqlalchemy.ext.asyncio import AsyncSession

    engine, sessions, tables, now = database
    entered = asyncio.Event()

    class PausingSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            result = await super().execute(statement, *args, **kwargs)
            entered.set()
            await asyncio.Event().wait()
            return result

    store = SQLAlchemyInbox(
        async_sessionmaker(engine, class_=PausingSession), tables.inbox, clock=lambda: now[0]
    )
    task = asyncio.create_task(store.claim("g", "cancelled"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with sessions() as session:
        assert (await session.execute(select(tables.inbox))).first() is None
    assert (await inbox(database).claim("g", "cancelled")).state == "acquired"

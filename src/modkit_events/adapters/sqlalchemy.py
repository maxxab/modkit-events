"""Explicit-schema SQLAlchemy asyncio stores, tested with SQLite 3.35+.

The application owns engine lifetime, migrations and retention. Operational
methods commit/close only factory-created sessions. ``enqueue`` instead joins
its caller's transaction and never commits it. Do not share an AsyncSession
between concurrent tasks. Clocks across workers must be synchronized.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import (
    Column,
    Float,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    and_,
    case,
    delete,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modkit_events.claims import Claim, ClaimResult, positive_seconds, validate_key
from modkit_events.codec import JsonCodec
from modkit_events.models import Event
from modkit_events.outbox import OutboxClaim


@dataclass(frozen=True, slots=True)
class EventTables:
    """Table definitions to include in the application's explicit migration."""

    inbox: Table
    outbox: Table


def create_tables(metadata: MetaData, prefix: str = "modkit_events") -> EventTables:
    """Define, but do not create, inbox/outbox tables in caller-owned metadata."""
    if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,47}", prefix):
        raise ValueError("prefix must be a SQL identifier of 1 to 48 characters")
    inbox = Table(
        f"{prefix}_inbox",
        metadata,
        Column("scope", String, primary_key=True),
        Column("key", String, primary_key=True),
        Column("state", String, nullable=False),
        Column("token", String, nullable=True),
        Column("lease_until", Float, nullable=True),
    )
    outbox = Table(
        f"{prefix}_outbox",
        metadata,
        Column("event_id", String, primary_key=True),
        Column("data", LargeBinary, nullable=False),
        Column("state", String, nullable=False),
        Column("attempt", Integer, nullable=False),
        Column("available_at", Float, nullable=False),
        Column("token", String, nullable=True),
        Column("lease_until", Float, nullable=True),
        Column("message_id", String, nullable=True),
        Column("last_error", Text, nullable=True),
    )
    return EventTables(inbox, outbox)


def _sqlite(session: AsyncSession) -> None:
    # Do not imply untested concurrency/isolation behavior on other dialects.
    if session.get_bind().dialect.name != "sqlite":
        raise ValueError("These adapters currently support SQLite only")


def _now(clock: Callable[[], float]) -> float:
    value = clock()
    if isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("clock must return a finite timestamp")
    return value


class SQLAlchemyInbox:
    """Durable, scoped claims with token-and-deadline conditional mutations.

    Completed rows remain indefinitely. If the application deletes them, old
    deliveries may run again. Lease expiry allows overlapping handlers; this
    store fences bookkeeping, not application side effects.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        table: Table,
        lease_seconds: float = 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        positive_seconds(lease_seconds)
        self.session_factory = session_factory
        self.table = table
        self.lease_seconds = lease_seconds
        self.clock = clock

    async def claim(self, scope: str, key: str) -> ClaimResult:
        """Acquire a missing/expired claim or distinguish inflight/completed."""
        validate_key(scope, key)
        now = _now(self.clock)
        token = uuid4().hex
        columns = self.table.c
        values = dict(
            scope=scope,
            key=key,
            state="processing",
            token=token,
            lease_until=now + self.lease_seconds,
        )
        async with self.session_factory.begin() as session:
            _sqlite(session)
            inserted = await session.execute(
                sqlite_insert(self.table)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[columns.scope, columns.key])
                .returning(columns.token)
            )
            if inserted.scalar_one_or_none() is not None:
                return ClaimResult("acquired", Claim(scope, key, token))
            recovered = await session.execute(
                update(self.table)
                .where(
                    columns.scope == scope,
                    columns.key == key,
                    columns.state == "processing",
                    columns.lease_until <= now,
                )
                .values(token=token, lease_until=now + self.lease_seconds)
                .returning(columns.token)
            )
            if recovered.scalar_one_or_none() is not None:
                return ClaimResult("acquired", Claim(scope, key, token))
            state: str = (
                await session.execute(
                    select(columns.state).where(
                        columns.scope == scope,
                        columns.key == key,
                    )
                )
            ).scalar_one()
            return ClaimResult("completed" if state == "completed" else "inflight")

    def _owned(self, claim: Claim):
        columns = self.table.c
        return and_(
            columns.scope == claim.scope,
            columns.key == claim.key,
            columns.token == claim.token,
            columns.state == "processing",
            columns.lease_until > _now(self.clock),
        )

    async def complete(self, claim: Claim) -> bool:
        """Mark completed only for a still-live matching owner."""
        async with self.session_factory.begin() as session:
            _sqlite(session)
            result = await session.execute(
                update(self.table)
                .where(self._owned(claim))
                .values(state="completed", token=None, lease_until=None)
                .returning(self.table.c.key)
            )
            return result.scalar_one_or_none() is not None

    async def release(self, claim: Claim) -> bool:
        """Remove a still-live matching claim, permitting retry."""
        async with self.session_factory.begin() as session:
            _sqlite(session)
            result = await session.execute(
                delete(self.table).where(self._owned(claim)).returning(self.table.c.key)
            )
            return result.scalar_one_or_none() is not None


class SQLAlchemyOutbox:
    """Transactional enqueue plus separately committed publisher claims.

    Duplicate event IDs raise IntegrityError rather than silently accepting a
    different payload. Failed rows become pending or dead. Published and dead
    rows are retained for application inspection/retention, never auto-deleted.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        table: Table,
        lease_seconds: float = 60,
        clock: Callable[[], float] = time.time,
        codec: JsonCodec | None = None,
    ) -> None:
        positive_seconds(lease_seconds)
        self.session_factory = session_factory
        self.table = table
        self.lease_seconds = lease_seconds
        self.clock = clock
        self.codec = codec if codec is not None else JsonCodec()

    async def enqueue(self, session: AsyncSession, event: Event) -> None:
        """Insert in caller transaction; caller commits/rolls back and closes."""
        _sqlite(session)
        await session.execute(
            insert(self.table).values(
                event_id=event.event_id,
                data=self.codec.encode(event),
                state="pending",
                attempt=0,
                available_at=_now(self.clock),
                token=None,
                lease_until=None,
            )
        )

    def _eligible(self, now: float):
        columns = self.table.c
        return or_(
            and_(columns.state == "pending", columns.available_at <= now),
            and_(columns.state == "publishing", columns.lease_until <= now),
        )

    async def claim(self, limit: int) -> list[OutboxClaim]:
        """Atomically claim up to 1000 due/expired rows; commit before return.

        Each acquisition increments attempt, including crash recovery. An
        undecodable stored envelope aborts the whole claim transaction.
        """
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer between 1 and 1000")
        now = _now(self.clock)
        token = uuid4().hex
        columns = self.table.c
        selected = (
            select(columns.event_id)
            .where(self._eligible(now))
            .order_by(
                columns.available_at,
                columns.event_id,
            )
            .limit(limit)
        )
        async with self.session_factory.begin() as session:
            _sqlite(session)
            rows = (
                (
                    await session.execute(
                        update(self.table)
                        .where(
                            columns.event_id.in_(selected),
                            self._eligible(now),
                        )
                        .values(
                            state="publishing",
                            token=token,
                            lease_until=now + self.lease_seconds,
                            attempt=columns.attempt + 1,
                        )
                        .returning(columns.event_id, columns.data, columns.attempt)
                    )
                )
                .mappings()
                .all()
            )
            claims = []
            for row in rows:
                event = self.codec.decode(row["data"])
                if event.event_id != row["event_id"]:
                    raise ValueError("Stored envelope identity does not match outbox row")
                claims.append(OutboxClaim(event, token, row["attempt"]))
            return claims

    def _owned(self, claim: OutboxClaim):
        columns = self.table.c
        return and_(
            columns.event_id == claim.event.event_id,
            columns.token == claim.token,
            columns.state == "publishing",
            columns.lease_until > _now(self.clock),
        )

    async def complete(self, claim: OutboxClaim, message_id: str) -> bool:
        """Persist broker receipt only for a still-live matching claim."""
        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("message_id must be a nonempty string")
        async with self.session_factory.begin() as session:
            _sqlite(session)
            result = await session.execute(
                update(self.table)
                .where(self._owned(claim))
                .values(
                    state="published",
                    message_id=message_id,
                    token=None,
                    lease_until=None,
                    last_error=None,
                )
                .returning(self.table.c.event_id)
            )
            return result.scalar_one_or_none() is not None

    async def fail(self, claim: OutboxClaim, error: str, delay: float, max_attempts: int) -> bool:
        """Schedule retry or retain a dead row, only for matching live owner."""
        if isinstance(delay, bool) or not math.isfinite(delay) or delay < 0:
            raise ValueError("delay must be finite and nonnegative")
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if not isinstance(error, str):
            raise ValueError("error must be a string")
        columns = self.table.c
        async with self.session_factory.begin() as session:
            _sqlite(session)
            result = await session.execute(
                update(self.table)
                .where(self._owned(claim))
                .values(
                    state=case((columns.attempt >= max_attempts, "dead"), else_="pending"),
                    available_at=_now(self.clock) + delay,
                    token=None,
                    lease_until=None,
                    last_error=error,
                )
                .returning(columns.event_id)
            )
            return result.scalar_one_or_none() is not None

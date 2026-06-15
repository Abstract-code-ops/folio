"""Shared test fixtures.

Uses an in-memory SQLite database for model unit tests. PostgreSQL-specific
types (Vector, JSONB) degrade gracefully — Vector columns are omitted from
SQLite reflection, and JSONB behaves as JSON/pickle.

Both sync and async session fixtures are provided. Async tests use
sqlite+aiosqlite://; sync tests use sqlite://.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base


# ── Sync fixtures (for model unit tests) ──────────────────────


@pytest.fixture
def engine():
    """Create a fresh in-memory SQLite engine for each test session."""
    e = create_engine(
        "sqlite:///:memory:",
        echo=False,
    )

    @event.listens_for(e, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=e)
    return e


@pytest.fixture
def session(engine) -> Generator[Session, None, None]:
    """Transactional sync session scoped to one test."""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    sess = SessionLocal()

    yield sess

    sess.close()
    transaction.rollback()
    connection.close()


# ── Async fixtures (for service tests) ────────────────────────


@pytest.fixture
async def async_engine():
    """Create a fresh in-memory async SQLite engine for each test session."""
    e = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield e

    await e.dispose()


@pytest.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Transactional async session scoped to one test."""
    connection = await async_engine.connect()
    transaction = await connection.begin()
    AsyncSessionLocal = async_sessionmaker(
        bind=connection, class_=AsyncSession, expire_on_commit=False,
    )
    sess = AsyncSessionLocal()

    yield sess

    await sess.close()
    await transaction.rollback()
    await connection.close()


# ── Helpers ────────────────────────────────────────────────────


def utcnow_naive() -> datetime:
    """Return naive UTC datetime for test assertions."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_book_id() -> uuid.UUID:
    return uuid.uuid4()


def make_section_id() -> uuid.UUID:
    return uuid.uuid4()

"""SQLAlchemy engine, session factory, and declarative base.

Supports both sync (Dramatiq workers) and async (FastAPI) usage
from a single model definition.

The async engine is derived from the configured ``database_url``
by swapping the driver to asyncpg (see ``config.make_async_dsn``).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, MetaData, TypeDecorator, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings

# Naming convention for Alembic-generated constraint names
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata


def utcnow() -> datetime:
    """Return the current UTC datetime, naive, for column defaults."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Cross-dialect type compatibility ──────────────────────────
# These wrappers let models use PostgreSQL-specific types (JSONB, Vector)
# while still being creatable on SQLite during testing.


class JSONB(TypeDecorator):
    """JSONB-compatible column that falls back to JSON on non-Postgres DBs.

    On PostgreSQL this resolves to native JSONB. On SQLite and other
    dialects it falls back to JSON, which is sufficient for testing.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())


class Vector(TypeDecorator):
    """pgvector Vector-compatible column that falls back to JSON on SQLite.

    On PostgreSQL stores actual pgvector vectors (dimension specified
    at construction). On SQLite stores the embedding as a JSON array.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 1536):
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector as PGVector

            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())


# ── Common reusable column mixins ──────────────────────────────


class TimestampMixin:
    """Adds created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        default=None,
        onupdate=utcnow,
        nullable=True,
    )


# ── Async engine + session (FastAPI routes / services) ────────

async_engine = create_async_engine(
    settings.database_url_async,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async session, rolls back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Sync engine + session (Dramatiq workers) ──────────────────

sync_engine = create_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
)


def get_sync_session() -> Generator[Session, None, None]:
    """Context manager for Dramatiq worker tasks."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

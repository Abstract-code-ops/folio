"""Alembic migration environment.

Uses synchronous psycopg2 (available in requirements.txt) for migration
execution while the application uses asyncpg at runtime.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object, which provides access to alembic.ini values
config = context.config

# Allow DATABASE_URL env var to override the ini value
# Usage: DATABASE_URL="postgresql://user:pass@host:5432/db" alembic upgrade head
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Set up Python logging from the ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all models so Base.metadata is fully populated ─────
from app.core.db import Base  # noqa: E402

# Import every model module to register its tables on Base.metadata
import app.models.book  # noqa: E402, F401
import app.models.chunk  # noqa: E402, F401
import app.models.coverage_event  # noqa: E402, F401
import app.models.note_session  # noqa: E402, F401
import app.models.qa_message  # noqa: E402, F401
import app.models.section  # noqa: E402, F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without connecting.

    Useful for generating SQL scripts or reviewing what a migration
    will produce before running it.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

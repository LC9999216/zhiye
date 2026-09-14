"""Alembic environment configuration — async PostgreSQL via app settings.

Uses ``target_metadata`` from the application's ORM ``Base`` so that
``alembic revision --autogenerate`` can detect schema changes.
Database URL is read from the project's ``Settings`` (DATABASE_URL env var)
rather than from alembic.ini, ensuring the real connection string is never
committed to the repository.

Run:
    alembic upgrade head       (online, async)
    alembic check              (validate pending migrations)
    alembic current            (show current revision)
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# Import the models so that Base.metadata is populated for autogenerate.
import app.models  # noqa: F401
from app.core.config import settings
from app.db.base import Base

# Alembic Config object.
config = context.config

# Interpret the config file for Python logging (loggers section).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the ini-file URL with the live project setting.
# This ensures the real DATABASE_URL is never written to alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation).

    Configures the context with the real ``database_url`` so generated SQL
    reflects the actual target database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection | AsyncConnection) -> None:
    """Configure the migration context on *connection* and run."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations asynchronously using an async engine.

    Uses ``create_async_engine`` with the project's ``database_url``
    (asyncpg driver), then runs migration steps via ``run_sync``.
    """
    db_url = config.get_main_option("sqlalchemy.url")
    connectable = create_async_engine(db_url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Delegates to the async runner via ``asyncio.run()``.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

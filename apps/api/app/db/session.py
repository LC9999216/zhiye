"""Async SQLAlchemy engine, session factory and connection helpers."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Health probes must not hang for the whole asyncpg connect timeout.
# Neon cold-start TLS handshakes can take a few seconds; 5s keeps the
# health endpoint responsive while tolerating managed-DB latency.
DB_CHECK_TIMEOUT_SECONDS = 5.0

# Neon (and most managed Postgres) require TLS.  asyncpg accepts an
# ``ssl`` context in connect_args; the ``?ssl=require`` query param alone
# is not honoured by asyncpg the way psycopg does.
_SSL_CONTEXT = ssl.create_default_context()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": _SSL_CONTEXT},
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async session; commits are the caller's responsibility."""
    async with async_session_factory() as session:
        yield session


async def check_db_connection() -> bool:
    """Return True when the database answers ``SELECT 1`` within a short timeout.

    Never raises: connection problems surface as ``False`` so the health
    endpoint can keep returning 200 with ``db="unavailable"`` (e.g. when
    ``APP_MODE=mock`` and no PostgreSQL is running).
    """
    try:
        async def _ping() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_ping(), timeout=DB_CHECK_TIMEOUT_SECONDS)
        return True
    except Exception as exc:  # noqa: BLE001 — intentional: report as bool
        logger.warning("Database connection check failed: %s", type(exc).__name__)
        return False


async def close_db() -> None:
    """Dispose the engine and its pool (called on application shutdown)."""
    await engine.dispose()

"""Shared pytest fixtures for the Zhibian API test suite.

When no database is available, DB-dependent routes use a monkey-patched
``get_db`` dependency that raises a clear error so tests can distinguish
between "no DB available" and actual logic failures.

PostgreSQL integration fixtures
-------------------------------
When a real ``DATABASE_URL`` (asyncpg) is reachable, the ``pg_engine`` /
``pg_session`` fixtures connect to it.  Tests that use them must:

1. Write only rows keyed by a unique UUID (the ``uniq`` fixture) so
   parallel-safe isolation is guaranteed.
2. Clean up their rows (the ``pg_cleanup`` fixture drops them after the
   test).

If no database is reachable, ``pg_engine`` raises ``pytest.skip`` so
DB-dependent tests are skipped (as before).
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Make the `app` package importable regardless of the current working
# directory, e.g. `python -m pytest apps/api/tests` from the repo root.
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.main import app  # noqa: E402


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client that talks to the ASGI app in-process.

    Uses ``ASGITransport`` so no live server is needed and the app
    ``lifespan`` is not executed (tests stay fully self-contained).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def uniq() -> str:
    """A unique hex suffix for isolating test data in a shared DB."""
    return uuid.uuid4().hex[:12]


def _resolve_test_database_url() -> str | None:
    """Return a usable asyncpg URL, or None when no DB is available.

    Priority:
    1. ``TEST_DATABASE_URL`` env var (explicit test DB).
    2. ``DATABASE_URL`` env var.
    """
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _direct_url(url: str) -> str:
    """Convert a Neon pooler URL (``-pooler.``) to the direct host.

    The Neon connection pooler routes transactions across replicas and
    does not reliably support asyncpg prepared statements, which makes
    integration tests flaky.  The direct host avoids both problems.
    """
    return url.replace("-pooler.", ".")


@pytest.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """Connect to a reachable PostgreSQL; skip when unavailable.

    - Prefers the direct (non-pooler) Neon host for stability.
    - Uses ``ssl=create_default_context()`` which Neon requires.
    - Disables the asyncpg prepared-statement cache (not supported by
      poolers and unnecessary for tests).
    """
    url = _resolve_test_database_url()
    if not url:
        pytest.skip("No TEST_DATABASE_URL / DATABASE_URL set")

    import ssl

    url = _direct_url(url)
    engine = create_async_engine(
        url,
        poolclass=__import__("sqlalchemy.pool", fromlist=["NullPool"]).NullPool,
        connect_args={
            "ssl": ssl.create_default_context(),
            "prepared_statement_cache_size": 0,
        },
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — unreachable DB → skip
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {type(exc).__name__}")
        raise

    yield engine
    await engine.dispose()


@pytest.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Async session bound to the test engine."""
    maker = async_sessionmaker(
        bind=pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with maker() as session:
        yield session

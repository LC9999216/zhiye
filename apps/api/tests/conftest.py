"""Shared pytest fixtures for the Zhibian API test suite.

When no database is available, DB-dependent routes use a monkey-patched
``get_db`` dependency that raises a clear error so tests can distinguish
between "no DB available" and actual logic failures.

Tests that genuinely exercise DB interactions should either:
1. Use an in-memory SQLite via ``aiosqlite``, or
2. Require a running PostgreSQL container and be explicitly marked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

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

"""Database initialization: create all tables (development / test convenience).

NOTE: per AGENTS.md, schema changes must go through Alembic migrations;
``init_db`` only exists as a convenience for local dev, fixtures and tests.
"""

from __future__ import annotations

# Importing the models package registers every table on Base.metadata.
import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import engine


async def init_db() -> None:
    """Create all tables defined by the current ORM models (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

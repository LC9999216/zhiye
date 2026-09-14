"""Shared FastAPI dependency-injection helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async SQLAlchemy session.

    The session is opened and closed per-request; commits are left to the
    caller so a failed request never half-persists state.
    """
    async for session in get_db_session():
        yield session

"""Shared FastAPI dependency-injection helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
import hashlib
import hmac

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async SQLAlchemy session.

    The session is opened and closed per-request; commits are left to the
    caller so a failed request never half-persists state.
    """
    async for session in get_db_session():
        yield session


async def require_invite_code(
    x_invite_code: str | None = Header(default=None, alias="X-Invite-Code"),
) -> None:
    """Protect business endpoints in production with a server-side digest."""
    if settings.is_mock_mode:
        return
    expected = settings.invite_code_sha256.strip().lower()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "INVITE_CODE_NOT_CONFIGURED",
                "message": "体验码尚未配置，请联系管理员",
            },
        )
    actual = hashlib.sha256((x_invite_code or "").encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_INVITE_CODE",
                "message": "体验码无效或已过期",
            },
        )

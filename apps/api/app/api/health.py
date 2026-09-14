"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import settings
from app.db.session import check_db_connection

router = APIRouter()


@router.get("/health", summary="API and database health check")
async def health() -> dict[str, str]:
    """Return service status, version, mode and database reachability.

    Always answers 200: when the database cannot be reached (e.g.
    ``APP_MODE=mock`` without a running PostgreSQL) ``db`` is
    ``"unavailable"`` so the endpoint stays useful for orchestration probes.
    No secrets or connection details are exposed.
    """
    db_status = "connected" if await check_db_connection() else "unavailable"
    return {
        "status": "ok",
        "version": __version__,
        "mode": settings.app_mode,
        "db": db_status,
    }

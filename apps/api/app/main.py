"""Zhibian API application entry point.

Run locally (from ``apps/api``):

    python -m app.main
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import async_session_factory, check_db_connection, close_db
from app.services.query_service import recover_running_jobs

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup: configure logging, probe DB, recover orphaned jobs.

    Shutdown: close database connections.
    """
    configure_logging()
    logger.info(
        "Zhibian API starting (version=%s mode=%s)",
        __version__,
        settings.app_mode,
    )
    db_ok = await check_db_connection()
    logger.info(
        "Database connection check: %s", "connected" if db_ok else "unavailable"
    )

    if db_ok:
        try:
            # Recover any jobs left running after a previous crash.
            async with async_session_factory() as session:
                # Enable pgvector extension if available.
                await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await session.commit()
                await recover_running_jobs(session)
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Startup recovery skipped: %s", exc)

    yield
    logger.info("Zhibian API shutting down")
    await close_db()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Zhibian API",
        description="知辨 MVP — 知乎搜索观点结构化与知识图谱后端",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")
    return app


app = create_app()


def main() -> None:
    """Run the API server with uvicorn using the configured host/port."""
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()

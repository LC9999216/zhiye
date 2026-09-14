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

from app import __version__
from app.api import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import check_db_connection, close_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup: configure logging, log config, probe the database.

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

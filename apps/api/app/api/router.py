"""Aggregate every sub-router into the main API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.queries import router as queries_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(queries_router)
api_router.include_router(jobs_router)

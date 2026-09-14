"""Aggregate every sub-router into the main API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router

api_router = APIRouter()

# Health only for now; queries / jobs / answers / graph / chat land in Stages 3-8.
# The health router already defines "/health"; main.py adds the "/api" prefix,
# so the endpoint is served at GET /api/health.
api_router.include_router(health_router, tags=["health"])

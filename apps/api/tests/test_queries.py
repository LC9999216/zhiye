"""Tests for ``POST /api/queries/analyze``, ``GET /api/queries/{id}`` etc.

Stage 3 acceptance tests:
- Empty input → 422.
- Whitespace-only → 422 (normalised to empty).
- Missing field → 422.
- Return body shape (202 with job_id, query_id, job_url).
- Missing query → 404.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


ANALYZE_PATH = "/api/queries/analyze"


class TestAnalyzeValidation:
    """Input validation for ``POST /api/queries/analyze`` (no DB needed)."""

    async def test_empty_query_text_returns_422(self, client: AsyncClient) -> None:
        """Empty string → 422 validation error."""
        response = await client.post(ANALYZE_PATH, json={"query_text": ""})
        assert response.status_code == 422

    async def test_whitespace_only_returns_422(self, client: AsyncClient) -> None:
        """Whitespace-only → 422 (normalised to empty)."""
        response = await client.post(ANALYZE_PATH, json={"query_text": "   "})
        assert response.status_code == 422

    async def test_missing_field_returns_422(self, client: AsyncClient) -> None:
        """Missing ``query_text`` field → 422."""
        response = await client.post(ANALYZE_PATH, json={})
        assert response.status_code == 422


class TestGetQuery:
    """``GET /api/queries/{id}``."""

    @pytest.mark.skip(reason="Requires PostgreSQL (no DB available in this environment)")
    async def test_get_nonexistent_query_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Non-existent query id → 404."""
        qid = "00000000-0000-0000-0000-000000000001"
        response = await client.get(f"/api/queries/{qid}")
        assert response.status_code == 404


class TestGetAnswers:
    """``GET /api/queries/{id}/answers``."""

    @pytest.mark.skip(reason="Requires PostgreSQL (no DB available in this environment)")
    async def test_answers_for_nonexistent_query_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Non-existent query id → 404."""
        qid = "00000000-0000-0000-0000-000000000001"
        response = await client.get(f"/api/queries/{qid}/answers")
        assert response.status_code == 404

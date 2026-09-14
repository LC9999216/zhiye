"""Tests for ``GET /api/jobs/{id}`` (no-DB subset).

Stage 3 acceptance:
- Missing job → 404 (requires PostgreSQL).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


JOB_PATH_PREFIX = "/api/jobs/"


class TestGetJob:
    """``GET /api/jobs/{id}``."""

    @pytest.mark.skip(reason="Requires PostgreSQL (no DB available in this environment)")
    async def test_get_nonexistent_job_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Non-existent job id → 404."""
        response = await client.get(
            f"{JOB_PATH_PREFIX}00000000-0000-0000-0000-000000000001"
        )
        assert response.status_code == 404

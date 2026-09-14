"""Tests for ``GET /api/health``."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app import __version__

HEALTH_PATH = "/api/health"


async def test_health_returns_200_with_expected_fields(client: AsyncClient) -> None:
    response = await client.get(HEALTH_PATH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == __version__ == "0.1.0"
    assert payload["mode"] in {"mock", "production"}
    assert payload["db"] in {"connected", "unavailable"}


async def test_health_reports_db_unavailable_when_database_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _db_down() -> bool:
        return False

    monkeypatch.setattr("app.api.health.check_db_connection", _db_down)

    response = await client.get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.json()["db"] == "unavailable"


async def test_health_reports_db_connected_when_database_up(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _db_up() -> bool:
        return True

    monkeypatch.setattr("app.api.health.check_db_connection", _db_up)

    response = await client.get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.json()["db"] == "connected"

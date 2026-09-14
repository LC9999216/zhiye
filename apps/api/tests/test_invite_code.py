from __future__ import annotations

import hashlib

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.dependencies import require_invite_code


@pytest.mark.asyncio
async def test_invite_code_uses_constant_time_hash_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_mode", "production")
    monkeypatch.setattr(
        settings,
        "invite_code_sha256",
        hashlib.sha256(b"demo-code").hexdigest(),
    )
    await require_invite_code("demo-code")


@pytest.mark.asyncio
async def test_invite_code_rejects_missing_or_wrong_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_mode", "production")
    monkeypatch.setattr(settings, "invite_code_sha256", hashlib.sha256(b"demo-code").hexdigest())
    with pytest.raises(HTTPException) as missing:
        await require_invite_code(None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as wrong:
        await require_invite_code("wrong")
    assert wrong.value.status_code == 401

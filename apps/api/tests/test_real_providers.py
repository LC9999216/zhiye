from __future__ import annotations

import json

import httpx
import pytest

from app.core.exceptions import (
    ProviderAuthError,
    ProviderContractError,
    ProviderRateLimitError,
)
from app.services.embedding_provider import VolcengineEmbeddingProvider
from app.services.llm_provider import DeepSeekLLMProvider


@pytest.mark.asyncio
async def test_deepseek_provider_sends_json_mode_and_returns_metadata() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "req-1",
                "model": "deepseek-flash",
                "choices": [{"message": {"content": '{"claims":[]}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            },
        )

    provider = DeepSeekLLMProvider(
        api_key="secret",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.complete_with_metadata("ANSWER_ID:a1\ncontent")

    assert result.text == '{"claims":[]}'
    assert result.model == "deepseek-flash"
    assert result.request_id == "req-1"
    assert result.total_tokens == 14
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    payload = seen["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "deepseek-flash"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    assert "只基于给定内容摘要" in payload["messages"][0]["content"]
    assert "只基于给定内容摘要" not in payload["messages"][1]["content"]


@pytest.mark.asyncio
async def test_deepseek_provider_maps_auth_and_rate_errors_without_retry() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    provider = DeepSeekLLMProvider(
        api_key="secret",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderAuthError):
        await provider.complete_with_metadata("prompt")
    assert calls == 1


@pytest.mark.asyncio
async def test_deepseek_missing_usage_is_marked_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "req-2", "choices": [{"message": {"content": "{}"}}]},
        )

    provider = DeepSeekLLMProvider(
        api_key="secret",
        base_url="https://api.deepseek.com",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.complete_with_metadata("prompt")
    assert result.usage.available is False
    assert provider.usage_records[-1]["usage_available"] is False


@pytest.mark.asyncio
async def test_embedding_provider_encodes_each_text_and_checks_dimension() -> None:
    requests: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "id": "emb-1",
                "model": "doubao-embedding-vision-251215",
                "data": {"embedding": [0.1] * 2048, "object": "embedding"},
                "usage": {"total_tokens": 3},
            },
        )

    provider = VolcengineEmbeddingProvider(
        api_key="secret",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="doubao-embedding-vision-251215",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.embed_texts(["first", "second"])

    assert len(result) == 2
    assert all(len(vector) == 2048 for vector in result)
    assert [request["input"][0]["text"] for request in requests] == ["first", "second"]
    assert all(request["dimensions"] == 2048 for request in requests)


@pytest.mark.asyncio
async def test_embedding_provider_rejects_wrong_dimension() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"embedding": [0.1, 0.2]}})

    provider = VolcengineEmbeddingProvider(
        api_key="secret",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="doubao-embedding-vision-251215",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderContractError):
        await provider.embed_texts(["text"])


@pytest.mark.asyncio
async def test_embedding_missing_usage_is_marked_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "doubao-embedding-vision-251215", "data": {"embedding": [0.1] * 2048}},
        )

    provider = VolcengineEmbeddingProvider(
        api_key="secret",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        transport=httpx.MockTransport(handler),
    )
    await provider.embed_texts(["text"])
    assert provider.last_result is not None
    assert provider.last_result.usage_available is False


@pytest.mark.asyncio
async def test_provider_maps_rate_limit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    provider = DeepSeekLLMProvider(
        api_key="secret",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderRateLimitError):
        await provider.complete_with_metadata("prompt")


def test_provider_rejects_lookalike_hosts() -> None:
    with pytest.raises(ValueError):
        DeepSeekLLMProvider(
            api_key="secret",
            base_url="https://api.deepseek.com.evil.example",
        )
    with pytest.raises(ValueError):
        VolcengineEmbeddingProvider(
            api_key="secret",
            base_url="https://ark.cn-beijing.volces.com.evil.example/api/v3",
        )

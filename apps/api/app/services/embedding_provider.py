"""Embedding provider isolation (Stage 4).

The analysis step records embeddings for answers and claims so Stage 5
can compute cosine similarity.  As with the LLM, embeddings are behind a
protocol; mock mode returns deterministic vectors (seeded from the text)
so similarity behaviour is testable offline.
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.exceptions import (
    ProviderAuthError,
    ProviderContractError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    request_ids: list[str | None]
    total_tokens: int = 0
    usage_available: bool = True


class EmbeddingProvider(Protocol):
    """Protocol for an embedding provider."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...


class MockEmbeddingProvider:
    """Deterministic, seeded mock embedding.

    Produces a fixed-dimension vector derived from a hash of the text so
    the same text always yields the same vector (needed for similarity
    tests in Stage 5).  Not semantically meaningful.
    """

    model_name = "mock-embed-v1"

    def __init__(self, dimension: int = 64) -> None:
        self._dimension = dimension
        self.last_result: EmbeddingResult | None = None
        self.usage_records: list[dict[str, object]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = [self._embed(text) for text in texts]
        self.last_result = EmbeddingResult(
            vectors=vectors,
            model=self.model_name,
            request_ids=[None] * len(vectors),
        )
        return vectors

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [float(byte) / 255.0 for byte in digest[: self._dimension]]
        return values


class VolcengineEmbeddingProvider:
    """Call the standard Volcengine ``/embeddings/multimodal`` API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "doubao-embedding-vision-251215",
        dimension: int = 2048,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderAuthError("Embedding API key is not configured")
        parsed_base_url = urlparse(base_url)
        if (
            parsed_base_url.scheme != "https"
            or parsed_base_url.hostname != "ark.cn-beijing.volces.com"
        ):
            raise ValueError("Embedding base URL must use a Volcengine Ark domain")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.dimension = dimension
        self.last_result: EmbeddingResult | None = None
        self.usage_records: list[dict[str, object]] = []
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        request_ids: list[str | None] = []
        total_tokens = 0
        for text in texts:
            (
                vector,
                request_id,
                used_tokens,
                actual_model,
                usage_available,
            ) = await self._embed_one(text)
            vectors.append(vector)
            request_ids.append(request_id)
            total_tokens += used_tokens
            self.model_name = actual_model
            self.usage_records.append(
                {
                    "model": actual_model,
                    "request_id": request_id,
                    "total_tokens": used_tokens,
                    "usage_available": usage_available,
                }
            )
        self.last_result = EmbeddingResult(
            vectors=vectors,
            model=self.model_name,
            request_ids=request_ids,
            total_tokens=total_tokens,
            usage_available=all(
                bool(record["usage_available"]) for record in self.usage_records[-len(vectors):]
            ) if vectors else True,
        )
        return vectors

    async def _embed_one(
        self, text: str
    ) -> tuple[list[float], str | None, int, str, bool]:
        try:
            response = await self._client.post(
                f"{self.base_url}/embeddings/multimodal",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "input": [{"type": "text", "text": text}],
                    "dimensions": self.dimension,
                    "encoding_format": "float",
                },
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("Embedding request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Embedding transport failed") from exc
        _raise_embedding_http_error(response)
        try:
            body = response.json()
            data = body["data"]
            if isinstance(data, list):
                data = data[0]
            vector = data["embedding"]
            actual_model = str(body.get("model") or self.model_name)
            request_id = body.get("id")
            usage = body.get("usage")
            used_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
            usage_available = (
                isinstance(used_tokens, int)
                and not isinstance(used_tokens, bool)
                and used_tokens >= 0
            )
            if not usage_available:
                used_tokens = 0
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderContractError("Embedding response has no usable vector") from exc
        if (
            not isinstance(vector, list)
            or len(vector) != self.dimension
            or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector)
            or not any(float(value) != 0.0 for value in vector)
        ):
            raise ProviderContractError(
                f"Embedding vector must contain {self.dimension} finite non-zero values"
            )
        return (
            [float(value) for value in vector],
            request_id,
            used_tokens,
            actual_model,
            usage_available,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _raise_embedding_http_error(response: httpx.Response) -> None:
    if response.status_code in (401, 403):
        raise ProviderAuthError("Embedding authentication failed")
    if response.status_code == 429:
        raise ProviderRateLimitError("Embedding rate limit or quota reached")
    if response.status_code >= 500:
        raise ProviderUnavailableError("Embedding service unavailable")
    if response.status_code >= 400:
        raise ProviderContractError("Embedding request rejected")


def get_embedding_provider() -> EmbeddingProvider:
    """Return an embedding provider for the current ``APP_MODE``."""
    if settings.is_mock_mode:
        return MockEmbeddingProvider()
    return VolcengineEmbeddingProvider(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        timeout_seconds=settings.embedding_timeout_seconds,
    )


__all__ = [
    "EmbeddingProvider",
    "EmbeddingResult",
    "MockEmbeddingProvider",
    "VolcengineEmbeddingProvider",
    "get_embedding_provider",
]

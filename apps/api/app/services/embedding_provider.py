"""Embedding provider isolation (Stage 4).

The analysis step records embeddings for answers and claims so Stage 5
can compute cosine similarity.  As with the LLM, embeddings are behind a
protocol; mock mode returns deterministic vectors (seeded from the text)
so similarity behaviour is testable offline.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from app.core.config import settings


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

    def __init__(self, dimension: int = 64) -> None:
        self._dimension = dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [float(byte) / 255.0 for byte in digest[: self._dimension]]
        return values


def get_embedding_provider() -> EmbeddingProvider:
    """Return an embedding provider for the current ``APP_MODE``."""
    if settings.is_mock_mode:
        return MockEmbeddingProvider()
    msg = "Real embedding provider not implemented — mock mode only."
    raise NotImplementedError(msg)


__all__ = ["EmbeddingProvider", "MockEmbeddingProvider", "get_embedding_provider"]

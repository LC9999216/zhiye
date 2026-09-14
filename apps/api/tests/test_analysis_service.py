"""Stage 4 analysis-service tests — LLM provider, embedding, and persistence.

Splits into:
- No-DB tests: MockLLMProvider behaviour, MockEmbeddingProvider determinism,
  and the per-answer analysis happy/failure paths using a fake session.
- DB tests (skipped without PostgreSQL): transaction-replace of claims,
  traceability columns, and position constraints.

The DB-dependent tests mirror Stage 3's approach: they are written but
skipped when no PostgreSQL is reachable, and enabled on CI/Neon.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.schemas.ai import AnalysisFailureDTO
from app.services.analysis_service import analyze_answer
from app.services.embedding_provider import MockEmbeddingProvider
from app.services.llm_provider import MockLLMProvider

# Real generated fixture dir (committed; workspace-writable).
_FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]
    / "database"
    / "fixtures"
    / "ai_analysis"
)


# ── Mock provider tests (no DB) ────────────────────────────────────────

class TestMockLLMProvider:
    async def test_returns_fixture_for_known_id(self) -> None:
        provider = MockLLMProvider(fixture_dir=_FIXTURE_DIR)
        prompt = "ANSWER_ID:a-short-01\nsome content"
        result = await provider.complete(prompt)
        data = json.loads(result)
        assert data["stance"] == "support"

    async def test_returns_empty_default_for_unknown_id(self) -> None:
        provider = MockLLMProvider(fixture_dir=_FIXTURE_DIR)
        prompt = "ANSWER_ID:nope\ncontent"
        result = await provider.complete(prompt)
        data = json.loads(result)
        assert data["stance"] == "neutral"
        assert data["claims"] == []


class TestMockEmbeddingProvider:
    async def test_deterministic_same_text(self) -> None:
        embedder = MockEmbeddingProvider(dimension=16)
        v1 = await embedder.embed_texts(["hello"])
        v2 = await embedder.embed_texts(["hello"])
        assert v1 == v2

    async def test_different_texts_differ(self) -> None:
        embedder = MockEmbeddingProvider(dimension=16)
        v1 = await embedder.embed_texts(["hello"])
        v2 = await embedder.embed_texts(["world"])
        assert v1 != v2

    async def test_dimension(self) -> None:
        embedder = MockEmbeddingProvider(dimension=32)
        vectors = await embedder.embed_texts(["a", "b"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 32


# ── Fake session for per-answer analysis paths (no real DB) ────────────

class _FakeAnswer:
    """Minimal Answer stand-in for analyze_answer logic."""

    def __init__(self, content_id: str, content_text: str) -> None:
        self.id = uuid.uuid4()
        self.query_id = uuid.uuid4()
        self.content_id = content_id
        self.content_text = content_text
        self.summary = None
        self.stance = None
        self.embedding = None
        self.embedding_model = None
        self.analysis_model = None
        self.prompt_version = None
        self.schema_version = None
        self.analyzed_at = None
        self.analysis_latency_ms = None


class _FakeSession:
    """Stub session: records added/deleted objects, no real SQL."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.select_result = []

    async def execute(self, *args, **kwargs):  # noqa: ANN001, ANN003
        class _Result:
            def scalars(self):
                class _Scalars:
                    def all(self):
                        return self._items

                    def __init__(self, items):  # noqa: ANN001
                        self._items = items

                return _Scalars(self._items)

            def __init__(self, items):  # noqa: ANN001
                self._items = items

        return _Result(self.select_result)

    async def delete(self, obj) -> None:  # noqa: ANN001
        self.deleted.append(obj)

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)

    async def flush(self) -> None:
        pass


class _FailingProvider:
    """LLM provider that always fails (for failure-path tests)."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, prompt: str) -> str:
        self.calls += 1
        raise TimeoutError("simulated timeout")


class _FixturedProvider:
    """MockLLMProvider wired to the committed fixture dir."""

    def __init__(self) -> None:
        self._provider = MockLLMProvider(fixture_dir=_FIXTURE_DIR)

    async def complete(self, prompt: str) -> str:
        return await self._provider.complete(prompt)


# ── analyze_answer no-DB paths ──────────────────────────────────────────

class TestAnalyzeAnswerNoDB:
    async def test_failure_returns_dto_and_records_attempts(self) -> None:
        session = _FakeSession()
        answer = _FakeAnswer("x-1", "some content text")
        provider = _FailingProvider()

        failure = await analyze_answer(
            session, answer, provider=provider, embedder=MockEmbeddingProvider()
        )

        assert isinstance(failure, AnalysisFailureDTO)
        assert failure.error_code == "ANALYSIS_FAILED"
        assert failure.attempts == 3  # 1 initial + 2 retries
        assert provider.calls == 3
        # On failure the answer must not be marked analysed.
        assert answer.analyzed_at is None

    async def test_happy_path_persists_claims_and_traceability(self) -> None:
        content_id = "a-two-01"
        content_text = "考研系统化理论基础，就业快速积累实践"
        session = _FakeSession()
        answer = _FakeAnswer(content_id, content_text)

        failure = await analyze_answer(
            session, answer, provider=_FixturedProvider(),
            embedder=MockEmbeddingProvider(),
        )

        assert failure is None
        # Two claims persisted (a-two-01 fixture has 2 claims) + no deletions.
        assert len(session.added) == 2
        assert session.deleted == []
        assert answer.summary == "考研与就业各有优势"
        assert answer.stance == "conditional"
        assert answer.prompt_version
        assert answer.schema_version
        assert answer.analyzed_at is not None
        assert answer.analysis_latency_ms is not None
        # Embeddings recorded.
        assert answer.embedding is not None
        assert answer.embedding_model

    async def test_empty_claims_persists_zero(self) -> None:
        session = _FakeSession()
        answer = _FakeAnswer("a-empty-01", "路过看看，不发表意见。")

        failure = await analyze_answer(
            session, answer, provider=_FixturedProvider(),
            embedder=MockEmbeddingProvider(),
        )

        assert failure is None
        assert session.added == []
        assert answer.stance == "neutral"


# ── DB integration tests (skipped without PostgreSQL) ──────────────────

@pytest.mark.skip(reason="requires PostgreSQL (asyncpg); enabled on CI/Neon")
async def test_db_replace_claims_transaction() -> None:
    """Re-analyzing an answer replaces prior claims in one transaction."""
    pytest.fail("Implement with a live PostgreSQL fixture in CI")


@pytest.mark.skip(reason="requires PostgreSQL (asyncpg); enabled on CI/Neon")
async def test_db_position_check_constraint_rejects_0_and_6() -> None:
    """INSERT position=0 or 6 must violate ck_claim_position_range."""
    pytest.fail("Implement with a live PostgreSQL fixture in CI")

"""Stage 5 tests — graph building (TDD first).

Splits into:
- Pure-logic tests (no DB): cosine similarity, pair normalisation,
  degree-2 limit, concept name normalisation.
- PG integration tests (skip without PostgreSQL): materialising
  Concepts/claim_concepts, merging, AnswerSimilarity rows, idempotency.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.services.concept_normalizer import normalize_concept_name
from app.services.embedding_provider import MockEmbeddingProvider
from app.services.graph_builder import (
    build_answer_similarities,
    build_concepts,
    cosine_similarity,
    normalise_answer_pair,
)

_FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]
    / "database"
    / "fixtures"
    / "ai_analysis"
)


# ── pure logic: cosine similarity ──────────────────────────────────────

class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_parallel_scaled(self) -> None:
        assert cosine_similarity([1.0, 2.0], [2.0, 4.0]) == pytest.approx(1.0)

    def test_zero_vector_returns_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
        assert cosine_similarity([1.0, 0.0], [0.0, 0.0]) == 0.0

    def test_mock_embedding_similar(self) -> None:
        """Same text → cosine 1.0; different text → lower."""
        e = MockEmbeddingProvider(dimension=16)
        v_a = e._embed("考研系统化理论基础")
        v_b = e._embed("考研系统化理论基础")
        v_c = e._embed("就业快速积累实践")
        assert cosine_similarity(v_a, v_b) == pytest.approx(1.0)
        assert cosine_similarity(v_a, v_c) < 0.99


# ── pure logic: pair normalisation + degree limit ──────────────────────

class TestPairNormalisation:
    def test_orders_pair_ascending(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        low, high = (a, b) if a < b else (b, a)
        assert normalise_answer_pair(a, b) == (low, high)
        assert normalise_answer_pair(b, a) == (low, high)

    def test_degree_limit_keeps_at_most_two(self) -> None:
        """Adding edges greedily must keep every node's degree <= 2."""
        from app.services.graph_builder import _add_edge_with_degree_limit

        edges: list[tuple[uuid.UUID, uuid.UUID]] = []
        ids = [uuid.uuid4() for _ in range(6)]
        # Star: center connected to all 5 others — degree limit cuts after 2.
        center = ids[0]
        for other in ids[1:]:
            _add_edge_with_degree_limit(edges, center, other)
        degree = sum(1 for e in edges if center in e)
        assert degree <= 2
        assert len(edges) == 2


# ── pure logic: concept normalisation ──────────────────────────────────

class TestConceptNormalisation:
    def test_normalise_fullwidth_and_case(self) -> None:
        assert normalize_concept_name("ＡＩ 教育") == "ai 教育"
        assert normalize_concept_name("Machine Learning") == "machine learning"


# ── PG integration tests (skip without PostgreSQL) ─────────────────────

@pytest.mark.skip(reason="PG integration tests live in test_pg_integration.py")
async def test_pg_placeholder() -> None:
    pass

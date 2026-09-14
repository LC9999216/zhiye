"""Stage 4 PostgreSQL integration tests (run on reachable PostgreSQL).

Covers the execution plan's automated acceptance that needs a real DB:

1. Idempotent query creation (same normalized query → same query_id).
2. Job status lifecycle (404 for missing; pending after creation).
3. Transactional claim replacement (re-analysis replaces prior claims).
4. ``ck_claim_position_range`` rejects position 0 and 6.
5. Composite FKs reject cross-query writes (added by migration 0002).

These tests connect to the reachable ``DATABASE_URL`` and write only
rows keyed by a unique ``uniq`` suffix, cleaning them up afterwards.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer
from app.models.claim import Claim
from app.models.query import Query
from app.services.analysis_service import analyze_answer
from app.services.embedding_provider import MockEmbeddingProvider
from app.services.llm_provider import MockLLMProvider
from app.services.mock_search_provider import MockSearchProvider
from app.services.query_service import create_job_for_query, create_or_get_query

# Real generated fixture dir (committed) — repo_root/database/fixtures/ai_analysis.
_FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]
    / "database"
    / "fixtures"
    / "ai_analysis"
)


# ── helpers ────────────────────────────────────────────────────────────

async def _cleanup_query(session: AsyncSession, query_id) -> None:  # noqa: ANN001
    """Delete a query (cascades to answers/claims/concepts/jobs)."""
    await session.execute(
        text("DELETE FROM queries WHERE id = :qid"), {"qid": query_id}
    )
    await session.commit()


# ── idempotent query creation ──────────────────────────────────────────

class TestQueryIdempotency:
    async def test_same_normalized_query_reuses_query(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """Submitting the same normalized query returns the same query_id."""
        raw = f"计算机专业考研还是就业 {uniq}"
        query1, created1 = await create_or_get_query(pg_session, raw)
        await pg_session.commit()
        query2, created2 = await create_or_get_query(pg_session, raw)
        await pg_session.commit()

        assert created1 is True
        assert created2 is False
        assert query1.id == query2.id

        await _cleanup_query(pg_session, query1.id)

    async def test_whitespace_variant_same_query(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """Whitespace variants normalize to the same query."""
        q1, _ = await create_or_get_query(pg_session, f"  AI  行业 {uniq}  ")
        await pg_session.commit()
        q2, created2 = await create_or_get_query(pg_session, f"ai 行业 {uniq}")
        await pg_session.commit()

        assert created2 is False
        assert q1.id == q2.id

        await _cleanup_query(pg_session, q1.id)


# ── job lifecycle ──────────────────────────────────────────────────────

class TestJobLifecycle:
    async def test_no_active_job_creates_new(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        query, _ = await create_or_get_query(pg_session, f"测试问题 {uniq}")
        await pg_session.commit()

        job1, is_new1 = await create_job_for_query(pg_session, query)
        await pg_session.commit()
        job2, is_new2 = await create_job_for_query(pg_session, query)
        await pg_session.commit()

        assert is_new1 is True
        assert is_new2 is False  # active job reused
        assert job1.id == job2.id

        await _cleanup_query(pg_session, query.id)


# ── transactional claim replacement ────────────────────────────────────

class TestClaimReplacement:
    async def test_reanalysis_replaces_claims(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """Re-analyzing an answer replaces prior claims (no duplicates)."""
        query = Query(
            query_text=f"题目 {uniq}",
            normalized_query=f"题目 {uniq}".casefold(),
            status="completed",
        )
        pg_session.add(query)
        await pg_session.flush()

        answer = Answer(
            query_id=query.id,
            content_id="a-two-01",  # fixture id → 2 claims
            content_text="考研系统化理论基础，就业快速积累实践",
            url=f"https://www.zhihu.com/answer/{uniq}",
            original_index=0,
            voteup_count=10,
        )
        pg_session.add(answer)
        await pg_session.flush()

        # First analysis: fixture a-two-01 → 2 claims.
        provider = MockLLMProvider(fixture_dir=_FIXTURE_DIR)
        failure = await analyze_answer(
            pg_session, answer, provider=provider,
            embedder=MockEmbeddingProvider(),
        )
        await pg_session.commit()
        assert failure is None

        count1 = await pg_session.execute(
            text("SELECT count(*) FROM claims WHERE answer_id = :aid"),
            {"aid": answer.id},
        )
        assert count1.scalar() == 2

        # Second analysis: replace with a different fixture's claims.
        # Use the single-claim fixture a-short-01 (no temp file needed).
        answer.content_id = "a-short-01"
        answer.content_text = "考研能提升学历竞争力"
        await pg_session.flush()

        failure2 = await analyze_answer(
            pg_session, answer, provider=provider,
            embedder=MockEmbeddingProvider(),
        )
        await pg_session.commit()
        assert failure2 is None

        count2 = await pg_session.execute(
            text("SELECT count(*) FROM claims WHERE answer_id = :aid"),
            {"aid": answer.id},
        )
        assert count2.scalar() == 1  # replaced, not appended

        await _cleanup_query(pg_session, query.id)


# ── position check constraint ──────────────────────────────────────────

class TestPositionConstraint:
    async def test_position_zero_rejected(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        query = Query(
            query_text=f"q {uniq}",
            normalized_query=f"q {uniq}".casefold(),
            status="completed",
        )
        pg_session.add(query)
        await pg_session.flush()
        answer = Answer(
            query_id=query.id,
            content_id=f"c-{uniq}",
            content_text="x",
            url=f"https://www.zhihu.com/answer/{uniq}",
            original_index=0,
        )
        pg_session.add(answer)
        await pg_session.flush()

        pg_session.add(
            Claim(
                query_id=query.id,
                answer_id=answer.id,
                text="c",
                evidence_text="x",
                position=0,
                confidence=0.5,
            )
        )
        with pytest.raises(IntegrityError):
            await pg_session.commit()
        await pg_session.rollback()
        await _cleanup_query(pg_session, query.id)

    async def test_position_six_rejected(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        query = Query(
            query_text=f"q {uniq}",
            normalized_query=f"q {uniq}".casefold(),
            status="completed",
        )
        pg_session.add(query)
        await pg_session.flush()
        answer = Answer(
            query_id=query.id,
            content_id=f"c-{uniq}",
            content_text="x",
            url=f"https://www.zhihu.com/answer/{uniq}",
            original_index=0,
        )
        pg_session.add(answer)
        await pg_session.flush()

        pg_session.add(
            Claim(
                query_id=query.id,
                answer_id=answer.id,
                text="c",
                evidence_text="x",
                position=6,
                confidence=0.5,
            )
        )
        with pytest.raises(IntegrityError):
            await pg_session.commit()
        await pg_session.rollback()
        await _cleanup_query(pg_session, query.id)


# ── composite foreign keys (Stage 5 cross-query integrity) ─────────────

class TestCompositeForeignKey:
    async def _seed_pair(
        self, session: AsyncSession, uniq: str
    ) -> tuple:
        """Create two queries, each with one answer; return their ids."""
        q1 = Query(
            query_text=f"q1 {uniq}",
            normalized_query=f"q1 {uniq}".casefold(),
            status="completed",
        )
        q2 = Query(
            query_text=f"q2 {uniq}",
            normalized_query=f"q2 {uniq}".casefold(),
            status="completed",
        )
        session.add_all([q1, q2])
        await session.flush()
        a1 = Answer(
            query_id=q1.id,
            content_id=f"a1-{uniq}",
            content_text="x",
            url=f"https://www.zhihu.com/answer/a1-{uniq}",
            original_index=0,
        )
        a2 = Answer(
            query_id=q2.id,
            content_id=f"a2-{uniq}",
            content_text="y",
            url=f"https://www.zhihu.com/answer/a2-{uniq}",
            original_index=0,
        )
        session.add_all([a1, a2])
        await session.flush()
        return q1, q2, a1, a2

    async def test_claim_cross_query_answer_rejected(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """claims(query_id=Q1, answer_id from Q2) must be rejected."""
        q1, q2, a1, a2 = await self._seed_pair(pg_session, uniq)
        pg_session.add(
            Claim(
                query_id=q1.id,      # query Q1
                answer_id=a2.id,     # but answer belongs to Q2
                text="c",
                evidence_text="x",
                position=1,
                confidence=0.5,
            )
        )
        with pytest.raises(IntegrityError):
            await pg_session.commit()
        await pg_session.rollback()
        await _cleanup_query(pg_session, q1.id)
        await _cleanup_query(pg_session, q2.id)

    async def test_answer_similarity_cross_query_source_rejected(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """answer_similarities must reject a cross-query source answer."""
        q1, q2, a1, a2 = await self._seed_pair(pg_session, uniq)
        from app.models.answer_similarity import AnswerSimilarity

        pg_session.add(
            AnswerSimilarity(
                query_id=q1.id,
                source_answer_id=a2.id,  # belongs to Q2
                target_answer_id=a1.id,  # belongs to Q1
                score=0.9,
                method_version="answer-cosine-v1",
            )
        )
        with pytest.raises(IntegrityError):
            await pg_session.commit()
        await pg_session.rollback()
        await _cleanup_query(pg_session, q1.id)
        await _cleanup_query(pg_session, q2.id)

    async def test_answer_similarity_cross_query_target_rejected(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """answer_similarities must reject a cross-query target answer."""
        q1, q2, a1, a2 = await self._seed_pair(pg_session, uniq)
        from app.models.answer_similarity import AnswerSimilarity

        pg_session.add(
            AnswerSimilarity(
                query_id=q1.id,
                source_answer_id=a1.id,  # belongs to Q1
                target_answer_id=a2.id,  # belongs to Q2
                score=0.9,
                method_version="answer-cosine-v1",
            )
        )
        with pytest.raises(IntegrityError):
            await pg_session.commit()
        await pg_session.rollback()
        await _cleanup_query(pg_session, q1.id)
        await _cleanup_query(pg_session, q2.id)


# ── Stage 5 graph building (materialise + merge + similarity) ──────────

class TestGraphBuilding:
    async def _seed_query_with_answers(
        self, session: AsyncSession, uniq: str, n_answers: int = 3
    ) -> tuple:
        """Create a completed query with *n_answers* analyzed answers.

        Answers are created directly with hand-set claim rows (each with
        a distinct concepts_json) so graph building is fully deterministic
        and does not depend on mock-fixture filename matching.
        """
        query = Query(
            query_text=f"graph {uniq}",
            normalized_query=f"graph {uniq}".casefold(),
            status="completed",
        )
        session.add(query)
        await session.flush()

        embedder = MockEmbeddingProvider()
        answers = []
        concept_sets = [
            ["考研"],
            ["就业"],
            ["考研", "就业"],
            ["AI"],
            ["计算机"],
            ["考研"],
        ]
        for i in range(n_answers):
            a = Answer(
                query_id=query.id,
                content_id=f"g-{uniq}-{i}",
                content_text=f"content {i} {uniq}",
                url=f"https://www.zhihu.com/answer/{uniq}-{i}",
                original_index=i,
                voteup_count=10 - i,
            )
            session.add(a)
            await session.flush()
            concepts = concept_sets[i % len(concept_sets)]
            # Persist one claim per answer with the concept set.
            claim = Claim(
                query_id=query.id,
                answer_id=a.id,
                text=f"claim {i}",
                evidence_text=f"content {i} {uniq}",
                position=1,
                confidence=0.8,
                concepts_json=json.dumps(concepts, ensure_ascii=False),
            )
            session.add(claim)
            # Answer embedding: hash of the concept set (distinct-ish).
            vecs = await embedder.embed_texts([" ".join(concepts)])
            a.embedding = vecs[0]
            a.embedding_model = "mock-embed-v1"
            answers.append(a)
        await session.commit()
        return query, answers

    async def test_build_concepts_materializes_and_links(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """Concepts + claim_concepts rows exist; each concept referenced."""
        query, answers = await self._seed_query_with_answers(pg_session, uniq)
        from app.services.graph_builder import build_concepts

        concepts = await build_concepts(pg_session, query.id)
        await pg_session.commit()

        assert len(concepts) >= 1
        # Every concept is query-scoped and normalized.
        for c in concepts:
            assert c.query_id == query.id
            assert c.normalized_name == c.normalized_name.strip()

        # At least one claim_concepts row exists.
        cc_count = await pg_session.execute(
            text(
                "SELECT count(*) FROM claim_concepts WHERE query_id = :qid"
            ),
            {"qid": query.id},
        )
        assert cc_count.scalar() >= 1

        await _cleanup_query(pg_session, query.id)

    async def test_build_concepts_idempotent(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """Re-running build_concepts does not duplicate rows."""
        query, answers = await self._seed_query_with_answers(pg_session, uniq)
        from app.services.graph_builder import build_concepts

        await build_concepts(pg_session, query.id)
        await pg_session.commit()
        c1 = await pg_session.execute(
            text("SELECT count(*) FROM concepts WHERE query_id = :qid"),
            {"qid": query.id},
        )
        first = c1.scalar()

        await build_concepts(pg_session, query.id)
        await pg_session.commit()
        c2 = await pg_session.execute(
            text("SELECT count(*) FROM concepts WHERE query_id = :qid"),
            {"qid": query.id},
        )
        second = c2.scalar()
        assert second == first, f"concepts grew {first} -> {second}"

        await _cleanup_query(pg_session, query.id)

    async def test_answer_similarity_respects_degree_limit(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """Each answer's SIMILAR_TO undirected degree <= 2."""
        query, answers = await self._seed_query_with_answers(
            pg_session, uniq, n_answers=6
        )
        from app.services.graph_builder import build_answer_similarities

        rows = await build_answer_similarities(pg_session, query.id)
        await pg_session.commit()

        # Degree check over persisted rows.
        result = await pg_session.execute(
            text(
                "SELECT source_answer_id, target_answer_id "
                "FROM answer_similarities WHERE query_id = :qid"
            ),
            {"qid": query.id},
        )
        degree: dict = {}
        for src, tgt in result.fetchall():
            degree[src] = degree.get(src, 0) + 1
            degree[tgt] = degree.get(tgt, 0) + 1
        assert all(d <= 2 for d in degree.values()), f"degree > 2: {degree}"

        await _cleanup_query(pg_session, query.id)

    async def test_answer_similarity_idempotent(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """Re-running similarity build does not duplicate edges."""
        query, answers = await self._seed_query_with_answers(
            pg_session, uniq, n_answers=4
        )
        from app.services.graph_builder import build_answer_similarities

        await build_answer_similarities(pg_session, query.id)
        await pg_session.commit()
        r1 = await pg_session.execute(
            text(
                "SELECT count(*) FROM answer_similarities WHERE query_id = :qid"
            ),
            {"qid": query.id},
        )
        first = r1.scalar()

        await build_answer_similarities(pg_session, query.id)
        await pg_session.commit()
        r2 = await pg_session.execute(
            text(
                "SELECT count(*) FROM answer_similarities WHERE query_id = :qid"
            ),
            {"qid": query.id},
        )
        second = r2.scalar()
        assert second == first, f"edges grew {first} -> {second}"

        await _cleanup_query(pg_session, query.id)

    async def test_concept_merge_rewires_claim_concepts(
        self, pg_session: AsyncSession, uniq: str
    ) -> None:
        """Embedding-similar concepts merge; claim_concepts rewire to survivor.

        Two concepts with *different* normalized names but *identical*
        embeddings (cosine 1.0 >= threshold) must merge: the absorbed row
        is deleted and both claims' claim_concepts point at the survivor.
        """
        from app.services.graph_builder import build_concepts
        from app.models.concept import Concept

        query = Query(
            query_text=f"merge {uniq}",
            normalized_query=f"merge {uniq}".casefold(),
            status="completed",
        )
        pg_session.add(query)
        await pg_session.flush()

        embedder = MockEmbeddingProvider()
        claims = []
        for i, raw in enumerate(["AI 教育", "人工智能 教育"]):
            a = Answer(
                query_id=query.id,
                content_id=f"m-{uniq}-{i}",
                content_text=f"content {i} {uniq}",
                url=f"https://www.zhihu.com/answer/m-{uniq}-{i}",
                original_index=i,
            )
            pg_session.add(a)
            await pg_session.flush()
            claim = Claim(
                query_id=query.id,
                answer_id=a.id,
                text=f"claim {i}",
                evidence_text=f"content {i} {uniq}",
                position=1,
                confidence=0.8,
                concepts_json=json.dumps([raw], ensure_ascii=False),
            )
            pg_session.add(claim)
            claims.append(claim)
        await pg_session.commit()

        # Pre-create two distinct concepts with identical embeddings so the
        # merge branch (not just alias collapse) is exercised.
        vec = (await embedder.embed_texts(["same embedding"]))[0]
        for raw in ["AI 教育", "人工智能 教育"]:
            concept = Concept(
                query_id=query.id,
                canonical_name=raw,
                normalized_name=raw.casefold(),
                frequency=1,
                embedding=vec,
                embedding_model="mock-embed-v1",
            )
            pg_session.add(concept)
        await pg_session.commit()

        concepts = await build_concepts(pg_session, query.id, threshold=0.9)
        await pg_session.commit()

        # Merge must leave exactly one concept (higher frequency wins; both
        # were frequency 1 → first candidate order decides survivor).
        assert len(concepts) == 1, f"expected 1 concept, got {len(concepts)}"
        survivor = concepts[0]

        cc = await pg_session.execute(
            text(
                "SELECT count(*) FROM claim_concepts WHERE query_id = :qid "
                "AND concept_id = :cid"
            ),
            {"qid": query.id, "cid": survivor.id},
        )
        assert cc.scalar() == 2, "both claims must reference the survivor"

        remaining = await pg_session.execute(
            text("SELECT count(*) FROM concepts WHERE query_id = :qid"),
            {"qid": query.id},
        )
        assert remaining.scalar() == 1, "absorbed concept row must be deleted"

        await _cleanup_query(pg_session, query.id)


# ── Job processing: fetch → analyze → build → completed ───────────────

class TestJobProcessing:
    class _RealFixtureSearchProvider:
        """Search provider backed by real Stage-0 zhihu fixtures.

        Uses ``.local/zhihu-fixtures/http_q1.json`` so returned content_ids
        match the real ai_analysis fixtures (claims can be extracted).
        """

        def __init__(self) -> None:
            self._real_dir = (
                Path(__file__).resolve().parents[3]
                / ".local"
                / "zhihu-fixtures"
            )

        async def search(self, query_text: str, count: int = 10):
            provider = MockSearchProvider(fixture_dir=self._real_dir)
            return await provider.search(
                query_text, count, fixture_name="http_q1.json"
            )

        async def close(self) -> None:
            return None

    async def test_process_job_reaches_completed(
        self, pg_session: AsyncSession, uniq: str, monkeypatch  # noqa: ANN001
    ) -> None:
        """A job with mock search + analysis reaches 'completed' with graph data."""
        from app.models.job import Job
        import app.services as services_pkg
        from app.services.job_processor import process_job

        # fetch_and_store calls ``from app.services import get_search_provider``
        # at call time → patch the package attribute.
        monkeypatch.setattr(
            services_pkg,
            "get_search_provider",
            lambda: self._RealFixtureSearchProvider(),
        )

        query = Query(
            query_text=f"job {uniq}",
            normalized_query=f"job {uniq}".casefold(),
            status="pending",
        )
        pg_session.add(query)
        await pg_session.flush()
        job = Job(query_id=query.id, status="pending", current_step="Queued")
        pg_session.add(job)
        await pg_session.commit()

        await process_job(pg_session, job)
        await pg_session.commit()

        # Job must reach a terminal state.
        assert job.status in {"completed", "failed"}, job.error_message
        if job.status == "failed":
            pytest.fail(f"job failed: {job.error_code} {job.error_message}")

        # Answers, claims, concepts must exist after processing.
        n_answers = await pg_session.execute(
            text("SELECT count(*) FROM answers WHERE query_id = :qid"),
            {"qid": query.id},
        )
        assert n_answers.scalar() >= 1, "no answers persisted"
        n_claims = await pg_session.execute(
            text("SELECT count(*) FROM claims WHERE query_id = :qid"),
            {"qid": query.id},
        )
        assert n_claims.scalar() >= 1, "no claims persisted"
        n_concepts = await pg_session.execute(
            text("SELECT count(*) FROM concepts WHERE query_id = :qid"),
            {"qid": query.id},
        )
        assert n_concepts.scalar() >= 1, "no concepts persisted"

        await _cleanup_query(pg_session, query.id)

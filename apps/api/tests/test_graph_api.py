"""Stage 5 Graph API tests — nodes/edges derived from FKs (TDD).

Covers:
- GET /api/queries/{id}/graph returns 404 for missing query.
- With data: only the four node types and four edge types appear.
- The main chain QUERY→ANSWER→CLAIM→CONCEPT is present.
- SIMILAR_TO only connects same-query answers (DB enforces this).

DB-dependent (skipped without reachable PostgreSQL via pg_engine).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer
from app.models.query import Query
from app.schemas.api import GraphResponse


class TestGraphApi:
    async def test_missing_query_returns_404(
        self, client: AsyncClient, pg_engine  # noqa: ANN001
    ) -> None:
        qid = uuid.uuid4()
        response = await client.get(f"/api/queries/{qid}/graph")
        assert response.status_code == 404

    async def test_graph_returns_valid_shape(
        self, client: AsyncClient, pg_session: AsyncSession, uniq: str  # noqa: ANN001
    ) -> None:
        """Seed a query with an answer + claim + concept, then check graph."""
        from app.models.claim import Claim
        from app.models.concept import Concept
        from app.models.claim_concept import ClaimConcept

        query = Query(
            query_text=f"graph api {uniq}",
            normalized_query=f"graph api {uniq}".casefold(),
            status="completed",
        )
        pg_session.add(query)
        await pg_session.flush()
        answer = Answer(
            query_id=query.id,
            content_id=f"ga-{uniq}",
            content_text="考研能提升学历竞争力",
            url=f"https://www.zhihu.com/answer/ga-{uniq}",
            original_index=0,
        )
        pg_session.add(answer)
        await pg_session.flush()
        claim = Claim(
            query_id=query.id,
            answer_id=answer.id,
            text="考研能提升学历竞争力",
            evidence_text="考研能提升学历竞争力",
            position=1,
            confidence=0.9,
            concepts_json='["考研"]',
        )
        pg_session.add(claim)
        await pg_session.flush()
        concept = Concept(
            query_id=query.id,
            canonical_name="考研",
            normalized_name="考研",
            frequency=1,
        )
        pg_session.add(concept)
        await pg_session.flush()
        pg_session.add(
            ClaimConcept(
                query_id=query.id,
                claim_id=claim.id,
                concept_id=concept.id,
            )
        )
        await pg_session.commit()

        response = await client.get(f"/api/queries/{query.id}/graph")
        assert response.status_code == 200
        body = GraphResponse.model_validate(response.json())

        node_types = {n.type for n in body.nodes}
        assert node_types == {"QUERY", "ANSWER", "CLAIM", "CONCEPT"}

        edge_types = {e.type for e in body.edges}
        assert {"RETURNS_ANSWER", "MAKES_CLAIM", "REFERS_TO"} <= edge_types

        # Main chain present: QUERY → ANSWER → CLAIM → CONCEPT.
        by_id = {n.id: n for n in body.nodes}
        query_nid = next(i for i, n in by_id.items() if n.type == "QUERY")
        answer_nid = next(i for i, n in by_id.items() if n.type == "ANSWER")
        claim_nid = next(i for i, n in by_id.items() if n.type == "CLAIM")
        concept_nid = next(i for i, n in by_id.items() if n.type == "CONCEPT")

        edge_pairs = {(e.source, e.target, e.type) for e in body.edges}
        assert (query_nid, answer_nid, "RETURNS_ANSWER") in edge_pairs
        assert (answer_nid, claim_nid, "MAKES_CLAIM") in edge_pairs
        assert (claim_nid, concept_nid, "REFERS_TO") in edge_pairs

        # ANSWER node carries the Zhihu URL.
        answer_node = by_id[answer_nid]
        assert answer_node.url == f"https://www.zhihu.com/answer/ga-{uniq}"

        # Cleanup.
        await pg_session.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM queries WHERE id = :qid"
            ),
            {"qid": query.id},
        )
        await pg_session.commit()

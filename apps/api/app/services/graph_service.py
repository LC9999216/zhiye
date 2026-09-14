"""Graph API response builder — derives nodes/edges from business FKs (Stage 5).

The knowledge graph is *not* stored as a generic edge table.  Every edge
comes from an authoritative FK:

- ``QUERY -RETURNS_ANSWER-> ANSWER``   from ``answers.query_id``
- ``ANSWER -MAKES_CLAIM-> CLAIM``      from ``claims.answer_id``
- ``CLAIM -REFERS_TO-> CONCEPT``       from ``claim_concepts``
- ``ANSWER -SIMILAR_TO-> ANSWER``      from ``answer_similarities``

Nodes use stable ids prefixed by type (``query:``, ``answer:``,
``claim:``, ``concept:``) so the UI can group/filter them without
collision.  ANSWER and CLAIM nodes carry the Zhihu source URL so clicks
open the original answer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.answer import Answer
from app.models.answer_similarity import AnswerSimilarity
from app.models.claim import Claim
from app.models.claim_concept import ClaimConcept
from app.models.concept import Concept
from app.models.query import Query
from app.schemas.api import GraphEdge, GraphNode, GraphResponse

logger = get_logger(__name__)


def _node_id(prefix: str, uid: uuid.UUID) -> str:
    return f"{prefix}:{uid}"


async def build_graph_response(
    session: AsyncSession,
    query: Query,
) -> GraphResponse:
    """Build the renderable graph for *query* from FK-derived edges."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # ── QUERY node ────────────────────────────────────────────────────
    query_nid = _node_id("query", query.id)
    nodes.append(
        GraphNode(
            id=query_nid,
            type="QUERY",
            label=query.query_text,
        )
    )

    # ── ANSWERS + RETURNS_ANSWER ─────────────────────────────────────
    answer_result = await session.execute(
        select(Answer).where(Answer.query_id == query.id)
    )
    answers = answer_result.scalars().all()
    answer_nids: dict[uuid.UUID, str] = {}
    for answer in answers:
        nid = _node_id("answer", answer.id)
        answer_nids[answer.id] = nid
        nodes.append(
            GraphNode(
                id=nid,
                type="ANSWER",
                label=(answer.title or answer.content_id or "回答"),
                url=answer.url,
                extra={
                    "voteup_count": answer.voteup_count,
                    "author_name": answer.author_name,
                    "stance": answer.stance or "",
                    "summary": answer.summary or "",
                },
            )
        )
        edges.append(
            GraphEdge(
                source=query_nid,
                target=nid,
                type="RETURNS_ANSWER",
            )
        )

    # ── CLAIMS + MAKES_CLAIM ─────────────────────────────────────────
    claim_result = await session.execute(
        select(Claim).where(Claim.query_id == query.id)
    )
    claims = claim_result.scalars().all()
    claim_nids: dict[uuid.UUID, str] = {}
    for claim in claims:
        nid = _node_id("claim", claim.id)
        claim_nids[claim.id] = nid
        nodes.append(
            GraphNode(
                id=nid,
                type="CLAIM",
                label=claim.text,
                url=_answer_url(answers, claim.answer_id),
                extra={"confidence": claim.confidence, "position": claim.position},
            )
        )
        answer_nid = answer_nids.get(claim.answer_id)
        if answer_nid:
            edges.append(
                GraphEdge(source=answer_nid, target=nid, type="MAKES_CLAIM")
            )
        else:
            logger.warning(
                "Claim %s references missing answer %s (skipped edge)",
                claim.id,
                claim.answer_id,
            )

    # ── CONCEPTS + REFERS_TO ─────────────────────────────────────────
    concept_result = await session.execute(
        select(Concept).where(Concept.query_id == query.id)
    )
    concepts = concept_result.scalars().all()
    concept_nids: dict[uuid.UUID, str] = {}
    for concept in concepts:
        nid = _node_id("concept", concept.id)
        concept_nids[concept.id] = nid
        nodes.append(
            GraphNode(
                id=nid,
                type="CONCEPT",
                label=concept.canonical_name,
                extra={"frequency": concept.frequency},
            )
        )

    if concepts:
        link_result = await session.execute(
            select(ClaimConcept).where(ClaimConcept.query_id == query.id)
        )
        for link in link_result.scalars().all():
            claim_nid = claim_nids.get(link.claim_id)
            concept_nid = concept_nids.get(link.concept_id)
            if claim_nid and concept_nid:
                edges.append(
                    GraphEdge(
                        source=claim_nid, target=concept_nid, type="REFERS_TO"
                    )
                )

    # ── SIMILAR_TO (only same-query, degree-limited rows) ────────────
    sim_result = await session.execute(
        select(AnswerSimilarity).where(AnswerSimilarity.query_id == query.id)
    )
    for sim in sim_result.scalars().all():
        src = answer_nids.get(sim.source_answer_id)
        tgt = answer_nids.get(sim.target_answer_id)
        if src and tgt:
            edges.append(
                GraphEdge(source=src, target=tgt, type="SIMILAR_TO")
            )

    return GraphResponse(query_id=query.id, nodes=nodes, edges=edges)


def _answer_url(answers: list[Answer], answer_id: uuid.UUID) -> str | None:
    """Return the Zhihu URL for *answer_id*, if present in *answers*."""
    for answer in answers:
        if answer.id == answer_id:
            return answer.url
    return None


__all__ = ["build_graph_response"]

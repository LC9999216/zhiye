"""Graph building from business FK tables (Stage 5).

The knowledge graph is *derived* — no generic edge table, no graph
database.  Every edge comes from an authoritative FK:

- ``RETURNS_ANSWER``: ``answers.query_id``
- ``MAKES_CLAIM``:    ``claims.answer_id``
- ``REFERS_TO``:      ``claim_concepts``
- ``SIMILAR_TO``:     ``answer_similarities`` (only same-query pairs
                      above threshold, each answer's undirected degree
                      <= 2)

Concept handling
----------------
``build_concepts`` materialises ``concepts`` + ``claim_concepts`` rows
from each claim's persisted ``concepts_json`` (the raw concept names the
LLM produced), then merges high-similarity concepts within the query.

Answer similarity
-----------------
``build_answer_similarities`` computes cosine similarity between answer
embeddings (same query only), sorts candidates by (score desc, id pair
asc), and greedily adds edges while both endpoints have undirected
degree < 2.  Pairs are normalised as ``(min(id), max(id))`` and stored
once with ``embedding_model`` + ``method_version=answer-cosine-v1``.
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.answer import Answer
from app.models.answer_similarity import AnswerSimilarity
from app.models.claim import Claim
from app.models.claim_concept import ClaimConcept
from app.models.concept import Concept
from app.services.concept_normalizer import (
    alias_group,
    normalize_concept_name,
)
from app.services.embedding_provider import get_embedding_provider

logger = get_logger(__name__)

# Versioned config — tuned against human-annotated pairs (Stage 5).
CONCEPT_SIMILARITY_THRESHOLD = 0.88
ANSWER_SIMILARITY_THRESHOLD = 0.82
CONCEPT_METHOD_VERSION = "concept-cosine-v1"
ANSWER_METHOD_VERSION = "answer-cosine-v1"
MAX_ANSWER_DEGREE = 2


# ── cosine similarity ─────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [0.0, 1.0]; 0.0 when either vector is zero."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def normalise_answer_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return ``(min(a,b), max(a,b))`` so each pair is stored once."""
    return (a, b) if a < b else (b, a)


def _add_edge_with_degree_limit(
    edges: list[tuple[uuid.UUID, uuid.UUID]],
    a: uuid.UUID,
    b: uuid.UUID,
    *,
    max_degree: int = MAX_ANSWER_DEGREE,
) -> bool:
    """Greedily add ``(a,b)`` if both endpoints' degree stays < max_degree."""
    a_deg = sum(1 for e in edges if a in e)
    b_deg = sum(1 for e in edges if b in e)
    if a_deg >= max_degree or b_deg >= max_degree:
        return False
    edges.append((a, b))
    return True


# ── concept building + merging ────────────────────────────────────────

async def build_concepts(
    session: AsyncSession,
    query_id: uuid.UUID,
    *,
    threshold: float = CONCEPT_SIMILARITY_THRESHOLD,
) -> list[Concept]:
    """Materialise query-scoped concepts + claim_concepts from claims.

    Steps:
    1. Load all claims of *query_id* with their ``concepts_json``.
    2. For each unique normalised concept name, create/reuse a Concept.
    3. Link each claim → concept via ``claim_concepts``.
    4. Merge concepts whose embeddings are similar (>= threshold) by
       keeping the higher-frequency canonical name and recording aliases.

    Returns the list of Concept rows for the query (after merging).
    """
    claim_result = await session.execute(
        select(Claim).where(Claim.query_id == query_id)
    )
    claims = claim_result.scalars().all()

    if not claims:
        return []

    embedder = get_embedding_provider()

    # name -> Concept (per query).  Collect all names first so we can
    # flush the new Concept rows once (they need DB-generated ids before
    # claim_concepts rows can reference them).
    name_to_claim_ids: dict[str, list[uuid.UUID]] = {}
    raw_names_by_claim: dict[uuid.UUID, list[str]] = {}
    for claim in claims:
        concepts = _parse_concepts_json(claim.concepts_json)
        raw_names_by_claim[claim.id] = concepts
        for raw_name in concepts:
            normalized = normalize_concept_name(raw_name)
            if not normalized:
                continue
            # Deterministic alias merging: collapse aliases into one key.
            group = alias_group(normalized)
            key = group if group else normalized
            name_to_claim_ids.setdefault(key, []).append(claim.id)

    if not name_to_claim_ids:
        return []

    by_name: dict[str, Concept] = {}
    for normalized, claim_ids in name_to_claim_ids.items():
        # Reuse an existing concept row if one already exists for the query.
        existing = await session.execute(
            select(Concept).where(
                Concept.query_id == query_id,
                Concept.normalized_name == normalized,
            )
        )
        concept = existing.scalar_one_or_none()
        if concept is None:
            concept = Concept(
                query_id=query_id,
                canonical_name=normalized,
                normalized_name=normalized,
                frequency=0,
            )
            session.add(concept)
            concept.frequency += len(claim_ids)
        by_name[normalized] = concept

    # Flush so every concept has a DB-generated id.
    await session.flush()

    # Load existing claim_concepts rows for the query (idempotency).
    existing_links = await session.execute(
        select(ClaimConcept.claim_id, ClaimConcept.concept_id).where(
            ClaimConcept.query_id == query_id
        )
    )
    existing_pairs = {
        (claim_id, concept_id)
        for claim_id, concept_id in existing_links.all()
    }

    for normalized, concept in by_name.items():
        if concept.embedding is None:
            vecs = await embedder.embed_texts([concept.canonical_name])
            concept.embedding = vecs[0]
            concept.embedding_model = "mock-embed-v1"
        for claim_id in name_to_claim_ids[normalized]:
            if (claim_id, concept.id) in existing_pairs:
                continue  # already linked (idempotent re-run)
            session.add(
                ClaimConcept(
                    query_id=query_id,
                    claim_id=claim_id,
                    concept_id=concept.id,
                )
            )

    await session.flush()
    concepts = list(by_name.values())

    # Merge similar concepts (within same query).
    merged = await _merge_similar_concepts(
        session, concepts, threshold, query_id=query_id
    )
    await session.flush()
    return merged


def _parse_concepts_json(raw: str | None) -> list[str]:
    """Parse a claim's persisted concepts_json (a JSON array of names)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, list):
        return [str(x) for x in data if str(x).strip()]
    return []


async def _merge_similar_concepts(
    session: AsyncSession,
    concepts: list[Concept],
    threshold: float,
    *,
    query_id: uuid.UUID,
) -> list[Concept]:
    """Merge concepts whose cosine similarity >= *threshold*.

    Greedy: iterate pairs in (similarity desc, id pair asc) order; when
    two concepts are similar, merge the lower-frequency one into the
    higher-frequency one (record alias, rewire claim_concepts, delete the
    absorbed row).  Low-confidence candidates stay separate.
    """
    if len(concepts) < 2:
        return concepts

    candidates: list[tuple[float, Concept, Concept]] = []
    for i in range(len(concepts)):
        for j in range(i + 1, len(concepts)):
            a, b = concepts[i], concepts[j]
            if a.embedding is None or b.embedding is None:
                continue
            sim = cosine_similarity(a.embedding, b.embedding)
            if sim >= threshold:
                candidates.append((sim, a, b))

    candidates.sort(key=lambda t: (-t[0], t[1].id, t[2].id))

    # Track survivors; absorbed concepts are removed.
    removed: set[uuid.UUID] = set()
    merges: list[tuple[Concept, Concept]] = []  # (survivor, absorbed)
    for sim, a, b in candidates:
        if a.id in removed or b.id in removed:
            continue
        # Merge the lower-frequency into the higher-frequency.
        if a.frequency >= b.frequency:
            survivor, absorbed = a, b
        else:
            survivor, absorbed = b, a
        removed.add(absorbed.id)
        survivor.aliases = _append_alias(survivor.aliases, absorbed.canonical_name)
        survivor.frequency += absorbed.frequency
        merges.append((survivor, absorbed))
        logger.info(
            "Merged concept %r into %r (sim=%.3f)",
            absorbed.canonical_name,
            survivor.canonical_name,
            sim,
        )

    # Rewire claim_concepts from absorbed → survivor, then delete absorbed.
    for survivor, absorbed in merges:
        links = (
            await session.execute(
                select(ClaimConcept).where(
                    ClaimConcept.query_id == query_id,
                    ClaimConcept.concept_id == absorbed.id,
                )
            )
        ).scalars().all()
        for link in links:
            dup = await session.execute(
                select(ClaimConcept.id).where(
                    ClaimConcept.query_id == query_id,
                    ClaimConcept.claim_id == link.claim_id,
                    ClaimConcept.concept_id == survivor.id,
                )
            )
            if dup.scalar_one_or_none() is not None:
                # Claim already references the survivor → drop the old link.
                await session.delete(link)
            else:
                link.concept_id = survivor.id
        await session.delete(absorbed)

    return [c for c in concepts if c.id not in removed]


def _append_alias(existing: str | None, alias: str) -> str:
    aliases = [a.strip() for a in (existing or "").split(",") if a.strip()]
    if alias.strip() and alias.strip() not in aliases:
        aliases.append(alias.strip())
    return ",".join(aliases)


# ── answer similarity ─────────────────────────────────────────────────

async def build_answer_similarities(
    session: AsyncSession,
    query_id: uuid.UUID,
    *,
    threshold: float = ANSWER_SIMILARITY_THRESHOLD,
    max_degree: int = MAX_ANSWER_DEGREE,
) -> list[AnswerSimilarity]:
    """Compute and persist SIMILAR_TO edges for one query.

    - Cosine similarity over answer embeddings (same query only).
    - Candidates sorted by (score desc, id pair asc).
    - Greedy add while both endpoints' undirected degree < max_degree.
    - Pairs normalised as (min(id), max(id)); stored once.
    """
    result = await session.execute(
        select(Answer).where(
            Answer.query_id == query_id,
            Answer.embedding.is_not(None),
        )
    )
    answers = result.scalars().all()
    if len(answers) < 2:
        return []

    candidates: list[tuple[float, Answer, Answer]] = []
    for i in range(len(answers)):
        for j in range(i + 1, len(answers)):
            a, b = answers[i], answers[j]
            if a.embedding is None or b.embedding is None:
                continue
            sim = cosine_similarity(a.embedding, b.embedding)
            if sim >= threshold:
                candidates.append((sim, a, b))

    candidates.sort(key=lambda t: (-t[0], t[1].id, t[2].id))

    edges: list[tuple[uuid.UUID, uuid.UUID]] = []
    rows: list[AnswerSimilarity] = []
    for sim, a, b in candidates:
        low, high = normalise_answer_pair(a.id, b.id)
        if _add_edge_with_degree_limit(edges, low, high, max_degree=max_degree):
            row = AnswerSimilarity(
                query_id=query_id,
                source_answer_id=low,
                target_answer_id=high,
                score=sim,
                embedding_model="mock-embed-v1",
                method_version=ANSWER_METHOD_VERSION,
            )
            session.add(row)
            rows.append(row)

    await session.flush()
    logger.info(
        "Query %s: %d answer pair(s) above threshold, %d edge(s) kept",
        query_id,
        len(candidates),
        len(rows),
    )
    return rows


__all__ = [
    "ANSWER_METHOD_VERSION",
    "ANSWER_SIMILARITY_THRESHOLD",
    "CONCEPT_METHOD_VERSION",
    "CONCEPT_SIMILARITY_THRESHOLD",
    "MAX_ANSWER_DEGREE",
    "build_answer_similarities",
    "build_concepts",
    "cosine_similarity",
    "normalise_answer_pair",
]

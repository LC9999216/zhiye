"""Answer analysis orchestration — extract, validate, persist (Stage 4).

For each answer in a query's result set:

1. Build the prompt and call the LLM provider (retry 2× on bad output).
2. Cap claims at 5 and verify each claim's evidence is a substring of the
   ContentText.
3. Generate embeddings for the answer text and each claim.
4. Persist the claims (replacing any prior claims for that answer in one
   transaction) and update the answer's traceability columns
   (``analysis_model``, ``prompt_version``, ``schema_version``,
   ``analyzed_at``, ``analysis_latency_ms``).
5. If a single answer fails after retries, record the failure and continue
   with the remaining answers (never block the batch).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.answer import Answer
from app.models.claim import Claim
from app.schemas.ai import (
    AnalysisFailureDTO,
    ClaimExtractionDTO,
)
from app.services.claim_extractor import (
    ClaimExtractionError,
    extract_claims,
)
from app.services.embedding_provider import (
    EmbeddingProvider,
    get_embedding_provider,
)
from app.services.llm_provider import LLMProvider, get_llm_provider
from app.services.prompts import PROMPT_VERSION, SCHEMA_VERSION

logger = get_logger(__name__)


class AnswerAnalysisError(Exception):
    """Raised for whole-batch analysis failures (not per-answer)."""


async def analyze_answer(
    session: AsyncSession,
    answer: Answer,
    *,
    provider: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
) -> AnalysisFailureDTO | None:
    """Analyse one answer and persist claims + traceability fields.

    Returns an :class:`AnalysisFailureDTO` when the answer could not be
    analysed (after retries); returns ``None`` on success.

    The caller owns the transaction boundary; this function only flushes
    its own changes.
    """
    provider = provider or get_llm_provider()
    embedder = embedder or get_embedding_provider()

    started = time.perf_counter()

    try:
        extraction: ClaimExtractionDTO = await extract_claims(
            provider,
            answer.content_id,
            answer.content_text or "",
        )
    except ClaimExtractionError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "Analysis failed for answer %s (%dms): %s",
            answer.content_id,
            elapsed_ms,
            exc,
        )
        return AnalysisFailureDTO(
            error_code="ANALYSIS_FAILED",
            message=str(exc),
            attempts=exc.attempts,
        )

    # Embeddings (answer-level + per-claim).
    try:
        texts = [answer.content_text or ""]
        texts += [c.text for c in extraction.claims]
        vectors = await embedder.embed_texts(texts)
        answer_vec = vectors[0]
        claim_vecs = vectors[1:]
    except Exception as exc:  # noqa: BLE001 — embeddings are best-effort
        logger.warning("Embedding failed for answer %s: %s", answer.content_id, exc)
        answer_vec = None
        claim_vecs = [None] * len(extraction.claims)

    # ── persist: replace claims in one transaction ────────────────────
    existing = await session.execute(
        select(Claim).where(Claim.answer_id == answer.id)
    )
    for claim in existing.scalars().all():
        await session.delete(claim)

    for i, claim in enumerate(extraction.claims):
        session.add(
            Claim(
                query_id=answer.query_id,
                answer_id=answer.id,
                text=claim.text,
                evidence_text=claim.evidence_text,
                position=claim.position,
                confidence=claim.confidence,
                embedding=claim_vecs[i] if claim_vecs and i < len(claim_vecs) else None,
                embedding_model=(
                    "mock-embed-v1" if claim_vecs and i < len(claim_vecs) else None
                ),
            )
        )

    # ── update answer traceability ────────────────────────────────────
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    answer.summary = extraction.summary
    answer.stance = extraction.stance
    answer.embedding = answer_vec
    answer.embedding_model = "mock-embed-v1" if answer_vec else None
    answer.analysis_model = (
        settings.llm_model or "mock-llm-stage4-v1"
    )
    answer.prompt_version = PROMPT_VERSION
    answer.schema_version = SCHEMA_VERSION
    answer.analyzed_at = datetime.now(timezone.utc)
    answer.analysis_latency_ms = elapsed_ms

    await session.flush()
    logger.info(
        "Analysed answer %s: %d claim(s), %dms",
        answer.content_id,
        len(extraction.claims),
        elapsed_ms,
    )
    return None


async def analyze_query_answers(
    session: AsyncSession,
    query_id,
) -> tuple[int, list[AnalysisFailureDTO]]:
    """Analyse every answer of *query_id*; return (analysed, failures)."""
    result = await session.execute(
        select(Answer).where(Answer.query_id == query_id)
    )
    answers = result.scalars().all()

    analysed = 0
    failures: list[AnalysisFailureDTO] = []
    for answer in answers:
        failure = await analyze_answer(session, answer)
        if failure is not None:
            failures.append(failure)
        else:
            analysed += 1

    return analysed, failures


__all__ = [
    "AnswerAnalysisError",
    "analyze_answer",
    "analyze_query_answers",
]

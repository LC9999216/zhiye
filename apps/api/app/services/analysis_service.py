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

import json
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ProviderAuthError,
    ProviderContractError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
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


class _UnavailableLLMProvider:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def complete(self, prompt: str) -> str:
        raise self.error


class _UnavailableEmbeddingProvider:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise self.error


def _analysis_error_code(error: Exception) -> str:
    if isinstance(error, ProviderAuthError):
        return "PROVIDER_AUTH_FAILED"
    if isinstance(error, ProviderRateLimitError):
        return "PROVIDER_RATE_LIMITED"
    if isinstance(error, ProviderUnavailableError):
        return "PROVIDER_UNAVAILABLE"
    if isinstance(error, ProviderContractError):
        return "PROVIDER_CONTRACT_FAILED"
    if isinstance(error, TimeoutError):
        return "PROVIDER_TIMEOUT"
    return "ANALYSIS_FAILED"


def _usage_records(provider: object, start: int = 0) -> list[dict[str, object]]:
    """Return a copy of provider usage records created after *start*."""
    records = getattr(provider, "usage_records", None)
    if not isinstance(records, list):
        return []
    return [dict(item) for item in records[start:] if isinstance(item, dict)]


def _analysis_usage_json(
    llm_calls: list[dict[str, object]],
    embedding_calls: list[dict[str, object]],
) -> str | None:
    if not llm_calls and not embedding_calls:
        return None
    return json.dumps(
        {"llm_calls": llm_calls, "embedding_calls": embedding_calls},
        ensure_ascii=False,
    )


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
    started = time.perf_counter()
    llm_usage_start = len(getattr(provider, "usage_records", []) or []) if provider else 0

    embedding_failure_unknown = False
    embedding_failure_code: str | None = None
    embedding_usage_start = 0
    try:
        provider = provider or get_llm_provider()
        extraction: ClaimExtractionDTO = await extract_claims(
            provider,
            answer.content_id,
            answer.content_text or "",
        )
    except (
        ClaimExtractionError,
        ProviderAuthError,
        ProviderContractError,
        ProviderRateLimitError,
        ProviderUnavailableError,
        TimeoutError,
    ) as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "Analysis failed for answer %s (%dms): %s",
            answer.content_id,
            elapsed_ms,
            exc,
        )
        answer.analysis_status = "failed"
        answer.analysis_error_code = _analysis_error_code(exc)
        llm_calls = _usage_records(provider, llm_usage_start)
        if not llm_calls:
            no_charge = isinstance(exc, (ProviderAuthError, ProviderRateLimitError))
            llm_calls.append(
                {
                    "model": getattr(provider, "model_name", None),
                    "request_id": None,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "usage_available": no_charge,
                    "no_charge": no_charge,
                    "error_code": _analysis_error_code(exc),
                }
            )
        answer.analysis_usage_json = _analysis_usage_json(
            llm_calls, []
        )
        await session.flush()
        return AnalysisFailureDTO(
            error_code=_analysis_error_code(exc),
            message=str(exc),
            attempts=getattr(exc, "attempts", 1),
        )

    # Embeddings (answer-level + per-claim).
    try:
        embedder = embedder or get_embedding_provider()
        embedding_usage_start = len(getattr(embedder, "usage_records", []) or [])
        texts = [answer.content_text or ""]
        texts += [c.text for c in extraction.claims]
        vectors = await embedder.embed_texts(texts)
        answer_vec = vectors[0]
        claim_vecs = vectors[1:]
    except Exception as exc:  # noqa: BLE001 — embeddings are best-effort
        logger.warning("Embedding failed for answer %s: %s", answer.content_id, exc)
        answer_vec = None
        claim_vecs = [None] * len(extraction.claims)
        embedding_failure_unknown = True
        embedding_failure_code = type(exc).__name__

    llm_result = getattr(provider, "last_result", None)
    llm_model = (
        getattr(llm_result, "model", None)
        or getattr(provider, "model_name", None)
        or settings.llm_model
    )
    embedding_result = getattr(embedder, "last_result", None)
    llm_calls = _usage_records(provider, llm_usage_start)
    embedding_calls = _usage_records(embedder, embedding_usage_start)
    if embedding_failure_unknown:
        embedding_calls.append(
            {
                "model": getattr(embedder, "model_name", None),
                "request_id": None,
                "total_tokens": 0,
                "usage_available": False,
                "error_code": embedding_failure_code or "EMBEDDING_FAILED",
            }
        )
    embedding_model = None
    if answer_vec is not None:
        embedding_model = (
            getattr(embedding_result, "model", None)
            or getattr(embedder, "model_name", None)
            or settings.embedding_model
        )

    # ── persist: replace claims in one transaction ────────────────────
    existing = await session.execute(
        select(Claim).where(Claim.answer_id == answer.id)
    )
    for claim in existing.scalars().all():
        await session.delete(claim)
    # Flush the deletes so the unique index (query_id, answer_id, position)
    # no longer conflicts with the new claims we insert below — PostgreSQL
    # checks UNIQUE constraints immediately, even within the same tx.
    await session.flush()

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
                    embedding_model if claim_vecs and i < len(claim_vecs) else None
                ),
                concepts_json=json.dumps(claim.concepts, ensure_ascii=False),
            )
        )

    # ── update answer traceability ────────────────────────────────────
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    answer.summary = extraction.summary
    answer.stance = extraction.stance
    answer.embedding = answer_vec
    answer.embedding_model = embedding_model
    answer.analysis_model = llm_model
    answer.analysis_request_id = getattr(llm_result, "request_id", None)
    answer.analysis_usage_json = _analysis_usage_json(llm_calls, embedding_calls)
    answer.analysis_status = "completed"
    answer.analysis_error_code = None
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
    *,
    provider: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
) -> tuple[int, list[AnalysisFailureDTO]]:
    """Analyse every answer of *query_id*; return (analysed, failures)."""
    result = await session.execute(
        select(Answer).where(Answer.query_id == query_id)
    )
    answers = result.scalars().all()

    owns_provider = provider is None
    owns_embedder = embedder is None
    if provider is None:
        try:
            provider = get_llm_provider()
        except Exception as exc:  # noqa: BLE001 — report per-answer safely
            provider = _UnavailableLLMProvider(exc)
    if embedder is None:
        try:
            embedder = get_embedding_provider()
        except Exception as exc:  # noqa: BLE001 — semantic vectors are optional
            embedder = _UnavailableEmbeddingProvider(exc)

    analysed = 0
    failures: list[AnalysisFailureDTO] = []
    try:
        for answer in answers:
            failure = await analyze_answer(
                session, answer, provider=provider, embedder=embedder
            )
            if failure is not None:
                failures.append(failure)
            else:
                analysed += 1
        return analysed, failures
    finally:
        for owned in (provider if owns_provider else None, embedder if owns_embedder else None):
            close = getattr(owned, "aclose", None)
            if close is not None:
                await close()


__all__ = [
    "AnswerAnalysisError",
    "analyze_answer",
    "analyze_query_answers",
]

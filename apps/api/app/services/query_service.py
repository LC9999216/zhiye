"""Query analysis orchestration — normalize, search, persist, track progress.

This service manages the full lifecycle of a query-analysis request:
1. Normalize the query text (NFKC, casefold, trim, collapse spaces).
2. Look up or create a ``Query`` record (idempotent on normalized form).
3. Create or reuse a ``Job`` to track processing.
4. Orchestrate search, analysis, and graph building steps via the job
   state machine.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.answer import Answer
from app.models.job import Job
from app.models.query import Query
from app.schemas.api import AnalyzeResponse, AnswerItem, AnswersResponse, JobResponse, QueryResponse
from app.services.search_service import SearchPipeline
from app.services import get_search_provider

logger = get_logger(__name__)


# ── Query normalisation ──────────────────────────────────────────────

def normalize_query_text(raw: str) -> str:
    """Normalise a user query for idempotent matching.

    Applies NFKC, strip, collapse whitespace, casefold.
    """
    return SearchPipeline.normalize_query(raw)


# ── Query / Job management ───────────────────────────────────────────

async def create_or_get_query(
    session: AsyncSession,
    query_text: str,
) -> tuple[Query, bool]:
    """Return (query, was_created) — idempotent on ``normalized_query``.

    If a query with the same normalized text exists, returns it.
    Otherwise creates a new ``Query`` row.
    """
    normalized = normalize_query_text(query_text)
    if not normalized:
        msg = "Query text is empty after normalisation"
        raise ValueError(msg)

    result = await session.execute(
        select(Query).where(Query.normalized_query == normalized)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        return existing, False

    query = Query(
        query_text=query_text.strip(),
        normalized_query=normalized,
        status="pending",
    )
    session.add(query)
    await session.flush()
    logger.info("Created query id=%s text=%r", query.id, query_text)
    return query, True


async def create_job_for_query(
    session: AsyncSession,
    query: Query,
) -> tuple[Job, bool]:
    """Create a new Job for *query*, or return the active job if one exists.

    Returns (job, is_new). An active job is one with status in
    ``{pending, fetching, analyzing, building}``.
    """
    active_statuses = {"pending", "fetching", "analyzing", "building"}
    result = await session.execute(
        select(Job)
        .where(Job.query_id == query.id)
        .where(Job.status.in_(active_statuses))
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    job = Job(
        query_id=query.id,
        status="pending",
        current_step="Queued for processing",
    )
    session.add(job)
    await session.flush()
    logger.info("Created job id=%s for query id=%s", job.id, query.id)
    return job, True


async def _fail_running_jobs(session: AsyncSession, query_id: uuid.UUID) -> None:
    """Mark any running jobs for *query_id* as failed (startup recovery)."""
    running_statuses = {"pending", "fetching", "analyzing", "building"}
    result = await session.execute(
        select(Job)
        .where(Job.query_id == query_id)
        .where(Job.status.in_(running_statuses))
    )
    for job in result.scalars().all():
        job.status = "failed"
        job.error_code = "SERVER_RESTART"
        job.error_message = "Job interrupted by server restart"
        job.finished_at = datetime.now(timezone.utc)
        logger.warning("Marked job %s as failed due to server restart", job.id)
    await session.flush()


async def recover_running_jobs(session: AsyncSession) -> None:
    """On startup, fail any jobs left in running states."""
    running_statuses = {"pending", "fetching", "analyzing", "building"}
    result = await session.execute(
        select(Job).where(Job.status.in_(running_statuses))
    )
    count = 0
    for job in result.scalars().all():
        job.status = "failed"
        job.error_code = "SERVER_RESTART"
        job.error_message = "Job interrupted by server restart"
        job.finished_at = datetime.now(timezone.utc)
        count += 1
    if count:
        await session.flush()
        logger.info("Recovered %d running job(s) to failed state", count)


# ── Job state machine ────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _transition(
    session: AsyncSession,
    job: Job,
    status: str,
    step: str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update job status and step, record timestamps on terminal transitions."""
    job.status = status
    job.current_step = step
    if status in ("fetching", "analyzing", "building") and job.started_at is None:
        job.started_at = _now()
    if status in ("completed", "failed"):
        job.finished_at = _now()
    if error_code:
        job.error_code = error_code
    if error_message:
        job.error_message = error_message
    await session.flush()


# ── API response builders ────────────────────────────────────────────

def build_job_response(
    job: Job,
    *,
    base_url: str = "",
) -> JobResponse:
    """Build a ``JobResponse`` from a ``Job`` ORM instance."""
    query_url = f"{base_url}/api/queries/{job.query_id}" if base_url else None
    answers_url = (
        f"{base_url}/api/queries/{job.query_id}/answers" if base_url else None
    )
    graph_url = (
        f"{base_url}/api/queries/{job.query_id}/graph" if base_url else None
    )

    return JobResponse(
        id=job.id,
        query_id=job.query_id,
        status=job.status,
        current_step=job.current_step or "",
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        updated_at=job.updated_at,
        query_url=query_url if job.status == "completed" else None,
        answers_url=answers_url if job.status == "completed" else None,
        graph_url=graph_url if job.status == "completed" else None,
    )


async def build_query_response(
    session: AsyncSession,
    query: Query,
    *,
    base_url: str = "",
) -> QueryResponse:
    """Build a ``QueryResponse`` from a ``Query`` ORM instance."""
    count_result = await session.execute(
        select(text("COUNT(*)")).select_from(Answer.__table__).where(
            Answer.query_id == query.id
        )
    )
    answer_count = count_result.scalar() or 0

    return QueryResponse(
        id=query.id,
        query_text=query.query_text,
        normalized_query=query.normalized_query,
        status=query.status,
        search_hash_id=query.search_hash_id,
        answer_count=answer_count,
        created_at=query.created_at,
        updated_at=query.updated_at,
    )


async def build_answers_response(
    session: AsyncSession,
    query: Query,
    *,
    base_url: str = "",
) -> AnswersResponse:
    """Build an ``AnswersResponse`` from a ``Query`` ORM instance.

    Answers are returned in ``voteup_count`` descending order (as stored).
    """
    result = await session.execute(
        select(Answer)
        .where(Answer.query_id == query.id)
        .order_by(Answer.voteup_count.desc(), Answer.original_index)
    )
    answers = result.scalars().all()

    items = [
        AnswerItem(
            id=a.id,
            content_id=a.content_id,
            title=a.title,
            author_name=a.author_name,
            content_text=a.content_text,
            voteup_count=a.voteup_count,
            url=a.url,
            original_index=a.original_index,
            summary=a.summary,
            stance=a.stance,
            claim_count=len(a.claims) if a.claims else 0,
        )
        for a in answers
    ]

    return AnswersResponse(
        query_id=query.id,
        query_text=query.query_text,
        answers=items,
        total=len(items),
    )

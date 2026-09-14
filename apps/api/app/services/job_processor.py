"""Job execution orchestration — fetch → analyze → build → completed (Stage 5).

Implements the single-process background job state machine required by
the execution plan (``jobs`` table statuses: pending → fetching →
analyzing → building → completed|failed).

For each job:
1. ``fetching``: run the search pipeline (mock or real Zhihu provider),
   persist answers, mark query completed.
2. ``analyzing``: run ``analyze_query_answers`` (AI extraction + claims).
3. ``building``: run ``build_concepts`` + ``build_answer_similarities``.
4. ``completed``: mark job terminal.

Any unrecoverable error marks the job ``failed`` with a machine-readable
code + message (never blocks other jobs).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.job import Job
from app.models.query import Query
from app.services.analysis_service import analyze_query_answers
from app.services.graph_builder import (
    build_answer_similarities,
    build_concepts,
)
from app.services.query_service import _transition
from app.services.search_service import SearchPipeline

logger = get_logger(__name__)


async def process_job(session: AsyncSession, job: Job) -> None:
    """Run one job to completion (or failure) in the current transaction.

    Caller owns the session/transaction; this function only flushes its
    own changes via ``_transition``.
    """
    if job.status not in {"pending", "fetching", "analyzing", "building"}:
        logger.info("Job %s already terminal (%s); skipping", job.id, job.status)
        return

    query_result = await session.execute(
        select(Query).where(Query.id == job.query_id)
    )
    query = query_result.scalar_one_or_none()
    if query is None:
        await _transition(
            session, job, "failed", "Query missing",
            error_code="QUERY_NOT_FOUND",
            error_message="Job references a missing query",
        )
        await session.commit()
        return

    try:
        # 1) fetching: search + persist answers.
        await _transition(session, job, "fetching", "Searching Zhihu")
        await session.commit()
        await SearchPipeline.fetch_and_store(session, query)
        query.status = "completed"
        await session.commit()

        # 2) analyzing: AI extraction for each answer.
        await _transition(session, job, "analyzing", "Extracting claims")
        await session.commit()
        analysed, failures = await analyze_query_answers(session, query.id)
        await session.commit()
        if failures:
            logger.warning(
                "Query %s: %d/%d answer(s) failed analysis",
                query.id,
                len(failures),
                analysed + len(failures),
            )

        # 3) building: concepts + answer similarities.
        await _transition(session, job, "building", "Building knowledge graph")
        await session.commit()
        await build_concepts(session, query.id)
        await build_answer_similarities(session, query.id)
        await session.commit()

        # 4) completed.
        await _transition(session, job, "completed", "Analysis complete")
        await session.commit()
        logger.info("Job %s completed for query %s", job.id, query.id)
    except Exception as exc:  # noqa: BLE001 — job must fail cleanly
        logger.exception("Job %s failed: %s", job.id, exc)
        await _transition(
            session,
            job,
            "failed",
            "Processing failed",
            error_code="JOB_FAILED",
            error_message=str(exc)[:2000],
        )
        await session.commit()


async def process_query_jobs(session: AsyncSession, query_id: uuid.UUID) -> None:
    """Process all pending/running jobs for *query_id* in order."""
    result = await session.execute(
        select(Job)
        .where(Job.query_id == query_id)
        .where(Job.status.in_({"pending", "fetching", "analyzing", "building"}))
        .order_by(Job.created_at)
    )
    for job in result.scalars().all():
        await process_job(session, job)


__all__ = ["process_job", "process_query_jobs"]

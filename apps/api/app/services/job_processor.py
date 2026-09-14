"""Job execution orchestration — fetch → analyze → build → terminal (Stage 5).

Implements the single-process background job state machine required by
the execution plan (``jobs`` table statuses: pending → fetching →
analyzing → building → completed|completed_partial|failed).

For each job:
1. ``fetching``: run the search pipeline (mock or real Zhihu provider),
   persist answers, mark query completed.
2. ``analyzing``: run ``analyze_query_answers`` (AI extraction + claims).
3. ``building``: run ``build_concepts`` + ``build_answer_similarities``.
4. ``completed`` or ``completed_partial``: mark job terminal.

Any unrecoverable error marks the job ``failed`` with a machine-readable
code + message (never blocks other jobs).
"""

from __future__ import annotations

import uuid
import json
import time
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BudgetExhaustedError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ZhihuAuthError,
    ZhihuDataContractError,
    ZhihuInternalError,
    ZhihuRateLimitError,
)
from app.core.logging import get_logger
from app.models.job import Job
from app.models.query import Query
from app.models.answer import Answer
from app.services.analysis_service import analyze_query_answers
from app.services.graph_builder import (
    build_answer_similarities,
    build_concepts,
)
from app.services.query_service import _transition
from app.services.search_service import SearchPipeline
from app.services.budget_service import (
    record_job_usage,
    release_job_budget_if_no_usage,
    reserve_job_budget,
    settle_job_budget,
)

logger = get_logger(__name__)


def _failure_details(exc: Exception) -> tuple[str, str]:
    """Map known provider failures to safe, actionable job details."""
    mappings: tuple[tuple[type[Exception], str, str], ...] = (
        (ZhihuAuthError, "ZHIHU_AUTH_FAILED", "知乎鉴权失败，请检查服务端 Secret"),
        (ZhihuRateLimitError, "ZHIHU_RATE_LIMITED", "知乎额度或频率受限，请稍后再试"),
        (ZhihuInternalError, "ZHIHU_UNAVAILABLE", "知乎服务暂时不可用，请稍后重试"),
        (ZhihuDataContractError, "ZHIHU_CONTRACT_FAILED", "知乎返回数据格式异常，请稍后重试"),
        (ProviderAuthError, "PROVIDER_AUTH_FAILED", "模型服务鉴权失败，请检查服务端配置"),
        (ProviderRateLimitError, "PROVIDER_RATE_LIMITED", "模型服务额度或频率受限，请稍后再试"),
        (ProviderUnavailableError, "PROVIDER_UNAVAILABLE", "模型服务暂时不可用，请稍后重试"),
    )
    for error_type, code, message in mappings:
        if isinstance(exc, error_type):
            return code, message
    if isinstance(exc, TimeoutError):
        return "JOB_TIMEOUT", "任务仍可能执行，已保存当前结果"
    return "JOB_FAILED", "分析任务失败，请稍后重试"


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
        started_monotonic = time.monotonic()

        def ensure_deadline() -> None:
            if time.monotonic() - started_monotonic > settings.job_timeout_seconds:
                raise TimeoutError("JOB_TIMEOUT")

        # 1) fetching: search + persist answers.
        ensure_deadline()
        await _transition(session, job, "fetching", "Searching Zhihu")
        await session.commit()
        remaining = settings.job_timeout_seconds - (time.monotonic() - started_monotonic)
        if remaining <= 0:
            raise TimeoutError("JOB_TIMEOUT")
        async with asyncio.timeout(remaining):
            await SearchPipeline.fetch_and_store(session, query)
        query.status = "completed"
        await session.commit()

        answer_result = await session.execute(
            select(Answer).where(Answer.query_id == query.id)
        )
        answer_rows = answer_result.scalars().all()
        if settings.app_mode == "production":
            try:
                await reserve_job_budget(session, job, query, answers=answer_rows)
                await session.commit()
            except BudgetExhaustedError as exc:
                job.warnings_json = json.dumps(
                    [
                        f"{exc}: 预算检查未通过，已保存知乎搜索结果，可稍后重新提交",
                    ],
                    ensure_ascii=False,
                )
                await session.flush()
                await _transition(
                    session,
                    job,
                    "completed_partial",
                    "Budget check failed",
                    error_code=str(exc),
                    error_message="预算不足或无法证明本次调用上界安全，搜索结果已保存",
                )
                await session.commit()
                return

        # 2) analyzing: AI extraction for each answer.
        ensure_deadline()
        await _transition(session, job, "analyzing", "Extracting claims")
        await session.commit()
        remaining = settings.job_timeout_seconds - (time.monotonic() - started_monotonic)
        if remaining <= 0:
            raise TimeoutError("JOB_TIMEOUT")
        async with asyncio.timeout(remaining):
            analysed, failures = await analyze_query_answers(session, query.id)
        await session.commit()
        embedding_warning = bool(answer_rows) and any(
            answer.embedding is None for answer in answer_rows
        )
        if failures:
            logger.warning(
                "Query %s: %d/%d answer(s) failed analysis",
                query.id,
                len(failures),
                analysed + len(failures),
            )
            warnings = [
                f"{failure.error_code}: {failure.message}" for failure in failures
            ]
            if not analysed:
                warnings.insert(0, "所有回答观点提取失败，已保留真实搜索结果")
            if embedding_warning:
                warnings.append("语义关联未完成，已保留有证据的基础观点")
            job.warnings_json = json.dumps(warnings[:20], ensure_ascii=False)
            await session.flush()
        elif embedding_warning:
            job.warnings_json = json.dumps(
                ["语义关联未完成，已保留有证据的基础观点"], ensure_ascii=False
            )
            await session.flush()

        # 3) building: concepts + answer similarities.
        ensure_deadline()
        await _transition(session, job, "building", "Building knowledge graph")
        await session.commit()
        remaining = settings.job_timeout_seconds - (time.monotonic() - started_monotonic)
        if remaining <= 0:
            raise TimeoutError("JOB_TIMEOUT")
        graph_usage: list[dict[str, object]] = []
        async with asyncio.timeout(remaining):
            await build_concepts(session, query.id, usage_sink=graph_usage)
            await build_answer_similarities(session, query.id)
        await record_job_usage(session, job.id, query.id, graph_usage=graph_usage)
        await session.commit()

        # 4) completed.
        ensure_deadline()
        await settle_job_budget(session, job.id)
        final_status = "completed_partial" if failures else "completed"
        final_step = (
            "Analysis partially complete"
            if final_status == "completed_partial"
            else "Analysis complete"
        )
        await _transition(session, job, final_status, final_step)
        await session.commit()
        logger.info("Job %s finished with status %s for query %s", job.id, final_status, query.id)
    except Exception as exc:  # noqa: BLE001 — job must fail cleanly
        logger.exception("Job %s failed: %s", job.id, exc)
        error_code, error_message = _failure_details(exc)
        # A timeout may cancel an in-flight HTTP request before its usage can
        # be persisted.  Keep the reservation conservatively because the
        # provider may still have accepted and billed that request.
        if error_code != "JOB_TIMEOUT":
            await release_job_budget_if_no_usage(session, job.id, reason=error_code)
        await _transition(
            session,
            job,
            "failed",
            "Processing failed",
            error_code=error_code,
            error_message=error_message,
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

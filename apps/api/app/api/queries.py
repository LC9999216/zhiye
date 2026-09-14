"""Query and analysis endpoints — ``/api/queries/analyze``, ``/api/queries/{id}``.

Stage 3 implementation: submit a query, track job progress, list answers.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.logging import get_logger
from app.models.job import Job
from app.models.query import Query
from app.schemas.api import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnswersResponse,
    ErrorResponse,
    GraphResponse,
    QueryResponse,
    JobResponse,
)
from app.services.query_service import (
    build_answers_response,
    build_job_response,
    build_query_response,
    create_job_for_query,
    create_or_get_query,
)
from app.services.graph_service import build_graph_response
from app.services.job_processor import process_job

logger = get_logger(__name__)

router = APIRouter(prefix="/queries", tags=["queries"])

_BASE_URL = ""  # Relative URLs — clients resolve against their base.


@router.post(
    "/analyze",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a natural-language question for analysis",
    responses={
        202: {"model": AnalyzeResponse, "description": "Job created"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def analyze_query(
    body: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """Submit a natural language question for Zhihu search and analysis.

    Returns 202 immediately with a ``job_id`` and ``query_id``.
    Actual processing (search → AI analysis → graph building) runs as a
    single-process background task, tracked through the ``jobs`` table.
    """
    query, _ = await create_or_get_query(session, body.query_text)
    job, is_new = await create_job_for_query(session, query)
    await session.commit()

    if not is_new:
        logger.info(
            "Reusing active job %s for query %s", job.id, query.id
        )
    else:
        # Kick off the job in the background (single-process worker).
        from app.db.session import async_session_factory

        async def _run() -> None:
            async with async_session_factory() as bg_session:
                # Reload the job in this session (avoid detached instance).
                job_row = await bg_session.get(Job, job.id)
                if job_row is not None:
                    await process_job(bg_session, job_row)

        background_tasks.add_task(_run)

    return AnalyzeResponse(
        job_id=job.id,
        query_id=query.id,
        job_url=f"/api/jobs/{job.id}",
    )


@router.get(
    "/{query_id}",
    summary="Get query details",
    responses={
        200: {"model": QueryResponse},
        404: {"model": ErrorResponse, "description": "Query not found"},
    },
)
async def get_query(
    query_id: uuid.UUID = Path(..., description="Query UUID"),
    session: AsyncSession = Depends(get_db),
) -> QueryResponse:
    """Return metadata about a previously submitted query."""
    result = await session.execute(
        select(Query).where(Query.id == query_id)
    )
    query = result.scalar_one_or_none()
    if query is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "QUERY_NOT_FOUND", "message": "Query not found"},
        )

    return await build_query_response(session, query)


@router.get(
    "/{query_id}/answers",
    summary="Get answers for a query",
    responses={
        200: {"model": AnswersResponse},
        404: {"model": ErrorResponse, "description": "Query not found"},
    },
)
async def get_answers(
    query_id: uuid.UUID = Path(..., description="Query UUID"),
    session: AsyncSession = Depends(get_db),
) -> AnswersResponse:
    """Return the sorted list of answers for a query."""
    result = await session.execute(
        select(Query).where(Query.id == query_id)
    )
    query = result.scalar_one_or_none()
    if query is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "QUERY_NOT_FOUND", "message": "Query not found"},
        )

    return await build_answers_response(session, query)


@router.get(
    "/{query_id}/graph",
    summary="Get the knowledge graph for a query",
    responses={
        200: {"model": GraphResponse},
        404: {"model": ErrorResponse, "description": "Query not found"},
    },
)
async def get_graph(
    query_id: uuid.UUID = Path(..., description="Query UUID"),
    session: AsyncSession = Depends(get_db),
) -> GraphResponse:
    """Return the directly renderable QUERY→ANSWER→CLAIM→CONCEPT graph.

    All edges are derived from authoritative FK tables — no generic edge
    table, no graph database.  ANSWER and CLAIM nodes carry the Zhihu
    source URL so clicks open the original answer.
    """
    result = await session.execute(
        select(Query).where(Query.id == query_id)
    )
    query = result.scalar_one_or_none()
    if query is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "QUERY_NOT_FOUND", "message": "Query not found"},
        )

    return await build_graph_response(session, query)

"""Job polling endpoint — ``GET /api/jobs/{id}``.

Stage 3 implementation: returns the current state of an analysis job,
including result URLs when the job is completed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db, require_invite_code
from app.core.logging import get_logger
from app.models.job import Job
from app.models.query import Query
from app.schemas.api import ErrorResponse, JobResponse
from app.services.query_service import build_job_response

logger = get_logger(__name__)

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_invite_code)],
)

# Base URL for generating absolute URLs in responses.
# In production this should come from the request's ``Host`` header.
_BASE_URL = ""


@router.get(
    "/{job_id}",
    summary="Poll job status",
    responses={
        200: {"model": JobResponse},
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def get_job(
    job_id: uuid.UUID = Path(..., description="Job UUID"),
    session: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Return the current status of an analysis job.

    When ``status`` is ``completed`` or ``completed_partial``, the response
    includes ``answers_url`` and ``graph_url`` for fetching results.
    """
    result = await session.execute(
        select(Job)
        .join(Query, Query.id == Job.query_id)
        .where(Job.id == job_id, Query.data_mode == settings.app_mode)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"},
        )

    return build_job_response(job, base_url=_BASE_URL)

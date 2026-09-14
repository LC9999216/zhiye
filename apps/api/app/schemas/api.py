"""Pydantic schemas for API request/response bodies (Stage 3).

These models define the wire format for the query-analysis endpoints.
Internal DTOs and database models are separate files.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.search_service import SearchPipeline


# ── POST /api/queries/analyze ────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Request body for submitting a natural-language question for analysis."""

    query_text: str = Field(
        min_length=1,
        max_length=200,
        description="Natural-language question to search on Zhihu",
    )

    @field_validator("query_text")
    @classmethod
    def _validate_not_blank(cls, v: str) -> str:
        """Reject whitespace-only strings (after normalisation would be empty)."""
        normalized = SearchPipeline.normalize_query(v)
        if not normalized:
            msg = "Query text is empty or only whitespace after normalisation"
            raise ValueError(msg)
        return v


class AnalyzeResponse(BaseModel):
    """202 response after successfully creating an analysis job."""

    job_id: uuid.UUID = Field(description="Job UUID for polling status")
    query_id: uuid.UUID = Field(description="Query UUID (reused on normalized match)")
    job_url: str = Field(description="URL to poll the job status at")


# ── GET /api/jobs/{id} ──────────────────────────────────────────────

class JobResponse(BaseModel):
    """Current state of an analysis job."""

    id: uuid.UUID
    query_id: uuid.UUID
    status: str = Field(
        pattern=r"^(pending|fetching|analyzing|building|completed|failed)$"
    )
    current_step: str = ""
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime

    # Terminal response: available when status == "completed".
    query_url: Optional[str] = None
    answers_url: Optional[str] = None
    graph_url: Optional[str] = None


# ── GET /api/queries/{id} ───────────────────────────────────────────

class QueryResponse(BaseModel):
    """Public view of a Query record."""

    id: uuid.UUID
    query_text: str
    normalized_query: str
    status: str
    search_hash_id: Optional[str] = None
    answer_count: int = 0
    created_at: datetime
    updated_at: datetime


# ── GET /api/queries/{id}/answers ───────────────────────────────────

class AnswerItem(BaseModel):
    """A single answer in the query's answer list."""

    id: uuid.UUID
    content_id: str
    title: str = ""
    author_name: str = ""
    content_text: str = ""
    voteup_count: int = 0
    url: str = ""
    original_index: int = 0
    # Analysis fields (nullable before Stage 4)
    summary: Optional[str] = None
    stance: Optional[str] = None
    claim_count: int = 0


class AnswersResponse(BaseModel):
    """Sorted list of answers for a query."""

    query_id: uuid.UUID
    query_text: str
    answers: list[AnswerItem]
    total: int


# ── Error body ───────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard machine-readable error body."""

    error_code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error description")
    detail: Optional[object] = None

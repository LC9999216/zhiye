"""Pydantic schemas (DTOs).

Exports the primary internal data-transfer objects used throughout the
codebase.
"""

from __future__ import annotations

from app.schemas.api import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnswerItem,
    AnswersResponse,
    ErrorResponse,
    JobResponse,
    QueryResponse,
)
from app.schemas.zhihu import SearchItemDTO, SearchResponseDTO

__all__ = [
    "AnalyzeRequest",
    "AnalyzeResponse",
    "AnswerItem",
    "AnswersResponse",
    "ErrorResponse",
    "JobResponse",
    "QueryResponse",
    "SearchItemDTO",
    "SearchResponseDTO",
]

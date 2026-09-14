"""Pydantic schemas (DTOs).

Exports the primary internal data-transfer objects used throughout the
codebase.
"""

from __future__ import annotations

from app.schemas.ai import (
    AnalysisFailureDTO,
    ClaimExtractionDTO,
    MAX_CLAIMS_PER_ANSWER,
    RawClaimDTO,
    RawExtractionDTO,
    ValidatedClaimDTO,
)
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
    "AnalysisFailureDTO",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "AnswerItem",
    "AnswersResponse",
    "ClaimExtractionDTO",
    "ErrorResponse",
    "JobResponse",
    "MAX_CLAIMS_PER_ANSWER",
    "QueryResponse",
    "RawClaimDTO",
    "RawExtractionDTO",
    "SearchItemDTO",
    "SearchResponseDTO",
    "ValidatedClaimDTO",
]

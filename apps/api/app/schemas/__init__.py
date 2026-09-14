"""Pydantic schemas (DTOs).

Exports the primary internal data-transfer objects used throughout the
codebase.
"""

from __future__ import annotations

from app.schemas.zhihu import SearchItemDTO, SearchResponseDTO

__all__ = [
    "SearchItemDTO",
    "SearchResponseDTO",
]

"""Internal DTOs for Zhihu search results.

These Pydantic models are the canonical internal representation of a
Zhihu Open Platform search response.  Every field has been mapped from
the raw API JSON keys (Title, ContentID, …) to snake_case Python names
so that the rest of the codebase never depends on the API's casing.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class SearchItemDTO(BaseModel):
    """A single item from a Zhihu search result.

    Maps directly from the ``Data.Items[ ]`` entries returned by the
    Zhihu Open Platform search endpoint.
    """

    original_index: int = Field(
        description="0-based position of this item in the original API response"
    )
    title: str = Field(description="Item title (as returned by the API)")
    content_type: str = Field(
        description="Content type, e.g. ``Answer``, ``Article``, …"
    )
    content_id: str = Field(description="Unique content identifier from Zhihu")
    content_text: str = Field(
        description="Content snippet/summary, stripped of ``<em>`` tags"
    )
    url: str = Field(description="Zhihu URL pointing to the original content")
    voteup_count: int = Field(
        ge=0, description="Number of up-votes received by this content"
    )
    author_name: str = Field(default="", description="Display name of the author")
    edit_time: int = Field(
        default=0,
        description="Last edit time as a Unix-epoch timestamp (seconds)",
    )
    ranking_score: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Zhihu internal relevance score.  Real API responses can "
            "exceed 1.0 (observed up to ~1.9 in Stage-0 fixtures), so "
            "only non-negativity is enforced."
        ),
    )

    # ── validators ────────────────────────────────────────────────────

    @field_validator("url")
    @classmethod
    def _validate_url_is_zhihu_host(cls, v: str) -> str:
        """Accept only official HTTPS Zhihu hosts for parsed search items."""
        parsed = urlparse(v)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or host not in {"www.zhihu.com", "zhihu.com", "zhuanlan.zhihu.com"}
        ):
            msg = f"URL must use an official HTTPS zhihu.com host: {v!r}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _validate_answer_path(self) -> "SearchItemDTO":
        """Require an answer path before a result can be opened as an Answer."""
        if self.content_type.lower() == "answer":
            parsed = urlparse(self.url)
            if "/answer/" not in parsed.path:
                raise ValueError("Answer URL must contain an /answer/ path")
        return self

    @field_validator("voteup_count")
    @classmethod
    def _validate_voteup_non_negative(cls, v: int) -> int:
        """Reject negative vote counts (defensive)."""
        if v < 0:
            msg = f"voteup_count must be >= 0, got {v}"
            raise ValueError(msg)
        return v

    @field_validator("ranking_score")
    @classmethod
    def _validate_ranking_score_non_negative(cls, v: float) -> float:
        """Reject negative ranking scores (defensive).

        Upper bound is NOT enforced: real API responses can exceed 1.0
        (observed ~1.9 in Stage-0 fixtures).
        """
        if v < 0.0:
            msg = f"ranking_score must be >= 0, got {v}"
            raise ValueError(msg)
        return v


class SearchResponseDTO(BaseModel):
    """The fully-parsed result of a Zhihu search query.

    This is the top-level DTO returned by every ``search()`` call,
    regardless of the underlying provider (real or mock).
    """

    search_hash_id: str = Field(
        description="Unique hash id for this search result batch"
    )
    has_more: bool = Field(
        description="Whether the API indicates there are more results"
    )
    items: list[SearchItemDTO] = Field(
        default_factory=list, description="Result items in pipeline order"
    )

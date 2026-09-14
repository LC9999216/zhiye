"""Answer ORM model — a single Zhihu search result of type Answer.

Each Answer belongs to exactly one Query. The ``(query_id, content_id)``
pair is unique, so re-fetching the same query idempotently replaces the
answer set without creating duplicates.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.claim import Claim
    from app.models.query import Query


class Answer(TimestampMixin, Base):
    """A Zhihu search result of ``ContentType == "Answer"``.

    Columns
    -------
    query_id : uuid.UUID
        Foreign key to ``queries.id``.
    content_id : str
        Zhihu's unique content identifier for this answer.
    title : str
        Answer title (as returned by the API).
    author_name : str
        Display name of the author.
    content_text : str
        Content snippet/summary from the API (not guaranteed to be the full
        answer body). Already stripped of ``<em>`` highlight tags.
    voteup_count : int
        Number of up-votes this answer has received.
    url : str
        Permanent URL pointing to ``zhihu.com/answer/``.
    original_index : int
        0-based position in the original API response (before filtering).
    edit_time : int
        Unix-epoch timestamp of the last edit (seconds).
    ranking_score : float
        Zhihu internal relevance score in [0.0, 1.0].

    Analysis columns (populated in Stage 4):
        summary, stance, embedding, embedding_model, analysis_model,
        prompt_version, schema_version, analyzed_at, analysis_latency_ms.
    """

    __tablename__ = "answers"

    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    author_name: Mapped[str] = mapped_column(String(200), default="")
    content_text: Mapped[str] = mapped_column(Text, default="")
    voteup_count: Mapped[int] = mapped_column(Integer, default=0)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    original_index: Mapped[int] = mapped_column(Integer, nullable=False)
    edit_time: Mapped[int] = mapped_column(Integer, default=0)
    ranking_score: Mapped[float] = mapped_column(Float, default=0.0)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Stage-4 analysis columns (populated later; null before analysis).
    summary: Mapped[Optional[str]] = mapped_column(Text)
    stance: Mapped[Optional[str]] = mapped_column(String(20))
    analysis_model: Mapped[Optional[str]] = mapped_column(String(200))
    analysis_request_id: Mapped[Optional[str]] = mapped_column(String(200))
    analysis_usage_json: Mapped[Optional[str]] = mapped_column(Text)
    analysis_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    analysis_error_code: Mapped[Optional[str]] = mapped_column(String(50))
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50))
    schema_version: Mapped[Optional[str]] = mapped_column(String(50))
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    analysis_latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # pgvector embedding column (mapped as ARRAY[Float]; the DB column is
    # created via raw SQL in migration 0001_core).
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        ARRAY(Float), nullable=True
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(String(200))

    # ── relationships ────────────────────────────────────────────────
    query: Mapped[Query] = relationship("Query", back_populates="answers")
    claims: Mapped[list[Claim]] = relationship(
        "Claim", back_populates="answer", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("query_id", "content_id", name="uq_answer_per_query"),
    )

    def __repr__(self) -> str:
        return f"<Answer id={self.id} qid={self.query_id} cid={self.content_id!r}>"

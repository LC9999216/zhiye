"""Query ORM model — a normalized user question with search state.

``normalized_query`` is unique (NFKC casefold). A second submission of the
same logical question reuses the existing Query row and starts a fresh Job,
unless a job is already running.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.answer import Answer
    from app.models.job import Job


class Query(TimestampMixin, Base):
    """A natural-language question submitted for analysis.

    Columns
    -------
    query_text : str
        The original user-submitted question text.
    normalized_query : str
        NFKC-casefold-trim-collapsed form; unique across the table.
    search_hash_id : str | None
        Hash ID returned by the Zhihu search API for the latest fetch.
    status : str
        Current processing status: ``pending`` | ``completed`` | ``failed``.
    search_fetched_at : datetime | None
        When the latest search fetch was completed.
    """

    __tablename__ = "queries"

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True
    )
    search_hash_id: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    search_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # ── relationships ────────────────────────────────────────────────
    answers: Mapped[list[Answer]] = relationship(
        "Answer", back_populates="query", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(
        "Job", back_populates="query", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Query id={self.id} text={self.query_text!r}>"

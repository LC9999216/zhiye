"""Job ORM model — tracks background analysis jobs for query processing.

Each ``POST /api/queries/analyze`` creates a Job. The job status machine
progresses through: ``pending`` → ``fetching`` → ``analyzing`` →
``building`` → ``completed`` (or ``failed`` on error).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.query import Query


class Job(TimestampMixin, Base):
    """Background analysis job state for ``POST /api/queries/analyze``.

    Columns
    -------
    query_id : uuid.UUID
        Foreign key to ``queries.id``.
    status : str
        One of ``pending`` | ``fetching`` | ``analyzing`` | ``building`` |
        ``completed`` | ``failed``.
    current_step : str
        Human-readable description of the current processing step.
    error_code : str | None
        Machine-readable error code when status is ``failed``.
    error_message : str | None
        User-visible error description when status is ``failed``.
    started_at : datetime | None
        When processing actually began.
    finished_at : datetime | None
        When processing reached a terminal state (``completed`` or ``failed``).
    """

    __tablename__ = "jobs"

    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    current_step: Mapped[str] = mapped_column(String(200), default="")
    error_code: Mapped[Optional[str]] = mapped_column(String(50))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ── relationships ────────────────────────────────────────────────
    query: Mapped[Query] = relationship("Query", back_populates="jobs")

    def __repr__(self) -> str:
        return f"<Job id={self.id} qid={self.query_id} status={self.status!r}>"

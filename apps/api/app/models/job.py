"""Job model placeholder — the real schema lands in Stage 3."""

from __future__ import annotations

from app.db.base import Base
from app.models.base import TimestampMixin


class Job(TimestampMixin, Base):
    """Background analysis job state for ``POST /api/queries/analyze``.

    Stage 3 adds: ``query_id``, ``status``, ``current_step``,
    ``error_code``, ``error_message``, start/end timestamps, ...
    """

    __tablename__ = "jobs"

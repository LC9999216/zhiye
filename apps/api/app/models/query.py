"""Query model placeholder — the real schema lands in Stage 3."""

from __future__ import annotations

from app.db.base import Base
from app.models.base import TimestampMixin


class Query(TimestampMixin, Base):
    """A natural-language question submitted for analysis.

    Stage 3 adds: ``query_text``, ``normalized_query`` (unique),
    ``search_hash_id``, ``status``, ``search_fetched_at``, ...
    """

    __tablename__ = "queries"

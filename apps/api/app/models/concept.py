"""Concept model placeholder — the real schema lands in Stage 5."""

from __future__ import annotations

from app.db.base import Base
from app.models.base import TimestampMixin


class Concept(TimestampMixin, Base):
    """A query-scoped normalized concept referenced by Claims.

    Stage 5 adds: ``query_id``, ``canonical_name``, ``normalized_name``,
    ``aliases``, ``frequency``, ``embedding``, ...
    """

    __tablename__ = "concepts"

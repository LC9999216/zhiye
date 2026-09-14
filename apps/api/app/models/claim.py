"""Claim model placeholder — the real schema lands in Stage 4."""

from __future__ import annotations

from app.db.base import Base
from app.models.base import TimestampMixin


class Claim(TimestampMixin, Base):
    """A structured claim extracted from an Answer's ``ContentText``.

    Stage 4 adds: ``query_id``, ``answer_id``, ``text``, ``evidence_text``,
    ``position`` (1..5), ``confidence``, ``embedding``, ...
    """

    __tablename__ = "claims"

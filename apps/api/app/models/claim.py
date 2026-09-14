"""Claim ORM model — a structured claim extracted from an Answer.

Full implementation lands in Stage 4. For Stage 3 we create the table
structure so the migration is forward-compatible.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.answer import Answer


class Claim(TimestampMixin, Base):
    """A structured claim extracted from an Answer's ``ContentText``.

    Columns
    -------
    query_id : uuid.UUID
        Foreign key to ``queries.id`` (enables cascade delete by query).
    answer_id : uuid.UUID
        Foreign key to ``answers.id``.
    text : str
        Claim text extracted by the LLM.
    evidence_text : str
        Substring from the answer's ``content_text`` supporting this claim.
    position : int
        1-based position of this claim within the answer (1..5).
    confidence : float
        Model confidence in this claim (0.0 — 1.0).
    embedding : pgvector vector (added via raw SQL in migration).
    embedding_model : str | None
        Model identifier used to generate the embedding.
    """

    __tablename__ = "claims"

    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, default="")
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # pgvector embedding (mapped as ARRAY[Float]; the DB column is created
    # via raw SQL in migration 0001_core).
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        ARRAY(Float), nullable=True
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(String(200))
    # Raw concept names the LLM attached to this claim, as a JSON array
    # string (e.g. '["考研", "就业"]').  Graph building (Stage 5) reads
    # this to materialise ``concepts`` + ``claim_concepts`` rows.
    concepts_json: Mapped[Optional[str]] = mapped_column(Text)

    # ── relationships ────────────────────────────────────────────────
    answer: Mapped[Answer] = relationship("Answer", back_populates="claims")

    __table_args__ = (
        UniqueConstraint("query_id", "answer_id", "position", name="uq_claim_position"),
        CheckConstraint(
            "position >= 1 AND position <= 5",
            name="ck_claim_position_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<Claim id={self.id} aid={self.answer_id} pos={self.position}>"

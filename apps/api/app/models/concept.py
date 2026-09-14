"""Concept ORM model — a query-scoped normalized concept referenced by Claims.

Full implementation lands in Stage 5. For Stage 3 we create the table
structure so the migration is forward-compatible.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.claim import Claim


class Concept(TimestampMixin, Base):
    """A query-scoped normalized concept referenced by Claims.

    Columns
    -------
    query_id : uuid.UUID
        Foreign key to ``queries.id`` (enables cascade delete by query).
    canonical_name : str
        The preferred display form of this concept.
    normalized_name : str
        NFKC-casefold-trimmed form; unique per query.
    aliases : str | None
        Comma-separated alternative names for matching.
    frequency : int
        How many claims reference this concept (denormalised counter).
    embedding : pgvector vector (added via raw SQL in migration).
    embedding_model : str | None
        Model identifier used to generate the embedding.
    """

    __tablename__ = "concepts"

    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_name: Mapped[str] = mapped_column(String(200), default="")
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[Optional[str]] = mapped_column(Text)
    frequency: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(200))

    __table_args__ = (
        UniqueConstraint("query_id", "normalized_name", name="uq_concept_per_query"),
    )

    def __repr__(self) -> str:
        return f"<Concept id={self.id} qid={self.query_id} name={self.canonical_name!r}>"

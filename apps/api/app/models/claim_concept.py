"""Claim-Concept association table — maps claims to concepts within a query.

Full implementation lands in Stage 5. For Stage 3 we create the table
structure so the migration is forward-compatible.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin


class ClaimConcept(TimestampMixin, Base):
    """Associates a Claim with a Concept within the same Query.

    This is the authoritative table that produces ``REFERS_TO`` edges in
    the knowledge graph.
    """

    __tablename__ = "claim_concepts"

    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "query_id", "claim_id", "concept_id",
            name="uq_claim_concept",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ClaimConcept qid={self.query_id} "
            f"claim={self.claim_id} concept={self.concept_id}>"
        )

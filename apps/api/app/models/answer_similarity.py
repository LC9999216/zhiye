"""Answer-Similarity association table — links similar answers within a query.

Full implementation lands in Stage 5. For Stage 3 we create the table
structure so the migration is forward-compatible.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin


class AnswerSimilarity(TimestampMixin, Base):
    """A similarity edge between two Answers within the same Query.

    Only one row per pair is stored (source_id < target_id). The
    ``SIMILAR_TO`` graph edge is derived from this table.
    """

    __tablename__ = "answer_similarities"

    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(200))
    method_version: Mapped[Optional[str]] = mapped_column(String(50))

    __table_args__ = (
        UniqueConstraint(
            "query_id", "source_answer_id", "target_answer_id",
            name="uq_answer_similarity",
        ),
        CheckConstraint(
            "source_answer_id < target_answer_id",
            name="ck_similarity_ordered_pair",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AnswerSimilarity qid={self.query_id} "
            f"{self.source_answer_id} ~ {self.target_answer_id}>"
        )

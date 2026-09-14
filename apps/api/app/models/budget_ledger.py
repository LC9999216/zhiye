"""Persistent project-side model budget reservations and settlements."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.query import Query


class BudgetLedger(TimestampMixin, Base):
    """One durable reservation for a real analysis job."""

    __tablename__ = "budget_ledger"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reserved_cny: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    actual_cny: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    provider_usage_json: Mapped[Optional[str]] = mapped_column(Text)

    job: Mapped[Job] = relationship("Job")
    query: Mapped[Query] = relationship("Query")

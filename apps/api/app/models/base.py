"""Shared ORM base columns: ``id``, ``created_at``, ``updated_at`` (UTC)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds a UUID primary key and UTC created/updated timestamps.

    - ``id``: UUID primary key (client-side default, no DB round-trip).
    - ``created_at`` / ``updated_at``: timezone-aware timestamps set by the
      database (``now()``) and maintained on update via ``onupdate``.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

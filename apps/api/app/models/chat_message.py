"""Chat message model placeholder — the real schema lands in Stage 8."""

from __future__ import annotations

from app.db.base import Base
from app.models.base import TimestampMixin


class ChatMessage(TimestampMixin, Base):
    """A message in the query-scoped AI Q&A thread.

    Stage 8 adds: ``query_id``, role, content, citation JSON, timestamps, ...
    """

    __tablename__ = "chat_messages"

"""Answer model placeholder — the real schema lands in Stage 3."""

from __future__ import annotations

from app.db.base import Base
from app.models.base import TimestampMixin


class Answer(TimestampMixin, Base):
    """A Zhihu search result of ``ContentType == "Answer"``.

    Stage 3 adds: ``query_id``, ``content_id``, ``title``, ``author_name``,
    ``content_text``, ``voteup_count``, ``url``, ``original_index``,
    ``edit_time``, ``ranking_score``, ``fetched_at``, analysis columns, ...
    """

    __tablename__ = "answers"

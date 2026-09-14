"""Search result pipeline — normalise, filter, dedup, sort, truncate.

The :class:`SearchPipeline` class applies a fixed sequence of
transformations to a list of :class:`SearchItemDTO` instances, producing
the final result set that the rest of the API works with.

Pipeline order (do NOT change without updating the execution plan):
1. ``filter_answers``       — keep only items with ``content_type == "Answer"``
2. ``dedup_by_content_id``  — keep the first occurrence of each ``content_id``
3. ``sort_by_voteup``       — descending ``voteup_count`` (stable sort)
4. ``truncate``             — keep at most 10 items
5. ``clean_content_text``   — strip ``<em>`` / ``</em>`` from each item
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer
from app.schemas.zhihu import SearchItemDTO

if TYPE_CHECKING:
    from app.models.query import Query
    from app.services import _SearchProvider

# Regex matching <em>, </em>, and <em /> (self-closing) tags (case-insensitive).
_EM_TAG_PATTERN = re.compile(r"</?em\s*/?>", re.IGNORECASE)

# Default max items after truncation.
_MAX_RESULTS = 10


class SearchPipeline:
    """Stateless pipeline that transforms raw search items.

    Every method is a classmethod so the pipeline can be used directly
    without instantiation.
    """

    # ── normalisation ─────────────────────────────────────────────────

    @staticmethod
    def normalize_query(text: str) -> str:
        """Normalise a user query string.

        1. NFKC Unicode normalisation (compatibility decomposition).
        2. Strip leading/trailing whitespace.
        3. Collapse internal runs of whitespace into a single space.
        4. Casefold (locale-independent lowercasing for matching).
        """
        text = unicodedata.normalize("NFKC", text)
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        text = text.casefold()
        return text

    # ── content-type filter ───────────────────────────────────────────

    @staticmethod
    def filter_answers(
        items: list[SearchItemDTO],
    ) -> list[SearchItemDTO]:
        """Keep only items whose ``content_type`` equals ``"Answer"``.

        Comparison is case-insensitive.
        """
        return [it for it in items if it.content_type.lower() == "answer"]

    # ── deduplication ─────────────────────────────────────────────────

    @staticmethod
    def dedup_by_content_id(
        items: list[SearchItemDTO],
    ) -> list[SearchItemDTO]:
        """Remove duplicate ``content_id`` entries, keeping the first occurrence.

        The relative order of remaining items is preserved.
        """
        seen: set[str] = set()
        result: list[SearchItemDTO] = []
        for it in items:
            if it.content_id not in seen:
                seen.add(it.content_id)
                result.append(it)
        return result

    # ── sorting ───────────────────────────────────────────────────────

    @staticmethod
    def sort_by_voteup(
        items: list[SearchItemDTO],
    ) -> list[SearchItemDTO]:
        """Sort items by ``voteup_count`` descending.

        The sort is **stable**, so items with the same vote count keep
        their original relative order (which was the API return order).
        """
        return sorted(items, key=lambda it: it.voteup_count, reverse=True)

    # ── truncation ────────────────────────────────────────────────────

    @staticmethod
    def truncate(
        items: list[SearchItemDTO],
        max_count: int = _MAX_RESULTS,
    ) -> list[SearchItemDTO]:
        """Keep the first ``max_count`` items."""
        return items[:max_count]

    # ── content-text cleaning ─────────────────────────────────────────

    @staticmethod
    def clean_content_text(text: str) -> str:
        """Remove ``<em>`` and ``</em>`` tags and normalise whitespace."""
        cleaned = _EM_TAG_PATTERN.sub("", text)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @classmethod
    def clean_item_content_text(
        cls, item: SearchItemDTO
    ) -> SearchItemDTO:
        """Return a copy of *item* with ``content_text`` cleaned."""
        return item.model_copy(
            update={"content_text": cls.clean_content_text(item.content_text)}
        )

    # ── full pipeline ─────────────────────────────────────────────────

    @classmethod
    def execute_pipeline(
        cls, items: list[SearchItemDTO]
    ) -> list[SearchItemDTO]:
        """Run the full search-result pipeline and return the final list.

        Pipeline order
        --------------
        1. :meth:`filter_answers` — keep only Answer type.
        2. :meth:`dedup_by_content_id` — first occurrence wins.
        3. :meth:`sort_by_voteup` — descending (stable).
        4. :meth:`truncate` — at most 10 items.
        5. :meth:`clean_item_content_text` — strip ``<em>`` tags.

        Any change to this order must first update the execution plan
        and be approved by the user.
        """
        result = cls.filter_answers(items)
        result = cls.dedup_by_content_id(result)
        result = cls.sort_by_voteup(result)
        result = cls.truncate(result)
        result = [cls.clean_item_content_text(it) for it in result]
        return result

    # ── fetch + persist (job processor) ───────────────────────────────

    @classmethod
    async def fetch_and_store(
        cls,
        session: AsyncSession,
        query: Query,
        provider: _SearchProvider | None = None,
    ) -> list[SearchItemDTO]:
        """Search for *query* via the provider, run the pipeline, persist Answers.

        Idempotent per ``(query_id, content_id)``: re-fetching replaces the
        answer set without duplicates.  Returns the final filtered DTOs.
        """
        from app.services import get_search_provider

        owns_provider = provider is None
        provider = provider or get_search_provider()
        try:
            response = await provider.search(query.query_text, count=10)

            items = response.items if response.items is not None else []
            final = cls.execute_pipeline(items)

            # Persist (delete-then-insert keeps the set in sync with the API).
            existing = await session.execute(
                select(Answer.id).where(Answer.query_id == query.id)
            )
            for (aid,) in existing.all():
                await session.delete(await session.get(Answer, aid))
            await session.flush()

            for idx, item in enumerate(final):
                session.add(
                    Answer(
                        query_id=query.id,
                        content_id=item.content_id,
                        title=item.title or "",
                        author_name=item.author_name or "",
                        content_text=item.content_text or "",
                        voteup_count=item.voteup_count or 0,
                        url=item.url or "",
                        original_index=idx,
                        edit_time=item.edit_time or 0,
                        ranking_score=item.ranking_score or 0.0,
                    )
                )
            await session.flush()
            return final
        finally:
            if owns_provider:
                close = getattr(provider, "close", None)
                if close is not None:
                    await close()

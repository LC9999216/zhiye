"""Unit tests for :class:`SearchPipeline` — filter, dedup, sort, truncate, clean.

These tests are fully self-contained (no network, no database, no fixtures).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.zhihu import SearchItemDTO
from app.services.search_service import SearchPipeline


# ── helpers ────────────────────────────────────────────────────────────

def _item(
    content_type: str = "Answer",
    content_id: str = "id-001",
    voteup_count: int = 0,
    content_text: str = "some text",
    original_index: int = 0,
) -> SearchItemDTO:
    """Factory helper — creates a ``SearchItemDTO`` with sensible defaults."""
    return SearchItemDTO(
        original_index=original_index,
        title=f"Title {content_id}",
        content_type=content_type,
        content_id=content_id,
        content_text=content_text,
        url=f"https://www.zhihu.com/answer/{content_id}",
        voteup_count=voteup_count,
        author_name="Author",
        edit_time=1700000000,
        ranking_score=0.5,
    )


# ── filter_answers ─────────────────────────────────────────────────────

class TestFilterAnswers:
    """``SearchPipeline.filter_answers`` behaviour."""

    def test_filter_answers(self) -> None:
        """Mixed items → only Answer type remains."""
        items = [
            _item(content_type="Answer", content_id="a1"),
            _item(content_type="Article", content_id="a2"),
            _item(content_type="Answer", content_id="a3"),
            _item(content_type="Video", content_id="a4"),
        ]
        result = SearchPipeline.filter_answers(items)
        assert len(result) == 2
        assert all(it.content_type.lower() == "answer" for it in result)

    def test_filter_answers_empty(self) -> None:
        """No Answer items → empty list."""
        items = [
            _item(content_type="Article", content_id="a1"),
            _item(content_type="Video", content_id="a2"),
        ]
        result = SearchPipeline.filter_answers(items)
        assert result == []

    def test_filter_answers_case_insensitive(self) -> None:
        """Case-insensitive match for 'answer'."""
        items = [
            _item(content_type="ANSWER", content_id="a1"),
            _item(content_type="answer", content_id="a2"),
            _item(content_type="Answer", content_id="a3"),
        ]
        result = SearchPipeline.filter_answers(items)
        assert len(result) == 3


# ── dedup_by_content_id ────────────────────────────────────────────────

class TestDedupByContentId:
    """``SearchPipeline.dedup_by_content_id`` behaviour."""

    def test_dedup_by_content_id(self) -> None:
        """Duplicate ``content_id`` → only first occurrence kept."""
        items = [
            _item(content_id="dup-1", original_index=0),
            _item(content_id="unique", original_index=1),
            _item(content_id="dup-1", original_index=2),
            _item(content_id="dup-2", original_index=3),
            _item(content_id="dup-1", original_index=4),
        ]
        result = SearchPipeline.dedup_by_content_id(items)
        assert len(result) == 3
        # First "dup-1" (index 0) is kept.
        assert result[0].content_id == "dup-1"
        assert result[0].original_index == 0
        assert result[1].content_id == "unique"
        assert result[2].content_id == "dup-2"

    def test_dedup_all_unique(self) -> None:
        """All items unique → no change."""
        items = [
            _item(content_id="a"),
            _item(content_id="b"),
            _item(content_id="c"),
        ]
        result = SearchPipeline.dedup_by_content_id(items)
        assert len(result) == 3
        assert result == items

    def test_dedup_empty(self) -> None:
        """Empty list → empty list."""
        assert SearchPipeline.dedup_by_content_id([]) == []


# ── sort_by_voteup ─────────────────────────────────────────────────────

class TestSortByVoteup:
    """``SearchPipeline.sort_by_voteup`` behaviour."""

    def test_sort_by_voteup(self) -> None:
        """Mixed vote counts → descending order."""
        items = [
            _item(content_id="a", voteup_count=10),
            _item(content_id="b", voteup_count=5),
            _item(content_id="c", voteup_count=100),
            _item(content_id="d", voteup_count=0),
        ]
        result = SearchPipeline.sort_by_voteup(items)
        counts = [it.voteup_count for it in result]
        assert counts == [100, 10, 5, 0]

    def test_sort_by_voteup_stable_tie(self) -> None:
        """Same vote count → original order preserved (stable sort)."""
        items = [
            _item(content_id="a", voteup_count=50, original_index=0),
            _item(content_id="b", voteup_count=30, original_index=1),
            _item(content_id="c", voteup_count=50, original_index=2),
            _item(content_id="d", voteup_count=10, original_index=3),
            _item(content_id="e", voteup_count=30, original_index=4),
        ]
        result = SearchPipeline.sort_by_voteup(items)
        ids = [it.content_id for it in result]
        # After stable sort descending: 50 (a, c tie → a then c),
        # 30 (b, e tie → b then e), 10 (d).
        assert ids == ["a", "c", "b", "e", "d"]

    def test_sort_single_item(self) -> None:
        """Single item → unchanged."""
        items = [_item(content_id="a", voteup_count=42)]
        result = SearchPipeline.sort_by_voteup(items)
        assert len(result) == 1
        assert result[0].content_id == "a"


# ── truncate ───────────────────────────────────────────────────────────

class TestTruncate:
    """``SearchPipeline.truncate`` behaviour."""

    def test_truncate(self) -> None:
        """More than 10 items → 10 items kept."""
        items = [_item(content_id=f"id-{i}", original_index=i) for i in range(15)]
        result = SearchPipeline.truncate(items)
        assert len(result) == 10
        assert result[0].original_index == 0
        assert result[-1].original_index == 9

    def test_truncate_less_than_10(self) -> None:
        """Fewer than 10 items → unchanged."""
        items = [_item(content_id=f"id-{i}", original_index=i) for i in range(4)]
        result = SearchPipeline.truncate(items)
        assert len(result) == 4
        assert result == items

    def test_truncate_custom_max(self) -> None:
        """Custom ``max_count`` respected."""
        items = [_item(content_id=f"id-{i}", original_index=i) for i in range(10)]
        result = SearchPipeline.truncate(items, max_count=3)
        assert len(result) == 3

    def test_truncate_empty(self) -> None:
        """Empty list → empty list."""
        assert SearchPipeline.truncate([]) == []


# ── clean_content_text ─────────────────────────────────────────────────

class TestCleanContentText:
    """``SearchPipeline.clean_content_text`` behaviour."""

    def test_clean_content_text(self) -> None:
        """Removes ``<em>`` and ``</em>`` tags."""
        text = "考研还是<em>就业</em>，取决于你的目标"
        cleaned = SearchPipeline.clean_content_text(text)
        assert "<em>" not in cleaned
        assert "</em>" not in cleaned
        assert "就业" in cleaned

    def test_clean_content_text_no_tags(self) -> None:
        """No tags → unchanged."""
        text = "Hello World"
        assert SearchPipeline.clean_content_text(text) == "Hello World"

    def test_clean_content_text_multiple_tags(self) -> None:
        """Multiple ``<em>`` tags removed and whitespace collapsed."""
        text = "<em>计算机</em>专业考研还是<em>就业</em>"
        cleaned = SearchPipeline.clean_content_text(text)
        # Tags removed, whitespace collapsed: "计算机专业考研还是就业"
        assert cleaned == "计算机专业考研还是就业"

    def test_clean_content_text_empty_string(self) -> None:
        """Empty string → empty string."""
        assert SearchPipeline.clean_content_text("") == ""

    def test_clean_content_text_self_closing(self) -> None:
        """Self-closing ``<em/>`` tag removed (no space insertion)."""
        text = "text<em/>more text"
        cleaned = SearchPipeline.clean_content_text(text)
        assert "<em" not in cleaned
        assert "em" not in cleaned
        assert cleaned == "textmore text"


# ── normalize_query ────────────────────────────────────────────────────

class TestNormalizeQuery:
    """``SearchPipeline.normalize_query`` behaviour."""

    def test_normalize_query(self) -> None:
        """NFKC normalisation, strip, collapse, casefold."""
        raw = "  计算机\t专业\n\r考研   "
        result = SearchPipeline.normalize_query(raw)
        # NFKC normalises full-width chars etc; casefold lowers.
        assert result == "计算机 专业 考研"
        # No leading/trailing spaces, no tabs/newlines.
        assert " " not in (result[0], result[-1])

    def test_normalize_query_fullwidth(self) -> None:
        """Full-width characters get NFKC-normalised."""
        raw = "ＡＢＣ　ＤＥＦ"  # full-width letters and ideographic space
        result = SearchPipeline.normalize_query(raw)
        assert result == "abc def"  # casefold also applied

    def test_normalize_query_already_clean(self) -> None:
        """Already normalised → unchanged."""
        raw = "python web development"
        result = SearchPipeline.normalize_query(raw)
        assert result == raw

    def test_normalize_query_casefold(self) -> None:
        """Casefold lowercases."""
        raw = "Machine Learning"
        result = SearchPipeline.normalize_query(raw)
        assert result == "machine learning"

    def test_normalize_query_empty_string(self) -> None:
        """Empty string → empty string."""
        assert SearchPipeline.normalize_query("") == ""

    def test_normalize_query_whitespace_only(self) -> None:
        """Whitespace only → empty string."""
        assert SearchPipeline.normalize_query("   \t\n  ") == ""


# ── execute_pipeline ───────────────────────────────────────────────────

class TestExecutePipeline:
    """Full pipeline integration via ``SearchPipeline.execute_pipeline``."""

    def test_execute_pipeline(self) -> None:
        """Full pipeline integration: mixed input → filtered, deduped, sorted, truncated, cleaned."""
        items = [
            # Article (will be filtered out)
            _item(
                content_type="Article",
                content_id="art-1",
                voteup_count=999,
                original_index=0,
            ),
            # Answers with various vote counts (some duplicates)
            _item(
                content_type="Answer",
                content_id="a1",
                voteup_count=10,
                content_text="Some <em>text</em> here",
                original_index=1,
            ),
            _item(
                content_type="Answer",
                content_id="a2",
                voteup_count=100,
                content_text="Second answer",
                original_index=2,
            ),
            # Duplicate of a1 (should be removed)
            _item(
                content_type="Answer",
                content_id="a1",
                voteup_count=5,
                content_text="Duplicate",
                original_index=3,
            ),
            _item(
                content_type="Answer",
                content_id="a3",
                voteup_count=50,
                content_text="<em>Third</em> answer",
                original_index=4,
            ),
        ]

        result = SearchPipeline.execute_pipeline(items)

        # Only 3 unique Answer items: a2 (100), a3 (50), a1 (10) — sorted desc.
        assert len(result) == 3
        assert result[0].content_id == "a2"
        assert result[1].content_id == "a3"
        assert result[2].content_id == "a1"

        # Content text cleaned.
        assert "<em>" not in result[2].content_text
        assert "text" in result[2].content_text  # "Some text here"

    def test_execute_pipeline_no_answers(self) -> None:
        """No Answer items → empty result."""
        items = [
            _item(content_type="Article", content_id="a1"),
            _item(content_type="Video", content_id="a2"),
        ]
        assert SearchPipeline.execute_pipeline(items) == []

    def test_execute_pipeline_truncates(self) -> None:
        """More than 10 Answer items → truncated to 10."""
        items = [
            _item(content_type="Answer", content_id=f"a{i}", voteup_count=i)
            for i in range(20)
        ]
        result = SearchPipeline.execute_pipeline(items)
        assert len(result) == 10

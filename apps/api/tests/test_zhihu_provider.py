"""Tests for ``MockSearchProvider`` — error mapping, parsing, and edge cases.

These tests use local fixture files only; no network calls are made.
HTTP-level tests (connection timeout, retry, real secrets) are considered
manual / integration tests and are NOT included here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import (
    ZhihuAuthError,
    ZhihuDataContractError,
    ZhihuInternalError,
    ZhihuRateLimitError,
)
from app.schemas.zhihu import SearchItemDTO, SearchResponseDTO
from app.services.mock_search_provider import MockSearchProvider


# ── Fixture directory relative to this test file ───────────────────────

_FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]  # tests/ -> api/ -> apps/ -> zhiye/ (repo root)
    / "database" / "fixtures" / "zhihu_search"
).resolve()


@pytest.fixture
def provider() -> MockSearchProvider:
    """Return a ``MockSearchProvider`` pointing at the checked-in fixture dir."""
    return MockSearchProvider(fixture_dir=str(_FIXTURE_DIR))


# ── success case ───────────────────────────────────────────────────────

class TestSearchSuccess:
    """``MockSearchProvider.search`` returns correctly parsed data."""

    @pytest.mark.asyncio
    async def test_search_success(self, provider: MockSearchProvider) -> None:
        """Default fixture → parsed ``SearchResponseDTO`` with expected items."""
        result: SearchResponseDTO = await provider.search("test query")
        assert isinstance(result, SearchResponseDTO)
        assert result.search_hash_id == "mock-fixture-search-hash-001"
        assert result.has_more is False
        assert len(result.items) == 5  # all 5 items in the fixture

    @pytest.mark.asyncio
    async def test_search_success_item_fields(self, provider: MockSearchProvider) -> None:
        """Parsed items contain the expected field values."""
        result = await provider.search("test query")
        first = result.items[0]
        assert isinstance(first, SearchItemDTO)
        assert first.original_index == 0
        assert first.content_id == "mock-content-id-001"
        assert first.title == "计算机专业考研还是就业？一位过来人的建议 - 知乎"
        assert first.content_type == "Answer"
        assert first.voteup_count == 128
        assert first.author_name == "编程达人"
        assert first.edit_time == 1700000000
        assert first.ranking_score == 0.95
        assert "zhihu.com" in first.url

    @pytest.mark.asyncio
    async def test_search_empty_results(self, provider: MockSearchProvider) -> None:
        """Empty ``Items`` array → zero items, no error."""
        result = await provider.search("empty", fixture_name="mock_empty_results.json")
        assert len(result.items) == 0
        assert result.search_hash_id == "mock-empty-hash-002"


# ── error mapping ──────────────────────────────────────────────────────

class TestSearchErrorMapping:
    """Error codes are mapped to the correct exception types."""

    @pytest.mark.asyncio
    async def test_search_auth_error(self, provider: MockSearchProvider) -> None:
        """20001 → ``ZhihuAuthError`` (subclass of ``PermissionError``)."""
        with pytest.raises(ZhihuAuthError) as exc_info:
            await provider.search("test", fixture_name="mock_auth_error.json")
        assert "20001" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_rate_limit(self, provider: MockSearchProvider) -> None:
        """30001 → ``ZhihuRateLimitError``."""
        with pytest.raises(ZhihuRateLimitError) as exc_info:
            await provider.search("test", fixture_name="mock_rate_limit.json")
        assert "30001" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_internal_error_unknown_code(self, provider: MockSearchProvider) -> None:
        """Unknown error code → ``RuntimeError``."""
        fixture = _FIXTURE_DIR / "mock_unknown_error.json"
        if not fixture.exists():
            pytest.skip("fixture file not present")

        with pytest.raises(RuntimeError):
            await provider.search("test", fixture_name="mock_unknown_error.json")

    @pytest.mark.asyncio
    async def test_search_data_contract_missing_top_key(self, provider: MockSearchProvider) -> None:
        """Missing top-level ``Code`` key → ``ZhihuDataContractError``."""
        raw = {"Message": "no code"}
        with pytest.raises(ZhihuDataContractError):
            provider._parse_response(raw)


# ── validation / contract ──────────────────────────────────────────────

class TestValidation:
    """Item and contract validation edge cases."""

    def test_url_must_contain_zhihu(self) -> None:
        """URL without ``zhihu.com`` → ``ValidationError``."""
        with pytest.raises(Exception) as exc_info:
            SearchItemDTO(
                original_index=0,
                title="Test",
                content_type="Answer",
                content_id="x",
                content_text="text",
                url="https://example.com/answer/x",
                voteup_count=10,
            )
        # Pydantic v2 raises ValidationError (pydantic.ValidationError).
        assert "zhihu.com" in str(exc_info.value)

    def test_voteup_count_must_be_non_negative(self) -> None:
        """Negative ``voteup_count`` → ``ValidationError``."""
        with pytest.raises(Exception):
            SearchItemDTO(
                original_index=0,
                title="Test",
                content_type="Answer",
                content_id="x",
                content_text="text",
                url="https://www.zhihu.com/answer/x",
                voteup_count=-1,
            )

    def test_missing_required_item_keys(self, provider: MockSearchProvider) -> None:
        """Item missing a required key → discarded."""
        raw = {
            "Code": 0,
            "Message": "ok",
            "Data": {
                "HasMore": False,
                "SearchHashId": "hash",
                "Items": [
                    {
                        "Title": "Bad item",
                        # ContentID is missing
                        "ContentType": "Answer",
                        "ContentText": "text",
                        "Url": "https://www.zhihu.com/answer/x",
                        "VoteUpCount": 10,
                    }
                ],
            },
        }
        with pytest.raises(ZhihuDataContractError, match="All 1 item"):
            provider._parse_response(raw)

    def test_ranking_score_accepts_above_one(self) -> None:
        """Real API responses can have ``ranking_score`` > 1.0 (~1.9).

        This was observed in Stage-0 fixtures; the DTO must accept it.
        Negative values are still rejected.
        """
        dto = SearchItemDTO(
            original_index=0,
            title="Test",
            content_type="Answer",
            content_id="x",
            content_text="text",
            url="https://www.zhihu.com/answer/x",
            voteup_count=10,
            ranking_score=1.89,
        )
        assert dto.ranking_score == 1.89

        with pytest.raises(Exception):
            SearchItemDTO(
                original_index=0,
                title="Test",
                content_type="Answer",
                content_id="x",
                content_text="text",
                url="https://www.zhihu.com/answer/x",
                voteup_count=10,
                ranking_score=-0.5,
            )

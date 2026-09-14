"""Mock search provider for local development & testing.

When ``APP_MODE=mock`` (the default), ``get_search_provider()`` returns an
instance of this class instead of the real ``ZhihuSearchProvider``, so the
app can start and run without a valid Zhihu API secret or network access.

Fixture files live under ``database/fixtures/zhihu_search/`` and are plain
JSON that mirrors the Zhihu Open Platform response shape.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.exceptions import (
    ZhihuAuthError,
    ZhihuDataContractError,
    ZhihuInternalError,
    ZhihuRateLimitError,
)
from app.schemas.zhihu import SearchItemDTO, SearchResponseDTO

logger = logging.getLogger(__name__)

# Error-code → exception mapping (same as the real provider).
_ERROR_CODE_MAP: dict[int, type[Exception]] = {
    10001: ValueError,
    20001: ZhihuAuthError,
    30001: ZhihuRateLimitError,
    90001: ZhihuInternalError,
}

# Required top-level and data keys (mirrored from the real provider).
_REQUIRED_TOP_KEYS = ("Code", "Message", "Data")
_REQUIRED_DATA_KEYS = ("HasMore", "SearchHashId", "Items")
_REQUIRED_ITEM_KEYS = frozenset(
    {"ContentID", "ContentText", "Url", "VoteUpCount", "ContentType"}
)
_ITEM_FIELD_MAP: dict[str, str] = {
    "Title": "title",
    "ContentType": "content_type",
    "ContentID": "content_id",
    "ContentText": "content_text",
    "Url": "url",
    "VoteUpCount": "voteup_count",
    "AuthorName": "author_name",
    "EditTime": "edit_time",
    "RankingScore": "ranking_score",
}

_DEFAULT_FIXTURE = "mock_mixed_answers.json"


class MockSearchProvider:
    """Reads zhihu-style search responses from local fixture files.

    Parameters
    ----------
    fixture_dir:
        Path to the directory containing fixture JSON files.  If
        ``None``, defaults to ``database/fixtures/zhihu_search/``
        relative to the repository root (resolved by walking up from
        this file).
    """

    def __init__(self, fixture_dir: str | Path | None = None) -> None:
        if fixture_dir is None:
            # Walk up from ``app/services/`` to the repo root.
            here = Path(__file__).resolve().parent
            # app/services -> app -> api -> apps -> repo-root
            repo_root = here.parents[3]
            fixture_dir = repo_root / "database" / "fixtures" / "zhihu_search"

        self._fixture_dir = Path(fixture_dir)
        logger.info("MockSearchProvider fixture dir: %s", self._fixture_dir)

    # ── public API ────────────────────────────────────────────────────

    async def search(
        self,
        query_text: str,
        count: int = 10,
        fixture_name: str | None = None,
    ) -> SearchResponseDTO:
        """Load a fixture and return the parsed result.

        Parameters are accepted for signature compatibility with the real
        provider.  ``fixture_name`` overrides the default fixture file.
        """
        # Ignore query_text / count — the mock always returns the fixture.
        _ = query_text, count

        name = fixture_name or _DEFAULT_FIXTURE
        fixture_path = self._fixture_dir / name

        if not fixture_path.is_file():
            msg = f"Fixture file not found: {fixture_path}"
            raise FileNotFoundError(msg)

        raw: dict = json.loads(fixture_path.read_text(encoding="utf-8"))
        return self._parse_response(raw)

    async def close(self) -> None:
        """No-op for the mock provider."""

    # ── response parsing ──────────────────────────────────────────────

    def _parse_response(self, raw: dict) -> SearchResponseDTO:
        """Parse and validate a raw JSON dict (identical logic to the real provider)."""
        self._check_top_level_keys(raw)

        code = raw["Code"]
        if code != 0:
            self._raise_for_code(code, raw.get("Message", ""))

        data: dict = raw["Data"]
        self._check_data_keys(data)

        raw_items: list[dict] = data["Items"]
        parsed_items: list[SearchItemDTO] = []
        discarded = 0

        for idx, item in enumerate(raw_items):
            try:
                dto = self._parse_item(idx, item)
                parsed_items.append(dto)
            except (ValueError, KeyError):
                discarded += 1

        if not parsed_items and raw_items:
            msg = (
                f"All {len(raw_items)} item(s) failed validation; "
                f"{discarded} discarded"
            )
            raise ZhihuDataContractError(msg)

        logger.info(
            "Mock parsed %d item(s), discarded %d invalid item(s)",
            len(parsed_items),
            discarded,
        )

        return SearchResponseDTO(
            search_hash_id=data["SearchHashId"],
            has_more=data["HasMore"],
            items=parsed_items,
        )

    @staticmethod
    def _check_top_level_keys(raw: dict) -> None:
        missing = [k for k in _REQUIRED_TOP_KEYS if k not in raw]
        if missing:
            msg = (
                f"Top-level response missing required key(s): "
                f"{', '.join(missing)}"
            )
            raise ZhihuDataContractError(msg)

    @staticmethod
    def _check_data_keys(data: dict) -> None:
        missing = [k for k in _REQUIRED_DATA_KEYS if k not in data]
        if missing:
            msg = (
                f"Response Data missing required key(s): "
                f"{', '.join(missing)}"
            )
            raise ZhihuDataContractError(msg)

    @staticmethod
    def _raise_for_code(code: int, message: str) -> None:
        exc_type = _ERROR_CODE_MAP.get(code)
        if exc_type is None:
            msg = f"Unknown error code {code}: {message}"
            raise RuntimeError(msg)

        if code == 10001:
            raise ValueError(f"Parameter error (10001): {message}")
        if code == 20001:
            raise ZhihuAuthError(f"Auth error (20001): {message}")
        if code == 30001:
            raise ZhihuRateLimitError(f"Rate limit (30001): {message}")
        if code == 90001:
            raise ZhihuInternalError(f"Internal error (90001): {message}")

        msg = f"Error code {code}: {message}"
        raise RuntimeError(msg)

    def _parse_item(self, idx: int, item: dict) -> SearchItemDTO:
        missing = _REQUIRED_ITEM_KEYS - item.keys()
        if missing:
            msg = f"Item {idx} missing required key(s): {', '.join(sorted(missing))}"
            raise ValueError(msg)

        mapped: dict[str, object] = {"original_index": idx}
        for api_key, dto_field in _ITEM_FIELD_MAP.items():
            mapped[dto_field] = item.get(api_key)

        voteup = mapped.get("voteup_count")
        if voteup is None or not isinstance(voteup, int):
            msg = f"Item {idx}: VoteUpCount must be an int, got {type(voteup).__name__}"
            raise ValueError(msg)

        return SearchItemDTO(**mapped)

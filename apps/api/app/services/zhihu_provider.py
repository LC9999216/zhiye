"""Real HTTP-based Zhihu Open Platform search provider.

Uses ``httpx.AsyncClient`` to call the Zhihu search endpoint with Bearer
token authentication, a request timestamp header, and configurable
timeouts.  Concurrency is limited to **2** simultaneous requests so the
app never spikes the API quota in a single request burst.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping

import httpx

from app.core.exceptions import (
    ZhihuAuthError,
    ZhihuDataContractError,
    ZhihuInternalError,
    ZhihuRateLimitError,
)
from app.schemas.zhihu import SearchItemDTO, SearchResponseDTO

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

_CONTENT_TYPE = "application/json"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
_RETRY_COUNT = 1
_RETRY_BACKOFF_MS = 500
_MAX_CONCURRENT_REQUESTS = 2

# Endpoint URL is controlled by config — never user input.
# The domain suffix provides an additional safety check.
_EXPECTED_URL_DOMAIN = "developer.zhihu.com"

# Mapping of API error codes → Python exceptions.
# Codes not explicitly listed raise RuntimeError.
_ERROR_CODE_MAP: Mapping[int, type[Exception]] = {
    0: ValueError,  # success — not actually raised
    10001: ValueError,
    20001: ZhihuAuthError,
    30001: ZhihuRateLimitError,
    90001: ZhihuInternalError,
}

# Required top-level keys in the deserialised response.
_REQUIRED_TOP_KEYS = ("Code", "Message", "Data")

# Required keys inside ``Data``.
_REQUIRED_DATA_KEYS = ("HasMore", "SearchHashId", "Items")

# Required keys on each item dict (the config says ContentID, ContentText,
# Url, VoteUpCount, ContentType were originally listed — adding Title too
# for completeness since it's always expected, but the spec names those 5).
_REQUIRED_ITEM_KEYS = frozenset(
    {"ContentID", "ContentText", "Url", "VoteUpCount", "ContentType"}
)

# Keys from the API JSON → internal DTO field mapping.
_ITEM_FIELD_MAP: Mapping[str, str] = {
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


class ZhihuSearchProvider:
    """Real HTTP provider that talks to the Zhihu Open Platform search API.

    Parameters
    ----------
    access_secret:
        Bearer token used in the ``Authorization`` header.
    search_url:
        Full endpoint URL (must be ``https://developer.zhihu.com/…``).
    connect_timeout:
        Connection timeout in seconds.
    read_timeout:
        Read timeout in seconds.
    """

    def __init__(
        self,
        access_secret: str,
        search_url: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 20.0,
    ) -> None:
        self._access_secret = access_secret
        self._search_url = search_url
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

        # Validate the URL at construction time.
        self._validate_search_url(search_url)

        # Build a reusable client (connections are pooled).
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=self._connect_timeout,
                read=self._read_timeout,
                write=self._connect_timeout,
                pool=self._connect_timeout,
            ),
            limits=httpx.Limits(
                max_connections=_MAX_CONCURRENT_REQUESTS,
                max_keepalive_connections=_MAX_CONCURRENT_REQUESTS,
            ),
        )

    # ── public API ────────────────────────────────────────────────────

    async def search(
        self, query_text: str, count: int = 10
    ) -> SearchResponseDTO:
        """Execute a search and return a parsed result.

        Parameters
        ----------
        query_text:
            Normalised search query (1 – 200 characters).
        count:
            Number of results requested (passed as ``Count`` to the API).

        Raises
        ------
        ZhihuAuthError
            The access secret was rejected.
        ZhihuRateLimitError
            Rate / daily-quota limit hit.
        ZhihuInternalError
            Server-side API error.
        ZhihuDataContractError
            Response violated the expected data contract.
        ValueError
            Invalid parameters.
        RuntimeError
            An unexpected error code was returned.
        """
        async with self._semaphore:
            return await self._do_search(query_text, count)

    async def close(self) -> None:
        """Release the underlying HTTP client resources."""
        await self._client.aclose()

    # ── internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _validate_search_url(url: str) -> None:
        """Ensure the endpoint URL is a ``developer.zhihu.com`` URL."""
        if _EXPECTED_URL_DOMAIN not in url.lower():
            msg = (
                f"Search URL must contain '{_EXPECTED_URL_DOMAIN}', "
                f"got {url!r}"
            )
            raise ValueError(msg)

    async def _do_search(
        self, query_text: str, count: int
    ) -> SearchResponseDTO:
        """Perform the HTTP POST (with optional single retry)."""
        last_exc: Exception | None = None

        for attempt in range(_RETRY_COUNT + 1):
            try:
                return await self._perform_request(query_text, count)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                # Only retry on connection / read timeout or 5xx.
                http_exc = exc
                if attempt < _RETRY_COUNT and self._is_retryable(http_exc):
                    last_exc = http_exc
                    await asyncio.sleep(_RETRY_BACKOFF_MS / 1000)
                    continue
                # Not retryable or exhausted — re-raise original.
                raise
            except (ZhihuAuthError, ZhihuRateLimitError) as exc:
                # Never retry auth or rate-limit errors.
                raise exc

        # Should not be reached — either _perform_request returned or an
        # exception was re-raised.  Defensive fallback:
        raise RuntimeError("Search failed after retries") from last_exc

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Return ``True`` if the exception warrants a retry."""
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return 500 <= exc.response.status_code < 600
        return False

    async def _perform_request(
        self, query_text: str, count: int
    ) -> SearchResponseDTO:
        """Execute one HTTP POST and parse the response."""
        headers = self._build_headers()

        payload = {"Query": query_text, "Count": count}

        start_time = time.monotonic()
        try:
            response = await self._client.post(
                self._search_url,
                json=payload,
                headers=headers,
            )

            # Raise on HTTP-level errors (4xx, 5xx).
            response.raise_for_status()

            # Enforce a body-size limit.
            body = response.content
            if len(body) > _MAX_RESPONSE_BYTES:
                msg = (
                    f"Response body ({len(body)} bytes) exceeds "
                    f"{_MAX_RESPONSE_BYTES}-byte limit"
                )
                raise ZhihuDataContractError(msg)

            raw: dict = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Zhihu search HTTP error: status=%s",
                exc.response.status_code,
            )
            raise
        except httpx.TimeoutException:
            logger.warning("Zhihu search request timed out")
            raise
        except Exception as exc:
            # Catch JSON decode errors as data-contract violations.
            if not isinstance(exc, (httpx.HTTPStatusError, httpx.TimeoutException)):
                logger.warning(
                    "Zhihu search unexpected error: %s: %s",
                    type(exc).__name__,
                    exc,
                )
            raise
        finally:
            elapsed = time.monotonic() - start_time
            # Log duration but NOT the auth header or full response body.
            logger.info(
                "Zhihu search request took %.3fs for query=%r",
                elapsed,
                query_text,
            )

        return self._parse_response(raw)

    def _build_headers(self) -> dict[str, str]:
        """Build request headers.

        The ``Authorization`` header and ``access_secret`` are NEVER logged.
        """
        return {
            "Content-Type": _CONTENT_TYPE,
            "Authorization": f"Bearer {self._access_secret}",
            "X-Request-Timestamp": str(int(time.time())),
        }

    # ── response parsing ──────────────────────────────────────────────

    def _parse_response(self, raw: dict) -> SearchResponseDTO:
        """Parse and validate the raw JSON dictionary.

        Steps (in order):

        1. Check top-level required keys.
        2. Map the error code.
        3. Check ``Data`` sub-object required keys.
        4. Parse individual items, discarding invalid ones.
        5. If all items are invalid, raise ``ZhihuDataContractError``.
        """
        # 1. Top-level contract.
        self._check_top_level_keys(raw)

        # 2. Error mapping.
        code = raw["Code"]
        if code != 0:
            self._raise_for_code(code, raw.get("Message", ""))

        # 3. Data-level contract.
        data: dict = raw["Data"]
        self._check_data_keys(data)

        # 4. Parse items.
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
            # Every item was invalid — data contract error.
            msg = (
                f"All {len(raw_items)} item(s) failed validation; "
                f"{discarded} discarded"
            )
            raise ZhihuDataContractError(msg)

        logger.info(
            "Parsed %d item(s), discarded %d invalid item(s)",
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
        """Ensure the response dict contains ``Code``, ``Message``, ``Data``."""
        missing = [k for k in _REQUIRED_TOP_KEYS if k not in raw]
        if missing:
            msg = (
                f"Top-level response missing required key(s): "
                f"{', '.join(missing)}"
            )
            raise ZhihuDataContractError(msg)

    @staticmethod
    def _check_data_keys(data: dict) -> None:
        """Ensure the ``Data`` sub-object contains ``HasMore``, ``SearchHashId``, ``Items``."""
        missing = [k for k in _REQUIRED_DATA_KEYS if k not in data]
        if missing:
            msg = (
                f"Response Data missing required key(s): "
                f"{', '.join(missing)}"
            )
            raise ZhihuDataContractError(msg)

    @staticmethod
    def _raise_for_code(code: int, message: str) -> None:
        """Map a non-zero error code to the matching exception."""
        exc_type = _ERROR_CODE_MAP.get(code)
        if exc_type is None:
            msg = (
                f"Unknown error code {code}: {message}"
            )
            raise RuntimeError(msg)

        # Code 0 signals success — should not reach this branch for 0.
        if code == 10001:
            raise ValueError(f"Parameter error (10001): {message}")
        if code == 20001:
            raise ZhihuAuthError(f"Auth error (20001): {message}")
        if code == 30001:
            raise ZhihuRateLimitError(f"Rate limit (30001): {message}")
        if code == 90001:
            raise ZhihuInternalError(f"Internal error (90001): {message}")

        # Fallback (should not be reached).
        msg = f"Error code {code}: {message}"
        raise RuntimeError(msg)

    def _parse_item(self, idx: int, item: dict) -> SearchItemDTO:
        """Parse one raw item dict into a ``SearchItemDTO``.

        Raises ``ValueError`` or ``KeyError`` when a required field is
        missing so the caller can discard the item.
        """
        # Check required keys first.
        missing = _REQUIRED_ITEM_KEYS - item.keys()
        if missing:
            msg = f"Item {idx} missing required key(s): {', '.join(sorted(missing))}"
            raise ValueError(msg)

        # Map and validate.
        mapped: dict[str, object] = {"original_index": idx}
        for api_key, dto_field in _ITEM_FIELD_MAP.items():
            mapped[dto_field] = item.get(api_key)  # may be None

        # Ensure VoteUpCount is an int (API returns it as int).
        voteup = mapped.get("voteup_count")
        if voteup is None or not isinstance(voteup, int):
            msg = f"Item {idx}: VoteUpCount must be an int, got {type(voteup).__name__}"
            raise ValueError(msg)

        # Pydantic validation will run field validators for url format etc.
        return SearchItemDTO(**mapped)

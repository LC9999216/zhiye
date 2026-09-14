"""Business services — provider factory and service exports.

The factory :func:`get_search_provider` returns a concrete provider
instance based on the current application mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.exceptions import ZhihuAuthError
from app.services.embedding_provider import get_embedding_provider
from app.services.llm_provider import get_llm_provider

if TYPE_CHECKING:
    from app.schemas.zhihu import SearchItemDTO, SearchResponseDTO

    # Provider protocol — both real and mock providers implement this.
    class _SearchProvider:
        async def search(self, query_text: str, count: int = 10) -> SearchResponseDTO: ...
        async def close(self) -> None: ...


def get_search_provider() -> _SearchProvider:
    """Return a search provider configured for the current ``APP_MODE``.

    * ``mock`` (default) → :class:`app.services.mock_search_provider.MockSearchProvider`
    * ``production`` → :class:`app.services.zhihu_provider.ZhihuSearchProvider`

    The caller is responsible for calling ``.close()`` on the provider
    when it is no longer needed.
    """
    if settings.is_mock_mode:
        from app.services.mock_search_provider import MockSearchProvider

        return MockSearchProvider()

    from app.services.zhihu_provider import ZhihuSearchProvider

    if not settings.zhihu_access_secret:
        raise ZhihuAuthError("ZHIHU_ACCESS_SECRET is not configured")

    return ZhihuSearchProvider(
        access_secret=settings.zhihu_access_secret,
        search_url=settings.zhihu_search_url,
    )


__all__ = [
    "get_embedding_provider",
    "get_llm_provider",
    "get_search_provider",
]

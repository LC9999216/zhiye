"""Business services — provider factory and service exports.

The factory :func:`get_search_provider` returns a concrete provider
instance based on the current application mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings

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
        msg = (
            "ZHIHU_ACCESS_SECRET is empty — cannot use production provider. "
            "Set the secret or switch to APP_MODE=mock."
        )
        raise ValueError(msg)

    return ZhihuSearchProvider(
        access_secret=settings.zhihu_access_secret,
        search_url=settings.zhihu_search_url,
    )


__all__ = [
    "get_search_provider",
]

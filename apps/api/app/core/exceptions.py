"""Custom exceptions for the Zhibian API.

These are used by providers to signal well-known error conditions instead
of raising generic ``Exception`` or ``RuntimeError``.
"""

from __future__ import annotations


class ZhihuAuthError(PermissionError):
    """Authentication with the Zhihu Open Platform failed (error code 20001).

    Never retried; indicates a permanent configuration issue (bad secret,
    revoked token, …).
    """


class ZhihuRateLimitError(Exception):
    """Rate limit or daily quota exhausted (error code 30001).

    Never retried within the same request.
    """


class ZhihuInternalError(Exception):
    """The Zhihu Open Platform returned an internal error (error code 90001)."""


class ZhihuDataContractError(Exception):
    """A search response violated the expected data contract.

    Raised when:
    * The top-level response is missing required fields, **or**
    * Every individual item in the response is invalid.
    """

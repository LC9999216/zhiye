"""LLM provider isolation — business logic never binds to a single vendor SDK.

The :class:`LLMProvider` protocol defines the only interaction the
analysis pipeline has with the outside world: given a prompt string,
return the raw model text output.

Two implementations exist:

* :class:`MockLLMProvider` — used in ``APP_MODE=mock`` (default).  It
  returns deterministic, fixture-driven output so the whole pipeline is
  testable without network or real credentials.
* ``get_llm_provider()`` — factory that returns the provider for the
  current ``APP_MODE``.

The production implementation uses DeepSeek's official OpenAI-compatible
chat-completions endpoint behind the same protocol.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.exceptions import (
    ProviderAuthError,
    ProviderContractError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.services.prompts import ANALYSIS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # False means the provider response did not contain a trustworthy usage
    # object; callers must keep the budget reservation in that case.
    available: bool = True


@dataclass(frozen=True)
class LLMCompletionResult:
    text: str
    model: str
    request_id: str | None = None
    usage: ProviderUsage = ProviderUsage()

    @property
    def total_tokens(self) -> int:
        return self.usage.total_tokens


class LLMProvider(Protocol):
    """Callable protocol for an LLM that returns raw text for a prompt."""

    async def complete(self, prompt: str) -> str:
        """Return the model's raw text output for *prompt*."""
        ...


class MockLLMProvider:
    """Deterministic mock LLM that returns pre-baked JSON analysis.

    In mock mode the ``complete()`` method returns a canned JSON string
    from a fixture directory, keyed by the first line of the prompt
    (which embeds the answer's ``content_id``).  This makes the entire
    Stage 4 pipeline testable offline.

    If a key is not found, returns a well-formed "empty analysis" JSON so
    the pipeline degrades gracefully instead of raising.
    """

    model_name = "mock-llm-stage4-v1"

    def __init__(
        self,
        fixture_dir: str | Path | None = None,
    ) -> None:
        if fixture_dir is None:
            here = Path(__file__).resolve().parent
            repo_root = here.parents[3]
            fixture_dir = repo_root / "database" / "fixtures" / "ai_analysis"
        self._fixture_dir = Path(fixture_dir)
        self.last_result: LLMCompletionResult | None = None
        self.usage_records: list[dict[str, object]] = []

    async def complete(self, prompt: str) -> str:
        """Return deterministic JSON for the embedded content_id.

        The prompt embeds a marker line ``ANSWER_ID:<content_id>`` that
        keys the fixture lookup.
        """
        content_id = _extract_answer_id(prompt)
        fixture = self._fixture_dir / f"{content_id}.json"
        if fixture.is_file():
            text = fixture.read_text(encoding="utf-8")
        else:
            text = json.dumps(
                {"summary": "", "stance": "neutral", "claims": []},
                ensure_ascii=False,
            )
        self.last_result = LLMCompletionResult(text=text, model=self.model_name)
        return text


def _extract_answer_id(prompt: str) -> str:
    """Pull the ``ANSWER_ID:xxx`` marker out of a prompt (fallback: default)."""
    for line in prompt.splitlines():
        line = line.strip()
        if line.startswith("ANSWER_ID:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


class DeepSeekLLMProvider:
    """Official DeepSeek Chat Completions provider with JSON mode."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "deepseek-flash",
        timeout_seconds: float = 45.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderAuthError("DeepSeek API key is not configured")
        parsed_base_url = urlparse(base_url)
        if parsed_base_url.scheme != "https" or parsed_base_url.hostname != "api.deepseek.com":
            raise ValueError("DeepSeek base URL must use api.deepseek.com")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.last_result: LLMCompletionResult | None = None
        self.usage_records: list[dict[str, object]] = []
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def complete(self, prompt: str) -> str:
        result = await self.complete_with_metadata(prompt)
        return result.text

    async def complete_with_metadata(self, prompt: str) -> LLMCompletionResult:
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": ANALYSIS_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "stream": False,
        }
        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("DeepSeek request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("DeepSeek transport failed") from exc
        _raise_provider_http_error(response, "DeepSeek")
        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise KeyError("choices[0].message.content")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderContractError("DeepSeek response has no usable text") from exc
        usage = _usage_from_body(body)
        result = LLMCompletionResult(
            text=text,
            model=str(body.get("model") or self.model_name),
            request_id=body.get("id"),
            usage=usage,
        )
        self.last_result = result
        self.usage_records.append(
            {
                "model": result.model,
                "request_id": result.request_id,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "usage_available": usage.available,
            }
        )
        return result

    async def aclose(self) -> None:
        await self._client.aclose()


def _usage_from_body(body: dict) -> ProviderUsage:
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return ProviderUsage(available=False)
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    valid = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in (prompt, completion, total)
    )
    if not valid or total < prompt + completion:
        return ProviderUsage(available=False)
    return ProviderUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        available=True,
    )


def _raise_provider_http_error(response: httpx.Response, provider: str) -> None:
    if response.status_code in (401, 403):
        raise ProviderAuthError(f"{provider} authentication failed")
    if response.status_code == 429:
        raise ProviderRateLimitError(f"{provider} rate limit or quota reached")
    if response.status_code >= 500:
        raise ProviderUnavailableError(f"{provider} service unavailable")
    if response.status_code >= 400:
        raise ProviderContractError(f"{provider} rejected the request")


def get_llm_provider() -> LLMProvider:
    """Return an LLM provider configured for the current ``APP_MODE``.

    * ``mock`` (default) → :class:`MockLLMProvider`
    * ``production`` → the official DeepSeek HTTP provider; missing keys fail
      explicitly instead of silently falling back to mock output.
    """
    if settings.is_mock_mode:
        return MockLLMProvider()

    return DeepSeekLLMProvider(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


__all__ = [
    "DeepSeekLLMProvider",
    "LLMCompletionResult",
    "LLMProvider",
    "MockLLMProvider",
    "ProviderUsage",
    "get_llm_provider",
]

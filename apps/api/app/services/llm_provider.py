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

Real providers (OpenAI-compatible chat completions) can be added later
behind the same protocol without touching business logic.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        fixture_dir: str | Path | None = None,
    ) -> None:
        if fixture_dir is None:
            here = Path(__file__).resolve().parent
            repo_root = here.parents[3]
            fixture_dir = repo_root / "database" / "fixtures" / "ai_analysis"
        self._fixture_dir = Path(fixture_dir)

    async def complete(self, prompt: str) -> str:
        """Return deterministic JSON for the embedded content_id.

        The prompt embeds a marker line ``ANSWER_ID:<content_id>`` that
        keys the fixture lookup.
        """
        content_id = _extract_answer_id(prompt)
        fixture = self._fixture_dir / f"{content_id}.json"
        if fixture.is_file():
            return fixture.read_text(encoding="utf-8")
        # Default: valid empty analysis (0 claims, neutral stance).
        return json.dumps(
            {"summary": "", "stance": "neutral", "claims": []},
            ensure_ascii=False,
        )


def _extract_answer_id(prompt: str) -> str:
    """Pull the ``ANSWER_ID:xxx`` marker out of a prompt (fallback: default)."""
    for line in prompt.splitlines():
        line = line.strip()
        if line.startswith("ANSWER_ID:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def get_llm_provider() -> LLMProvider:
    """Return an LLM provider configured for the current ``APP_MODE``.

    * ``mock`` (default) → :class:`MockLLMProvider`
    * ``production`` → raises unless a real provider is configured
      (not implemented yet; the analysis pipeline is mock-first).
    """
    if settings.is_mock_mode:
        return MockLLMProvider()

    msg = (
        "Real LLM provider not implemented yet — Stage 4 uses "
        "APP_MODE=mock with deterministic fixtures."
    )
    raise NotImplementedError(msg)


__all__ = ["LLMProvider", "MockLLMProvider", "get_llm_provider"]

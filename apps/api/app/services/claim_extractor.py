"""Claim extraction from raw LLM output (Stage 4 core).

Pipeline for one Answer:

1. Build the prompt from the answer's ``content_id`` + ``content_text``.
2. Call the LLM provider (up to ``MAX_RETRIES + 1`` attempts).
3. Parse the raw text as JSON — tolerating markdown code fences.
4. Validate against :class:`RawExtractionDTO` (structural only).
5. Cap claims at 5 (hard ceiling).
6. For each claim, verify ``evidence_text`` is a *normalised substring*
   of the ContentText; drop claims that fail the check.
7. Return a validated :class:`ClaimExtractionDTO`.

Any failure that persists after retries raises a typed error so the
caller can record ``AnalysisFailureDTO`` per-answer without blocking the
other answers.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.core.logging import get_logger
from app.schemas.ai import (
    ClaimExtractionDTO,
    MAX_CLAIMS_PER_ANSWER,
    RawClaimDTO,
    RawExtractionDTO,
    ValidatedClaimDTO,
)
from app.services.prompts import build_analysis_prompt
from app.services.search_service import SearchPipeline

if TYPE_CHECKING:
    from app.services.llm_provider import LLMProvider

logger = get_logger(__name__)

# Number of retries after the first failed attempt (total attempts = 3).
MAX_RETRIES = 2

# Tolerated wrapper: ```json ... ``` or ``` ... ```.
_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class ClaimExtractionError(Exception):
    """Raised when an answer cannot be analysed after all retries.

    Attributes
    ----------
    attempts : int
        Number of LLM attempts made before giving up.
    """

    def __init__(self, message: str, *, attempts: int) -> None:
        super().__init__(message)
        self.attempts = attempts


def extract_json_object(raw: str) -> dict:
    """Parse *raw* as JSON, tolerating common LLM output noise.

    Handles, in order:
    1. Markdown code fences (```json ... ```).
    2. Leading prose / trailing commentary: locates the outermost
       ``{ ... }`` span and parses only that substring.

    Raises :class:`json.JSONDecodeError` when no valid JSON object can
    be found.
    """
    text = raw.strip()
    fence = _FENCE_PATTERN.match(text)
    if fence:
        text = fence.group(1).strip()
    if not text:
        msg = "Model returned empty output"
        raise json.JSONDecodeError(msg, raw, 0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back: extract the outermost {...} object span.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            msg = "No JSON object found in model output"
            raise json.JSONDecodeError(msg, raw, 0) from None
        obj_text = text[start : end + 1]
        return json.loads(obj_text)


def normalize_evidence(text: str) -> str:
    """Normalise an evidence fragment: strip tags, collapse whitespace.

    Applies NFKC first (converts full-width spaces and compatibility
    characters), strips ``<em>`` tags, then collapses all whitespace runs
    into a single space.  Uses the same cleaner as the search pipeline so
    evidence extracted from a cleaned ContentText can be matched.
    """
    import unicodedata

    text = unicodedata.normalize("NFKC", text)
    return SearchPipeline.clean_content_text(text)


def evidence_is_substring(evidence: str, content_text: str) -> bool:
    """True when *evidence* (normalised) is a substring of *content_text* (normalised).

    Both sides are normalised by :func:`normalize_evidence` (strip
    highlight tags + collapse whitespace) before matching, per the
    execution plan's "空白和高亮标签规范化" rule.
    """
    norm_evidence = normalize_evidence(evidence)
    if not norm_evidence:
        return False
    return norm_evidence in normalize_evidence(content_text)


def validate_and_cap(raw: RawExtractionDTO, content_text: str) -> ClaimExtractionDTO:
    """Validate claims from raw model output against the ContentText.

    Steps
    -----
    1. Cap the claim list at 5.
    2. Drop claims whose evidence is not a normalised substring.
    3. Re-assign 1-based positions for the surviving claims.
    """
    kept: list[ValidatedClaimDTO] = []
    for idx, claim in enumerate(raw.claims[:MAX_CLAIMS_PER_ANSWER], start=1):
        if not evidence_is_substring(claim.evidence_text, content_text):
            logger.debug(
                "Dropping claim %d: evidence not found in ContentText", idx
            )
            continue
        kept.append(
            ValidatedClaimDTO(
                text=claim.text.strip(),
                evidence_text=claim.evidence_text.strip(),
                confidence=claim.confidence,
                concepts=claim.concepts,
                position=idx,
            )
        )

    return ClaimExtractionDTO(
        summary=raw.summary.strip(),
        stance=raw.stance,
        claims=kept,
    )


async def extract_claims(
    provider: LLMProvider,
    content_id: str,
    content_text: str,
    *,
    max_retries: int = MAX_RETRIES,
) -> ClaimExtractionDTO:
    """Analyse one answer and return a validated extraction.

    Raises
    ------
    ClaimExtractionError
        When the model output cannot be parsed/validated after all
        retries (dirty JSON, invalid schema, etc.).
    """
    prompt = build_analysis_prompt(content_id, content_text)

    last_error: Exception | None = None
    attempts = 0
    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        try:
            raw_text = await provider.complete(prompt)
            raw_dict = extract_json_object(raw_text)
            raw = RawExtractionDTO.model_validate(raw_dict)
            return validate_and_cap(raw, content_text)
        except (
            json.JSONDecodeError,
            ValidationError,
            TypeError,
            ValueError,
            TimeoutError,
            OSError,
        ) as exc:
            last_error = exc
            logger.warning(
                "Analysis attempt %d failed for answer %s: %s",
                attempt + 1,
                content_id,
                type(exc).__name__,
            )
            if attempt < max_retries:
                continue
            break

    assert last_error is not None  # loop always runs at least once
    msg = (
        f"Answer {content_id} failed analysis after {attempts} attempts: "
        f"{type(last_error).__name__}: {last_error}"
    )
    raise ClaimExtractionError(msg, attempts=attempts) from last_error


__all__ = [
    "ClaimExtractionError",
    "MAX_RETRIES",
    "evidence_is_substring",
    "extract_claims",
    "extract_json_object",
    "normalize_evidence",
    "validate_and_cap",
]

"""Stage 4 tests — claim extraction pipeline (no DB, no network).

Covers the unit-testable core:
- JSON parsing (tolerating markdown fences, rejecting dirty JSON)
- Schema validation (stance enum, claim fields)
- Claim capping at 5
- Evidence-substring validation
- Retry logic (dirty JSON → retry → success; persistent failure)
- Empty-array / empty-analysis handling
- LLM timeout / provider exceptions surface as failures
"""

from __future__ import annotations

import json

import pytest

from app.core.exceptions import ProviderAuthError
from app.schemas.ai import (
    ClaimExtractionDTO,
    MAX_CLAIMS_PER_ANSWER,
    RawClaimDTO,
    RawExtractionDTO,
    ValidatedClaimDTO,
)
from app.services.claim_extractor import (
    ClaimExtractionError,
    evidence_is_substring,
    extract_claims,
    extract_json_object,
    normalize_evidence,
    validate_and_cap,
)
from app.services.prompts import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    build_analysis_prompt,
)

# ── helpers ────────────────────────────────────────────────────────────

CONTENT = (
    "计算机专业考研需要长期投入但回报稳定，"
    "就业则看重实际项目经验。"
    "我个人认为考研能系统化理论基础，而工作能快速积累实践。"
)


class FakeProvider:
    """Scriptable LLM provider for tests."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        if not self._responses:
            msg = "No more responses configured"
            raise AssertionError(msg)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _raw_dto(
    *,
    summary: str = "考研 vs 就业",
    stance: str = "conditional",
    claims: list[dict] | None = None,
) -> RawExtractionDTO:
    default_claims = [
        {
            "text": "考研能系统化理论基础",
            "evidence_text": "考研能系统化理论基础",
            "confidence": 0.9,
            "concepts": ["考研"],
        },
        {
            "text": "就业能快速积累实践",
            "evidence_text": "就业则看重实际项目经验",
            "confidence": 0.8,
            "concepts": ["就业"],
        },
    ]
    return RawExtractionDTO(
        summary=summary,
        stance=stance,
        claims=claims if claims is not None else default_claims,
    )


def _claim(text: str, evidence: str, **kwargs) -> dict:
    return {
        "text": text,
        "evidence_text": evidence,
        "confidence": kwargs.get("confidence", 0.5),
        "concepts": kwargs.get("concepts", []),
    }


# ── JSON parsing ───────────────────────────────────────────────────────

class TestExtractJsonObject:
    def test_plain_json(self) -> None:
        raw = '{"summary":"s","stance":"neutral","claims":[]}'
        assert extract_json_object(raw)["stance"] == "neutral"

    def test_markdown_fence_json(self) -> None:
        raw = '```json\n{"summary":"s","stance":"support","claims":[]}\n```'
        assert extract_json_object(raw)["stance"] == "support"

    def test_bare_fence_json(self) -> None:
        raw = '```\n{"summary":"s","stance":"oppose","claims":[]}\n```'
        assert extract_json_object(raw)["stance"] == "oppose"

    def test_dirty_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            extract_json_object('{"summary": "unclosed')

    def test_empty_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            extract_json_object("   ")


# ── Schema validation ──────────────────────────────────────────────────

class TestRawExtractionSchema:
    def test_valid_stance_accepted(self) -> None:
        for stance in ("support", "oppose", "conditional", "neutral"):
            _raw_dto(stance=stance)

    def test_invalid_stance_rejected(self) -> None:
        with pytest.raises(ValueError):
            _raw_dto(stance="maybe")

    def test_claim_requires_evidence(self) -> None:
        with pytest.raises(ValueError):
            RawClaimDTO(text="x")  # missing evidence_text

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValueError):
            _raw_dto(claims=[_claim("t", "e", confidence=1.5)])


# ── Capping ────────────────────────────────────────────────────────────

class TestCapClaims:
    def test_never_exceeds_five(self) -> None:
        raw = _raw_dto(
            claims=[
                _claim(f"c{i}", f"证据{i}", concepts=["c"])
                for i in range(8)
            ]
        )
        result = validate_and_cap(raw, "证据0 证据1 证据2 证据3 证据4 证据5 证据6 证据7")
        assert len(result.claims) <= MAX_CLAIMS_PER_ANSWER

    def test_positions_are_1_based(self) -> None:
        raw = _raw_dto(claims=[_claim("c1", "证据1"), _claim("c2", "证据2")])
        result = validate_and_cap(raw, "证据1 证据2")
        assert [c.position for c in result.claims] == [1, 2]

    def test_claim_extraction_dto_caps_too(self) -> None:
        """The DTO itself enforces the ceiling (defence in depth)."""
        dto = ClaimExtractionDTO(
            summary="s",
            stance="neutral",
            claims=[
                ValidatedClaimDTO(
                    text=f"c{i}",
                    evidence_text="e",
                    confidence=0.5,
                    concepts=[],
                    position=(i % 5) + 1,
                )
                for i in range(6)
            ],
        )
        assert len(dto.claims) == MAX_CLAIMS_PER_ANSWER

    def test_validated_claim_rejects_position_zero(self) -> None:
        """position=0 is rejected by the DTO (mirrors DB check constraint)."""
        with pytest.raises(ValueError):
            ValidatedClaimDTO(
                text="c", evidence_text="e", confidence=0.5,
                concepts=[], position=0,
            )

    def test_validated_claim_rejects_position_six(self) -> None:
        """position=6 is rejected by the DTO (mirrors DB check constraint)."""
        with pytest.raises(ValueError):
            ValidatedClaimDTO(
                text="c", evidence_text="e", confidence=0.5,
                concepts=[], position=6,
            )


# ── Evidence substring validation ──────────────────────────────────────

class TestEvidenceValidation:
    def test_exact_substring_ok(self) -> None:
        assert evidence_is_substring("考研能系统化理论基础", CONTENT)

    def test_with_highlight_tags_normalised(self) -> None:
        content = "观点<em>强调</em>重点内容"
        assert evidence_is_substring("观点强调重点内容", content)

    def test_not_substring_rejected(self) -> None:
        assert not evidence_is_substring("完全无关的内容", CONTENT)

    def test_empty_evidence_rejected(self) -> None:
        assert not evidence_is_substring("   ", CONTENT)

    def test_drops_claim_without_evidence(self) -> None:
        raw = _raw_dto(
            claims=[
                _claim("valid", "考研能系统化理论基础"),
                _claim("invalid", "这不是证据"),
            ]
        )
        result = validate_and_cap(raw, CONTENT)
        assert len(result.claims) == 1
        assert result.claims[0].text == "valid"

    def test_normalize_evidence_collapses_whitespace(self) -> None:
        # Multiple whitespace runs (incl. full-width) collapse to one space.
        # Input: "  多  个  空白 " → NFKC → collapse → "多 个 空白"
        assert normalize_evidence("  多  个  空白 ") == "多 个 空白"


# ── Retry logic ────────────────────────────────────────────────────────

class TestRetry:
    async def test_dirty_then_success_retries(self) -> None:
        provider = FakeProvider(
            [
                '{"summary": "unclosed',
                json.dumps(
                    _raw_dto(
                        claims=[_claim("ok", "考研能系统化理论基础")]
                    ).model_dump()
                ),
            ]
        )
        result = await extract_claims(provider, "a1", CONTENT)
        assert len(provider.calls) == 2  # retried once
        assert result.claims[0].text == "ok"

    async def test_invalid_schema_retries(self) -> None:
        provider = FakeProvider(
            [
                json.dumps({"summary": "s", "stance": "bogus", "claims": []}),
                json.dumps(_raw_dto().model_dump()),
            ]
        )
        result = await extract_claims(provider, "a2", CONTENT)
        assert len(provider.calls) == 2
        assert result.stance == "conditional"

    async def test_persistent_failure_raises_with_attempts(self) -> None:
        provider = FakeProvider(["bad json", "still bad", "worse"])
        with pytest.raises(ClaimExtractionError) as exc_info:
            await extract_claims(provider, "a3", CONTENT)
        assert exc_info.value.attempts == 3
        assert len(provider.calls) == 3

    async def test_provider_timeout_is_not_retried(self) -> None:
        provider = FakeProvider(
            [TimeoutError("LLM timed out")] * 3
        )
        with pytest.raises(TimeoutError):
            await extract_claims(provider, "a4", CONTENT)
        assert len(provider.calls) == 1

    async def test_provider_auth_is_not_retried(self) -> None:
        provider = FakeProvider([ProviderAuthError("bad key")])
        with pytest.raises(ProviderAuthError):
            await extract_claims(provider, "a-auth", CONTENT)
        assert len(provider.calls) == 1

    async def test_empty_array_output(self) -> None:
        provider = FakeProvider(
            [json.dumps({"summary": "s", "stance": "neutral", "claims": []})]
        )
        result = await extract_claims(provider, "a5", CONTENT)
        assert result.claims == []
        assert result.stance == "neutral"


# ── Prompt building ────────────────────────────────────────────────────

class TestPrompt:
    def test_prompt_contains_content_and_marker(self) -> None:
        prompt = build_analysis_prompt("cid-1", CONTENT)
        assert "ANSWER_ID:cid-1" in prompt
        assert "考研能系统化理论基础" in prompt

    def test_versions_are_defined(self) -> None:
        assert PROMPT_VERSION
        assert SCHEMA_VERSION

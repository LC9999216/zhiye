"""AI extraction DTOs (Stage 4).

These Pydantic models define the *validated* structured output of the
LLM analysis step.  They mirror the 6.2 AI extraction contract from the
execution plan:

    {
      "summary": "string",
      "stance": "support|oppose|conditional|neutral",
      "claims": [
        {
          "text": "string",
          "evidence_text": "must be a substring of the current ContentText",
          "confidence": 0.0,
          "concepts": ["string"]
        }
      ]
    }

Hard constraints (enforced in code, not just by the schema):
- ``claims`` length <= 5
- ``evidence_text`` must be a (normalised) substring of the ContentText

Two schemas are provided:
- :class:`RawExtractionDTO` — the *unvalidated* model used to parse the
  LLM's raw JSON output (only structural validation).
- :class:`ClaimExtractionDTO` — the *validated* model returned after
  claim truncation and evidence-substring checks.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Stance is a fixed 4-value enum from the execution plan.
StanceValue = Literal["support", "oppose", "conditional", "neutral"]

# Maximum number of claims a single answer may produce.
MAX_CLAIMS_PER_ANSWER = 5


class RawClaimDTO(BaseModel):
    """A claim exactly as returned by the LLM (before validation)."""

    text: str = Field(description="Claim text extracted by the model")
    evidence_text: str = Field(
        description="Substring of the ContentText supporting this claim"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in this claim (0.0–1.0)",
    )
    concepts: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Concept names referenced by this claim",
    )


class RawExtractionDTO(BaseModel):
    """Top-level model as produced by the LLM (raw JSON → this model)."""

    summary: str = Field(
        default="", description="Concise summary of the answer's viewpoint"
    )
    stance: StanceValue = Field(description="Overall stance of the answer")
    claims: list[RawClaimDTO] = Field(
        default_factory=list,
        description="0 to 5 structured claims with evidence",
    )


class ValidatedClaimDTO(BaseModel):
    """A claim that passed validation (evidence found in ContentText)."""

    text: str
    evidence_text: str
    confidence: float = 0.0
    concepts: list[str] = Field(default_factory=list)
    position: int = Field(
        ge=1,
        le=MAX_CLAIMS_PER_ANSWER,
        description="1-based position of this claim (1..5)",
    )


class ClaimExtractionDTO(BaseModel):
    """Final, validated analysis result for a single Answer.

    Guarantees:
    - ``len(claims) <= 5``
    - every ``evidence_text`` is a normalised substring of ContentText
    - ``stance`` is one of support|oppose|conditional|neutral
    """

    summary: str = ""
    stance: StanceValue = "neutral"
    claims: list[ValidatedClaimDTO] = Field(default_factory=list)

    @field_validator("claims")
    @classmethod
    def _cap_claims_at_five(cls, v: list[ValidatedClaimDTO]) -> list[ValidatedClaimDTO]:
        """Enforce the hard ceiling of 5 claims per answer."""
        if len(v) > MAX_CLAIMS_PER_ANSWER:
            return v[:MAX_CLAIMS_PER_ANSWER]
        return v


class AnalysisFailureDTO(BaseModel):
    """Records why a single Answer could not be analysed."""

    error_code: str = Field(description="Machine-readable failure code")
    message: str = Field(description="Human-readable failure description")
    attempts: int = Field(ge=0, description="Number of LLM attempts made")


__all__ = [
    "ClaimExtractionDTO",
    "AnalysisFailureDTO",
    "MAX_CLAIMS_PER_ANSWER",
    "RawClaimDTO",
    "RawExtractionDTO",
    "StanceValue",
    "ValidatedClaimDTO",
]

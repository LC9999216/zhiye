"""Stage 5 tests — deterministic concept normalisation (TDD first).

Verifies the execution plan's deterministic normalisation step:
- Unicode NFKC (full-width → half-width, compatibility chars).
- Case folding (English uppercase → lowercase).
- Whitespace collapsing + trimming.
- Common alias handling (e.g. trailing/leading variants).

The normaliser must be *deterministic* and *idempotent*: applying it to
an already-normalised name is a no-op.
"""

from __future__ import annotations

import pytest

from app.services.concept_normalizer import (
    CONCEPT_METHOD_VERSION,
    normalize_concept_name,
)


class TestNormalizeConceptName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Trim + collapse internal whitespace
            ("  计算机专业  ", "计算机专业"),
            ("人工智能  就业", "人工智能 就业"),  # single space preserved
            ("AI  与   教育", "ai 与 教育"),  # casefold + collapse
            # Full-width → half-width (NFKC)
            ("ＡＩ 教育", "ai 教育"),
            ("Ｃｏｍｐｕｔｅｒ", "computer"),
            # Full-width space → normal space
            ("机器\u3000学习", "机器 学习"),
            # Case folding
            ("AI", "ai"),
            ("Machine Learning", "machine learning"),
            ("GPT-4", "gpt-4"),
            # Idempotent
            ("ai 教育", "ai 教育"),
            # Empty / whitespace-only → empty
            ("", ""),
            ("   ", ""),
            ("\u3000", ""),
        ],
    )
    def test_normalizes(self, raw: str, expected: str) -> None:
        assert normalize_concept_name(raw) == expected

    def test_idempotent(self) -> None:
        once = normalize_concept_name("  Machine\u3000Learning  ")
        twice = normalize_concept_name(once)
        assert once == twice

    def test_method_version_is_versioned(self) -> None:
        assert CONCEPT_METHOD_VERSION == "concept-normalize-v1"


class TestConceptMergerGate:
    """The concept-similarity threshold must be versioned config (TDD)."""

    def test_has_versioned_config(self) -> None:
        from app.services.concept_merger import (
            CONCEPT_SIMILARITY_THRESHOLD,
            CONCEPT_METHOD_VERSION,
        )

        assert CONCEPT_SIMILARITY_THRESHOLD > 0.0
        assert CONCEPT_METHOD_VERSION.startswith("concept-cosine-")

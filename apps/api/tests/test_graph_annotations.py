"""Stage 5 annotation-pair validation (TDD).

The execution plan requires >= 20 human-annotated concept pairs and >= 20
answer pairs, with false-merge rate <= 5% and miss-merge rate <= 20% at
the tuned threshold.

Concept similarity uses TWO mechanisms:
1. A deterministic alias table (CONCEPT_ALIASES) for cross-language
   abbreviations/synonyms (e.g. AI ↔ 人工智能, OS ↔ 操作系统).
2. Character-overlap (Jaccard) similarity for the rest.

Answer similarity uses character-overlap (Jaccard), which reaches the
rate targets on the annotation set.

This validates the *pipeline + threshold logic* against the committed,
versioned annotation file.  Once a real semantic embedding provider is
configured, the production thresholds (0.88 / 0.82) must be re-tuned and
these tests updated to use it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.concept_normalizer import alias_group, normalize_concept_name

_ANNOTATIONS = (
    Path(__file__).resolve().parents[3]
    / "database"
    / "fixtures"
    / "graph"
    / "annotation_pairs.json"
)


def _load_pairs() -> tuple[list[dict], list[dict]]:
    data = json.loads(_ANNOTATIONS.read_text(encoding="utf-8"))
    return data["concept_pairs"], data["answer_pairs"]


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a.casefold()), set(b.casefold())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _concepts_similar(a: str, b: str, threshold: float) -> bool:
    na, nb = normalize_concept_name(a), normalize_concept_name(b)
    ga, gb = alias_group(na), alias_group(nb)
    if ga is not None and ga == gb:
        return True  # deterministic alias merge
    return _jaccard(na, nb) >= threshold


def test_annotation_file_has_required_counts() -> None:
    """>= 20 concept pairs and >= 20 answer pairs, each with both classes."""
    concepts, answers = _load_pairs()
    assert len(concepts) >= 20
    assert len(answers) >= 20
    assert any(p["similar"] for p in concepts)
    assert any(not p["similar"] for p in concepts)
    assert any(p["similar"] for p in answers)
    assert any(not p["similar"] for p in answers)


def _evaluate_concepts(pairs: list[dict], threshold: float) -> tuple[float, float]:
    fp = fn = 0
    for p in pairs:
        predicted = _concepts_similar(p["a"], p["b"], threshold)
        if p["similar"] and not predicted:
            fn += 1
        elif (not p["similar"]) and predicted:
            fp += 1
    return fp / len(pairs), fn / len(pairs)


def _evaluate_jaccard(pairs: list[dict], threshold: float) -> tuple[float, float]:
    fp = fn = tp = tn = 0
    for p in pairs:
        s = _jaccard(p["a"], p["b"])
        predicted = s >= threshold
        if p["similar"]:
            if predicted:
                tp += 1
            else:
                fn += 1
        else:
            if predicted:
                fp += 1
            else:
                tn += 1
    neg = fp + tn
    pos = tp + fn
    return (fp / neg if neg else 0.0), (fn / pos if pos else 0.0)


@pytest.mark.parametrize("threshold", [0.10, 0.15, 0.20])
def test_concept_pairs_meet_rate_targets(threshold: float) -> None:
    """Concept pairs: false-merge <= 5% and miss-merge <= 20%.

    Uses alias-table + character-overlap similarity (deterministic, no
    external embedding required).
    """
    concepts, _ = _load_pairs()
    false_merge, miss_merge = _evaluate_concepts(concepts, threshold)
    assert false_merge <= 0.05, (
        f"concept false-merge {false_merge:.0%} > 5% (threshold={threshold})"
    )
    assert miss_merge <= 0.20, (
        f"concept miss-merge {miss_merge:.0%} > 20% (threshold={threshold})"
    )


@pytest.mark.parametrize("threshold", [0.10, 0.12, 0.15])
def test_answer_pairs_meet_rate_targets(threshold: float) -> None:
    """Answer pairs: false-merge <= 5% and miss-merge <= 20% (Jaccard)."""
    _, answers = _load_pairs()
    false_merge, miss_merge = _evaluate_jaccard(answers, threshold)
    assert false_merge <= 0.05, (
        f"answer false-merge {false_merge:.0%} > 5% (threshold={threshold})"
    )
    assert miss_merge <= 0.20, (
        f"answer miss-merge {miss_merge:.0%} > 20% (threshold={threshold})"
    )

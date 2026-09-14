"""Concept merging via embedding cosine similarity (Stage 5).

Low-confidence candidates are NOT auto-merged.  Merging only happens
when two concepts within the same query have cosine similarity >= the
versioned threshold; the survivor keeps the canonical (higher-frequency)
name and records the alias + normalisation method version.

Config lives here as versioned constants so the threshold can be tuned
against the human-annotated concept pairs and recorded.
"""

from __future__ import annotations

# Versioned config — tuned against the human-annotated concept pairs.
# Start value per execution plan (0.88); overridden after tuning.
CONCEPT_SIMILARITY_THRESHOLD = 0.88
CONCEPT_METHOD_VERSION = "concept-cosine-v1"

__all__ = [
    "CONCEPT_METHOD_VERSION",
    "CONCEPT_SIMILARITY_THRESHOLD",
]

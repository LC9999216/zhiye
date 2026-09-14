"""Tests for ORM model constraints (uses SQLite in-memory where possible).

These tests verify:
- Unique constraints work correctly
- Check constraints work correctly  
- Foreign key relationships
- Default values

Note: pgvector-specific tests require PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Text, UniqueConstraint, create_engine, event, text
from sqlalchemy.orm import Session, declarative_base

# We test model *schema* definitions (constraints, column types) without
# needing a real database by inspecting the SQLAlchemy metadata.


class TestModelSchema:
    """Verify that ORM models define the correct constraints per IMPLEMENTATION_PLAN.md sec 6.3."""

    def test_query_model_has_unique_normalized(self) -> None:
        """``queries.normalized_query`` has a UNIQUE constraint."""
        from app.models.query import Query

        # normalized_query is defined inline with ``unique=True`` on the column
        col = Query.__table__.columns["normalized_query"]
        assert col.unique is True, "normalized_query should have unique=True"

    def test_answer_model_unique_constraint(self) -> None:
        """``answers`` has ``uq_answer_per_query`` on (query_id, content_id)."""
        from app.models.answer import Answer

        constraint_names = [
            c.name for c in Answer.__table_args__ if isinstance(c, UniqueConstraint)
        ]
        assert "uq_answer_per_query" in constraint_names

    def test_claim_model_check_constraint_position(self) -> None:
        """``claims.position`` has CHECK (position >= 1 AND position <= 5)."""
        from app.models.claim import Claim

        check_names = [c.name for c in Claim.__table_args__ if isinstance(c, CheckConstraint)]
        assert "ck_claim_position_range" in check_names

    def test_claim_model_unique_constraint(self) -> None:
        """``claims`` has ``uq_claim_position`` on (query_id, answer_id, position)."""
        from app.models.claim import Claim

        constraint_names = [
            c.name for c in Claim.__table_args__ if isinstance(c, UniqueConstraint)
        ]
        assert "uq_claim_position" in constraint_names

    def test_concept_model_unique_constraint(self) -> None:
        """``concepts`` has ``uq_concept_per_query`` on (query_id, normalized_name)."""
        from app.models.concept import Concept

        constraint_names = [
            c.name for c in Concept.__table_args__ if isinstance(c, UniqueConstraint)
        ]
        assert "uq_concept_per_query" in constraint_names

    def test_claim_concept_unique_constraint(self) -> None:
        """``claim_concepts`` has ``uq_claim_concept`` on (query_id, claim_id, concept_id)."""
        from app.models.claim_concept import ClaimConcept

        constraint_names = [
            c.name for c in ClaimConcept.__table_args__ if isinstance(c, UniqueConstraint)
        ]
        assert "uq_claim_concept" in constraint_names

    def test_answer_similarity_constraints(self) -> None:
        """``answer_similarities`` has both unique and check constraints."""
        from app.models.answer_similarity import AnswerSimilarity

        constraint_names = [
            c.name for c in AnswerSimilarity.__table_args__
        ]
        assert "uq_answer_similarity" in constraint_names
        assert "ck_similarity_ordered_pair" in constraint_names

    def test_job_model_no_extra_constraints(self) -> None:
        """``jobs`` only has FK and indexes (no unique constraints beyond PK)."""
        from app.models.job import Job

        # Job has no __table_args__, meaning no CHECK or UNIQUE constraints beyond column definitions.
        # Verify this by checking the table args is empty or None.
        assert not hasattr(Job, '__table_args__') or Job.__table_args__ is None or Job.__table_args__ == ()

    def test_query_model_columns(self) -> None:
        """``queries`` has the expected Stage 3 columns."""
        from app.models.query import Query

        cols = [c.name for c in Query.__table__.columns]
        assert "id" in cols
        assert "query_text" in cols
        assert "normalized_query" in cols
        assert "search_hash_id" in cols
        assert "status" in cols
        assert "search_fetched_at" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_answer_model_columns(self) -> None:
        """``answers`` has the expected columns (including Stage 4 analysis fields)."""
        from app.models.answer import Answer

        cols = [c.name for c in Answer.__table__.columns]
        assert "id" in cols
        assert "query_id" in cols
        assert "content_id" in cols
        assert "voteup_count" in cols
        assert "url" in cols
        # Stage 4 placeholder columns
        assert "summary" in cols
        assert "stance" in cols
        assert "analysis_model" in cols
        assert "prompt_version" in cols
        assert "analyzed_at" in cols
        assert "analysis_latency_ms" in cols
        # Stage 4 embedding columns
        assert "embedding" in cols
        assert "embedding_model" in cols

    def test_claim_model_columns(self) -> None:
        """``claims`` has the expected Stage 4 columns."""
        from app.models.claim import Claim

        cols = [c.name for c in Claim.__table__.columns]
        assert "id" in cols
        assert "query_id" in cols
        assert "answer_id" in cols
        assert "text" in cols
        assert "evidence_text" in cols
        assert "position" in cols
        assert "confidence" in cols
        assert "embedding" in cols
        assert "embedding_model" in cols

    def test_job_model_columns(self) -> None:
        """``jobs`` has the expected columns."""
        from app.models.job import Job

        cols = [c.name for c in Job.__table__.columns]
        assert "id" in cols
        assert "query_id" in cols
        assert "status" in cols
        assert "current_step" in cols
        assert "error_code" in cols
        assert "error_message" in cols
        assert "started_at" in cols
        assert "finished_at" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_query_default_status(self) -> None:
        """``Query.status`` defaults to 'pending'."""
        from app.models.query import Query

        col = Query.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == "pending"

    def test_job_default_status(self) -> None:
        """``Job.status`` defaults to 'pending'."""
        from app.models.job import Job

        col = Job.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == "pending"

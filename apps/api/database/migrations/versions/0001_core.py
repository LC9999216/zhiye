"""0001_core — initial schema: queries, answers, claims, concepts, jobs, and associations.

Revision ID: 0001_core
Revises: None
Create Date: 2025-07-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_core"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema: enable pgvector, create all core tables."""
    # ── Enable pgvector extension ────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── queries ──────────────────────────────────────────────────────
    op.create_table(
        "queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.String(500), nullable=False),
        sa.Column("search_hash_id", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("search_fetched_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("normalized_query", name="uq_queries_normalized"),
    )
    op.create_index(op.f("ix_queries_status"), "queries", ["status"])

    # ── answers ──────────────────────────────────────────────────────
    op.create_table(
        "answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("queries.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("content_id", sa.String(200), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(200), nullable=False,
                  server_default=""),
        sa.Column("content_text", sa.Text(), nullable=False,
                  server_default=""),
        sa.Column("voteup_count", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("original_index", sa.Integer(), nullable=False),
        sa.Column("edit_time", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("ranking_score", sa.Float(), nullable=False,
                  server_default="0.0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        # Analysis columns (Stage 4)
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("stance", sa.String(20), nullable=True),
        sa.Column("analysis_model", sa.String(200), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("schema_version", sa.String(50), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analysis_latency_ms", sa.Integer(), nullable=True),
        # pgvector embedding column (1536 dimensions)
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("query_id", "content_id",
                            name="uq_answer_per_query"),
    )

    # ── claims ───────────────────────────────────────────────────────
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("queries.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("answers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_text", sa.Text(), nullable=False,
                  server_default=""),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False,
                  server_default="0.0"),
        # pgvector embedding column
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("embedding_model", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("query_id", "answer_id", "position",
                            name="uq_claim_position"),
        sa.CheckConstraint("position >= 1 AND position <= 5",
                           name="ck_claim_position_range"),
    )

    # ── concepts ─────────────────────────────────────────────────────
    op.create_table(
        "concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("queries.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("canonical_name", sa.String(200), nullable=False,
                  server_default=""),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column("frequency", sa.Integer(), nullable=False,
                  server_default="0"),
        # pgvector embedding column
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("embedding_model", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("query_id", "normalized_name",
                            name="uq_concept_per_query"),
    )

    # ── claim_concepts (association) ────────────────────────────────
    op.create_table(
        "claim_concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("queries.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("claims.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("concept_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("concepts.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("query_id", "claim_id", "concept_id",
                            name="uq_claim_concept"),
    )

    # ── answer_similarities ─────────────────────────────────────────
    op.create_table(
        "answer_similarities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("queries.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("source_answer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("answers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("target_answer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("answers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("embedding_model", sa.String(200), nullable=True),
        sa.Column("method_version", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("query_id", "source_answer_id", "target_answer_id",
                            name="uq_answer_similarity"),
        sa.CheckConstraint("source_answer_id < target_answer_id",
                           name="ck_similarity_ordered_pair"),
    )

    # ── jobs ─────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("queries.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending", index=True),
        sa.Column("current_step", sa.String(200), nullable=False,
                  server_default=""),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # ── chat_messages (Stage 8 placeholder) ──────────────────────────
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("queries.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citation_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_chat_messages_query_id"), "chat_messages",
                    ["query_id"])

    # ── Convert embedding columns to pgvector type ───────────────────
    # Note: In production with PostgreSQL + pgvector, the ARRAY columns
    # above should be replaced with vector(1536) via raw SQL:
    #
    #   op.execute("ALTER TABLE answers ALTER COLUMN embedding TYPE vector(1536)")
    #   op.execute("ALTER TABLE claims ALTER COLUMN embedding TYPE vector(1536)")
    #   op.execute("ALTER TABLE concepts ALTER COLUMN embedding TYPE vector(1536)")
    #
    # This is done separately so the migration works without pgvector
    # on SQLite-based test environments.


def downgrade() -> None:
    """Drop all core tables in reverse dependency order."""
    op.drop_table("answer_similarities")
    op.drop_table("claim_concepts")
    op.drop_table("concepts")
    op.drop_table("claims")
    op.drop_table("answers")
    op.drop_table("jobs")
    op.drop_table("chat_messages")
    op.drop_table("queries")

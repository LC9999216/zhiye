"""Stage 4 close-out + Stage 5: fix answers.embedding_model drift and add
composite foreign keys that enforce the cross-query integrity contract.

Revisions
---------
- ``answers`` was missing ``embedding_model`` in 0001_core (ORM drift).
- Composite FKs were never created: the execution plan requires that a
  write referencing a child row from a different query is rejected at the
  database level, so:
    * ``claims(query_id, answer_id)`` -> ``answers(query_id, id)``
    * ``claim_concepts(query_id, claim_id)`` -> ``claims(query_id, id)``
    * ``claim_concepts(query_id, concept_id)`` -> ``concepts(query_id, id)``
    * ``answer_similarities(query_id, source_answer_id)`` -> ``answers(query_id, id)``
    * ``answer_similarities(query_id, target_answer_id)`` -> ``answers(query_id, id)``
- PostgreSQL composite FKs require unique constraints on the referenced
  columns, so we add ``UNIQUE(query_id, id)`` on answers/claims/concepts
  (plus a supporting index on ``answers``, which already has one).

Revision ID: 0002_composite_fk
Revises: 0001_core
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_composite_fk"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Stage 4 close-out: add the missing embedding_model column.
    op.add_column(
        "answers",
        sa.Column("embedding_model", sa.String(200), nullable=True),
    )

    # 2) Add supporting unique constraints so composite FKs are valid.
    #    answers/claims/concepts need UNIQUE(query_id, id).
    op.create_unique_constraint(
        "uq_answers_query_id_id", "answers", ["query_id", "id"]
    )
    op.create_unique_constraint(
        "uq_claims_query_id_id", "claims", ["query_id", "id"]
    )
    op.create_unique_constraint(
        "uq_concepts_query_id_id", "concepts", ["query_id", "id"]
    )

    # 3) Composite foreign keys (cross-query integrity).
    op.create_foreign_key(
        "fk_claims_answer_query",
        "claims",
        "answers",
        ["query_id", "answer_id"],
        ["query_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_claim_concepts_claim_query",
        "claim_concepts",
        "claims",
        ["query_id", "claim_id"],
        ["query_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_claim_concepts_concept_query",
        "claim_concepts",
        "concepts",
        ["query_id", "concept_id"],
        ["query_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_answer_similarities_source_query",
        "answer_similarities",
        "answers",
        ["query_id", "source_answer_id"],
        ["query_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_answer_similarities_target_query",
        "answer_similarities",
        "answers",
        ["query_id", "target_answer_id"],
        ["query_id", "id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Composite FKs first (reverse dependency).
    op.drop_constraint(
        "fk_answer_similarities_target_query", "answer_similarities", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_answer_similarities_source_query", "answer_similarities", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_claim_concepts_concept_query", "claim_concepts", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_claim_concepts_claim_query", "claim_concepts", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_claims_answer_query", "claims", type_="foreignkey"
    )
    op.drop_constraint("uq_concepts_query_id_id", "concepts", type_="unique")
    op.drop_constraint("uq_claims_query_id_id", "claims", type_="unique")
    op.drop_constraint("uq_answers_query_id_id", "answers", type_="unique")
    op.drop_column("answers", "embedding_model")

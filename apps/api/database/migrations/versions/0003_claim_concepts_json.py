"""Stage 5: add ``claims.concepts_json`` for graph building.

The Stage 4 analysis persists each claim's raw concept names so Stage 5's
``build_concepts`` can materialise ``concepts`` + ``claim_concepts`` rows
(the REFERS_TO authority).  This column stores the JSON-array string the
LLM produced (e.g. ``["考研", "就业"]``); existing rows default to NULL
(no concepts → no claim_concepts link).

Revision ID: 0003_claim_concepts_json
Revises: 0002_composite_fk
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_claim_concepts_json"
down_revision = "0002_composite_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("concepts_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("claims", "concepts_json")

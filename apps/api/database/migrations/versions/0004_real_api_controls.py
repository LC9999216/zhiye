"""Stage 6 real API controls: data isolation, warnings and budget ledger."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_real_api_controls"
down_revision: Union[str, Sequence[str], None] = "0003_claim_concepts_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("queries", sa.Column("data_mode", sa.String(20), nullable=True))
    op.execute("UPDATE queries SET data_mode = 'legacy' WHERE data_mode IS NULL")
    op.alter_column("queries", "data_mode", nullable=False, server_default="mock")
    op.drop_constraint("uq_queries_normalized", "queries", type_="unique")
    op.create_unique_constraint(
        "uq_queries_mode_normalized", "queries", ["data_mode", "normalized_query"]
    )

    op.add_column("jobs", sa.Column("warnings_json", sa.Text(), nullable=True))
    op.add_column(
        "answers", sa.Column("analysis_status", sa.String(20), nullable=True)
    )
    op.execute("UPDATE answers SET analysis_status = 'pending' WHERE analysis_status IS NULL")
    op.alter_column("answers", "analysis_status", nullable=False, server_default="pending")
    op.add_column("answers", sa.Column("analysis_error_code", sa.String(50), nullable=True))
    op.add_column("answers", sa.Column("analysis_request_id", sa.String(200), nullable=True))
    op.add_column("answers", sa.Column("analysis_usage_json", sa.Text(), nullable=True))

    op.create_table(
        "budget_ledger",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "query_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("queries.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("reserved_cny", sa.Numeric(12, 4), nullable=False),
        sa.Column("actual_cny", sa.Numeric(12, 4), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="reserved"),
        sa.Column("provider_usage_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_budget_ledger_job_id", "budget_ledger", ["job_id"])
    op.create_index("ix_budget_ledger_query_id", "budget_ledger", ["query_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_ledger_query_id", table_name="budget_ledger")
    op.drop_index("ix_budget_ledger_job_id", table_name="budget_ledger")
    op.drop_table("budget_ledger")
    op.drop_column("answers", "analysis_error_code")
    op.drop_column("answers", "analysis_usage_json")
    op.drop_column("answers", "analysis_request_id")
    op.drop_column("answers", "analysis_status")
    op.drop_column("jobs", "warnings_json")
    op.drop_constraint("uq_queries_mode_normalized", "queries", type_="unique")
    op.create_unique_constraint("uq_queries_normalized", "queries", ["normalized_query"])
    op.drop_column("queries", "data_mode")

"""Add replayable public AgentRun events.

Revision ID: 20260726_0009
Revises: 20260726_0008
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0009"
down_revision: str | Sequence[str] | None = "20260726_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("agent_run_id", sa.String(36), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sequence > 0",
            name="ck_run_events_sequence_positive",
        ),
        sa.CheckConstraint(
            "event_type IN ('run.started', 'stage.changed', 'tool.completed', "
            "'approval.required', 'result.updated', 'run.completed', 'run.failed')",
            name="ck_run_events_type",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_run_events_agent_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_events"),
        sa.UniqueConstraint(
            "trace_id",
            "sequence",
            name="uq_run_events_trace_sequence",
        ),
    )
    op.create_index(
        "ix_run_events_owner_trace_sequence",
        "run_events",
        ["user_id", "trace_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_events_owner_trace_sequence", table_name="run_events")
    op.drop_table("run_events")

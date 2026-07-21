"""Add AgentRun and ToolRun tracking tables.

Revision ID: 20260721_0002
Revises: 20260721_0001
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0002"
down_revision: str | Sequence[str] | None = "20260721_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGENT_STATUSES = (
    "queued",
    "running",
    "waiting_user",
    "succeeded",
    "partially_succeeded",
    "failed",
    "cancelled",
)
_TOOL_STATUSES = ("running", "succeeded", "failed", "blocked", "cancelled")


def _in_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Create only the two M0-1C run tracking tables and their indexes."""

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("workflow", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "model_names_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "model_calls_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("cost_currency", sa.String(length=3), nullable=True),
        sa.Column("cost_estimation_source", sa.String(length=64), nullable=False),
        sa.Column("cost_unknown_reason", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_in_values(_AGENT_STATUSES)})",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_agent_runs_input_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_agent_runs_output_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_agent_runs_total_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0",
            name="ck_agent_runs_estimated_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR (duration_ms >= 0 AND duration_ms <= 60000)",
            name="ck_agent_runs_duration_bound",
        ),
        sa.CheckConstraint(
            "estimated_cost IS NULL OR cost_currency IS NOT NULL",
            name="ck_agent_runs_known_cost_currency",
        ),
        sa.CheckConstraint(
            "(estimated_cost IS NULL AND cost_unknown_reason IS NOT NULL) OR "
            "(estimated_cost IS NOT NULL AND cost_unknown_reason IS NULL)",
            name="ck_agent_runs_cost_known_or_explained",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_agent_runs_time_order",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.UniqueConstraint("trace_id", name="uq_agent_runs_trace_id"),
    )
    op.create_index("ix_agent_runs_trace_id", "agent_runs", ["trace_id"], unique=False)

    op.create_table(
        "tool_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_call_id", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence > 0", name="ck_tool_runs_sequence_positive"),
        sa.CheckConstraint(
            f"status IN ({_in_values(_TOOL_STATUSES)})",
            name="ck_tool_runs_status",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_tool_runs_latency_nonnegative",
        ),
        sa.CheckConstraint(
            "length(arguments_fingerprint) = 64",
            name="ck_tool_runs_fingerprint_length",
        ),
        sa.CheckConstraint(
            "length(input_summary) <= 512",
            name="ck_tool_runs_input_summary_length",
        ),
        sa.CheckConstraint(
            "output_summary IS NULL OR length(output_summary) <= 512",
            name="ck_tool_runs_output_summary_length",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_tool_runs_time_order",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_tool_runs_agent_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tool_runs"),
        sa.UniqueConstraint(
            "agent_run_id",
            "sequence",
            name="uq_tool_runs_run_sequence",
        ),
    )
    op.create_index(
        "ix_tool_runs_agent_run_id",
        "tool_runs",
        ["agent_run_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove all M0-1C tables and indexes."""

    op.drop_index("ix_tool_runs_agent_run_id", table_name="tool_runs")
    op.drop_table("tool_runs")
    op.drop_index("ix_agent_runs_trace_id", table_name="agent_runs")
    op.drop_table("agent_runs")

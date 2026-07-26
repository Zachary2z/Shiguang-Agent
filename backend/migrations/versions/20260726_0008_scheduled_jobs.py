"""Add the durable ScheduledJob queue.

Revision ID: 20260726_0008
Revises: 20260724_0007
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0008"
down_revision: str | Sequence[str] | None = "20260724_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("job_type", sa.String(128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("result_summary_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_scheduled_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt BETWEEN 0 AND max_attempts",
            name="ck_scheduled_jobs_attempt_range",
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 3",
            name="ck_scheduled_jobs_max_attempts",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND worker_id IS NOT NULL AND "
            "lease_expires_at IS NOT NULL) OR "
            "(status <> 'running' AND worker_id IS NULL AND lease_expires_at IS NULL)",
            name="ck_scheduled_jobs_lease_shape",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_scheduled_jobs_time_order",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scheduled_jobs"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_scheduled_jobs_user_idempotency",
        ),
    )
    op.create_index(
        "ix_scheduled_jobs_claim",
        "scheduled_jobs",
        ["status", "run_at", "created_at"],
    )
    op.create_index(
        "ix_scheduled_jobs_trace_sequence",
        "scheduled_jobs",
        ["trace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_jobs_trace_sequence", table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_claim", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")

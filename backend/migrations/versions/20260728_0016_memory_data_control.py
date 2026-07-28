"""Add structured Memory, decisions, operations, and plan usage.

Revision ID: 20260728_0016
Revises: 20260728_0015
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0016"
down_revision: str | None = "20260728_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("content", sa.String(500), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_summary", sa.String(500), nullable=False),
        sa.Column("source_feedback_id", sa.String(36)),
        sa.Column("source_plan_id", sa.String(36)),
        sa.Column("confirmation_status", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memories_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_feedback_id", "source_plan_id", "user_id"],
            [
                "plan_feedback_audits.id",
                "plan_feedback_audits.plan_id",
                "plan_feedback_audits.user_id",
            ],
            name="fk_memories_feedback_source_owner",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_memories_id_user"),
        sa.CheckConstraint(
            "type IN ('positive_preference', 'negative_preference', "
            "'pace_preference', 'usual_area')",
            name="ck_memories_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('explicit_user', 'feedback_inference')",
            name="ck_memories_source_type",
        ),
        sa.CheckConstraint(
            "confirmation_status = 'confirmed'", name="ck_memories_confirmation_status"
        ),
        sa.CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_memories_confidence"),
        sa.CheckConstraint("version >= 1", name="ck_memories_version"),
        sa.CheckConstraint(
            "(source_type = 'feedback_inference' AND source_feedback_id IS NOT NULL "
            "AND source_plan_id IS NOT NULL) OR "
            "(source_type = 'explicit_user' AND source_feedback_id IS NULL "
            "AND source_plan_id IS NULL)",
            name="ck_memories_source_shape",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at", name="ck_memories_expiry"
        ),
    )
    op.create_index("ix_memories_owner_updated", "memories", ["user_id", "updated_at"])
    op.create_index(
        "ix_memories_effective",
        "memories",
        ["user_id", "type"],
        sqlite_where=sa.text("disabled_at IS NULL AND deleted_at IS NULL"),
        postgresql_where=sa.text("disabled_at IS NULL AND deleted_at IS NULL"),
    )
    op.create_table(
        "memory_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("memory_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["memory_id", "user_id"],
            ["memories.id", "memories.user_id"],
            name="fk_memory_operations_memory_owner",
        ),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_memory_operations_owner_key"
        ),
        sa.CheckConstraint(
            "operation IN ('create', 'update', 'delete')",
            name="ck_memory_operations_operation",
        ),
    )
    op.create_index(
        "ix_memory_operations_owner_created",
        "memory_operations",
        ["user_id", "created_at"],
    )
    op.create_table(
        "memory_suggestion_decisions",
        sa.Column("suggestion_id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("memory_id", sa.String(36)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["suggestion_id", "plan_id", "user_id"],
            [
                "plan_feedback_audits.id",
                "plan_feedback_audits.plan_id",
                "plan_feedback_audits.user_id",
            ],
            name="fk_memory_suggestion_decisions_feedback_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["memory_id", "user_id"],
            ["memories.id", "memories.user_id"],
            name="fk_memory_suggestion_decisions_memory_owner",
        ),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_memory_suggestion_decisions_owner_key",
        ),
        sa.CheckConstraint(
            "decision IN ('confirmed', 'rejected')",
            name="ck_memory_suggestion_decisions_decision",
        ),
        sa.CheckConstraint(
            "(decision = 'confirmed' AND memory_id IS NOT NULL) OR "
            "(decision = 'rejected' AND memory_id IS NULL)",
            name="ck_memory_suggestion_decisions_shape",
        ),
    )
    op.create_index(
        "ix_memory_suggestion_decisions_owner",
        "memory_suggestion_decisions",
        ["user_id", "decided_at"],
    )
    op.create_table(
        "memory_plan_usages",
        sa.Column("memory_id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("basis", sa.String(500), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["memory_id", "user_id"],
            ["memories.id", "memories.user_id"],
            name="fk_memory_plan_usages_memory_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_memory_plan_usages_plan_owner",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_memory_plan_usages_owner_used",
        "memory_plan_usages",
        ["user_id", "used_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    counts = sum(
        connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
        for table in (
            "memories",
            "memory_operations",
            "memory_suggestion_decisions",
            "memory_plan_usages",
        )
    )
    if counts:
        raise RuntimeError("Memory data exists; remove it before downgrading.")
    op.drop_index("ix_memory_plan_usages_owner_used", table_name="memory_plan_usages")
    op.drop_table("memory_plan_usages")
    op.drop_index(
        "ix_memory_suggestion_decisions_owner",
        table_name="memory_suggestion_decisions",
    )
    op.drop_table("memory_suggestion_decisions")
    op.drop_index("ix_memory_operations_owner_created", table_name="memory_operations")
    op.drop_table("memory_operations")
    op.drop_index("ix_memories_effective", table_name="memories")
    op.drop_index("ix_memories_owner_updated", table_name="memories")
    op.drop_table("memories")

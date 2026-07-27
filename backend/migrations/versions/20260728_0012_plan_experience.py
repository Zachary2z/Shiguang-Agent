"""Persist immutable plan versions, plan item snapshots, and approvals.

Revision ID: 20260728_0012
Revises: 20260727_0011
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0012"
down_revision: str | Sequence[str] | None = "20260727_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("root_plan_id", sa.String(36), nullable=False),
        sa.Column("parent_plan_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("constraints_json", sa.JSON(), nullable=False),
        sa.Column("adjustment_text", sa.Text(), nullable=True),
        sa.Column("draft_json", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_plans_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["root_plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plans_root_owner",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["parent_plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plans_parent_owner",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_plans_id_user"),
        sa.UniqueConstraint("root_plan_id", "version", name="uq_plans_root_version"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_plans_user_idempotency",
        ),
        sa.UniqueConstraint("trace_id", name="uq_plans_trace_id"),
        sa.CheckConstraint(
            "status IN ('generating', 'waiting_approval', 'draft', 'confirmed', "
            "'superseded', 'failed', 'cancelled')",
            name="ck_plans_status",
        ),
        sa.CheckConstraint(
            "operation IN ('generate', 'adjust')",
            name="ck_plans_operation",
        ),
        sa.CheckConstraint("version >= 1", name="ck_plans_version_positive"),
        sa.CheckConstraint(
            "(version = 1 AND id = root_plan_id AND parent_plan_id IS NULL "
            "AND operation = 'generate' AND adjustment_text IS NULL) OR "
            "(version > 1 AND id <> root_plan_id AND parent_plan_id IS NOT NULL "
            "AND operation = 'adjust' AND adjustment_text IS NOT NULL)",
            name="ck_plans_version_shape",
        ),
        sa.CheckConstraint(
            "(status IN ('draft', 'confirmed', 'superseded') AND draft_json IS NOT NULL) "
            "OR (status NOT IN ('draft', 'confirmed', 'superseded') "
            "AND draft_json IS NULL)",
            name="ck_plans_draft_shape",
        ),
        sa.CheckConstraint(
            "(status = 'confirmed' AND confirmed_at IS NOT NULL) OR "
            "(status = 'superseded') OR "
            "(status NOT IN ('confirmed', 'superseded') AND confirmed_at IS NULL)",
            name="ck_plans_confirmation_shape",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) OR "
            "(status <> 'failed' AND error_code IS NULL)",
            name="ck_plans_error_shape",
        ),
    )
    op.create_index("ix_plans_owner_created", "plans", ["user_id", "created_at"])
    op.create_index(
        "ix_plans_owner_root_version",
        "plans",
        ["user_id", "root_plan_id", "version"],
    )
    op.create_index(
        "uq_plans_one_confirmed_per_root",
        "plans",
        ["root_plan_id"],
        unique=True,
        sqlite_where=sa.text("status = 'confirmed'"),
        postgresql_where=sa.text("status = 'confirmed'"),
    )

    op.create_table(
        "plan_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("option_index", sa.Integer(), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plan_items_plan_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "plan_id",
            "option_index",
            "item_index",
            name="uq_plan_items_position",
        ),
        sa.CheckConstraint("option_index >= 0", name="ck_plan_items_option_index"),
        sa.CheckConstraint("item_index >= 0", name="ck_plan_items_item_index"),
        sa.CheckConstraint("end_at > start_at", name="ck_plan_items_time_order"),
    )
    op.create_index(
        "ix_plan_items_plan_position",
        "plan_items",
        ["plan_id", "option_index", "item_index"],
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("target_plan_id", sa.String(36), nullable=False),
        sa.Column("external_requirement_id", sa.String(41), nullable=True),
        sa.Column("display_text", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["target_plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_approvals_plan_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_approvals_id_user"),
        sa.CheckConstraint(
            "action IN ('external_place_supplement', 'confirm_plan')",
            name="ck_approvals_action",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired')",
            name="ck_approvals_status",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_approvals_expiry_order"),
        sa.CheckConstraint(
            "(status = 'pending' AND decided_at IS NULL) OR "
            "(status <> 'pending' AND decided_at IS NOT NULL)",
            name="ck_approvals_decision_shape",
        ),
        sa.CheckConstraint(
            "(action = 'external_place_supplement' "
            "AND external_requirement_id IS NOT NULL) OR "
            "(action <> 'external_place_supplement' "
            "AND external_requirement_id IS NULL)",
            name="ck_approvals_external_requirement_shape",
        ),
    )
    op.create_index(
        "ix_approvals_owner_status",
        "approvals",
        ["user_id", "status", "created_at"],
    )
    op.create_index(
        "uq_approvals_confirm_idempotency",
        "approvals",
        ["user_id", "action", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_approvals_confirm_idempotency", table_name="approvals")
    op.drop_index("ix_approvals_owner_status", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_plan_items_plan_position", table_name="plan_items")
    op.drop_table("plan_items")
    op.drop_index("uq_plans_one_confirmed_per_root", table_name="plans")
    op.drop_index("ix_plans_owner_root_version", table_name="plans")
    op.drop_index("ix_plans_owner_created", table_name="plans")
    op.drop_table("plans")

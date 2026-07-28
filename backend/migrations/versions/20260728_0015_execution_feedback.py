"""Add confirmed-plan execution and auditable feedback.

Revision ID: 20260728_0015
Revises: 20260728_0014
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0015"
down_revision: str | None = "20260728_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLAN_STATUSES = (
    "'generating', 'waiting_approval', 'draft', 'confirmed', 'superseded', "
    "'failed', 'cancelled', 'completed', 'partially_completed', 'not_completed'"
)


def upgrade() -> None:
    op.drop_index("uq_plans_one_confirmed_per_root", table_name="plans")
    with op.batch_alter_table("plans") as batch:
        batch.drop_constraint("ck_plans_status", type_="check")
        batch.drop_constraint("ck_plans_draft_shape", type_="check")
        batch.drop_constraint("ck_plans_confirmation_shape", type_="check")
        batch.create_check_constraint("ck_plans_status", f"status IN ({_PLAN_STATUSES})")
        batch.create_check_constraint(
            "ck_plans_draft_shape",
            "(status IN ('draft', 'confirmed', 'superseded', 'completed', "
            "'partially_completed', 'not_completed') AND draft_json IS NOT NULL) "
            "OR (status NOT IN ('draft', 'confirmed', 'superseded', 'completed', "
            "'partially_completed', 'not_completed') AND draft_json IS NULL)",
        )
        batch.create_check_constraint(
            "ck_plans_confirmation_shape",
            "(status IN ('confirmed', 'completed', 'partially_completed', "
            "'not_completed') AND confirmed_at IS NOT NULL) OR "
            "(status = 'superseded') OR "
            "(status NOT IN ('confirmed', 'completed', 'partially_completed', "
            "'not_completed', 'superseded') AND confirmed_at IS NULL)",
        )
    op.create_index(
        "uq_plans_one_confirmed_per_root",
        "plans",
        ["root_plan_id"],
        unique=True,
        sqlite_where=sa.text(
            "status IN ('confirmed', 'completed', 'partially_completed', "
            "'not_completed')"
        ),
        postgresql_where=sa.text(
            "status IN ('confirmed', 'completed', 'partially_completed', "
            "'not_completed')"
        ),
    )

    with op.batch_alter_table("plan_items") as batch:
        batch.create_unique_constraint("uq_plan_items_id_user", ["id", "user_id"])
        batch.add_column(
            sa.Column(
                "execution_status",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            )
        )
        batch.create_check_constraint(
            "ck_plan_items_execution_status",
            "execution_status IN ('pending', 'visited', 'not_visited')",
        )

    op.create_table(
        "plan_feedback_audits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("completion_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("visited_plan_item_ids_json", sa.JSON(), nullable=False),
        sa.Column("preference_suggestion_json", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("corrects_feedback_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plan_feedback_audits_plan_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["corrects_feedback_id", "plan_id", "user_id"],
            [
                "plan_feedback_audits.id",
                "plan_feedback_audits.plan_id",
                "plan_feedback_audits.user_id",
            ],
            name="fk_plan_feedback_audits_corrects",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_plan_feedback_audits_id_user"),
        sa.UniqueConstraint(
            "id",
            "plan_id",
            "user_id",
            name="uq_plan_feedback_audits_id_plan_owner",
        ),
        sa.UniqueConstraint(
            "plan_id", "revision", name="uq_plan_feedback_audits_plan_revision"
        ),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_plan_feedback_audits_owner_key"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_plan_feedback_audits_revision"),
        sa.CheckConstraint(
            "completion_status IN ('completed', 'partially_completed', 'not_completed')",
            name="ck_plan_feedback_audits_completion_status",
        ),
    )
    op.create_index(
        "ix_plan_feedback_audits_plan_created",
        "plan_feedback_audits",
        ["plan_id", "created_at"],
    )

    op.create_table(
        "plan_feedback_states",
        sa.Column("plan_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("current_feedback_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("completion_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("preference_suggestion_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plan_feedback_states_plan_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["current_feedback_id", "plan_id", "user_id"],
            [
                "plan_feedback_audits.id",
                "plan_feedback_audits.plan_id",
                "plan_feedback_audits.user_id",
            ],
            name="fk_plan_feedback_states_current_audit",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_plan_feedback_states_revision"),
        sa.CheckConstraint(
            "completion_status IN ('completed', 'partially_completed', 'not_completed')",
            name="ck_plan_feedback_states_completion_status",
        ),
    )
    op.create_index(
        "ix_plan_feedback_states_owner_updated",
        "plan_feedback_states",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "collection_visit_states",
        sa.Column("collection_item_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("baseline_visited", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_collection_visit_states_collection_owner",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "collection_visit_sources",
        sa.Column("plan_item_id", sa.String(length=36), primary_key=True),
        sa.Column("collection_item_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("feedback_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_item_id", "user_id"],
            ["plan_items.id", "plan_items.user_id"],
            name="fk_collection_visit_sources_plan_item_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_collection_visit_sources_collection_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id", "user_id"],
            ["plan_feedback_audits.id", "plan_feedback_audits.user_id"],
            name="fk_collection_visit_sources_feedback_owner",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_collection_visit_sources_collection",
        "collection_visit_sources",
        ["collection_item_id", "user_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT COUNT(*) FROM plan_feedback_audits").scalar_one():
        raise RuntimeError("Plan feedback exists; remove it before downgrading.")
    op.drop_index(
        "ix_collection_visit_sources_collection",
        table_name="collection_visit_sources",
    )
    op.drop_table("collection_visit_sources")
    op.drop_table("collection_visit_states")
    op.drop_index(
        "ix_plan_feedback_states_owner_updated", table_name="plan_feedback_states"
    )
    op.drop_table("plan_feedback_states")
    op.drop_index(
        "ix_plan_feedback_audits_plan_created", table_name="plan_feedback_audits"
    )
    op.drop_table("plan_feedback_audits")
    with op.batch_alter_table("plan_items") as batch:
        batch.drop_constraint("ck_plan_items_execution_status", type_="check")
        batch.drop_column("execution_status")
        batch.drop_constraint("uq_plan_items_id_user", type_="unique")
    op.drop_index("uq_plans_one_confirmed_per_root", table_name="plans")
    with op.batch_alter_table("plans") as batch:
        batch.drop_constraint("ck_plans_confirmation_shape", type_="check")
        batch.drop_constraint("ck_plans_draft_shape", type_="check")
        batch.drop_constraint("ck_plans_status", type_="check")
        batch.create_check_constraint(
            "ck_plans_status",
            "status IN ('generating', 'waiting_approval', 'draft', 'confirmed', "
            "'superseded', 'failed', 'cancelled')",
        )
        batch.create_check_constraint(
            "ck_plans_draft_shape",
            "(status IN ('draft', 'confirmed', 'superseded') AND draft_json IS NOT NULL) "
            "OR (status NOT IN ('draft', 'confirmed', 'superseded') "
            "AND draft_json IS NULL)",
        )
        batch.create_check_constraint(
            "ck_plans_confirmation_shape",
            "(status = 'confirmed' AND confirmed_at IS NOT NULL) OR "
            "(status = 'superseded') OR "
            "(status NOT IN ('confirmed', 'superseded') AND confirmed_at IS NULL)",
        )
    op.create_index(
        "uq_plans_one_confirmed_per_root",
        "plans",
        ["root_plan_id"],
        unique=True,
        sqlite_where=sa.text("status = 'confirmed'"),
        postgresql_where=sa.text("status = 'confirmed'"),
    )

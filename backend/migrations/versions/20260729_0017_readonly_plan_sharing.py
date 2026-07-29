"""Add hashed, revocable read-only plan shares.

Revision ID: 20260729_0017
Revises: 20260728_0016
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0017"
down_revision: str | None = "20260728_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_share_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plan_share_links_plan_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="uq_plan_share_links_token_hash"),
        sa.CheckConstraint(
            "length(token_hash) = 64 AND token_hash = lower(token_hash)",
            name="ck_plan_share_links_token_hash_format",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_plan_share_links_expiry",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_plan_share_links_revocation",
        ),
    )
    op.create_index(
        "uq_plan_share_links_one_unrevoked_per_plan",
        "plan_share_links",
        ["plan_id"],
        unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_plan_share_links_owner_created",
        "plan_share_links",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    count = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM plan_share_links"
    ).scalar_one()
    if count:
        raise RuntimeError("Plan share data exists; remove it before downgrading.")
    op.drop_index(
        "ix_plan_share_links_owner_created",
        table_name="plan_share_links",
    )
    op.drop_index(
        "uq_plan_share_links_one_unrevoked_per_plan",
        table_name="plan_share_links",
    )
    op.drop_table("plan_share_links")

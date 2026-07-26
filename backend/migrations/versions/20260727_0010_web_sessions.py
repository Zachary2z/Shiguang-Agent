"""Add durable hashed browser sessions.

Revision ID: 20260727_0010
Revises: 20260726_0009
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0010"
down_revision: str | Sequence[str] | None = "20260726_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "web_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'wbs_'",
            name="ck_web_sessions_id_format",
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64 AND token_hash = lower(token_hash)",
            name="ck_web_sessions_token_hash_format",
        ),
        sa.CheckConstraint(
            "length(csrf_token_hash) = 64 AND csrf_token_hash = lower(csrf_token_hash)",
            name="ck_web_sessions_csrf_hash_format",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_web_sessions_expiry_order",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_web_sessions_revocation_order",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_web_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_web_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_web_sessions_token_hash"),
    )
    op.create_index(
        "ix_web_sessions_user_expires",
        "web_sessions",
        ["user_id", "expires_at"],
    )
    op.create_index(
        "ix_web_sessions_active_expiry",
        "web_sessions",
        ["revoked_at", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_web_sessions_active_expiry", table_name="web_sessions")
    op.drop_index("ix_web_sessions_user_expires", table_name="web_sessions")
    op.drop_table("web_sessions")

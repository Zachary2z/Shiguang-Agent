"""Remember the exact collection status for the public restore action.

Revision ID: 20260727_0011
Revises: 20260727_0010
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0011"
down_revision: str | Sequence[str] | None = "20260727_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("collection_items") as batch_op:
        batch_op.add_column(
            sa.Column("deleted_from_status", sa.String(32), nullable=True),
        )
        batch_op.create_check_constraint(
            "ck_collection_items_deleted_from_status",
            "deleted_from_status IS NULL OR deleted_from_status IN "
            "('active', 'pending_selection', 'pending_details')",
        )


def downgrade() -> None:
    with op.batch_alter_table("collection_items") as batch_op:
        batch_op.drop_constraint(
            "ck_collection_items_deleted_from_status",
            type_="check",
        )
        batch_op.drop_column("deleted_from_status")

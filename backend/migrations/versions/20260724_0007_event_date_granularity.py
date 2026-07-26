"""Add inclusive Event effective-date bounds.

Revision ID: 20260724_0007
Revises: 20260722_0006
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0007"
down_revision: str | Sequence[str] | None = "20260722_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add date-only Event facts without converting them to timestamps."""

    with op.batch_alter_table("collection_items", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("event_start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("event_end_date", sa.Date(), nullable=True))
        batch_op.create_check_constraint(
            "ck_collection_items_event_date_order",
            "event_end_date IS NULL OR event_start_date IS NULL OR "
            "event_end_date >= event_start_date",
        )
        batch_op.drop_constraint("ck_collection_items_place_without_event_time", type_="check")
        batch_op.create_check_constraint(
            "ck_collection_items_place_without_event_time",
            "kind <> 'place' OR (event_start_date IS NULL AND event_end_date IS NULL AND "
            "event_start_at IS NULL AND event_end_at IS NULL)",
        )


def downgrade() -> None:
    """Remove date columns only when no date facts would be lost."""

    connection = op.get_bind()
    date_fact_count = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM collection_items "
            "WHERE event_start_date IS NOT NULL OR event_end_date IS NOT NULL"
        )
    )
    if date_fact_count:
        raise RuntimeError(
            "cannot downgrade to 20260722_0006 while Event date facts exist"
        )

    with op.batch_alter_table("collection_items", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_collection_items_place_without_event_time", type_="check")
        batch_op.create_check_constraint(
            "ck_collection_items_place_without_event_time",
            "kind <> 'place' OR (event_start_at IS NULL AND event_end_at IS NULL)",
        )
        batch_op.drop_constraint("ck_collection_items_event_date_order", type_="check")
        batch_op.drop_column("event_end_date")
        batch_op.drop_column("event_start_date")

"""Keep transient recognition states out of collection item storage.

Revision ID: 20260721_0004
Revises: 20260721_0003
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0004"
down_revision: str | Sequence[str] | None = "20260721_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERSISTED_COLLECTION_STATUSES = (
    "active",
    "pending_selection",
    "pending_details",
    "visited",
    "archived",
    "deleted",
)
_LEGACY_COLLECTION_STATUSES = (
    "recognizing",
    *_PERSISTED_COLLECTION_STATUSES,
)


def _in_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace_status_constraint(values: tuple[str, ...]) -> None:
    with op.batch_alter_table("collection_items") as batch_op:
        batch_op.drop_constraint("ck_collection_items_status", type_="check")
        batch_op.create_check_constraint(
            "ck_collection_items_status",
            f"status IN ({_in_values(values)})",
        )


def upgrade() -> None:
    """Delete transient rows and reject future recognizing/failed collection items."""

    op.execute(
        sa.text(
            "DELETE FROM collection_sources WHERE collection_item_id IN "
            "(SELECT id FROM collection_items WHERE status = 'recognizing')"
        )
    )
    op.execute(sa.text("DELETE FROM collection_items WHERE status = 'recognizing'"))
    _replace_status_constraint(_PERSISTED_COLLECTION_STATUSES)


def downgrade() -> None:
    """Restore the legacy recognizing constraint without recreating deleted rows."""

    _replace_status_constraint(_LEGACY_COLLECTION_STATUSES)

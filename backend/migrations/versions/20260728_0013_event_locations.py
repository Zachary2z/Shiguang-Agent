"""Allow exact confirmed POI facts on Event collections.

Revision ID: 20260728_0013
Revises: 20260728_0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0013"
down_revision: str | None = "20260728_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT_LOCATION_CHECK = (
    "kind = 'place' OR ((place_scope IS NULL OR place_scope = 'exact') AND "
    "(place_scope IS NOT NULL OR place_target_json IS NULL) AND "
    "place_candidate_snapshot_json IS NULL AND candidate_count = 0)"
)
_OLD_EVENT_LOCATION_CHECK = (
    "kind = 'place' OR (place_scope IS NULL AND place_target_json IS NULL AND "
    "place_candidate_snapshot_json IS NULL AND candidate_count = 0)"
)
_PLACE_EXACT_INDEX = (
    "kind = 'place' AND place_scope = 'exact' AND status <> 'deleted'"
)
_OLD_EXACT_INDEX = "place_scope = 'exact' AND status <> 'deleted'"


def upgrade() -> None:
    op.drop_index("uq_collection_items_user_exact_poi", table_name="collection_items")
    with op.batch_alter_table("collection_items") as batch_op:
        batch_op.drop_constraint(
            "ck_collection_items_event_without_place_target",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_event_without_place_target",
            _EVENT_LOCATION_CHECK,
        )
    op.create_index(
        "uq_collection_items_user_exact_poi",
        "collection_items",
        ["user_id", "poi_provider", "poi_id"],
        unique=True,
        sqlite_where=sa.text(_PLACE_EXACT_INDEX),
        postgresql_where=sa.text(_PLACE_EXACT_INDEX),
    )


def downgrade() -> None:
    connection = op.get_bind()
    count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM collection_items "
            "WHERE kind = 'event' AND place_scope IS NOT NULL"
        )
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Event exact location facts exist; remove them before downgrading."
        )
    op.drop_index("uq_collection_items_user_exact_poi", table_name="collection_items")
    with op.batch_alter_table("collection_items") as batch_op:
        batch_op.drop_constraint(
            "ck_collection_items_event_without_place_target",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_event_without_place_target",
            _OLD_EVENT_LOCATION_CHECK,
        )
    op.create_index(
        "uq_collection_items_user_exact_poi",
        "collection_items",
        ["user_id", "poi_provider", "poi_id"],
        unique=True,
        sqlite_where=sa.text(_OLD_EXACT_INDEX),
        postgresql_where=sa.text(_OLD_EXACT_INDEX),
    )

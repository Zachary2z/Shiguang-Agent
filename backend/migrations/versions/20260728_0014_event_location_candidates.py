"""Allow user-confirmed POI candidate snapshots on Event collections.

Revision ID: 20260728_0014
Revises: 20260728_0013
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260728_0014"
down_revision: str | None = "20260728_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT_LOCATION_CHECK = (
    "kind = 'place' OR ((place_scope IS NULL OR place_scope = 'exact') AND "
    "(place_scope IS NOT NULL OR place_target_json IS NULL))"
)
_OLD_EVENT_LOCATION_CHECK = (
    "kind = 'place' OR ((place_scope IS NULL OR place_scope = 'exact') AND "
    "(place_scope IS NOT NULL OR place_target_json IS NULL) AND "
    "place_candidate_snapshot_json IS NULL AND candidate_count = 0)"
)


def upgrade() -> None:
    with op.batch_alter_table("collection_items") as batch_op:
        batch_op.drop_constraint(
            "ck_collection_items_event_without_place_target",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_event_without_place_target",
            _EVENT_LOCATION_CHECK,
        )


def downgrade() -> None:
    connection = op.get_bind()
    count = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM collection_items "
        "WHERE kind = 'event' AND place_candidate_snapshot_json IS NOT NULL"
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Event location candidate snapshots exist; remove them before downgrading."
        )
    with op.batch_alter_table("collection_items") as batch_op:
        batch_op.drop_constraint(
            "ck_collection_items_event_without_place_target",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_event_without_place_target",
            _OLD_EVENT_LOCATION_CHECK,
        )

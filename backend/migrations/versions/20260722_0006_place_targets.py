"""Add unified M0-3D Place targets and idempotent selection operations.

Revision ID: 20260722_0006
Revises: 20260721_0005
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0006"
down_revision: str | Sequence[str] | None = "20260721_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend the existing collection aggregate; do not create a brand collection."""

    with op.batch_alter_table("collection_items", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("place_scope", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("place_target_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("poi_provider", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("poi_id", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("poi_city_code", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("poi_latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("poi_longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("poi_coordinate_system", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("brand_namespace", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("brand_id", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("place_match_status", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("place_confirmed_by", sa.String(32), nullable=True))
        batch_op.add_column(
            sa.Column("place_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("place_candidate_snapshot_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "candidate_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column("candidates_queried_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_collection_items_place_scope",
            "place_scope IS NULL OR place_scope IN ('exact', 'any_branch')",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_place_target_shape",
            "(place_scope IS NULL AND place_target_json IS NULL AND "
            "poi_provider IS NULL AND poi_id IS NULL AND poi_city_code IS NULL AND "
            "poi_latitude IS NULL AND poi_longitude IS NULL AND "
            "poi_coordinate_system IS NULL AND brand_namespace IS NULL AND "
            "brand_id IS NULL AND place_confirmed_by IS NULL AND "
            "place_confirmed_at IS NULL AND place_match_status IS NULL) OR "
            "(place_scope = 'exact' AND place_target_json IS NOT NULL AND "
            "poi_provider IS NOT NULL AND poi_id IS NOT NULL AND "
            "poi_city_code IS NOT NULL AND poi_latitude IS NOT NULL AND "
            "poi_longitude IS NOT NULL AND poi_coordinate_system = 'gcj_02' AND "
            "brand_namespace IS NULL AND brand_id IS NULL AND "
            "place_confirmed_by IS NOT NULL AND place_confirmed_at IS NOT NULL AND "
            "place_match_status = 'matched') OR "
            "(place_scope = 'any_branch' AND place_target_json IS NOT NULL AND "
            "poi_provider IS NULL AND poi_id IS NULL AND poi_city_code IS NULL AND "
            "poi_latitude IS NULL AND poi_longitude IS NULL AND "
            "poi_coordinate_system IS NULL AND brand_namespace IS NOT NULL AND "
            "brand_id IS NOT NULL AND place_confirmed_by = 'user_selection' AND "
            "place_confirmed_at IS NOT NULL AND place_match_status IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_place_target_json_consistency",
            "place_target_json IS NULL OR (json_valid(place_target_json) AND "
            "json_type(place_target_json, '$') = 'object' AND "
            "json_extract(place_target_json, '$.scope') = place_scope AND "
            "json_extract(place_target_json, '$.match_status') = place_match_status AND "
            "json_extract(place_target_json, '$.confirmed_by') = place_confirmed_by AND "
            "julianday(json_extract(place_target_json, '$.confirmed_at')) = "
            "julianday(place_confirmed_at) AND ((place_scope = 'exact' AND "
            "json_extract(place_target_json, '$.poi.provider') = poi_provider AND "
            "json_extract(place_target_json, '$.poi.poi_id') = poi_id AND "
            "json_extract(place_target_json, '$.poi.city_code') = poi_city_code AND "
            "json_extract(place_target_json, '$.poi.coordinate.latitude') = poi_latitude AND "
            "json_extract(place_target_json, '$.poi.coordinate.longitude') = poi_longitude AND "
            "json_extract(place_target_json, '$.poi.coordinate.coordinate_system') = "
            "poi_coordinate_system AND "
            "json_type(place_target_json, '$.brand_identity') = 'null') OR "
            "(place_scope = 'any_branch' AND "
            "json_extract(place_target_json, '$.brand_identity.namespace') = "
            "brand_namespace AND "
            "json_extract(place_target_json, '$.brand_identity.stable_id') = brand_id AND "
            "json_type(place_target_json, '$.poi') = 'null')))",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_candidate_snapshot_shape",
            "(place_candidate_snapshot_json IS NULL AND candidate_count = 0 AND "
            "candidates_queried_at IS NULL) OR "
            "(place_candidate_snapshot_json IS NOT NULL AND "
            "candidate_count BETWEEN 0 AND 3 AND candidates_queried_at IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_candidate_snapshot_json_consistency",
            "place_candidate_snapshot_json IS NULL OR "
            "(json_valid(place_candidate_snapshot_json) AND "
            "json_type(place_candidate_snapshot_json, '$') = 'object' AND "
            "json_array_length(place_candidate_snapshot_json, '$.result.candidates') = "
            "candidate_count AND "
            "julianday(json_extract(place_candidate_snapshot_json, '$.queried_at')) = "
            "julianday(candidates_queried_at))",
        )
        batch_op.create_check_constraint(
            "ck_collection_items_event_without_place_target",
            "kind = 'place' OR (place_scope IS NULL AND place_target_json IS NULL AND "
            "place_candidate_snapshot_json IS NULL AND candidate_count = 0)",
        )

    op.create_index(
        "uq_collection_items_user_exact_poi",
        "collection_items",
        ["user_id", "poi_provider", "poi_id"],
        unique=True,
        sqlite_where=sa.text("place_scope = 'exact' AND status <> 'deleted'"),
    )
    op.create_index(
        "uq_collection_items_user_any_brand",
        "collection_items",
        ["user_id", "brand_namespace", "brand_id"],
        unique=True,
        sqlite_where=sa.text("place_scope = 'any_branch' AND status <> 'deleted'"),
    )

    op.create_table(
        "place_selection_operations",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("collection_item_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("result_item_ids_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_place_selection_operations_idempotency_length",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_place_selection_operations_fingerprint_length",
        ),
        sa.CheckConstraint(
            "json_array_length(result_item_ids_json) >= 1",
            name="ck_place_selection_operations_results_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_place_selection_operations_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_place_selection_operations_item_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "user_id"],
            ["sources.id", "sources.user_id"],
            name="fk_place_selection_operations_source_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "idempotency_key",
            name="pk_place_selection_operations",
        ),
    )


def downgrade() -> None:
    """Reject lossy rollback before removing the M0-3D shape."""

    connection = op.get_bind()
    operation_count = connection.scalar(sa.text("SELECT COUNT(*) FROM place_selection_operations"))
    target_count = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM collection_items WHERE place_scope IS NOT NULL OR "
            "place_target_json IS NOT NULL OR place_candidate_snapshot_json IS NOT NULL OR "
            "candidate_count <> 0 OR candidates_queried_at IS NOT NULL"
        )
    )
    if operation_count or target_count:
        raise RuntimeError("cannot downgrade to 20260721_0005 while M0-3D Place target data exist")

    op.drop_table("place_selection_operations")
    op.drop_index("uq_collection_items_user_any_brand", table_name="collection_items")
    op.drop_index("uq_collection_items_user_exact_poi", table_name="collection_items")
    with op.batch_alter_table("collection_items", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_collection_items_event_without_place_target", type_="check")
        batch_op.drop_constraint(
            "ck_collection_items_candidate_snapshot_json_consistency", type_="check"
        )
        batch_op.drop_constraint("ck_collection_items_candidate_snapshot_shape", type_="check")
        batch_op.drop_constraint(
            "ck_collection_items_place_target_json_consistency", type_="check"
        )
        batch_op.drop_constraint("ck_collection_items_place_target_shape", type_="check")
        batch_op.drop_constraint("ck_collection_items_place_scope", type_="check")
        batch_op.drop_column("candidates_queried_at")
        batch_op.drop_column("candidate_count")
        batch_op.drop_column("place_candidate_snapshot_json")
        batch_op.drop_column("place_confirmed_at")
        batch_op.drop_column("place_confirmed_by")
        batch_op.drop_column("place_match_status")
        batch_op.drop_column("brand_id")
        batch_op.drop_column("brand_namespace")
        batch_op.drop_column("poi_coordinate_system")
        batch_op.drop_column("poi_longitude")
        batch_op.drop_column("poi_latitude")
        batch_op.drop_column("poi_city_code")
        batch_op.drop_column("poi_id")
        batch_op.drop_column("poi_provider")
        batch_op.drop_column("place_target_json")
        batch_op.drop_column("place_scope")

"""Add M0-2C reversible collection writes and candidate metadata.

Revision ID: 20260721_0005
Revises: 20260721_0004
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0005"
down_revision: str | Sequence[str] | None = "20260721_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist candidate detail, one idempotent operation, and its Undo group."""

    with op.batch_alter_table("collection_items", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("business_district", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("landmark", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("metro_station", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("event_start_clue", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("event_end_clue", sa.String(120), nullable=True))
        batch_op.add_column(
            sa.Column(
                "missing_fields_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "uncertainties_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.create_check_constraint(
            "ck_collection_items_place_without_event_clues",
            "kind <> 'place' OR "
            "(event_start_clue IS NULL AND event_end_clue IS NULL)",
        )

    op.create_table(
        "collection_write_operations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("undo_token_hash", sa.String(64), nullable=False),
        sa.Column("undo_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'cwo_'",
            name="ck_collection_write_operations_id_format",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_collection_write_operations_idempotency_length",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_collection_write_operations_fingerprint_length",
        ),
        sa.CheckConstraint(
            "length(undo_token_hash) = 64",
            name="ck_collection_write_operations_undo_hash_length",
        ),
        sa.CheckConstraint(
            "undo_expires_at > created_at",
            name="ck_collection_write_operations_expiry_order",
        ),
        sa.CheckConstraint(
            "undone_at IS NULL OR undone_at >= created_at",
            name="ck_collection_write_operations_undone_order",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_collection_write_operations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "user_id"],
            ["sources.id", "sources.user_id"],
            name="fk_collection_write_operations_source_owner_sources",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_collection_write_operations"),
        sa.UniqueConstraint(
            "id",
            "user_id",
            name="uq_collection_write_operations_id_user",
        ),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_collection_write_operations_user_idempotency",
        ),
        sa.UniqueConstraint(
            "user_id",
            "source_id",
            name="uq_collection_write_operations_user_source",
        ),
        sa.UniqueConstraint(
            "undo_token_hash",
            name="uq_collection_write_operations_undo_hash",
        ),
    )

    op.create_table(
        "collection_write_operation_items",
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("collection_item_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sequence > 0",
            name="ck_collection_write_operation_items_sequence_positive",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id", "user_id"],
            ["collection_write_operations.id", "collection_write_operations.user_id"],
            name="fk_collection_write_operation_items_operation_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_collection_write_operation_items_item_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "operation_id",
            "collection_item_id",
            name="pk_collection_write_operation_items",
        ),
        sa.UniqueConstraint(
            "operation_id",
            "sequence",
            name="uq_collection_write_operation_items_operation_sequence",
        ),
    )


def downgrade() -> None:
    """Reject lossy rollback before any DDL, otherwise restore the exact 0004 shape."""

    connection = op.get_bind()
    operation_count = connection.scalar(
        sa.text(
            "SELECT (SELECT COUNT(*) FROM collection_write_operations) + "
            "(SELECT COUNT(*) FROM collection_write_operation_items)"
        )
    )
    json_text = "::text" if connection.dialect.name == "postgresql" else ""
    metadata_count = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM collection_items WHERE "
            "business_district IS NOT NULL OR landmark IS NOT NULL OR "
            "metro_station IS NOT NULL OR event_start_clue IS NOT NULL OR "
            f"event_end_clue IS NOT NULL OR missing_fields_json{json_text} <> '[]' OR "
            f"uncertainties_json{json_text} <> '[]'"
        )
    )
    if operation_count or metadata_count:
        raise RuntimeError(
            "cannot downgrade to 20260721_0004 while M0-2C reversible writes "
            "or candidate metadata exist"
        )

    op.drop_table("collection_write_operation_items")
    op.drop_table("collection_write_operations")
    with op.batch_alter_table("collection_items", recreate="auto") as batch_op:
        batch_op.drop_constraint(
            "ck_collection_items_place_without_event_clues",
            type_="check",
        )
        batch_op.drop_column("uncertainties_json")
        batch_op.drop_column("missing_fields_json")
        batch_op.drop_column("event_end_clue")
        batch_op.drop_column("event_start_clue")
        batch_op.drop_column("metro_station")
        batch_op.drop_column("landmark")
        batch_op.drop_column("business_district")

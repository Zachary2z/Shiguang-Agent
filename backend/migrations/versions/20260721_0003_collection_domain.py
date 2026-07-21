"""Add the M0-2A collection domain tables.

Revision ID: 20260721_0003
Revises: 20260721_0002
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0003"
down_revision: str | Sequence[str] | None = "20260721_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_MODES = ("real", "demo")
_CITIES = ("shenzhen",)
_TIMEZONES = ("Asia/Shanghai",)
_SESSION_CHANNELS = ("web", "demo")
_SESSION_STATUSES = ("active", "closed")
_MESSAGE_ROLES = ("user", "assistant")
_MESSAGE_CONTENT_TYPES = ("text", "url", "image")
_SOURCE_TYPES = ("text", "url", "image")
_SOURCE_PARSE_STATUSES = ("pending", "parsed", "failed")
_COLLECTION_KINDS = ("place", "event")
_COLLECTION_STATUSES = (
    "recognizing",
    "active",
    "pending_selection",
    "pending_details",
    "visited",
    "archived",
    "deleted",
)


def _in_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Create only User, Session, Message, Source, CollectionItem and their source link."""

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("city", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"mode IN ({_in_values(_USER_MODES)})",
            name="ck_users_mode",
        ),
        sa.CheckConstraint(
            f"city IN ({_in_values(_CITIES)})",
            name="ck_users_city",
        ),
        sa.CheckConstraint(
            f"timezone IN ({_in_values(_TIMEZONES)})",
            name="ck_users_timezone",
        ),
        sa.CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'usr_'",
            name="ck_users_id_format",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"channel IN ({_in_values(_SESSION_CHANNELS)})",
            name="ck_sessions_channel",
        ),
        sa.CheckConstraint(
            f"status IN ({_in_values(_SESSION_STATUSES)})",
            name="ck_sessions_status",
        ),
        sa.CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'ses_'",
            name="ck_sessions_id_format",
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_sessions_time_order"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
    )
    op.create_index(
        "ix_sessions_user_updated",
        "sessions",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"role IN ({_in_values(_MESSAGE_ROLES)})",
            name="ck_messages_role",
        ),
        sa.CheckConstraint(
            f"content_type IN ({_in_values(_MESSAGE_CONTENT_TYPES)})",
            name="ck_messages_content_type",
        ),
        sa.CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'msg_'",
            name="ck_messages_id_format",
        ),
        sa.CheckConstraint(
            "length(content) > 0 AND length(content) <= 20000",
            name="ck_messages_content_length",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_messages_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index(
        "ix_messages_session_created",
        "messages",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("file_key", sa.String(length=128), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("parse_status", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"type IN ({_in_values(_SOURCE_TYPES)})",
            name="ck_sources_type",
        ),
        sa.CheckConstraint(
            f"parse_status IN ({_in_values(_SOURCE_PARSE_STATUSES)})",
            name="ck_sources_parse_status",
        ),
        sa.CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'src_'",
            name="ck_sources_id_format",
        ),
        sa.CheckConstraint(
            "(type = 'text' AND url IS NULL AND file_key IS NULL) OR "
            "(type = 'url' AND url IS NOT NULL AND file_key IS NULL) OR "
            "(type = 'image' AND url IS NULL AND file_key IS NOT NULL)",
            name="ck_sources_type_fields",
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_sources_time_order"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_sources_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("id", "user_id", name="uq_sources_id_user_id"),
    )
    op.create_index(
        "ix_sources_user_parse_created",
        "sources",
        ["user_id", "parse_status", "created_at"],
        unique=False,
    )
    op.create_table(
        "collection_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("city", sa.String(length=32), nullable=False),
        sa.Column("district", sa.String(length=100), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("event_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("price_currency", sa.String(length=3), nullable=True),
        sa.Column(
            "tags_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"kind IN ({_in_values(_COLLECTION_KINDS)})",
            name="ck_collection_items_kind",
        ),
        sa.CheckConstraint(
            f"status IN ({_in_values(_COLLECTION_STATUSES)})",
            name="ck_collection_items_status",
        ),
        sa.CheckConstraint(
            f"city IN ({_in_values(_CITIES)})",
            name="ck_collection_items_city",
        ),
        sa.CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'col_'",
            name="ck_collection_items_id_format",
        ),
        sa.CheckConstraint(
            "length(title) > 0",
            name="ck_collection_items_title_nonempty",
        ),
        sa.CheckConstraint("version > 0", name="ck_collection_items_version_positive"),
        sa.CheckConstraint(
            "event_end_at IS NULL OR event_start_at IS NULL OR event_end_at > event_start_at",
            name="ck_collection_items_event_time_order",
        ),
        sa.CheckConstraint(
            "kind <> 'place' OR (event_start_at IS NULL AND event_end_at IS NULL)",
            name="ck_collection_items_place_without_event_time",
        ),
        sa.CheckConstraint(
            "(price_amount IS NULL AND price_currency IS NULL) OR "
            "(price_amount IS NOT NULL AND price_amount >= 0 AND price_currency IS NOT NULL)",
            name="ck_collection_items_price_pair",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_collection_items_time_order",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_collection_items_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_collection_items"),
        sa.UniqueConstraint("id", "user_id", name="uq_collection_items_id_user_id"),
    )
    op.create_index(
        "ix_collection_items_user_status_created",
        "collection_items",
        ["user_id", "status", "created_at"],
        unique=False,
    )
    op.create_table(
        "collection_sources",
        sa.Column("collection_item_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_collection_sources_item_owner_collection_items",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "user_id"],
            ["sources.id", "sources.user_id"],
            name="fk_collection_sources_source_owner_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "collection_item_id",
            "source_id",
            name="pk_collection_sources",
        ),
    )
    op.create_index(
        "ix_collection_sources_source_id",
        "collection_sources",
        ["source_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove only the six M0-2A tables, preserving M0-1C run tracking."""

    op.drop_index("ix_collection_sources_source_id", table_name="collection_sources")
    op.drop_table("collection_sources")
    op.drop_index(
        "ix_collection_items_user_status_created",
        table_name="collection_items",
    )
    op.drop_table("collection_items")
    op.drop_index("ix_sources_user_parse_created", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_messages_session_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_sessions_user_updated", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")

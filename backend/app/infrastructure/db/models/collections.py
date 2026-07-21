"""SQLAlchemy models for the six M0-2A collection tables."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.collections import (
    PERSISTABLE_COLLECTION_STATUSES,
    CollectionKind,
    MessageContentType,
    MessageRole,
    SessionChannel,
    SessionStatus,
    SourceParseStatus,
    SourceType,
    SupportedCity,
    SupportedTimezone,
    UserMode,
)
from app.domain.time import utc_now
from app.infrastructure.db.base import Base


def _sql_values(values: type[Any] | tuple[Any, ...]) -> str:
    return ", ".join(f"'{member.value}'" for member in values)


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"mode IN ({_sql_values(UserMode)})", name="ck_users_mode"),
        CheckConstraint(f"city IN ({_sql_values(SupportedCity)})", name="ck_users_city"),
        CheckConstraint(
            f"timezone IN ({_sql_values(SupportedTimezone)})",
            name="ck_users_timezone",
        ),
        CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'usr_'",
            name="ck_users_id_format",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    city: Mapped[str] = mapped_column(String(32), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SessionModel(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            f"channel IN ({_sql_values(SessionChannel)})",
            name="ck_sessions_channel",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(SessionStatus)})",
            name="ck_sessions_status",
        ),
        CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'ses_'",
            name="ck_sessions_id_format",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_sessions_time_order",
        ),
        Index("ix_sessions_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_sessions_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(f"role IN ({_sql_values(MessageRole)})", name="ck_messages_role"),
        CheckConstraint(
            f"content_type IN ({_sql_values(MessageContentType)})",
            name="ck_messages_content_type",
        ),
        CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'msg_'",
            name="ck_messages_id_format",
        ),
        CheckConstraint(
            "length(content) > 0 AND length(content) <= 20000",
            name="ck_messages_content_length",
        ),
        Index("ix_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", name="fk_messages_session_id_sessions", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SourceModel(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_sources_id_user_id"),
        CheckConstraint(f"type IN ({_sql_values(SourceType)})", name="ck_sources_type"),
        CheckConstraint(
            f"parse_status IN ({_sql_values(SourceParseStatus)})",
            name="ck_sources_parse_status",
        ),
        CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'src_'",
            name="ck_sources_id_format",
        ),
        CheckConstraint(
            "(type = 'text' AND url IS NULL AND file_key IS NULL) OR "
            "(type = 'url' AND url IS NOT NULL AND file_key IS NULL) OR "
            "(type = 'image' AND url IS NULL AND file_key IS NOT NULL)",
            name="ck_sources_type_fields",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_sources_time_order"),
        Index("ix_sources_user_parse_created", "user_id", "parse_status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_sources_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    file_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CollectionItemModel(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_collection_items_id_user_id"),
        CheckConstraint(
            f"kind IN ({_sql_values(CollectionKind)})",
            name="ck_collection_items_kind",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(PERSISTABLE_COLLECTION_STATUSES)})",
            name="ck_collection_items_status",
        ),
        CheckConstraint(
            f"city IN ({_sql_values(SupportedCity)})",
            name="ck_collection_items_city",
        ),
        CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'col_'",
            name="ck_collection_items_id_format",
        ),
        CheckConstraint("length(title) > 0", name="ck_collection_items_title_nonempty"),
        CheckConstraint("version > 0", name="ck_collection_items_version_positive"),
        CheckConstraint(
            "event_end_at IS NULL OR event_start_at IS NULL OR event_end_at > event_start_at",
            name="ck_collection_items_event_time_order",
        ),
        CheckConstraint(
            "kind <> 'place' OR (event_start_at IS NULL AND event_end_at IS NULL)",
            name="ck_collection_items_place_without_event_time",
        ),
        CheckConstraint(
            "(price_amount IS NULL AND price_currency IS NULL) OR "
            "(price_amount IS NOT NULL AND price_amount >= 0 AND price_currency IS NOT NULL)",
            name="ck_collection_items_price_pair",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_collection_items_time_order"),
        Index(
            "ix_collection_items_user_status_created",
            "user_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_collection_items_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(32), nullable=False)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    event_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CollectionSourceModel(Base):
    __tablename__ = "collection_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_collection_sources_item_owner_collection_items",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_id", "user_id"],
            ["sources.id", "sources.user_id"],
            name="fk_collection_sources_source_owner_sources",
            ondelete="CASCADE",
        ),
        Index("ix_collection_sources_source_id", "source_id"),
    )

    collection_item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

"""SQLAlchemy models for the six M0-2A collection tables."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.collections import (
    PERSISTABLE_COLLECTION_STATUSES,
    CollectionKind,
    MessageContentType,
    MessageRole,
    PlanCity,
    SessionChannel,
    SessionStatus,
    SourceParseStatus,
    SourceType,
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
        CheckConstraint(
            f"default_plan_city IN ({_sql_values(PlanCity)})",
            name="ck_users_default_plan_city",
        ),
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
    default_plan_city: Mapped[str] = mapped_column(String(32), nullable=False)
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
            "city_hint IS NULL OR "
            "(city_hint = trim(city_hint) AND length(city_hint) BETWEEN 1 AND 100)",
            name="ck_collection_items_city_hint",
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
            "event_end_date IS NULL OR event_start_date IS NULL OR "
            "event_end_date >= event_start_date",
            name="ck_collection_items_event_date_order",
        ),
        CheckConstraint(
            "kind <> 'place' OR (event_start_date IS NULL AND event_end_date IS NULL AND "
            "event_start_at IS NULL AND event_end_at IS NULL)",
            name="ck_collection_items_place_without_event_time",
        ),
        CheckConstraint(
            "kind <> 'place' OR (event_start_clue IS NULL AND event_end_clue IS NULL)",
            name="ck_collection_items_place_without_event_clues",
        ),
        CheckConstraint(
            "(price_amount IS NULL AND price_currency IS NULL) OR "
            "(price_amount IS NOT NULL AND price_amount >= 0 AND price_currency IS NOT NULL)",
            name="ck_collection_items_price_pair",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_collection_items_time_order"),
        CheckConstraint(
            "place_scope IS NULL OR place_scope IN ('exact', 'any_branch')",
            name="ck_collection_items_place_scope",
        ),
        CheckConstraint(
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
            name="ck_collection_items_place_target_shape",
        ),
        CheckConstraint(
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
            name="ck_collection_items_place_target_json_consistency",
        ),
        CheckConstraint(
            "(place_candidate_snapshot_json IS NULL AND candidate_count = 0 AND "
            "candidates_queried_at IS NULL) OR "
            "(place_candidate_snapshot_json IS NOT NULL AND "
            "candidate_count BETWEEN 0 AND 3 AND candidates_queried_at IS NOT NULL)",
            name="ck_collection_items_candidate_snapshot_shape",
        ),
        CheckConstraint(
            "place_candidate_snapshot_json IS NULL OR "
            "(json_valid(place_candidate_snapshot_json) AND "
            "json_type(place_candidate_snapshot_json, '$') = 'object' AND "
            "json_array_length(place_candidate_snapshot_json, '$.result.candidates') = "
            "candidate_count AND "
            "julianday(json_extract(place_candidate_snapshot_json, '$.queried_at')) = "
            "julianday(candidates_queried_at))",
            name="ck_collection_items_candidate_snapshot_json_consistency",
        ),
        CheckConstraint(
            "kind = 'place' OR (place_scope IS NULL AND place_target_json IS NULL AND "
            "place_candidate_snapshot_json IS NULL AND candidate_count = 0)",
            name="ck_collection_items_event_without_place_target",
        ),
        Index(
            "ix_collection_items_user_status_created",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "uq_collection_items_user_exact_poi",
            "user_id",
            "poi_provider",
            "poi_id",
            unique=True,
            sqlite_where=text("place_scope = 'exact' AND status <> 'deleted'"),
            postgresql_where=text("place_scope = 'exact' AND status <> 'deleted'"),
        ),
        Index(
            "uq_collection_items_user_any_brand",
            "user_id",
            "brand_namespace",
            "brand_id",
            unique=True,
            sqlite_where=text("place_scope = 'any_branch' AND status <> 'deleted'"),
            postgresql_where=text("place_scope = 'any_branch' AND status <> 'deleted'"),
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
    city_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    business_district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(160), nullable=True)
    metro_station: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_start_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    event_end_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    event_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_start_clue: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_end_clue: Mapped[str | None] = mapped_column(String(120), nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    missing_fields_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    uncertainties_json: Mapped[list[dict[str, str]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    place_scope: Mapped[str | None] = mapped_column(String(16), nullable=True)
    place_target_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    poi_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    poi_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    poi_city_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    poi_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    poi_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    poi_coordinate_system: Mapped[str | None] = mapped_column(String(16), nullable=True)
    brand_namespace: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brand_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    place_match_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    place_confirmed_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    place_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    place_candidate_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidates_queried_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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


class CollectionWriteOperationModel(Base):
    __tablename__ = "collection_write_operations"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_collection_write_operations_id_user"),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_collection_write_operations_user_idempotency",
        ),
        UniqueConstraint(
            "user_id",
            "source_id",
            name="uq_collection_write_operations_user_source",
        ),
        UniqueConstraint(
            "undo_token_hash",
            name="uq_collection_write_operations_undo_hash",
        ),
        ForeignKeyConstraint(
            ["source_id", "user_id"],
            ["sources.id", "sources.user_id"],
            name="fk_collection_write_operations_source_owner_sources",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'cwo_'",
            name="ck_collection_write_operations_id_format",
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_collection_write_operations_idempotency_length",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_collection_write_operations_fingerprint_length",
        ),
        CheckConstraint(
            "length(undo_token_hash) = 64",
            name="ck_collection_write_operations_undo_hash_length",
        ),
        CheckConstraint(
            "undo_expires_at > created_at",
            name="ck_collection_write_operations_expiry_order",
        ),
        CheckConstraint(
            "undone_at IS NULL OR undone_at >= created_at",
            name="ck_collection_write_operations_undone_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "users.id",
            name="fk_collection_write_operations_user_id_users",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    undo_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    undo_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CollectionWriteOperationItemModel(Base):
    __tablename__ = "collection_write_operation_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["operation_id", "user_id"],
            ["collection_write_operations.id", "collection_write_operations.user_id"],
            name="fk_collection_write_operation_items_operation_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_collection_write_operation_items_item_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "operation_id",
            "sequence",
            name="uq_collection_write_operation_items_operation_sequence",
        ),
        CheckConstraint(
            "sequence > 0",
            name="ck_collection_write_operation_items_sequence_positive",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    collection_item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlaceSelectionOperationModel(Base):
    __tablename__ = "place_selection_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_place_selection_operations_item_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_id", "user_id"],
            ["sources.id", "sources.user_id"],
            name="fk_place_selection_operations_source_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_place_selection_operations_idempotency_length",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_place_selection_operations_fingerprint_length",
        ),
        CheckConstraint(
            "json_array_length(result_item_ids_json) >= 1",
            name="ck_place_selection_operations_results_nonempty",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_place_selection_operations_user", ondelete="CASCADE"),
        primary_key=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    collection_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_item_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

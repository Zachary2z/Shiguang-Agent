"""SQLAlchemy persistence for immutable plan versions and approvals."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.plans import (
    ApprovalAction,
    ApprovalStatus,
    PlanOperation,
    PlanStatus,
)
from app.domain.time import utc_now
from app.infrastructure.db.base import Base

_PLAN_STATUSES = ", ".join(f"'{value.value}'" for value in PlanStatus)
_PLAN_OPERATIONS = ", ".join(f"'{value.value}'" for value in PlanOperation)
_APPROVAL_ACTIONS = ", ".join(f"'{value.value}'" for value in ApprovalAction)
_APPROVAL_STATUSES = ", ".join(f"'{value.value}'" for value in ApprovalStatus)


class PlanModel(Base):
    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_plans_id_user"),
        UniqueConstraint(
            "root_plan_id",
            "version",
            name="uq_plans_root_version",
        ),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_plans_user_idempotency",
        ),
        ForeignKeyConstraint(
            ["root_plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plans_root_owner",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["parent_plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plans_parent_owner",
        ),
        CheckConstraint(f"status IN ({_PLAN_STATUSES})", name="ck_plans_status"),
        CheckConstraint(
            f"operation IN ({_PLAN_OPERATIONS})",
            name="ck_plans_operation",
        ),
        CheckConstraint("version >= 1", name="ck_plans_version_positive"),
        CheckConstraint(
            "(version = 1 AND id = root_plan_id AND parent_plan_id IS NULL "
            "AND operation = 'generate' AND adjustment_text IS NULL) OR "
            "(version > 1 AND id <> root_plan_id AND parent_plan_id IS NOT NULL "
            "AND operation = 'adjust' AND adjustment_text IS NOT NULL)",
            name="ck_plans_version_shape",
        ),
        CheckConstraint(
            "(status IN ('draft', 'confirmed', 'superseded', 'completed', "
            "'partially_completed', 'not_completed') AND draft_json IS NOT NULL) "
            "OR (status NOT IN ('draft', 'confirmed', 'superseded', 'completed', "
            "'partially_completed', 'not_completed') "
            "AND draft_json IS NULL)",
            name="ck_plans_draft_shape",
        ),
        CheckConstraint(
            "(status IN ('confirmed', 'completed', 'partially_completed', "
            "'not_completed') AND confirmed_at IS NOT NULL) OR "
            "(status = 'superseded') OR "
            "(status NOT IN ('confirmed', 'completed', 'partially_completed', "
            "'not_completed', 'superseded') AND confirmed_at IS NULL)",
            name="ck_plans_confirmation_shape",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) OR "
            "(status <> 'failed' AND error_code IS NULL)",
            name="ck_plans_error_shape",
        ),
        Index("ix_plans_owner_created", "user_id", "created_at"),
        Index("ix_plans_owner_root_version", "user_id", "root_plan_id", "version"),
        Index(
            "uq_plans_one_confirmed_per_root",
            "root_plan_id",
            unique=True,
            sqlite_where=text(
                "status IN ('confirmed', 'completed', 'partially_completed', "
                "'not_completed')"
            ),
            postgresql_where=text(
                "status IN ('confirmed', 'completed', 'partially_completed', "
                "'not_completed')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    root_plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_plans_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    constraints_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    adjustment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class PlanItemModel(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_plan_items_id_user"),
        ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plan_items_plan_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "plan_id",
            "option_index",
            "item_index",
            name="uq_plan_items_position",
        ),
        CheckConstraint("option_index >= 0", name="ck_plan_items_option_index"),
        CheckConstraint("item_index >= 0", name="ck_plan_items_item_index"),
        CheckConstraint("end_at > start_at", name="ck_plan_items_time_order"),
        CheckConstraint(
            "execution_status IN ('pending', 'visited', 'not_visited')",
            name="ck_plan_items_execution_status",
        ),
        Index("ix_plan_items_plan_position", "plan_id", "option_index", "item_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    option_index: Mapped[int] = mapped_column(Integer, nullable=False)
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    execution_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PlanFeedbackStateModel(Base):
    __tablename__ = "plan_feedback_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plan_feedback_states_plan_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint("revision >= 1", name="ck_plan_feedback_states_revision"),
        CheckConstraint(
            "completion_status IN ('completed', 'partially_completed', 'not_completed')",
            name="ck_plan_feedback_states_completion_status",
        ),
        Index("ix_plan_feedback_states_owner_updated", "user_id", "updated_at"),
    )

    plan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    current_feedback_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preference_suggestion_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanFeedbackAuditModel(Base):
    __tablename__ = "plan_feedback_audits"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_plan_feedback_audits_id_user"),
        ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plan_feedback_audits_plan_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "plan_id", "revision", name="uq_plan_feedback_audits_plan_revision"
        ),
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_plan_feedback_audits_owner_key"
        ),
        CheckConstraint("revision >= 1", name="ck_plan_feedback_audits_revision"),
        CheckConstraint(
            "completion_status IN ('completed', 'partially_completed', 'not_completed')",
            name="ck_plan_feedback_audits_completion_status",
        ),
        Index("ix_plan_feedback_audits_plan_created", "plan_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    visited_plan_item_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    preference_suggestion_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    corrects_feedback_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "plan_feedback_audits.id",
            name="fk_plan_feedback_audits_corrects",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CollectionVisitStateModel(Base):
    __tablename__ = "collection_visit_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_collection_visit_states_collection_owner",
            ondelete="CASCADE",
        ),
    )

    collection_item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    baseline_visited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CollectionVisitSourceModel(Base):
    __tablename__ = "collection_visit_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_item_id", "user_id"],
            ["plan_items.id", "plan_items.user_id"],
            name="fk_collection_visit_sources_plan_item_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["collection_item_id", "user_id"],
            ["collection_items.id", "collection_items.user_id"],
            name="fk_collection_visit_sources_collection_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["feedback_id", "user_id"],
            ["plan_feedback_audits.id", "plan_feedback_audits.user_id"],
            name="fk_collection_visit_sources_feedback_owner",
            ondelete="CASCADE",
        ),
        Index(
            "ix_collection_visit_sources_collection",
            "collection_item_id",
            "user_id",
        ),
    )

    plan_item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    collection_item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    feedback_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalModel(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_approvals_id_user"),
        ForeignKeyConstraint(
            ["target_plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_approvals_plan_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"action IN ({_APPROVAL_ACTIONS})", name="ck_approvals_action"),
        CheckConstraint(
            f"status IN ({_APPROVAL_STATUSES})",
            name="ck_approvals_status",
        ),
        CheckConstraint("expires_at > created_at", name="ck_approvals_expiry_order"),
        CheckConstraint(
            "(status = 'pending' AND decided_at IS NULL) OR "
            "(status <> 'pending' AND decided_at IS NOT NULL)",
            name="ck_approvals_decision_shape",
        ),
        CheckConstraint(
            "(action = 'external_place_supplement' "
            "AND external_requirement_id IS NOT NULL) OR "
            "(action <> 'external_place_supplement' "
            "AND external_requirement_id IS NULL)",
            name="ck_approvals_external_requirement_shape",
        ),
        Index("ix_approvals_owner_status", "user_id", "status", "created_at"),
        Index(
            "uq_approvals_confirm_idempotency",
            "user_id",
            "action",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    target_plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    external_requirement_id: Mapped[str | None] = mapped_column(
        String(41), nullable=True
    )
    display_text: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

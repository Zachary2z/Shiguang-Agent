"""SQLAlchemy persistence for the single structured Memory aggregate."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class MemoryModel(Base):
    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_memories_id_user"),
        ForeignKeyConstraint(
            ["source_feedback_id", "source_plan_id", "user_id"],
            [
                "plan_feedback_audits.id",
                "plan_feedback_audits.plan_id",
                "plan_feedback_audits.user_id",
            ],
            name="fk_memories_feedback_source_owner",
        ),
        CheckConstraint(
            "type IN ('positive_preference', 'negative_preference', "
            "'pace_preference', 'usual_area')",
            name="ck_memories_type",
        ),
        CheckConstraint(
            "source_type IN ('explicit_user', 'feedback_inference')",
            name="ck_memories_source_type",
        ),
        CheckConstraint(
            "confirmation_status = 'confirmed'",
            name="ck_memories_confirmation_status",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_memories_confidence"),
        CheckConstraint("version >= 1", name="ck_memories_version"),
        CheckConstraint(
            "(source_type = 'feedback_inference' AND source_feedback_id IS NOT NULL "
            "AND source_plan_id IS NOT NULL) OR "
            "(source_type = 'explicit_user' AND source_feedback_id IS NULL "
            "AND source_plan_id IS NULL)",
            name="ck_memories_source_shape",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_memories_expiry",
        ),
        Index("ix_memories_owner_updated", "user_id", "updated_at"),
        Index(
            "ix_memories_effective",
            "user_id",
            "type",
            sqlite_where=text("disabled_at IS NULL AND deleted_at IS NULL"),
            postgresql_where=text("disabled_at IS NULL AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_memories_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    source_feedback_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confirmation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class MemorySuggestionDecisionModel(Base):
    __tablename__ = "memory_suggestion_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["suggestion_id", "plan_id", "user_id"],
            [
                "plan_feedback_audits.id",
                "plan_feedback_audits.plan_id",
                "plan_feedback_audits.user_id",
            ],
            name="fk_memory_suggestion_decisions_feedback_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["memory_id", "user_id"],
            ["memories.id", "memories.user_id"],
            name="fk_memory_suggestion_decisions_memory_owner",
        ),
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_memory_suggestion_decisions_owner_key"
        ),
        CheckConstraint(
            "decision IN ('confirmed', 'rejected')",
            name="ck_memory_suggestion_decisions_decision",
        ),
        CheckConstraint(
            "(decision = 'confirmed' AND memory_id IS NOT NULL) OR "
            "(decision = 'rejected' AND memory_id IS NULL)",
            name="ck_memory_suggestion_decisions_shape",
        ),
        Index("ix_memory_suggestion_decisions_owner", "user_id", "decided_at"),
    )

    suggestion_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    memory_id: Mapped[str | None] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryOperationModel(Base):
    __tablename__ = "memory_operations"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_memory_operations_owner_key"),
        ForeignKeyConstraint(
            ["memory_id", "user_id"],
            ["memories.id", "memories.user_id"],
            name="fk_memory_operations_memory_owner",
        ),
        CheckConstraint(
            "operation IN ('create', 'update', 'delete')",
            name="ck_memory_operations_operation",
        ),
        Index("ix_memory_operations_owner_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    memory_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryPlanUsageModel(Base):
    __tablename__ = "memory_plan_usages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["memory_id", "user_id"],
            ["memories.id", "memories.user_id"],
            name="fk_memory_plan_usages_memory_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_memory_plan_usages_plan_owner",
            ondelete="CASCADE",
        ),
        Index("ix_memory_plan_usages_owner_used", "user_id", "used_at"),
    )

    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    basis: Mapped[str] = mapped_column(String(500), nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

"""Hashed bearer records for read-only plan sharing."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.time import utc_now
from app.infrastructure.db.base import Base


class PlanShareLinkModel(Base):
    __tablename__ = "plan_share_links"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_plan_share_links_token_hash"),
        ForeignKeyConstraint(
            ["plan_id", "user_id"],
            ["plans.id", "plans.user_id"],
            name="fk_plan_share_links_plan_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(token_hash) = 64 AND token_hash = lower(token_hash)",
            name="ck_plan_share_links_token_hash_format",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_plan_share_links_expiry",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_plan_share_links_revocation",
        ),
        Index(
            "uq_plan_share_links_one_unrevoked_per_plan",
            "plan_id",
            unique=True,
            sqlite_where=text("revoked_at IS NULL"),
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_plan_share_links_owner_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

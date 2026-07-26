"""SQLAlchemy persistence for durable browser sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class BrowserSessionModel(Base):
    __tablename__ = "web_sessions"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 36 AND substr(id, 1, 4) = 'wbs_'",
            name="ck_web_sessions_id_format",
        ),
        CheckConstraint(
            "length(token_hash) = 64 AND token_hash = lower(token_hash)",
            name="ck_web_sessions_token_hash_format",
        ),
        CheckConstraint(
            "length(csrf_token_hash) = 64 AND csrf_token_hash = lower(csrf_token_hash)",
            name="ck_web_sessions_csrf_hash_format",
        ),
        CheckConstraint("expires_at > created_at", name="ck_web_sessions_expiry_order"),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_web_sessions_revocation_order",
        ),
        Index("ix_web_sessions_user_expires", "user_id", "expires_at"),
        Index("ix_web_sessions_active_expiry", "revoked_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", name="fk_web_sessions_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

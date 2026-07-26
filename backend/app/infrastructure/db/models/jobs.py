"""SQLAlchemy ScheduledJob persistence on the one application Base."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.jobs import JobStatus
from app.domain.time import utc_now
from app.infrastructure.db.base import Base

_JOB_STATUSES = ", ".join(f"'{status.value}'" for status in JobStatus)


class ScheduledJobModel(Base):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_scheduled_jobs_user_idempotency",
        ),
        CheckConstraint(f"status IN ({_JOB_STATUSES})", name="ck_scheduled_jobs_status"),
        CheckConstraint(
            "attempt BETWEEN 0 AND max_attempts",
            name="ck_scheduled_jobs_attempt_range",
        ),
        CheckConstraint(
            "max_attempts BETWEEN 1 AND 3",
            name="ck_scheduled_jobs_max_attempts",
        ),
        CheckConstraint(
            "(status = 'running' AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'running' AND worker_id IS NULL AND lease_expires_at IS NULL)",
            name="ck_scheduled_jobs_lease_shape",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_scheduled_jobs_time_order",
        ),
        Index("ix_scheduled_jobs_claim", "status", "run_at", "created_at"),
        Index("ix_scheduled_jobs_trace_sequence", "trace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

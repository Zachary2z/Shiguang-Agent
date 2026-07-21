"""SQLAlchemy persistence models for AgentRun and ToolRun."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.runs.statuses import AgentRunStatus, ToolRunStatus
from app.domain.time import utc_now
from app.infrastructure.db.base import Base

_AGENT_STATUS_SQL = ", ".join(f"'{status.value}'" for status in AgentRunStatus)
_TOOL_STATUS_SQL = ", ".join(f"'{status.value}'" for status in ToolRunStatus)


class AgentRunModel(Base):
    """One durable application-level execution record."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("trace_id", name="uq_agent_runs_trace_id"),
        CheckConstraint(f"status IN ({_AGENT_STATUS_SQL})", name="ck_agent_runs_status"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_agent_runs_input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_agent_runs_output_tokens_nonnegative",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_agent_runs_total_tokens_nonnegative",
        ),
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0",
            name="ck_agent_runs_estimated_cost_nonnegative",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR (duration_ms >= 0 AND duration_ms <= 60000)",
            name="ck_agent_runs_duration_bound",
        ),
        CheckConstraint(
            "estimated_cost IS NULL OR cost_currency IS NOT NULL",
            name="ck_agent_runs_known_cost_currency",
        ),
        CheckConstraint(
            "(estimated_cost IS NULL AND cost_unknown_reason IS NOT NULL) OR "
            "(estimated_cost IS NOT NULL AND cost_unknown_reason IS NULL)",
            name="ck_agent_runs_cost_known_or_explained",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_agent_runs_time_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    model_names_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    model_calls_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    cost_estimation_source: Mapped[str] = mapped_column(String(64), nullable=False)
    cost_unknown_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ToolRunModel(Base):
    """One ordered, safe record of a requested tool call."""

    __tablename__ = "tool_runs"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "sequence", name="uq_tool_runs_run_sequence"),
        CheckConstraint("sequence > 0", name="ck_tool_runs_sequence_positive"),
        CheckConstraint(f"status IN ({_TOOL_STATUS_SQL})", name="ck_tool_runs_status"),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_tool_runs_latency_nonnegative",
        ),
        CheckConstraint(
            "length(arguments_fingerprint) = 64",
            name="ck_tool_runs_fingerprint_length",
        ),
        CheckConstraint(
            "length(input_summary) <= 512",
            name="ck_tool_runs_input_summary_length",
        ),
        CheckConstraint(
            "output_summary IS NULL OR length(output_summary) <= 512",
            name="ck_tool_runs_output_summary_length",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_tool_runs_time_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

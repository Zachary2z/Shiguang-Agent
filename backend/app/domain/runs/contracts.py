"""Validated application contracts for tracked Agent and tool runs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.runs.identifiers import validate_trace_id
from app.domain.runs.statuses import AgentRunStatus, ToolRunStatus
from nanobot_core.providers import FinishReason, TokenUsage


class ModelCallStatus(StrEnum):
    """Persistable outcomes for model-call metadata entries."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelCallSummary(BaseModel):
    """One provider invocation's metadata; content and prompts are intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sequence: int = Field(ge=1)
    status: ModelCallStatus
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    usage: TokenUsage | None = None
    latency_ms: int = Field(ge=0)
    finish_reason: FinishReason | None = None
    error_code: str | None = Field(default=None, min_length=1, max_length=64)
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    cost_estimation_source: str = Field(min_length=1, max_length=64)
    cost_unknown_reason: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.status is ModelCallStatus.SUCCEEDED:
            if self.model_name is None or self.usage is None or self.finish_reason is None:
                raise ValueError("successful model calls require model, usage, and finish reason")
            if self.error_code is not None:
                raise ValueError("successful model calls cannot have an error code")
        elif self.finish_reason is not None:
            raise ValueError("unfinished model calls cannot have a finish reason")
        if self.estimated_cost is not None:
            if self.cost_currency is None or self.cost_unknown_reason is not None:
                raise ValueError("known cost requires currency and no unknown reason")
        elif self.cost_unknown_reason is None:
            raise ValueError("unknown cost requires an explicit reason")
        return self


class ToolRunSummary(BaseModel):
    """Safe, queryable metadata for one requested tool call."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str
    sequence: int = Field(ge=1)
    tool_call_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    arguments_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_summary: str = Field(max_length=512)
    status: ToolRunStatus
    output_summary: str | None = Field(default=None, max_length=512)
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, min_length=1, max_length=64)
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime


class AgentRunSummary(BaseModel):
    """Complete application-level run summary returned by trace lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str
    trace_id: str
    user_id: str | None
    session_id: str | None
    intent: str
    workflow: str
    status: AgentRunStatus
    model_names: list[str]
    model_calls: list[ModelCallSummary]
    usage: TokenUsage
    estimated_cost: Decimal | None
    cost_currency: str | None
    cost_estimation_source: str
    cost_unknown_reason: str | None
    duration_ms: int | None
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tool_runs: list[ToolRunSummary]
    ended_due_to_timeout: bool
    ended_due_to_tool_limit: bool
    ended_due_to_repeated_tool_call: bool
    ended_due_to_external_cancellation: bool

    @field_validator("trace_id")
    @classmethod
    def validate_summary_trace_id(cls, value: str) -> str:
        return validate_trace_id(value)

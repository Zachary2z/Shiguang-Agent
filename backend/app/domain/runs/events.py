"""Safe public progress events attached to the existing AgentRun."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.identifiers import validate_trace_id
from app.domain.public_data import validate_safe_public_data
from app.domain.time import required_utc

MAX_RUN_EVENT_SUMMARY_BYTES = 1024


class RunEventType(StrEnum):
    RUN_STARTED = "run.started"
    STAGE_CHANGED = "stage.changed"
    TOOL_COMPLETED = "tool.completed"
    APPROVAL_REQUIRED = "approval.required"
    RESULT_UPDATED = "result.updated"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


TERMINAL_RUN_EVENT_TYPES = frozenset(
    {RunEventType.RUN_COMPLETED, RunEventType.RUN_FAILED}
)


class PublicRunEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    trace_id: str
    event_type: RunEventType
    sequence: int = Field(ge=1)
    summary: dict[str, Any] = Field(default_factory=dict, repr=False)
    created_at: datetime

    @field_validator("trace_id")
    @classmethod
    def valid_trace_id(cls, value: str) -> str:
        return validate_trace_id(value)

    @field_validator("summary")
    @classmethod
    def safe_summary(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_safe_public_data(
            value,
            maximum_bytes=MAX_RUN_EVENT_SUMMARY_BYTES,
        )

    @field_validator("created_at")
    @classmethod
    def utc_created_at(cls, value: datetime) -> datetime:
        return required_utc(value)


__all__ = [
    "MAX_RUN_EVENT_SUMMARY_BYTES",
    "PublicRunEvent",
    "RunEventType",
    "TERMINAL_RUN_EVENT_TYPES",
]

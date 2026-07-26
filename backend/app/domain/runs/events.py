"""Explicit public progress contracts attached to the existing AgentRun."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.identifiers import validate_trace_id
from app.domain.runs.statuses import AgentRunStatus, ToolRunStatus
from app.domain.time import required_utc


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


class _RunEventSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class RunStartedSummary(_RunEventSummary):
    status: Literal[AgentRunStatus.RUNNING]


class StageChangedSummary(_RunEventSummary):
    stage: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ToolCompletedSummary(_RunEventSummary):
    tool_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    status: ToolRunStatus
    tool_sequence: int = Field(ge=1)


class ApprovalRequiredSummary(_RunEventSummary):
    approval_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ResultUpdatedSummary(_RunEventSummary):
    status: AgentRunStatus
    content_sha256: str | None = None

    @field_validator("content_sha256")
    @classmethod
    def valid_content_sha256(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(
                "content_sha256 must be 64 lowercase hexadecimal characters"
            )
        return value


class RunCompletedSummary(_RunEventSummary):
    status: Literal[
        AgentRunStatus.SUCCEEDED,
        AgentRunStatus.PARTIALLY_SUCCEEDED,
    ]


class RunFailedSummary(_RunEventSummary):
    status: Literal[AgentRunStatus.FAILED, AgentRunStatus.CANCELLED]
    error_code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


RunEventSummary = (
    RunStartedSummary
    | StageChangedSummary
    | ToolCompletedSummary
    | ApprovalRequiredSummary
    | ResultUpdatedSummary
    | RunCompletedSummary
    | RunFailedSummary
)


def serialize_run_event_summary(
    event_type: RunEventType,
    summary: RunEventSummary,
) -> dict[str, object]:
    """Serialize only the summary model assigned to this public event type."""

    if _summary_event_type(summary) is not event_type:
        raise ValueError("RunEvent summary does not match its event type")
    return summary.model_dump(mode="json", exclude_none=True)


def parse_run_event_summary(
    event_type: RunEventType,
    value: dict[str, object],
) -> RunEventSummary:
    """Validate persisted JSON through the same explicit public contract."""

    if event_type is RunEventType.RUN_STARTED:
        return RunStartedSummary.model_validate(value, strict=False)
    if event_type is RunEventType.STAGE_CHANGED:
        return StageChangedSummary.model_validate(value, strict=False)
    if event_type is RunEventType.TOOL_COMPLETED:
        return ToolCompletedSummary.model_validate(value, strict=False)
    if event_type is RunEventType.APPROVAL_REQUIRED:
        return ApprovalRequiredSummary.model_validate(value, strict=False)
    if event_type is RunEventType.RESULT_UPDATED:
        return ResultUpdatedSummary.model_validate(value, strict=False)
    if event_type is RunEventType.RUN_COMPLETED:
        return RunCompletedSummary.model_validate(value, strict=False)
    return RunFailedSummary.model_validate(value, strict=False)


def _summary_event_type(summary: RunEventSummary) -> RunEventType:
    if isinstance(summary, RunStartedSummary):
        return RunEventType.RUN_STARTED
    if isinstance(summary, StageChangedSummary):
        return RunEventType.STAGE_CHANGED
    if isinstance(summary, ToolCompletedSummary):
        return RunEventType.TOOL_COMPLETED
    if isinstance(summary, ApprovalRequiredSummary):
        return RunEventType.APPROVAL_REQUIRED
    if isinstance(summary, ResultUpdatedSummary):
        return RunEventType.RESULT_UPDATED
    if isinstance(summary, RunCompletedSummary):
        return RunEventType.RUN_COMPLETED
    if isinstance(summary, RunFailedSummary):
        return RunEventType.RUN_FAILED
    raise TypeError("RunEvent summary must use an explicit public summary model")


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
    summary: RunEventSummary = Field(repr=False)
    created_at: datetime

    @field_validator("trace_id")
    @classmethod
    def valid_trace_id(cls, value: str) -> str:
        return validate_trace_id(value)

    @field_validator("summary", mode="before")
    @classmethod
    def require_explicit_summary(cls, value: object) -> object:
        if not isinstance(value, _RunEventSummary):
            raise ValueError("summary must be an explicit public RunEvent model")
        return value

    @field_validator("created_at")
    @classmethod
    def utc_created_at(cls, value: datetime) -> datetime:
        return required_utc(value)

    @model_validator(mode="after")
    def matching_summary(self) -> PublicRunEvent:
        serialize_run_event_summary(self.event_type, self.summary)
        return self


__all__ = [
    "ApprovalRequiredSummary",
    "PublicRunEvent",
    "ResultUpdatedSummary",
    "RunCompletedSummary",
    "RunEventSummary",
    "RunEventType",
    "RunFailedSummary",
    "RunStartedSummary",
    "StageChangedSummary",
    "TERMINAL_RUN_EVENT_TYPES",
    "ToolCompletedSummary",
    "parse_run_event_summary",
    "serialize_run_event_summary",
]

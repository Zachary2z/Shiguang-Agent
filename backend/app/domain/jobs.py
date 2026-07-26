"""Safe, provider-neutral ScheduledJob contracts."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.identifiers import validate_trace_id, validate_user_id
from app.domain.public_data import validate_safe_public_data
from app.domain.time import required_utc

MAX_JOB_ATTEMPTS = 3
MAX_JOB_PAYLOAD_BYTES = 4096
MAX_JOB_SUMMARY_BYTES = 1024
JOB_LEASE_SECONDS = 60
JOB_RETRY_DELAYS_SECONDS = (5, 30)

_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
)


def validate_safe_label(value: str, *, name: str) -> str:
    if not isinstance(value, str) or _SAFE_LABEL.fullmatch(value) is None:
        raise ValueError(f"{name} must be a safe label")
    return value


def validate_safe_job_data(
    value: dict[str, Any],
    *,
    maximum_bytes: int = MAX_JOB_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Reject secrets and unbounded/private material at the durable boundary."""

    return validate_safe_public_data(value, maximum_bytes=maximum_bytes)


class _JobModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class JobCreate(_JobModel):
    user_id: str
    job_type: str
    payload: dict[str, Any] = Field(default_factory=dict, repr=False)
    run_at: datetime
    max_attempts: int = Field(default=MAX_JOB_ATTEMPTS, ge=1, le=MAX_JOB_ATTEMPTS)
    idempotency_key: str = Field(repr=False)
    trace_id: str | None = None

    @field_validator("job_type", "idempotency_key")
    @classmethod
    def safe_labels(cls, value: str, info: Any) -> str:
        return validate_safe_label(value, name=str(info.field_name))

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("trace_id")
    @classmethod
    def valid_trace_id(cls, value: str | None) -> str | None:
        return None if value is None else validate_trace_id(value)

    @field_validator("run_at")
    @classmethod
    def utc_run_at(cls, value: datetime) -> datetime:
        return required_utc(value)

    @field_validator("payload")
    @classmethod
    def safe_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_safe_job_data(value)


class ScheduledJob(_JobModel):
    id: str
    user_id: str
    job_type: str
    payload: dict[str, Any] = Field(repr=False)
    run_at: datetime
    status: JobStatus
    attempt: int
    max_attempts: int
    idempotency_key: str = Field(repr=False)
    trace_id: str | None
    worker_id: str | None
    lease_expires_at: datetime | None
    last_error_code: str | None
    result_summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    replayed: bool = False

    @field_validator(
        "run_at",
        "lease_expires_at",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
    )
    @classmethod
    def utc_datetimes(cls, value: datetime | None) -> datetime | None:
        return None if value is None else required_utc(value)


class JobConflictError(RuntimeError):
    """An idempotency key was reused for different job content."""


__all__ = [
    "JOB_LEASE_SECONDS",
    "JOB_RETRY_DELAYS_SECONDS",
    "MAX_JOB_ATTEMPTS",
    "MAX_JOB_PAYLOAD_BYTES",
    "MAX_JOB_SUMMARY_BYTES",
    "JobConflictError",
    "JobCreate",
    "JobStatus",
    "ScheduledJob",
    "TERMINAL_JOB_STATUSES",
    "validate_safe_job_data",
    "validate_safe_label",
]

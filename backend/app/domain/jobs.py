"""Safe, provider-neutral ScheduledJob contracts."""

from __future__ import annotations

import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.identifiers import validate_trace_id, validate_user_id
from app.domain.time import required_utc

MAX_JOB_ATTEMPTS = 3
MAX_JOB_PAYLOAD_BYTES = 4096
JOB_LEASE_SECONDS = 60
JOB_HEARTBEAT_SECONDS = 20
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


def validate_job_payload(value: dict[str, object]) -> dict[str, object]:
    """Validate bounded JSON for internal persistence, never public serialization."""

    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("job payload must contain finite JSON values") from error
    if len(encoded.encode("utf-8")) > MAX_JOB_PAYLOAD_BYTES:
        raise ValueError("job payload exceeds its size limit")
    return value


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
    payload: dict[str, object] = Field(default_factory=dict, repr=False)
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
    def bounded_payload(cls, value: dict[str, object]) -> dict[str, object]:
        return validate_job_payload(value)


class JobResultSummary(_JobModel):
    """The complete allowlisted public result surface for infrastructure jobs."""

    outcome: str
    content_sha256: str | None = None

    @field_validator("outcome")
    @classmethod
    def safe_outcome(cls, value: str) -> str:
        return validate_safe_label(value, name="outcome")

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


class ScheduledJob(_JobModel):
    id: str
    user_id: str
    job_type: str
    payload: dict[str, object] = Field(repr=False)
    run_at: datetime
    status: JobStatus
    attempt: int
    max_attempts: int
    idempotency_key: str = Field(repr=False)
    trace_id: str | None
    worker_id: str | None
    lease_expires_at: datetime | None
    last_error_code: str | None
    result_summary: JobResultSummary | None
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
    "JOB_HEARTBEAT_SECONDS",
    "JOB_RETRY_DELAYS_SECONDS",
    "MAX_JOB_ATTEMPTS",
    "MAX_JOB_PAYLOAD_BYTES",
    "JobConflictError",
    "JobCreate",
    "JobResultSummary",
    "JobStatus",
    "ScheduledJob",
    "TERMINAL_JOB_STATUSES",
    "validate_job_payload",
    "validate_safe_label",
]

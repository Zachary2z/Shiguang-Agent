"""Safe, provider-neutral ScheduledJob contracts."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from enum import StrEnum
from pathlib import PurePath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.identifiers import validate_trace_id, validate_user_id
from app.domain.time import required_utc

MAX_JOB_ATTEMPTS = 3
MAX_JOB_PAYLOAD_BYTES = 4096
MAX_JOB_SUMMARY_BYTES = 1024
JOB_LEASE_SECONDS = 60
JOB_RETRY_DELAYS_SECONDS = (5, 30)

_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BASE64_BLOB = re.compile(r"^[A-Za-z0-9+/]{64,}={0,2}$")
_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "base64",
        "cookie",
        "file_key",
        "full_prompt",
        "model_response",
        "password",
        "path",
        "prompt",
        "secret",
        "token",
    }
)


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

    if not isinstance(value, dict):
        raise ValueError("job data must be an object")
    _validate_safe_value(value)
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > maximum_bytes:
        raise ValueError("job data exceeds its safe size limit")
    return value


def _validate_safe_value(value: Any) -> None:
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("job data numbers must be finite")
        return
    if isinstance(value, str):
        if len(value) > 512:
            raise ValueError("job data strings are too long")
        lowered = value.casefold()
        if (
            "bearer " in lowered
            or "authorization:" in lowered
            or "cookie:" in lowered
            or "base64" in lowered
            or _BASE64_BLOB.fullmatch(value) is not None
            or value.startswith(("/", "~"))
            or PurePath(value).is_absolute()
        ):
            raise ValueError("job data contains private or credential material")
        return
    if isinstance(value, list):
        if len(value) > 50:
            raise ValueError("job data arrays are too large")
        for item in value:
            _validate_safe_value(item)
        return
    if isinstance(value, dict):
        if len(value) > 50:
            raise ValueError("job data objects are too large")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise ValueError("job data keys must be bounded strings")
            normalized = key.casefold().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ValueError("job data contains a forbidden field")
            _validate_safe_value(item)
        return
    raise ValueError("job data contains an unsupported value")


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

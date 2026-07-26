"""Internal ScheduledJob payload and explicit public result contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.jobs import JobCreate, JobResultSummary

USER_ID = "usr_0123456789abcdef0123456789abcdef"
CONTENT_SHA256 = "a" * 64


def _request(payload: dict[str, object]) -> JobCreate:
    return JobCreate(
        user_id=USER_ID,
        job_type="deterministic.noop",
        payload=payload,
        run_at=datetime(2026, 7, 26, tzinfo=UTC),
        idempotency_key="safe-job",
    )


def test_internal_payload_is_bounded_json_not_a_public_summary() -> None:
    payload = {
        "apiKey": "internal-value",
        "access_token": "internal-value",
        "modelResponse": "internal-value",
        "content_sha256": CONTENT_SHA256,
    }

    request = _request(payload)

    assert request.payload == payload
    assert repr(request).find("internal-value") == -1


def test_internal_payload_rejects_non_json_and_oversized_data() -> None:
    with pytest.raises(ValidationError, match="finite JSON"):
        _request({"value": float("nan")})
    with pytest.raises(ValidationError, match="finite JSON"):
        _request({"value": b"not-json"})
    with pytest.raises(ValidationError, match="size limit"):
        _request({"value": "x" * 4096})


@pytest.mark.parametrize(
    "field",
    [
        "apiKey",
        "access_token",
        "modelResponse",
        "file_key",
        "path",
        "prompt",
        "authorization",
        "cookie",
    ],
)
def test_public_job_result_rejects_every_non_allowlisted_field(field: str) -> None:
    with pytest.raises(ValidationError):
        JobResultSummary.model_validate(
            {"outcome": "completed", field: "private-value"},
            strict=True,
        )


def test_public_job_result_accepts_explicit_content_hash() -> None:
    summary = JobResultSummary(
        outcome="completed",
        content_sha256=CONTENT_SHA256,
    )

    assert summary.model_dump(exclude_none=True) == {
        "outcome": "completed",
        "content_sha256": CONTENT_SHA256,
    }

"""ScheduledJob public-boundary safety tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.jobs import JobCreate, validate_safe_job_data

USER_ID = "usr_0123456789abcdef0123456789abcdef"


def _request(payload: dict[str, object]) -> JobCreate:
    return JobCreate(
        user_id=USER_ID,
        job_type="deterministic.noop",
        payload=payload,
        run_at=datetime(2026, 7, 26, tzinfo=UTC),
        idempotency_key="safe-job",
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"api_key": "value"},
        {"authorization": "value"},
        {"cookie": "value"},
        {"prompt": "private input"},
        {"model_response": "private output"},
        {"image": "base64"},
        {"path": "private"},
        {"value": "Bearer credential"},
        {"value": "/Users/person/private.txt"},
    ],
)
def test_job_payload_rejects_sensitive_material(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _request(payload)


def test_job_payload_and_summary_accept_only_bounded_safe_data() -> None:
    request = _request({"operation": "probe", "count": 1})

    assert request.payload == {"operation": "probe", "count": 1}
    assert validate_safe_job_data({"outcome": "completed"}, maximum_bytes=64) == {
        "outcome": "completed"
    }
    with pytest.raises(ValueError, match="size limit"):
        validate_safe_job_data(
            {"value": "this is safe bounded content"},
            maximum_bytes=32,
        )

"""Explicit RunEvent summaries and SSE serialization boundary tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.application.sse import encode_run_event
from app.domain.runs.events import (
    ApprovalRequiredSummary,
    PublicRunEvent,
    ResultUpdatedSummary,
    RunCompletedSummary,
    RunEventSummary,
    RunEventType,
    RunFailedSummary,
    RunStartedSummary,
    StageChangedSummary,
    ToolCompletedSummary,
    serialize_run_event_summary,
)
from app.domain.runs.statuses import AgentRunStatus, ToolRunStatus

TRACE_ID = "trc_0123456789abcdef0123456789abcdef"
NOW = datetime(2026, 7, 26, tzinfo=UTC)
CONTENT_SHA256 = "a" * 64


def _event(
    event_type: RunEventType,
    summary: RunEventSummary,
    *,
    sequence: int = 1,
) -> PublicRunEvent:
    return PublicRunEvent(
        trace_id=TRACE_ID,
        event_type=event_type,
        sequence=sequence,
        summary=summary,
        created_at=NOW,
    )


def test_all_public_event_types_use_their_explicit_summary_model() -> None:
    events = (
        _event(
            RunEventType.RUN_STARTED,
            RunStartedSummary(status=AgentRunStatus.RUNNING),
        ),
        _event(
            RunEventType.STAGE_CHANGED,
            StageChangedSummary(stage="execution"),
        ),
        _event(
            RunEventType.TOOL_COMPLETED,
            ToolCompletedSummary(
                tool_name="fixture.tool",
                status=ToolRunStatus.SUCCEEDED,
                tool_sequence=1,
            ),
        ),
        _event(
            RunEventType.APPROVAL_REQUIRED,
            ApprovalRequiredSummary(approval_id="approval_1"),
        ),
        _event(
            RunEventType.RESULT_UPDATED,
            ResultUpdatedSummary(
                status=AgentRunStatus.SUCCEEDED,
                content_sha256=CONTENT_SHA256,
            ),
        ),
        _event(
            RunEventType.RUN_COMPLETED,
            RunCompletedSummary(status=AgentRunStatus.SUCCEEDED),
        ),
        _event(
            RunEventType.RUN_FAILED,
            RunFailedSummary(
                status=AgentRunStatus.FAILED,
                error_code="RUN_INTERNAL_ERROR",
            ),
        ),
    )

    assert tuple(event.event_type for event in events) == tuple(RunEventType)
    assert all(event.summary.model_dump(exclude_none=True) for event in events)


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
        "headers",
    ],
)
def test_common_sensitive_aliases_have_no_public_summary_field(field: str) -> None:
    with pytest.raises(ValidationError):
        ResultUpdatedSummary.model_validate(
            {
                "status": AgentRunStatus.SUCCEEDED,
                field: "private-value",
            },
            strict=True,
        )


def test_content_sha256_is_valid_only_in_its_explicit_field() -> None:
    summary = ResultUpdatedSummary(
        status=AgentRunStatus.SUCCEEDED,
        content_sha256=CONTENT_SHA256,
    )
    event = _event(RunEventType.RESULT_UPDATED, summary)

    frame = encode_run_event(event)
    data_line = next(
        line.removeprefix("data: ")
        for line in frame.splitlines()
        if line.startswith("data: ")
    )
    payload = json.loads(data_line)

    assert payload["summary"] == {
        "content_sha256": CONTENT_SHA256,
        "status": "succeeded",
    }
    assert "prompt" not in frame.casefold()
    assert "modelresponse" not in frame.casefold()


def test_event_type_and_summary_type_must_match() -> None:
    summary = StageChangedSummary(stage="execution")

    with pytest.raises(ValueError, match="does not match"):
        serialize_run_event_summary(RunEventType.RUN_STARTED, summary)
    with pytest.raises(ValidationError, match="does not match"):
        _event(RunEventType.RUN_STARTED, summary)


def test_public_event_rejects_arbitrary_summary_dict() -> None:
    with pytest.raises(ValidationError, match="explicit public RunEvent model"):
        PublicRunEvent.model_validate(
            {
                "trace_id": TRACE_ID,
                "event_type": RunEventType.RESULT_UPDATED,
                "sequence": 1,
                "summary": {
                    "status": AgentRunStatus.SUCCEEDED,
                    "apiKey": "private-value",
                },
                "created_at": NOW,
            },
            strict=True,
        )

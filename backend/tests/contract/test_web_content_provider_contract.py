from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.web import (
    WebFetchDiagnostics,
    WebFetchFailure,
    WebFetchFailureCode,
    WebFetchOutcome,
    WebPageContent,
    WebPageMetadata,
    WebRecoveryAction,
)
from app.providers.web import WebContentProvider

NOW = datetime(2026, 7, 22, tzinfo=UTC)


def test_success_contract_contains_only_normalized_safe_content() -> None:
    result = WebPageContent(
        normalized_url="https://example.com/source",
        final_url="https://example.com/article",
        title="A page",
        text="Readable body",
        metadata=WebPageMetadata(
            description="Summary",
            canonical_url="https://example.com/canonical",
            open_graph_title="OG title",
            open_graph_description="OG summary",
            open_graph_site_name="Example",
        ),
        content_type="text/html",
        fetched_at=NOW,
        diagnostics=WebFetchDiagnostics(
            http_status=200,
            redirect_count=1,
            decoded_byte_size=100,
        ),
    )

    assert result.outcome is WebFetchOutcome.SUCCESS
    payload = result.model_dump(mode="json")
    assert payload["normalized_url"] == "https://example.com/source"
    assert payload["final_url"] == "https://example.com/article"
    forbidden = {
        "html",
        "raw_html",
        "headers",
        "cookies",
        "authorization",
        "response",
        "exception",
        "stack",
        "file_path",
        "ip_address",
    }
    assert forbidden.isdisjoint(payload)
    assert "Readable body" not in repr(result)
    assert "example.com/source" not in repr(result)


@pytest.mark.parametrize("code", list(WebFetchFailureCode))
def test_failure_contract_has_fixed_safe_recovery(code: WebFetchFailureCode) -> None:
    status = 503 if code is WebFetchFailureCode.HTTP_STATUS else None
    failure = WebFetchFailure.for_code(code, http_status=status)

    public = failure.to_public_dict()
    assert public["code"] == code.value
    assert public["recovery_actions"] == (
        WebRecoveryAction.SUPPLY_TEXT.value,
        WebRecoveryAction.SEND_SCREENSHOT.value,
    )
    assert "url" not in public
    assert "exception" not in public
    assert "traceback" not in public


def test_failure_contract_rejects_forged_semantics() -> None:
    with pytest.raises(ValidationError):
        WebFetchFailure(
            code=WebFetchFailureCode.TIMEOUT,
            summary="secret exception text",
            retryable=False,
        )
    with pytest.raises(ValidationError):
        WebFetchFailure(
            outcome=WebFetchOutcome.SUCCESS,
            code=WebFetchFailureCode.TIMEOUT,
            summary="The public web page request timed out.",
            retryable=True,
        )
    with pytest.raises(ValidationError):
        WebFetchFailure(
            code=WebFetchFailureCode.TIMEOUT,
            summary="The public web page request timed out.",
            retryable=True,
            recovery_actions=(),
        )


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(400, False), (404, False), (429, True), (500, True), (503, True)],
)
def test_http_failure_retryability_is_fixed_by_status(status: int, retryable: bool) -> None:
    failure = WebFetchFailure.for_code(WebFetchFailureCode.HTTP_STATUS, http_status=status)
    assert failure.retryable is retryable


def test_provider_contract_is_abstract() -> None:
    with pytest.raises(TypeError):
        WebContentProvider()

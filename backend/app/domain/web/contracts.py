"""Provider-neutral contracts for safe public web content retrieval."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.time import require_aware_utc
from app.domain.web.security import UrlPolicyError, validate_web_url


class WebContentModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class WebFetchOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class WebFetchFailureCode(StrEnum):
    INVALID_URL = "WEB_INVALID_URL"
    TARGET_BLOCKED = "WEB_TARGET_BLOCKED"
    DNS_FAILED = "WEB_DNS_FAILED"
    CONNECTION_FAILED = "WEB_CONNECTION_FAILED"
    TIMEOUT = "WEB_TIMEOUT"
    REDIRECT_BLOCKED = "WEB_REDIRECT_BLOCKED"
    REDIRECT_LOOP = "WEB_REDIRECT_LOOP"
    REDIRECT_LIMIT = "WEB_REDIRECT_LIMIT"
    HTTP_STATUS = "WEB_HTTP_STATUS"
    CONTENT_TYPE_UNSUPPORTED = "WEB_CONTENT_TYPE_UNSUPPORTED"
    RESPONSE_TOO_LARGE = "WEB_RESPONSE_TOO_LARGE"
    CONTENT_UNREADABLE = "WEB_CONTENT_UNREADABLE"
    RESPONSE_MALFORMED = "WEB_RESPONSE_MALFORMED"
    UNKNOWN = "WEB_FETCH_UNKNOWN"


class WebRecoveryAction(StrEnum):
    SUPPLY_TEXT = "supply_text"
    SEND_SCREENSHOT = "send_screenshot"


_FAILURE_SUMMARIES = {
    WebFetchFailureCode.INVALID_URL: "The web address is invalid.",
    WebFetchFailureCode.TARGET_BLOCKED: "The web target is blocked by the safety policy.",
    WebFetchFailureCode.DNS_FAILED: "The web address could not be resolved.",
    WebFetchFailureCode.CONNECTION_FAILED: "The public web page could not be reached.",
    WebFetchFailureCode.TIMEOUT: "The public web page request timed out.",
    WebFetchFailureCode.REDIRECT_BLOCKED: "The web page redirect was blocked.",
    WebFetchFailureCode.REDIRECT_LOOP: "The web page contains a redirect loop.",
    WebFetchFailureCode.REDIRECT_LIMIT: "The web page exceeded the redirect limit.",
    WebFetchFailureCode.HTTP_STATUS: "The web page returned an unsuccessful status.",
    WebFetchFailureCode.CONTENT_TYPE_UNSUPPORTED: "The web page type is not supported.",
    WebFetchFailureCode.RESPONSE_TOO_LARGE: "The web page exceeds the size limit.",
    WebFetchFailureCode.CONTENT_UNREADABLE: "The web page contains no readable text.",
    WebFetchFailureCode.RESPONSE_MALFORMED: "The web page response is malformed.",
    WebFetchFailureCode.UNKNOWN: "The web page could not be fetched.",
}

_RETRYABLE_FAILURES = {
    WebFetchFailureCode.DNS_FAILED,
    WebFetchFailureCode.CONNECTION_FAILED,
    WebFetchFailureCode.TIMEOUT,
}


class WebPageMetadata(WebContentModel):
    """A fixed metadata allowlist; arbitrary meta tags and script data have no field."""

    description: str | None = Field(default=None, max_length=1000)
    canonical_url: str | None = Field(default=None, max_length=2048, repr=False)
    open_graph_title: str | None = Field(default=None, max_length=300)
    open_graph_description: str | None = Field(default=None, max_length=1000)
    open_graph_site_name: str | None = Field(default=None, max_length=200)

    @field_validator("canonical_url")
    @classmethod
    def validate_canonical_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            normalized = validate_web_url(value).normalized_url
        except UrlPolicyError:
            raise ValueError("canonical_url must be a normalized public HTTP(S) URL") from None
        if normalized != value:
            raise ValueError("canonical_url must already be normalized")
        return value


class WebFetchDiagnostics(WebContentModel):
    http_status: int = Field(ge=200, le=299)
    redirect_count: int = Field(ge=0, le=5)
    decoded_byte_size: int = Field(ge=1, le=2_000_000)
    text_truncated: bool = False


class WebPageContent(WebContentModel):
    """Successful safe page content. Raw HTML and HTTP response objects are excluded."""

    outcome: Literal[WebFetchOutcome.SUCCESS] = WebFetchOutcome.SUCCESS
    normalized_url: str = Field(min_length=1, max_length=2048, repr=False)
    final_url: str = Field(min_length=1, max_length=2048, repr=False)
    title: str = Field(max_length=300)
    text: str = Field(min_length=1, max_length=50_000, repr=False)
    metadata: WebPageMetadata = Field(default_factory=WebPageMetadata, repr=False)
    content_type: str = Field(pattern=r"^(text/html|application/xhtml\+xml|text/plain)$")
    fetched_at: datetime
    diagnostics: WebFetchDiagnostics

    @field_validator("fetched_at")
    @classmethod
    def normalize_fetched_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @field_validator("normalized_url", "final_url")
    @classmethod
    def validate_result_urls(cls, value: str) -> str:
        try:
            normalized = validate_web_url(value).normalized_url
        except UrlPolicyError:
            raise ValueError("web result URLs must be normalized public HTTP(S) URLs") from None
        if normalized != value:
            raise ValueError("web result URLs must already be normalized")
        return value


class WebFetchFailure(WebContentModel):
    """Public-safe, recoverable failure with no URL, payload, exception, or DNS details."""

    outcome: Literal[WebFetchOutcome.FAILURE] = WebFetchOutcome.FAILURE
    code: WebFetchFailureCode
    summary: str
    retryable: bool
    recovery_actions: tuple[WebRecoveryAction, ...] = (
        WebRecoveryAction.SUPPLY_TEXT,
        WebRecoveryAction.SEND_SCREENSHOT,
    )
    http_status: int | None = Field(default=None, ge=400, le=599)

    @model_validator(mode="after")
    def validate_fixed_semantics(self) -> Self:
        if self.recovery_actions != (
            WebRecoveryAction.SUPPLY_TEXT,
            WebRecoveryAction.SEND_SCREENSHOT,
        ):
            raise ValueError("recovery_actions must match the fixed recovery contract")
        if self.summary != _FAILURE_SUMMARIES[self.code]:
            raise ValueError("summary must match the fixed failure code")
        if self.retryable is not _is_retryable(self.code, self.http_status):
            raise ValueError("retryable must match the fixed failure code")
        if self.code is WebFetchFailureCode.HTTP_STATUS:
            if self.http_status is None:
                raise ValueError("HTTP status failures require http_status")
        elif self.http_status is not None:
            raise ValueError("http_status is only valid for HTTP status failures")
        return self

    @classmethod
    def for_code(
        cls,
        code: WebFetchFailureCode,
        *,
        http_status: int | None = None,
    ) -> WebFetchFailure:
        return cls(
            code=code,
            summary=_FAILURE_SUMMARIES[code],
            retryable=_is_retryable(code, http_status),
            http_status=http_status,
        )

    def to_public_dict(self) -> dict[str, object]:
        public: dict[str, object] = {
            "outcome": self.outcome.value,
            "code": self.code.value,
            "summary": self.summary,
            "retryable": self.retryable,
            "recovery_actions": tuple(action.value for action in self.recovery_actions),
        }
        if self.http_status is not None:
            public["http_status"] = self.http_status
        return public


WebFetchResult = WebPageContent | WebFetchFailure


def _is_retryable(code: WebFetchFailureCode, http_status: int | None) -> bool:
    if code in _RETRYABLE_FAILURES:
        return True
    return code is WebFetchFailureCode.HTTP_STATUS and http_status is not None and (
        http_status in {408, 429} or http_status >= 500
    )

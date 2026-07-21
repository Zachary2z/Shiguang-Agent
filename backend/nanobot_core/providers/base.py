"""Provider-neutral model request and response contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any

Message = dict[str, Any]
ToolDefinition = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model request to execute one registered tool."""

    id: str
    name: str
    arguments: dict[str, Any] | str = field(repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenUsage:
    """Provider-neutral token counts; ``None`` means the value is unknown."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer or None")

        known_parts = [
            value
            for value in (self.input_tokens, self.output_tokens)
            if value is not None
        ]
        if self.total_tokens is not None and self.total_tokens < sum(known_parts):
            raise ValueError("total_tokens cannot be less than the known token counts")

        if self.input_tokens is not None and self.output_tokens is not None:
            expected_total = self.input_tokens + self.output_tokens
            if self.total_tokens is None:
                object.__setattr__(self, "total_tokens", expected_total)
            elif self.total_tokens != expected_total:
                raise ValueError("total_tokens must equal input_tokens plus output_tokens")


class FinishReason(StrEnum):
    """Stable completion semantics normalized by every provider adapter."""

    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelResponse:
    """A provider-independent model response with normalized metadata."""

    model_name: str
    usage: TokenUsage
    latency_ms: int
    finish_reason: FinishReason
    provider_request_id: str | None = None
    content: str | None = field(default=None, repr=False)
    tool_calls: list[ToolCall] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name must be a non-empty string")
        if not isinstance(self.usage, TokenUsage):
            raise TypeError("usage must be a TokenUsage")
        if type(self.latency_ms) is not int or self.latency_ms < 0:
            raise ValueError("latency_ms must be a non-negative integer")
        if not isinstance(self.finish_reason, FinishReason):
            raise TypeError("finish_reason must be a FinishReason")
        if self.provider_request_id is not None and (
            not isinstance(self.provider_request_id, str)
            or not self.provider_request_id.strip()
        ):
            raise ValueError("provider_request_id must be a non-empty string or None")
        if any(not isinstance(call, ToolCall) for call in self.tool_calls):
            raise TypeError("tool_calls must contain only ToolCall values")
        if self.tool_calls and self.finish_reason is not FinishReason.TOOL_CALLS:
            raise ValueError("responses with tool_calls must use the tool_calls finish reason")
        if not self.tool_calls and self.finish_reason is FinishReason.TOOL_CALLS:
            raise ValueError("the tool_calls finish reason requires at least one tool call")


class ProviderErrorCode(StrEnum):
    """Stable error codes that do not expose provider SDK exception types."""

    TIMEOUT = "PROVIDER_TIMEOUT"
    RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    AUTHENTICATION_FAILED = "PROVIDER_AUTHENTICATION_FAILED"
    INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"
    PROVIDER_ERROR = "PROVIDER_ERROR"


_RETRYABLE_PROVIDER_ERRORS = {
    ProviderErrorCode.TIMEOUT,
    ProviderErrorCode.RATE_LIMITED,
}

_PROVIDER_ERROR_SUMMARIES = {
    ProviderErrorCode.TIMEOUT: "The model provider request timed out.",
    ProviderErrorCode.RATE_LIMITED: "The model provider rate limit was reached.",
    ProviderErrorCode.AUTHENTICATION_FAILED: (
        "The model provider rejected authentication."
    ),
    ProviderErrorCode.INVALID_RESPONSE: "The model provider returned an invalid response.",
    ProviderErrorCode.PROVIDER_ERROR: "The model provider request failed.",
}


class ProviderError(Exception):
    """A safe, structured model-provider failure exposed by all adapters."""

    def __init__(
        self,
        *,
        code: ProviderErrorCode,
        retry_after_seconds: float | None = None,
    ) -> None:
        if not isinstance(code, ProviderErrorCode):
            raise TypeError("code must be a ProviderErrorCode")
        if retry_after_seconds is not None:
            if (
                isinstance(retry_after_seconds, bool)
                or not isinstance(retry_after_seconds, int | float)
                or not isfinite(retry_after_seconds)
                or retry_after_seconds < 0
            ):
                raise ValueError("retry_after_seconds must be a finite non-negative number")
            if code is not ProviderErrorCode.RATE_LIMITED:
                raise ValueError("retry_after_seconds is only valid for rate-limited errors")

        summary = _PROVIDER_ERROR_SUMMARIES[code]
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.retryable = code in _RETRYABLE_PROVIDER_ERRORS
        self.retry_after_seconds = (
            None if retry_after_seconds is None else float(retry_after_seconds)
        )

    def to_public_dict(self) -> dict[str, object]:
        """Serialize only fields safe for public logs or user-facing responses."""

        return {
            "code": self.code.value,
            "summary": self.summary,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
        }


class ModelProvider(ABC):
    """Provider interface implemented by offline fakes and later model adapters."""

    @abstractmethod
    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
    ) -> ModelResponse:
        """Return a response or raise ``ProviderError`` without swallowing cancellation."""

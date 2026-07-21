"""Provider-neutral, secret-safe events emitted by the Agent runner."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeAlias

from nanobot_core.providers import FinishReason, TokenUsage


class RunTermination(StrEnum):
    """Deterministic reasons why a runner invocation stopped."""

    COMPLETED = "completed"
    EMPTY_RESPONSE = "empty_response"
    MAX_ITERATIONS = "max_iterations"
    MAX_TOOL_CALLS = "max_tool_calls"
    REPEATED_TOOL_CALL = "repeated_tool_call"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelCallFinished:
    """Metadata for one completed provider call, excluding model content."""

    sequence: int
    model_name: str
    usage: TokenUsage
    latency_ms: int
    finish_reason: FinishReason


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelCallFailed:
    """A provider call that failed without exposing exception details."""

    sequence: int
    latency_ms: int
    error_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelCallCancelled:
    """A provider call cancelled by the run deadline or its caller."""

    sequence: int
    latency_ms: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallStarted:
    """A tool call accepted for execution with only a structural input summary."""

    sequence: int
    tool_call_id: str
    tool_name: str
    arguments_fingerprint: str
    input_summary: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallFinished:
    """A completed tool call with a structural, bounded output summary."""

    sequence: int
    success: bool
    latency_ms: int
    output_summary: str
    error_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallCancelled:
    """A tool call cancelled by the run deadline or its caller."""

    sequence: int
    latency_ms: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallBlocked:
    """A model-requested call rejected before tool execution."""

    sequence: int
    tool_call_id: str
    tool_name: str
    arguments_fingerprint: str
    input_summary: str
    reason: RunTermination


RunEvent: TypeAlias = (
    ModelCallFinished
    | ModelCallFailed
    | ModelCallCancelled
    | ToolCallStarted
    | ToolCallFinished
    | ToolCallCancelled
    | ToolCallBlocked
)


class RunObserver(Protocol):
    """Synchronous observation boundary; implementations must not block the runner."""

    def __call__(self, event: RunEvent) -> None:
        """Observe one immutable event containing no prompts or raw tool values."""

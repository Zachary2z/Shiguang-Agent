"""Offline providers and tools shared by core tests."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import cast

from nanobot_core.providers import (
    FinishReason,
    Message,
    ModelProvider,
    ModelResponse,
    StructuredOutput,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from nanobot_core.tools import Tool, ToolInput, ToolResult


@dataclass(frozen=True, slots=True)
class ProviderCall:
    messages: list[Message] = field(repr=False)
    tools: list[ToolDefinition] | None = field(repr=False)
    response_format: StructuredOutput | None = field(default=None, repr=False)


class FakeProvider(ModelProvider):
    """Return fixed responses and retain isolated snapshots of every request."""

    def __init__(self, responses: Sequence[ModelResponse | BaseException | None]) -> None:
        self.responses = deque(responses)
        self.calls: list[ProviderCall] = []

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_format: StructuredOutput | None = None,
    ) -> ModelResponse:
        self.calls.append(
            ProviderCall(
                deepcopy(messages),
                deepcopy(tools),
                deepcopy(response_format),
            )
        )
        if not self.responses:
            raise AssertionError("FakeProvider has no response left")
        outcome = self.responses.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return cast(ModelResponse, outcome)


def fake_response(
    *,
    content: str | None = None,
    tool_calls: Sequence[ToolCall] = (),
    model_name: str = "fixture-model",
    usage: TokenUsage | None = None,
    latency_ms: int = 4,
) -> ModelResponse:
    """Build a complete, deterministic response for runner-focused tests."""

    calls = list(tool_calls)
    return ModelResponse(
        model_name=model_name,
        usage=usage or TokenUsage(input_tokens=2, output_tokens=3),
        latency_ms=latency_ms,
        finish_reason=FinishReason.TOOL_CALLS if calls else FinishReason.STOP,
        provider_request_id="fixture-request-id",
        content=content,
        tool_calls=calls,
    )


class EchoInput(ToolInput):
    text: str


class EchoTool(Tool[EchoInput]):
    name = "echo"
    description = "Return the supplied text."
    input_model = EchoInput

    def __init__(self, calls: list[str] | None = None) -> None:
        self.calls = calls if calls is not None else []

    async def execute(self, arguments: EchoInput) -> ToolResult:
        self.calls.append(arguments.text)
        return ToolResult.ok(message="Text echoed.", data={"text": arguments.text})


class ExplodingTool(Tool[EchoInput]):
    name = "explode"
    description = "Raise an exception for failure-path tests."
    input_model = EchoInput

    async def execute(self, arguments: EchoInput) -> ToolResult:
        del arguments
        raise RuntimeError("internal-secret-detail")

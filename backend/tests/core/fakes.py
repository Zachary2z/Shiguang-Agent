"""Offline providers and tools shared by core tests."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from nanobot_core.providers import Message, ModelProvider, ModelResponse, ToolDefinition
from nanobot_core.tools import Tool, ToolInput, ToolResult


@dataclass(frozen=True, slots=True)
class ProviderCall:
    messages: list[Message]
    tools: list[ToolDefinition] | None


class FakeProvider(ModelProvider):
    """Return fixed responses and retain isolated snapshots of every request."""

    def __init__(self, responses: Sequence[ModelResponse | None]) -> None:
        self.responses = deque(responses)
        self.calls: list[ProviderCall] = []

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
    ) -> ModelResponse:
        self.calls.append(ProviderCall(deepcopy(messages), deepcopy(tools)))
        if not self.responses:
            raise AssertionError("FakeProvider has no response left")
        return cast(ModelResponse, self.responses.popleft())


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

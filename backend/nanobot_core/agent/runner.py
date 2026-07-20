"""The bounded model -> tool -> model runner."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nanobot_core.providers import Message, ModelProvider, ToolCall
from nanobot_core.tools import ToolRegistry

EMPTY_RESPONSE_MESSAGE = "The model returned no usable content."


class RunTermination(StrEnum):
    """Deterministic reasons why a runner invocation stopped."""

    COMPLETED = "completed"
    EMPTY_RESPONSE = "empty_response"
    MAX_ITERATIONS = "max_iterations"


@dataclass(slots=True)
class RunResult:
    """The final answer and isolated conversation produced by one run."""

    answer: str
    messages: list[Message]
    new_messages: list[Message]
    tools_used: list[str]
    termination: RunTermination
    iterations: int


class AgentRunner:
    """Call a provider and execute registered tools within a fixed bound."""

    def __init__(
        self,
        provider: ModelProvider,
        tools: ToolRegistry,
        *,
        max_iterations: int = 8,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be greater than 0")
        self.provider = provider
        self.tools = tools
        self.max_iterations = max_iterations

    async def run(self, messages: list[Message]) -> RunResult:
        conversation = deepcopy(messages)
        start_index = len(conversation)
        tools_used: list[str] = []

        for iteration in range(1, self.max_iterations + 1):
            definitions = self.tools.definitions()
            response = await self.provider.chat(
                messages=deepcopy(conversation),
                tools=deepcopy(definitions) if definitions else None,
            )

            if response is None or not response.tool_calls:
                content = "" if response is None or response.content is None else response.content
                answer = content.strip()
                termination = RunTermination.COMPLETED
                if not answer:
                    answer = EMPTY_RESPONSE_MESSAGE
                    termination = RunTermination.EMPTY_RESPONSE
                conversation.append({"role": "assistant", "content": answer})
                return RunResult(
                    answer=answer,
                    messages=conversation,
                    new_messages=deepcopy(conversation[start_index:]),
                    tools_used=tools_used,
                    termination=termination,
                    iterations=iteration,
                )

            conversation.append(self._assistant_tool_message(response.content, response.tool_calls))
            for call in response.tool_calls:
                tools_used.append(call.name)
                result = await self.tools.execute(call.name, call.arguments)
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": result.to_json(),
                    }
                )

        answer = (
            f"The model did not finish within the maximum of {self.max_iterations} iterations."
        )
        conversation.append({"role": "assistant", "content": answer})
        return RunResult(
            answer=answer,
            messages=conversation,
            new_messages=deepcopy(conversation[start_index:]),
            tools_used=tools_used,
            termination=RunTermination.MAX_ITERATIONS,
            iterations=self.max_iterations,
        )

    @staticmethod
    def _assistant_tool_message(content: str | None, calls: list[ToolCall]) -> Message:
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": AgentRunner._serialize_arguments(call.arguments),
                    },
                }
                for call in calls
            ],
        }

    @staticmethod
    def _serialize_arguments(arguments: dict[str, Any] | str) -> str:
        if isinstance(arguments, str):
            return arguments
        return json.dumps(
            arguments,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

"""The bounded model -> tool -> model runner."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial
from math import isfinite
from time import monotonic
from typing import Any, TypeVar, cast

from nanobot_core.agent.events import (
    ModelCallCancelled,
    ModelCallFailed,
    ModelCallFinished,
    RunEvent,
    RunObserver,
    RunTermination,
    ToolCallBlocked,
    ToolCallCancelled,
    ToolCallFinished,
    ToolCallStarted,
)
from nanobot_core.agent.limits import MAX_RUN_TIMEOUT_SECONDS, MAX_TOOL_CALLS_PER_RUN
from nanobot_core.providers import Message, ModelProvider, ModelResponse, ProviderError, ToolCall
from nanobot_core.tools import ToolRegistry, ToolResult

EMPTY_RESPONSE_MESSAGE = "The model returned no usable content."
MAX_TOOL_CALLS_MESSAGE = "The run stopped at the maximum number of tool calls."
REPEATED_TOOL_CALL_MESSAGE = "The run stopped after a repeated tool call."
RUN_TIMEOUT_MESSAGE = "The run stopped after reaching its total time limit."

_T = TypeVar("_T")
TimeoutRunner = Callable[[Awaitable[Any], float], Awaitable[Any]]


async def _wait_for(awaitable: Awaitable[_T], timeout_seconds: float) -> _T:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


class _RunTimedOut(Exception):
    """Internal signal used only to turn an active-operation timeout into a result."""


@dataclass(slots=True)
class RunResult:
    """The final answer and isolated conversation produced by one run."""

    answer: str = field(repr=False)
    messages: list[Message] = field(repr=False)
    new_messages: list[Message] = field(repr=False)
    tools_used: list[str] = field(repr=False)
    termination: RunTermination
    iterations: int
    model_calls: int
    tool_calls: int
    duration_ms: int


class AgentRunner:
    """Call a provider and execute registered tools within fixed safety bounds."""

    def __init__(
        self,
        provider: ModelProvider,
        tools: ToolRegistry,
        *,
        max_iterations: int = 8,
        max_tool_calls: int = MAX_TOOL_CALLS_PER_RUN,
        timeout_seconds: float = MAX_RUN_TIMEOUT_SECONDS,
        clock: Callable[[], float] = monotonic,
        timeout_runner: TimeoutRunner = _wait_for,
    ) -> None:
        if type(max_iterations) is not int or max_iterations < 1:
            raise ValueError("max_iterations must be greater than 0")
        if (
            type(max_tool_calls) is not int
            or max_tool_calls < 1
            or max_tool_calls > MAX_TOOL_CALLS_PER_RUN
        ):
            raise ValueError(
                f"max_tool_calls must be an integer from 1 to {MAX_TOOL_CALLS_PER_RUN}"
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int | float)
            or not isfinite(timeout_seconds)
            or timeout_seconds <= 0
            or timeout_seconds > MAX_RUN_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "timeout_seconds must be a finite number in "
                f"(0, {MAX_RUN_TIMEOUT_SECONDS:g}]"
            )
        self.provider = provider
        self.tools = tools
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.timeout_seconds = float(timeout_seconds)
        self._clock = clock
        self._timeout_runner = timeout_runner

    async def run(
        self,
        messages: list[Message],
        *,
        observer: RunObserver | None = None,
    ) -> RunResult:
        conversation = deepcopy(messages)
        start_index = len(conversation)
        tools_used: list[str] = []
        seen_tool_calls: set[str] = set()
        started_at = self._clock()
        model_call_count = 0
        executed_tool_calls = 0
        tool_sequence = 0
        current_iteration = 0

        try:
            for iteration in range(1, self.max_iterations + 1):
                current_iteration = iteration
                definitions = self.tools.definitions()
                model_call_count += 1
                response = await self._within_budget(
                    partial(
                        self._call_model,
                        sequence=model_call_count,
                        messages=deepcopy(conversation),
                        definitions=deepcopy(definitions) if definitions else None,
                        observer=observer,
                    ),
                    started_at=started_at,
                )

                if response is None or not response.tool_calls:
                    content = (
                        "" if response is None or response.content is None else response.content
                    )
                    answer = content.strip()
                    termination = RunTermination.COMPLETED
                    if not answer:
                        answer = EMPTY_RESPONSE_MESSAGE
                        termination = RunTermination.EMPTY_RESPONSE
                    conversation.append({"role": "assistant", "content": answer})
                    return self._result(
                        answer=answer,
                        conversation=conversation,
                        start_index=start_index,
                        tools_used=tools_used,
                        termination=termination,
                        iterations=iteration,
                        model_calls=model_call_count,
                        tool_calls=executed_tool_calls,
                        started_at=started_at,
                    )

                conversation.append(
                    self._assistant_tool_message(response.content, response.tool_calls)
                )
                for call in response.tool_calls:
                    tool_sequence += 1
                    fingerprint = self._tool_fingerprint(call.name, call.arguments)
                    input_summary = self._input_summary(call.arguments)
                    safe_call_id = self._safe_identifier(call.id, prefix="call")
                    safe_tool_name = self._safe_identifier(call.name, prefix="tool")

                    if tool_sequence > min(self.max_tool_calls, MAX_TOOL_CALLS_PER_RUN):
                        self._observe(
                            observer,
                            ToolCallBlocked(
                                sequence=tool_sequence,
                                tool_call_id=safe_call_id,
                                tool_name=safe_tool_name,
                                arguments_fingerprint=fingerprint,
                                input_summary=input_summary,
                                reason=RunTermination.MAX_TOOL_CALLS,
                            ),
                        )
                        conversation.append(
                            {"role": "assistant", "content": MAX_TOOL_CALLS_MESSAGE}
                        )
                        return self._result(
                            answer=MAX_TOOL_CALLS_MESSAGE,
                            conversation=conversation,
                            start_index=start_index,
                            tools_used=tools_used,
                            termination=RunTermination.MAX_TOOL_CALLS,
                            iterations=iteration,
                            model_calls=model_call_count,
                            tool_calls=executed_tool_calls,
                            started_at=started_at,
                        )

                    if fingerprint in seen_tool_calls:
                        self._observe(
                            observer,
                            ToolCallBlocked(
                                sequence=tool_sequence,
                                tool_call_id=safe_call_id,
                                tool_name=safe_tool_name,
                                arguments_fingerprint=fingerprint,
                                input_summary=input_summary,
                                reason=RunTermination.REPEATED_TOOL_CALL,
                            ),
                        )
                        conversation.append(
                            {"role": "assistant", "content": REPEATED_TOOL_CALL_MESSAGE}
                        )
                        return self._result(
                            answer=REPEATED_TOOL_CALL_MESSAGE,
                            conversation=conversation,
                            start_index=start_index,
                            tools_used=tools_used,
                            termination=RunTermination.REPEATED_TOOL_CALL,
                            iterations=iteration,
                            model_calls=model_call_count,
                            tool_calls=executed_tool_calls,
                            started_at=started_at,
                        )

                    seen_tool_calls.add(fingerprint)
                    executed_tool_calls += 1
                    tools_used.append(call.name)
                    result = await self._within_budget(
                        partial(
                            self._execute_tool,
                            sequence=tool_sequence,
                            call=call,
                            safe_call_id=safe_call_id,
                            safe_tool_name=safe_tool_name,
                            fingerprint=fingerprint,
                            input_summary=input_summary,
                            observer=observer,
                        ),
                        started_at=started_at,
                    )
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": result.to_json(),
                        }
                    )

            answer = (
                f"The model did not finish within the maximum of {self.max_iterations} "
                "iterations."
            )
            conversation.append({"role": "assistant", "content": answer})
            return self._result(
                answer=answer,
                conversation=conversation,
                start_index=start_index,
                tools_used=tools_used,
                termination=RunTermination.MAX_ITERATIONS,
                iterations=self.max_iterations,
                model_calls=model_call_count,
                tool_calls=executed_tool_calls,
                started_at=started_at,
            )
        except _RunTimedOut:
            conversation.append({"role": "assistant", "content": RUN_TIMEOUT_MESSAGE})
            return self._result(
                answer=RUN_TIMEOUT_MESSAGE,
                conversation=conversation,
                start_index=start_index,
                tools_used=tools_used,
                termination=RunTermination.TIMEOUT,
                iterations=current_iteration,
                model_calls=model_call_count,
                tool_calls=executed_tool_calls,
                started_at=started_at,
            )

    async def _call_model(
        self,
        *,
        sequence: int,
        messages: list[Message],
        definitions: list[dict[str, Any]] | None,
        observer: RunObserver | None,
    ) -> ModelResponse | None:
        started_at = self._clock()
        try:
            response = await self.provider.chat(messages=messages, tools=definitions)
        except asyncio.CancelledError:
            self._observe(
                observer,
                ModelCallCancelled(
                    sequence=sequence,
                    latency_ms=self._elapsed_ms(started_at),
                ),
            )
            raise
        except ProviderError as exc:
            self._observe(
                observer,
                ModelCallFailed(
                    sequence=sequence,
                    latency_ms=self._elapsed_ms(started_at),
                    error_code=exc.code.value,
                ),
            )
            raise
        except Exception:
            self._observe(
                observer,
                ModelCallFailed(
                    sequence=sequence,
                    latency_ms=self._elapsed_ms(started_at),
                    error_code=None,
                ),
            )
            raise

        if response is None:
            self._observe(
                observer,
                ModelCallFailed(
                    sequence=sequence,
                    latency_ms=self._elapsed_ms(started_at),
                    error_code=None,
                ),
            )
        else:
            self._observe(
                observer,
                ModelCallFinished(
                    sequence=sequence,
                    model_name=response.model_name,
                    usage=response.usage,
                    latency_ms=response.latency_ms,
                    finish_reason=response.finish_reason,
                ),
            )
        return response

    async def _execute_tool(
        self,
        *,
        sequence: int,
        call: ToolCall,
        safe_call_id: str,
        safe_tool_name: str,
        fingerprint: str,
        input_summary: str,
        observer: RunObserver | None,
    ) -> ToolResult:
        self._observe(
            observer,
            ToolCallStarted(
                sequence=sequence,
                tool_call_id=safe_call_id,
                tool_name=safe_tool_name,
                arguments_fingerprint=fingerprint,
                input_summary=input_summary,
            ),
        )
        started_at = self._clock()
        try:
            result = await self.tools.execute(call.name, call.arguments)
        except asyncio.CancelledError:
            self._observe(
                observer,
                ToolCallCancelled(
                    sequence=sequence,
                    latency_ms=self._elapsed_ms(started_at),
                ),
            )
            raise

        self._observe(
            observer,
            ToolCallFinished(
                sequence=sequence,
                success=result.success,
                latency_ms=self._elapsed_ms(started_at),
                output_summary=self._output_summary(result),
                error_code=None if result.error_code is None else result.error_code.value,
            ),
        )
        return result

    async def _within_budget(
        self,
        operation: Callable[[], Awaitable[_T]],
        *,
        started_at: float,
    ) -> _T:
        budget_seconds = min(self.timeout_seconds, MAX_RUN_TIMEOUT_SECONDS)
        remaining = budget_seconds - (self._clock() - started_at)
        if remaining <= 0:
            raise _RunTimedOut
        try:
            result = await self._timeout_runner(operation(), remaining)
        except TimeoutError as exc:
            raise _RunTimedOut from exc
        if self._clock() - started_at >= budget_seconds:
            raise _RunTimedOut
        return cast(_T, result)

    def _result(
        self,
        *,
        answer: str,
        conversation: list[Message],
        start_index: int,
        tools_used: list[str],
        termination: RunTermination,
        iterations: int,
        model_calls: int,
        tool_calls: int,
        started_at: float,
    ) -> RunResult:
        duration_ms = self._elapsed_ms(started_at)
        if termination is RunTermination.TIMEOUT:
            budget_seconds = min(self.timeout_seconds, MAX_RUN_TIMEOUT_SECONDS)
            duration_ms = min(duration_ms, int(budget_seconds * 1000))
        return RunResult(
            answer=answer,
            messages=conversation,
            new_messages=deepcopy(conversation[start_index:]),
            tools_used=tools_used,
            termination=termination,
            iterations=iterations,
            model_calls=model_calls,
            tool_calls=tool_calls,
            duration_ms=duration_ms,
        )

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((self._clock() - started_at) * 1000))

    @staticmethod
    def _observe(observer: RunObserver | None, event: RunEvent) -> None:
        if observer is not None:
            observer(event)

    @staticmethod
    def _tool_fingerprint(name: str, arguments: object) -> str:
        canonical = AgentRunner._canonical_arguments(arguments)
        payload = json.dumps(
            {"arguments": canonical, "tool": name},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _canonical_arguments(arguments: object) -> object:
        value = arguments
        if isinstance(arguments, str):
            try:
                value = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                return {"invalid_json_sha256": hashlib.sha256(arguments.encode()).hexdigest()}
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            return json.loads(encoded)
        except (TypeError, ValueError):
            type_name = f"{type(value).__module__}.{type(value).__qualname__}"
            return {"unsupported_type": type_name}

    @staticmethod
    def _input_summary(arguments: object) -> str:
        value = arguments
        if isinstance(arguments, str):
            try:
                value = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                summary: dict[str, object] = {
                    "type": "invalid_json",
                    "length": len(arguments),
                }
                return json.dumps(summary, separators=(",", ":"), sort_keys=True)[:512]

        summary = AgentRunner._structural_summary(value)
        return json.dumps(summary, separators=(",", ":"), sort_keys=True)[:512]

    @staticmethod
    def _structural_summary(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            return {"field_count": len(value), "type": "object"}
        if isinstance(value, list):
            return {"item_count": len(value), "type": "array"}
        if isinstance(value, str):
            return {"length": len(value), "type": "string"}
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "boolean"}
        if isinstance(value, int | float):
            return {"type": "number"}
        return {"type": "unsupported"}

    @staticmethod
    def _output_summary(result: ToolResult) -> str:
        data_type = AgentRunner._structural_summary(result.data)["type"]
        summary = {
            "data_type": data_type,
            "source_count": len(result.sources),
            "success": result.success,
        }
        return json.dumps(summary, separators=(",", ":"), sort_keys=True)[:512]

    @staticmethod
    def _safe_identifier(value: str, *, prefix: str) -> str:
        if (
            isinstance(value, str)
            and 1 <= len(value) <= 128
            and value.isascii()
            and all(character.isalnum() or character in "._:-" for character in value)
        ):
            return value
        digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:24]
        return f"{prefix}_{digest}"

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

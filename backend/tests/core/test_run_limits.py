"""Absolute tool-call, repetition, event, and deadline behavior."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

import pytest

from nanobot_core.agent import (
    AgentRunner,
    ModelCallFinished,
    RunEvent,
    RunTermination,
    ToolCallBlocked,
    ToolCallStarted,
)
from nanobot_core.providers import Message, ModelProvider, ModelResponse, ToolCall, ToolDefinition
from nanobot_core.tools import Tool, ToolInput, ToolRegistry, ToolResult
from tests.core.fakes import EchoTool, FakeProvider, fake_response


@pytest.mark.asyncio
async def test_exactly_eight_absolute_tool_calls_can_complete() -> None:
    executed: list[str] = []
    calls = [ToolCall(f"call-{index}", "echo", {"text": str(index)}) for index in range(8)]
    provider = FakeProvider(
        [fake_response(tool_calls=calls), fake_response(content="all completed")]
    )
    registry = ToolRegistry()
    registry.register(EchoTool(executed))

    result = await AgentRunner(provider, registry).run([])

    assert result.termination is RunTermination.COMPLETED
    assert result.tool_calls == 8
    assert executed == [str(index) for index in range(8)]


@pytest.mark.asyncio
async def test_ninth_tool_call_is_recorded_as_blocked_and_never_executes() -> None:
    executed: list[str] = []
    events: list[RunEvent] = []
    calls = [ToolCall(f"call-{index}", "echo", {"text": str(index)}) for index in range(9)]
    registry = ToolRegistry()
    registry.register(EchoTool(executed))

    result = await AgentRunner(FakeProvider([fake_response(tool_calls=calls)]), registry).run(
        [], observer=events.append
    )

    assert result.termination is RunTermination.MAX_TOOL_CALLS
    assert result.tool_calls == 8
    assert executed == [str(index) for index in range(8)]
    blocked = [event for event in events if isinstance(event, ToolCallBlocked)]
    assert len(blocked) == 1
    assert blocked[0].sequence == 9


@pytest.mark.asyncio
async def test_single_response_counts_each_tool_call_against_absolute_limit() -> None:
    executed: list[str] = []
    registry = ToolRegistry()
    registry.register(EchoTool(executed))
    provider = FakeProvider(
        [
            fake_response(
                tool_calls=[
                    ToolCall("call-1", "echo", {"text": "first"}),
                    ToolCall("call-2", "echo", {"text": "second"}),
                ]
            )
        ]
    )

    result = await AgentRunner(provider, registry, max_tool_calls=1).run([])

    assert result.termination is RunTermination.MAX_TOOL_CALLS
    assert result.tool_calls == 1
    assert executed == ["first"]


@pytest.mark.asyncio
async def test_equivalent_json_arguments_are_fingerprinted_and_blocked_without_values() -> None:
    executed: list[str] = []
    events: list[RunEvent] = []
    secret = "pseudo-secret-value"
    registry = ToolRegistry()
    registry.register(EchoTool(executed))
    provider = FakeProvider(
        [
            fake_response(
                tool_calls=[ToolCall("call-1", "echo", {"text": secret})]
            ),
            fake_response(
                tool_calls=[ToolCall("call-2", "echo", f' {{ "text" : "{secret}" }} ')]
            ),
        ]
    )

    result = await AgentRunner(provider, registry).run([], observer=events.append)

    assert result.termination is RunTermination.REPEATED_TOOL_CALL
    assert executed == [secret]
    starts = [event for event in events if isinstance(event, ToolCallStarted)]
    blocked = [event for event in events if isinstance(event, ToolCallBlocked)]
    assert starts[0].arguments_fingerprint == blocked[0].arguments_fingerprint
    assert secret not in repr(events)


@pytest.mark.asyncio
async def test_public_runtime_repr_excludes_messages_model_content_and_tool_values() -> None:
    secret = "pseudo-secret-Authorization-Cookie"
    call = ToolCall("call-secret", "echo", {"text": secret})
    response = fake_response(content=secret, tool_calls=[call])
    tool_result = ToolResult.ok(message=secret, data={"value": secret}, sources=[secret])
    runner_result = await AgentRunner(
        FakeProvider([fake_response(content=secret)]), ToolRegistry()
    ).run([{"role": "user", "content": secret}])

    assert secret not in repr(call)
    assert secret not in repr(response)
    assert secret not in repr(tool_result)
    assert secret not in repr(runner_result)


@pytest.mark.asyncio
async def test_different_arguments_do_not_trigger_repetition() -> None:
    executed: list[str] = []
    registry = ToolRegistry()
    registry.register(EchoTool(executed))
    provider = FakeProvider(
        [
            fake_response(tool_calls=[ToolCall("call-1", "echo", {"text": "one"})]),
            fake_response(tool_calls=[ToolCall("call-2", "echo", {"text": "two"})]),
            fake_response(content="done"),
        ]
    )

    result = await AgentRunner(provider, registry).run([])

    assert result.termination is RunTermination.COMPLETED
    assert executed == ["one", "two"]


class _BlockingProvider(ModelProvider):
    def __init__(self) -> None:
        self.cancelled = False

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
    ) -> ModelResponse:
        del messages, tools
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_total_deadline_cancels_an_active_provider_call() -> None:
    provider = _BlockingProvider()

    result = await AgentRunner(
        provider,
        ToolRegistry(),
        timeout_seconds=0.01,
    ).run([])

    assert result.termination is RunTermination.TIMEOUT
    assert result.duration_ms <= 10
    assert provider.cancelled is True


class _NoInput(ToolInput):
    pass


class _BlockingTool(Tool[_NoInput]):
    name = "blocking"
    description = "Wait until cancelled."
    input_model = _NoInput

    def __init__(self) -> None:
        self.cancelled = False

    async def execute(self, arguments: _NoInput) -> ToolResult:
        del arguments
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_total_deadline_cancels_an_active_tool_call() -> None:
    tool = _BlockingTool()
    registry = ToolRegistry()
    registry.register(tool)
    provider = FakeProvider(
        [fake_response(tool_calls=[ToolCall("call-1", "blocking", {})])]
    )

    result = await AgentRunner(
        provider,
        registry,
        timeout_seconds=0.01,
    ).run([])

    assert result.termination is RunTermination.TIMEOUT
    assert tool.cancelled is True


class _FakeClock:
    def __init__(self, elapsed_after_await: float) -> None:
        self.value = 0.0
        self.elapsed_after_await = elapsed_after_await

    def __call__(self) -> float:
        return self.value

    async def timeout_runner(
        self,
        awaitable: Awaitable[Any],
        remaining: float,
    ) -> Any:
        assert remaining > 0
        result = await awaitable
        self.value = self.elapsed_after_await
        return result


@pytest.mark.parametrize(
    ("elapsed", "termination"),
    [(59.999, RunTermination.COMPLETED), (60.0, RunTermination.TIMEOUT)],
)
@pytest.mark.asyncio
async def test_deadline_boundary_uses_injected_monotonic_clock(
    elapsed: float,
    termination: RunTermination,
) -> None:
    clock = _FakeClock(elapsed)
    events: list[RunEvent] = []

    result = await AgentRunner(
        FakeProvider([fake_response(content="done")]),
        ToolRegistry(),
        timeout_seconds=60,
        clock=clock,
        timeout_runner=clock.timeout_runner,
    ).run([], observer=events.append)

    assert result.termination is termination
    assert any(isinstance(event, ModelCallFinished) for event in events)

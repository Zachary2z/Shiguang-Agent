from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nanobot_core.agent import AgentRunner, RunTermination
from nanobot_core.providers import ModelResponse, ToolCall
from nanobot_core.tools import ToolErrorCode, ToolRegistry
from tests.core.fakes import EchoTool, ExplodingTool, FakeProvider


@pytest.mark.asyncio
async def test_runner_returns_provider_text_without_tools() -> None:
    provider = FakeProvider([ModelResponse(content="Direct answer")])

    result = await AgentRunner(provider, ToolRegistry()).run(
        [{"role": "user", "content": "hello"}]
    )

    assert result.answer == "Direct answer"
    assert result.termination is RunTermination.COMPLETED
    assert result.iterations == 1
    assert result.tools_used == []
    assert provider.calls[0].tools is None


@pytest.mark.asyncio
async def test_runner_performs_one_tool_call_then_returns_final_answer() -> None:
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "echo", {"text": "hello"})]),
            ModelResponse(content="The tool said hello."),
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = await AgentRunner(provider, registry).run([{"role": "user", "content": "test"}])

    tool_message = provider.calls[1].messages[-1]
    payload = json.loads(tool_message["content"])
    assert payload["success"] is True
    assert payload["data"] == {"text": "hello"}
    assert result.answer == "The tool said hello."
    assert result.tools_used == ["echo"]
    assert result.iterations == 2


@pytest.mark.asyncio
async def test_runner_preserves_multi_round_tool_order_and_results() -> None:
    calls: list[str] = []
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "echo", {"text": "first"})]),
            ModelResponse(tool_calls=[ToolCall("call-2", "echo", {"text": "second"})]),
            ModelResponse(content="done"),
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoTool(calls))

    result = await AgentRunner(provider, registry).run([])

    assert calls == ["first", "second"]
    assert result.tools_used == ["echo", "echo"]
    assert json.loads(provider.calls[1].messages[-1]["content"])["data"] == {
        "text": "first"
    }
    assert json.loads(provider.calls[2].messages[-1]["content"])["data"] == {
        "text": "second"
    }


@pytest.mark.asyncio
async def test_runner_executes_multiple_calls_from_one_response_in_order() -> None:
    calls: list[str] = []
    provider = FakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall("call-1", "echo", {"text": "first"}),
                    ToolCall("call-2", "echo", {"text": "second"}),
                ]
            ),
            ModelResponse(content="both done"),
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoTool(calls))

    result = await AgentRunner(provider, registry).run([])

    assert calls == ["first", "second"]
    assert result.tools_used == ["echo", "echo"]
    assert [message["tool_call_id"] for message in provider.calls[1].messages[-2:]] == [
        "call-1",
        "call-2",
    ]


@pytest.mark.asyncio
async def test_runner_passes_structured_unknown_tool_failure_back_to_provider() -> None:
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "missing", {})]),
            ModelResponse(content="I could not use that tool."),
        ]
    )

    result = await AgentRunner(provider, ToolRegistry()).run([])

    payload = json.loads(provider.calls[1].messages[-1]["content"])
    assert payload["success"] is False
    assert payload["error_code"] == ToolErrorCode.NOT_FOUND
    assert result.answer == "I could not use that tool."


@pytest.mark.asyncio
async def test_runner_passes_invalid_arguments_failure_back_to_provider() -> None:
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "echo", "{not-json")]),
            ModelResponse(content="The arguments were invalid."),
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoTool())

    await AgentRunner(provider, registry).run([])

    payload = json.loads(provider.calls[1].messages[-1]["content"])
    assert payload["success"] is False
    assert payload["error_code"] == ToolErrorCode.INVALID_ARGUMENTS


@pytest.mark.asyncio
async def test_runner_passes_tool_execution_failure_back_without_exception_detail() -> None:
    provider = FakeProvider(
        [
            ModelResponse(
                tool_calls=[ToolCall("call-1", "explode", {"text": "hello"})]
            ),
            ModelResponse(content="The tool failed."),
        ]
    )
    registry = ToolRegistry()
    registry.register(ExplodingTool())

    await AgentRunner(provider, registry).run([])

    content = provider.calls[1].messages[-1]["content"]
    payload = json.loads(content)
    assert payload["success"] is False
    assert payload["error_code"] == ToolErrorCode.EXECUTION_FAILED
    assert "internal-secret-detail" not in content


@pytest.mark.parametrize("content", [None, "", "   \n"])
@pytest.mark.asyncio
async def test_runner_classifies_empty_provider_content(content: str | None) -> None:
    result = await AgentRunner(
        FakeProvider([ModelResponse(content=content)]),
        ToolRegistry(),
    ).run([])

    assert result.answer == "The model returned no usable content."
    assert result.termination is RunTermination.EMPTY_RESPONSE


@pytest.mark.asyncio
async def test_runner_handles_none_provider_response() -> None:
    result = await AgentRunner(FakeProvider([None]), ToolRegistry()).run([])

    assert result.answer == "The model returned no usable content."
    assert result.termination is RunTermination.EMPTY_RESPONSE


@pytest.mark.parametrize("max_iterations", [0, -1])
def test_runner_rejects_non_positive_iteration_limits(max_iterations: int) -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        AgentRunner(FakeProvider([]), ToolRegistry(), max_iterations=max_iterations)


@pytest.mark.asyncio
async def test_runner_minimum_limit_executes_exactly_one_round_then_stops() -> None:
    provider = FakeProvider(
        [ModelResponse(tool_calls=[ToolCall("call-1", "missing", {})])]
    )

    result = await AgentRunner(provider, ToolRegistry(), max_iterations=1).run([])

    assert result.termination is RunTermination.MAX_ITERATIONS
    assert result.iterations == 1
    assert len(provider.calls) == 1
    assert result.tools_used == ["missing"]
    assert json.loads(result.messages[-2]["content"])["error_code"] == "TOOL_NOT_FOUND"


@pytest.mark.asyncio
async def test_runner_stops_at_exact_iteration_boundary_without_extra_provider_call() -> None:
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "missing", {})]),
            ModelResponse(tool_calls=[ToolCall("call-2", "missing", {})]),
        ]
    )

    result = await AgentRunner(provider, ToolRegistry(), max_iterations=2).run([])

    assert result.termination is RunTermination.MAX_ITERATIONS
    assert result.iterations == 2
    assert len(provider.calls) == 2
    assert result.tools_used == ["missing", "missing"]


@pytest.mark.asyncio
async def test_runner_does_not_mutate_input_or_share_it_with_provider() -> None:
    messages = [{"role": "user", "content": {"parts": ["hello"]}}]
    original = deepcopy(messages)
    provider = FakeProvider([ModelResponse(content="done")])

    result = await AgentRunner(provider, ToolRegistry()).run(messages)
    provider.calls[0].messages[0]["content"]["parts"].append("changed")

    assert messages == original
    assert result.messages[0] == original[0]


@pytest.mark.asyncio
async def test_fake_provider_records_each_messages_and_tools_snapshot() -> None:
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall("call-1", "echo", {"text": "hello"})]),
            ModelResponse(content="done"),
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoTool())

    await AgentRunner(provider, registry).run([{"role": "user", "content": "test"}])

    assert len(provider.calls) == 2
    assert provider.calls[0].messages == [{"role": "user", "content": "test"}]
    assert provider.calls[0].tools is not None
    assert provider.calls[0].tools[0]["function"]["name"] == "echo"
    assert provider.calls[1].messages[-1]["role"] == "tool"

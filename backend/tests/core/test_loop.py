from __future__ import annotations

from collections.abc import Sequence

import pytest

from nanobot_core.agent import AgentContext, AgentLoop, AgentRunner
from nanobot_core.providers import Message
from nanobot_core.tools import ToolRegistry
from tests.core.fakes import FakeProvider, fake_response


@pytest.mark.asyncio
async def test_loop_builds_one_turn_from_explicit_context_and_history() -> None:
    provider = FakeProvider([fake_response(content="answer")])
    loop = AgentLoop(
        AgentRunner(provider, ToolRegistry()),
        context_builder=AgentContext(system_prompt="Explicit system."),
    )
    history = [{"role": "assistant", "content": "old answer"}]

    result = await loop.run("new question", history=history)

    assert result.answer == "answer"
    assert provider.calls[0].messages == [
        {"role": "system", "content": "Explicit system."},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "new question"},
    ]


class CapturingContextBuilder:
    def __init__(self) -> None:
        self.received: tuple[str, Sequence[Message]] | None = None

    def build_messages(
        self,
        *,
        user_message: str,
        history: Sequence[Message] = (),
    ) -> list[Message]:
        self.received = (user_message, history)
        return [{"role": "user", "content": f"built:{user_message}"}]


@pytest.mark.asyncio
async def test_loop_accepts_an_injected_context_builder() -> None:
    provider = FakeProvider([fake_response(content="answer")])
    builder = CapturingContextBuilder()
    loop = AgentLoop(
        AgentRunner(provider, ToolRegistry()),
        context_builder=builder,
    )

    await loop.run("question")

    assert builder.received == ("question", ())
    assert provider.calls[0].messages[-1]["content"] == "built:question"


@pytest.mark.parametrize("user_message", ["", " ", "\n\t"])
@pytest.mark.asyncio
async def test_loop_rejects_empty_user_messages_before_context_building(
    user_message: str,
) -> None:
    loop = AgentLoop(AgentRunner(FakeProvider([]), ToolRegistry()))

    with pytest.raises(ValueError, match="must not be empty"):
        await loop.run(user_message)

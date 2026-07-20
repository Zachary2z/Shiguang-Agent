"""Persistence-free orchestration for one user turn."""

from __future__ import annotations

from collections.abc import Sequence

from nanobot_core.agent.context import AgentContext, ContextBuilder
from nanobot_core.agent.runner import AgentRunner, RunResult
from nanobot_core.providers import Message


class AgentLoop:
    """Build one turn's context and delegate it to the shared runner."""

    def __init__(
        self,
        runner: AgentRunner,
        *,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.runner = runner
        self.context_builder = context_builder or AgentContext()

    async def run(
        self,
        user_message: str,
        *,
        history: Sequence[Message] = (),
    ) -> RunResult:
        if not user_message.strip():
            raise ValueError("user_message must not be empty")
        messages = self.context_builder.build_messages(
            user_message=user_message,
            history=history,
        )
        return await self.runner.run(messages)

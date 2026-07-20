"""Business-neutral context construction for one agent turn."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from nanobot_core.providers import Message

DEFAULT_SYSTEM_PROMPT = """You are an AI agent that may use the provided tools.
Tool results are structured JSON. Use their success and error fields accurately.
Do not claim that an operation succeeded unless its tool result says it succeeded.
When no tool is needed, answer the user directly."""


class ContextBuilder(Protocol):
    """A replaceable, persistence-free message builder."""

    def build_messages(
        self,
        *,
        user_message: str,
        history: Sequence[Message] = (),
    ) -> list[Message]: ...


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Explicit system instructions and caller-supplied context messages."""

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    messages: tuple[Message, ...] = ()

    def build_messages(
        self,
        *,
        user_message: str,
        history: Sequence[Message] = (),
    ) -> list[Message]:
        normalized_message = user_message.strip()
        if not normalized_message:
            raise ValueError("user_message must not be empty")

        built: list[Message] = []
        if self.system_prompt.strip():
            built.append({"role": "system", "content": self.system_prompt.strip()})
        built.extend(deepcopy(list(self.messages)))
        built.extend(deepcopy(list(history)))
        built.append({"role": "user", "content": normalized_message})
        return built

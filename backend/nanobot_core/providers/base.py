"""Provider-neutral model request and response contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

Message = dict[str, Any]
ToolDefinition = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model request to execute one registered tool."""

    id: str
    name: str
    arguments: dict[str, Any] | str


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """The minimal provider-independent response used by the core runner."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class ModelProvider(ABC):
    """Provider interface implemented by offline fakes and later model adapters."""

    @abstractmethod
    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
    ) -> ModelResponse:
        """Return the model's next text response or tool calls."""

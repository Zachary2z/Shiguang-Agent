"""Validated tool inputs and structured tool results."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class ToolErrorCode(StrEnum):
    """Stable failure categories understood by the runner and model."""

    NOT_FOUND = "TOOL_NOT_FOUND"
    INVALID_ARGUMENTS = "TOOL_INVALID_ARGUMENTS"
    EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"


class ToolResult(BaseModel):
    """JSON-serializable result returned by every tool execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    data: JsonValue | None = None
    message: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    error_code: ToolErrorCode | None = None
    retryable: bool = False
    recovery: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.success and self.error_code is not None:
            raise ValueError("successful tool results cannot include an error code")
        if not self.success and self.error_code is None:
            raise ValueError("failed tool results must include an error code")
        if self.success and self.retryable:
            raise ValueError("successful tool results cannot be retryable")
        return self

    @classmethod
    def ok(
        cls,
        *,
        message: str,
        data: JsonValue | None = None,
        sources: list[str] | None = None,
    ) -> ToolResult:
        return cls(
            success=True,
            data=data,
            message=message,
            sources=list(sources or []),
        )

    @classmethod
    def fail(
        cls,
        *,
        error_code: ToolErrorCode,
        message: str,
        data: JsonValue | None = None,
        sources: list[str] | None = None,
        retryable: bool = False,
        recovery: str | None = None,
    ) -> ToolResult:
        return cls(
            success=False,
            data=data,
            message=message,
            sources=list(sources or []),
            error_code=error_code,
            retryable=retryable,
            recovery=recovery,
        )

    def to_json(self) -> str:
        """Serialize with stable keys so tool messages are deterministic."""

        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class ToolInput(BaseModel):
    """Base for every tool input; unknown fields are always rejected."""

    model_config = ConfigDict(extra="forbid", strict=True)


ToolInputT = TypeVar("ToolInputT", bound=ToolInput)


class Tool(ABC, Generic[ToolInputT]):
    """A capability with an explicit Pydantic input schema."""

    name: str
    description: str
    input_model: type[ToolInputT]

    def to_definition(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_model.model_json_schema(),
            },
        }

    def validate(self, arguments: object) -> ToolInputT:
        return self.input_model.model_validate(arguments)

    @abstractmethod
    async def execute(self, arguments: ToolInputT) -> ToolResult:
        """Execute the capability and return a structured result."""

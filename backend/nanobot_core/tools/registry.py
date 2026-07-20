"""Deterministic tool registration, validation, and execution."""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import JsonValue, ValidationError

from nanobot_core.tools.base import Tool, ToolErrorCode, ToolResult


class ToolRegistry:
    """The single general-purpose registry used by the Nanobot core."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any]] = {}

    def register(self, tool: Tool[Any]) -> None:
        if not tool.name.strip():
            raise ValueError("tool name must not be empty")
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    def definitions(self) -> list[dict[str, object]]:
        return [self._tools[name].to_definition() for name in sorted(self._tools)]

    async def execute(self, name: str, arguments: object) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult.fail(
                error_code=ToolErrorCode.NOT_FOUND,
                message=f"No tool named {name!r} is registered.",
                recovery="Choose one of the tools provided in the tool definitions.",
            )

        parsed_arguments = self._parse_arguments(arguments)
        if isinstance(parsed_arguments, ToolResult):
            return parsed_arguments

        try:
            validated = tool.validate(parsed_arguments)
        except ValidationError as exc:
            errors = [
                {
                    "path": ".".join(str(part) for part in error["loc"]) or "$",
                    "type": str(error["type"]),
                }
                for error in exc.errors(
                    include_context=False,
                    include_input=False,
                    include_url=False,
                )
            ]
            return ToolResult.fail(
                error_code=ToolErrorCode.INVALID_ARGUMENTS,
                message="Tool arguments did not match the required schema.",
                data={"validation_errors": cast(JsonValue, errors)},
                recovery="Correct the listed fields and call the tool again.",
            )

        try:
            result = await tool.execute(validated)
        except Exception:
            return ToolResult.fail(
                error_code=ToolErrorCode.EXECUTION_FAILED,
                message="The tool could not complete its operation.",
                retryable=False,
                recovery="Use another available approach or report that the tool failed.",
            )

        if not isinstance(result, ToolResult):
            return ToolResult.fail(
                error_code=ToolErrorCode.EXECUTION_FAILED,
                message="The tool returned an invalid result.",
                recovery="Report that the tool failed to return a structured result.",
            )
        return result

    @staticmethod
    def _parse_arguments(arguments: object) -> object | ToolResult:
        if not isinstance(arguments, str):
            return arguments
        try:
            parsed: object = json.loads(arguments)
            return parsed
        except (json.JSONDecodeError, TypeError):
            return ToolResult.fail(
                error_code=ToolErrorCode.INVALID_ARGUMENTS,
                message="Tool arguments were not valid JSON.",
                recovery="Call the tool again with one JSON object matching its schema.",
            )

    def __contains__(self, name: str) -> bool:
        return name in self._tools

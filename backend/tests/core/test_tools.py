from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from nanobot_core.tools import ToolErrorCode, ToolRegistry, ToolResult
from tests.core.fakes import EchoTool, ExplodingTool


def test_tool_result_success_contract_is_json_serializable() -> None:
    result = ToolResult.ok(
        message="Found one result.",
        data={"count": 1, "items": ["a"]},
        sources=["fixture://one"],
    )

    payload = json.loads(result.to_json())

    assert payload == {
        "data": {"count": 1, "items": ["a"]},
        "error_code": None,
        "message": "Found one result.",
        "recovery": None,
        "retryable": False,
        "sources": ["fixture://one"],
        "success": True,
    }


def test_tool_result_failure_contract_is_json_serializable() -> None:
    result = ToolResult.fail(
        error_code=ToolErrorCode.EXECUTION_FAILED,
        message="Operation failed.",
        retryable=True,
        recovery="Try later.",
    )

    payload = json.loads(result.to_json())

    assert payload["success"] is False
    assert payload["error_code"] == "TOOL_EXECUTION_FAILED"
    assert payload["retryable"] is True
    assert payload["recovery"] == "Try later."


@pytest.mark.parametrize(
    "fields",
    [
        {"success": True, "message": "bad", "error_code": "TOOL_NOT_FOUND"},
        {"success": False, "message": "bad"},
        {"success": True, "message": "bad", "retryable": True},
    ],
)
def test_tool_result_rejects_inconsistent_states(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate(fields)


def test_registry_definitions_are_sorted_by_name() -> None:
    first = EchoTool()
    first.name = "z-last"
    second = EchoTool()
    second.name = "a-first"
    registry = ToolRegistry()
    registry.register(first)
    registry.register(second)

    definitions = registry.definitions()

    assert [item["function"]["name"] for item in definitions] == ["a-first", "z-last"]  # type: ignore[index]
    parameters = definitions[0]["function"]["parameters"]  # type: ignore[index]
    assert parameters["additionalProperties"] is False  # type: ignore[index]


def test_registry_rejects_duplicate_names_without_replacing_original() -> None:
    original = EchoTool()
    duplicate = EchoTool()
    registry = ToolRegistry()
    registry.register(original)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(duplicate)

    assert registry.get("echo") is original


@pytest.mark.asyncio
async def test_registry_returns_structured_unknown_tool_failure() -> None:
    result = await ToolRegistry().execute("missing", {})

    assert result.success is False
    assert result.error_code is ToolErrorCode.NOT_FOUND


@pytest.mark.parametrize("arguments", ["{not-json", "[]", 42, None])
@pytest.mark.asyncio
async def test_registry_rejects_non_object_or_invalid_json_arguments(arguments: object) -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = await registry.execute("echo", arguments)

    assert result.success is False
    assert result.error_code is ToolErrorCode.INVALID_ARGUMENTS


@pytest.mark.parametrize(
    ("arguments", "expected_error_type"),
    [
        ({}, "missing"),
        ({"text": "hello", "unexpected": True}, "extra_forbidden"),
        ({"text": 123}, "string_type"),
    ],
)
@pytest.mark.asyncio
async def test_registry_classifies_pydantic_validation_failures(
    arguments: object,
    expected_error_type: str,
) -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = await registry.execute("echo", arguments)

    assert result.error_code is ToolErrorCode.INVALID_ARGUMENTS
    assert result.data is not None
    assert expected_error_type in result.to_json()


@pytest.mark.asyncio
async def test_registry_executes_validated_tool() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(EchoTool(calls))

    result = await registry.execute("echo", '{"text":"hello"}')

    assert result.success is True
    assert result.data == {"text": "hello"}
    assert calls == ["hello"]


@pytest.mark.asyncio
async def test_registry_hides_tool_exception_details() -> None:
    registry = ToolRegistry()
    registry.register(ExplodingTool())

    result = await registry.execute("explode", {"text": "hello"})

    assert result.success is False
    assert result.error_code is ToolErrorCode.EXECUTION_FAILED
    assert "internal-secret-detail" not in result.to_json()

"""Explicitly gated, side-effect-free real model Tool Calling verification."""

from __future__ import annotations

import os

import pytest

from app.config import DEFAULT_ENV_FILE, ModelConfigurationError, Settings
from app.providers import OpenAICompatibleProvider
from nanobot_core.agent import AgentRunner, RunTermination
from nanobot_core.tools import Tool, ToolInput, ToolRegistry, ToolResult


class AddInput(ToolInput):
    left: int
    right: int


class AddTestNumbersTool(Tool[AddInput]):
    """A deterministic test-only tool with no file, network, or message side effects."""

    name = "add_test_numbers"
    description = "Add two integers for a deterministic provider integration test."
    input_model = AddInput

    async def execute(self, arguments: AddInput) -> ToolResult:
        return ToolResult.ok(
            message="The deterministic addition completed.",
            data={"sum": arguments.left + arguments.right},
        )


def _real_provider_settings() -> Settings:
    if os.environ.get("RUN_REAL_MODEL_TESTS") != "1":
        pytest.skip(
            "real provider test not run: set RUN_REAL_MODEL_TESTS=1 to authorize one "
            "side-effect-free Tool Calling run; no network request was made"
        )

    settings = Settings(_env_file=DEFAULT_ENV_FILE)  # type: ignore[call-arg]
    try:
        settings.require_model_provider()
    except ModelConfigurationError as exc:
        pytest.skip(f"real provider test not run: {exc}; no network request was made")
    return settings


@pytest.mark.real_provider
@pytest.mark.asyncio
async def test_real_model_completes_one_side_effect_free_tool_call() -> None:
    provider = OpenAICompatibleProvider.from_settings(_real_provider_settings())
    registry = ToolRegistry()
    registry.register(AddTestNumbersTool())
    try:
        result = await AgentRunner(provider, registry, max_iterations=2).run(
            [
                {
                    "role": "system",
                    "content": (
                        "Use add_test_numbers exactly once with left=17 and right=25, then "
                        "answer with the returned sum. Do not calculate it without the tool."
                    ),
                },
                {"role": "user", "content": "What is the test sum?"},
            ]
        )
    finally:
        await provider.close()

    assert result.termination is RunTermination.COMPLETED
    assert result.tools_used == ["add_test_numbers"]
    assert "42" in result.answer

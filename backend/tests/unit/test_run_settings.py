"""Strict offline configuration for run bounds and pricing."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.config import Settings
from nanobot_core.agent import MAX_RUN_TIMEOUT_SECONDS, MAX_TOOL_CALLS_PER_RUN


def test_run_and_pricing_settings_accept_decimal_strings_and_legal_zero() -> None:
    settings = Settings(
        _env_file=None,
        model_input_price_per_million_tokens="0",
        model_output_price_per_million_tokens="12.345",
        model_cost_currency="CNY",
        model_pricing_source="manual_2026-07-21",
        agent_max_tool_calls=MAX_TOOL_CALLS_PER_RUN,
        agent_timeout_seconds=MAX_RUN_TIMEOUT_SECONDS,
    )

    assert settings.model_input_price_per_million_tokens == Decimal(0)
    assert settings.model_output_price_per_million_tokens == Decimal("12.345")
    assert settings.agent_max_tool_calls == MAX_TOOL_CALLS_PER_RUN
    assert settings.agent_timeout_seconds == MAX_RUN_TIMEOUT_SECONDS


def test_run_settings_defaults_reuse_core_hard_ceiling_constants() -> None:
    settings = Settings(_env_file=None)

    assert settings.agent_max_tool_calls == MAX_TOOL_CALLS_PER_RUN
    assert settings.agent_timeout_seconds == MAX_RUN_TIMEOUT_SECONDS


def test_run_settings_accept_lower_tool_limit_and_positive_subsecond_timeout() -> None:
    settings = Settings(
        _env_file=None,
        agent_max_tool_calls=1,
        agent_timeout_seconds=0.001,
    )

    assert settings.agent_max_tool_calls == 1
    assert settings.agent_timeout_seconds == 0.001


@pytest.mark.parametrize(
    "field_values",
    [
        {"model_input_price_per_million_tokens": -1},
        {"model_input_price_per_million_tokens": "NaN"},
        {"model_input_price_per_million_tokens": "Infinity"},
        {"model_input_price_per_million_tokens": True},
        {"model_input_price_per_million_tokens": 0.1},
        {"model_output_price_per_million_tokens": -1},
        {"agent_max_tool_calls": 0},
        {"agent_max_tool_calls": -1},
        {"agent_max_tool_calls": 9},
        {"agent_max_tool_calls": True},
        {"agent_timeout_seconds": 0},
        {"agent_timeout_seconds": -1},
        {"agent_timeout_seconds": 60.001},
        {"agent_timeout_seconds": float("nan")},
        {"agent_timeout_seconds": float("inf")},
        {"agent_timeout_seconds": float("-inf")},
        {"agent_timeout_seconds": True},
        {"model_cost_currency": "cny"},
        {"model_pricing_source": "unsafe source"},
    ],
)
def test_run_and_pricing_settings_reject_invalid_values(
    field_values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **field_values)  # type: ignore[arg-type]

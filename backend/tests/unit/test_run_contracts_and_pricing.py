"""AgentRun contracts, state transitions, identifiers, and Decimal pricing."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.application.pricing import ConfiguredPricingPolicy
from app.domain.identifiers import (
    generate_agent_run_id,
    generate_tool_run_id,
    generate_trace_id,
    validate_trace_id,
)
from app.domain.runs import AgentRunCreate, AgentRunStatus
from app.domain.runs.statuses import ensure_run_transition
from nanobot_core.providers import TokenUsage


def test_generated_identifiers_are_stable_shape_unique_and_not_sequential() -> None:
    trace_ids = {generate_trace_id() for _ in range(128)}
    run_ids = {generate_agent_run_id() for _ in range(128)}
    tool_ids = {generate_tool_run_id() for _ in range(128)}

    assert len(trace_ids) == len(run_ids) == len(tool_ids) == 128
    assert all(validate_trace_id(trace_id) == trace_id for trace_id in trace_ids)
    assert all(run_id.startswith("arn_") and len(run_id) == 36 for run_id in run_ids)
    assert all(tool_id.startswith("tlr_") and len(tool_id) == 36 for tool_id in tool_ids)


@pytest.mark.parametrize(
    "trace_id",
    ["1", "trc_short", "trc_" + "a" * 31, "trc_" + "a" * 33, "trc_" + "!" * 32],
)
def test_trace_id_validation_rejects_predictable_or_malformed_shapes(trace_id: str) -> None:
    with pytest.raises(ValueError, match="trace_id"):
        validate_trace_id(trace_id)


def test_create_contract_rejects_unsafe_or_unknown_values() -> None:
    with pytest.raises(ValidationError):
        AgentRunCreate(intent="collect content", workflow="collect")
    with pytest.raises(ValidationError):
        AgentRunCreate(intent="collect", workflow="collect", unexpected=True)  # type: ignore[call-arg]


def test_agent_run_state_machine_allows_only_forward_documented_transitions() -> None:
    ensure_run_transition(AgentRunStatus.QUEUED, AgentRunStatus.RUNNING)
    ensure_run_transition(AgentRunStatus.RUNNING, AgentRunStatus.WAITING_USER)
    ensure_run_transition(AgentRunStatus.WAITING_USER, AgentRunStatus.RUNNING)
    ensure_run_transition(AgentRunStatus.RUNNING, AgentRunStatus.SUCCEEDED)
    ensure_run_transition(AgentRunStatus.SUCCEEDED, AgentRunStatus.SUCCEEDED)

    with pytest.raises(ValueError, match="illegal AgentRun transition"):
        ensure_run_transition(AgentRunStatus.QUEUED, AgentRunStatus.SUCCEEDED)
    with pytest.raises(ValueError, match="illegal AgentRun transition"):
        ensure_run_transition(AgentRunStatus.SUCCEEDED, AgentRunStatus.RUNNING)


def _policy(
    *,
    model_name: str | None = "fixture-model",
    input_price: Decimal | None = Decimal("2.5"),
    output_price: Decimal | None = Decimal("10"),
) -> ConfiguredPricingPolicy:
    return ConfiguredPricingPolicy(
        model_name=model_name,
        input_price_per_million_tokens=input_price,
        output_price_per_million_tokens=output_price,
        currency="CNY",
        source="test_rates_v1",
    )


def test_decimal_pricing_preserves_zero_and_rounds_half_up_to_database_scale() -> None:
    zero = _policy().estimate(
        "fixture-model", TokenUsage(input_tokens=0, output_tokens=0)
    )
    rounded = _policy(input_price=Decimal("0.005")).estimate(
        "fixture-model", TokenUsage(input_tokens=1, output_tokens=0)
    )

    assert zero.amount == Decimal("0E-8")
    assert zero.currency == "CNY"
    assert zero.unknown_reason is None
    assert rounded.amount == Decimal("1E-8")


@pytest.mark.parametrize(
    ("model_name", "usage", "input_price", "output_price", "reason"),
    [
        (
            "other-model",
            TokenUsage(input_tokens=1, output_tokens=1),
            Decimal("1"),
            Decimal("1"),
            "model_price_not_configured",
        ),
        (
            "fixture-model",
            TokenUsage(input_tokens=1, output_tokens=1),
            None,
            Decimal("1"),
            "model_price_incomplete",
        ),
        (
            "fixture-model",
            TokenUsage(input_tokens=None, output_tokens=1),
            Decimal("1"),
            Decimal("1"),
            "token_usage_incomplete",
        ),
    ],
)
def test_incomplete_price_or_usage_is_unknown_not_fake_zero(
    model_name: str,
    usage: TokenUsage,
    input_price: Decimal | None,
    output_price: Decimal | None,
    reason: str,
) -> None:
    estimate = _policy(input_price=input_price, output_price=output_price).estimate(
        model_name, usage
    )

    assert estimate.amount is None
    assert estimate.currency is None
    assert estimate.unknown_reason == reason


@pytest.mark.parametrize(
    "invalid_price",
    [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.0, True],
)
def test_configured_pricing_policy_rejects_non_decimal_or_unsafe_prices(
    invalid_price: object,
) -> None:
    with pytest.raises(ValueError, match="finite non-negative Decimal"):
        ConfiguredPricingPolicy(
            model_name="fixture-model",
            input_price_per_million_tokens=invalid_price,  # type: ignore[arg-type]
            output_price_per_million_tokens=Decimal("1"),
            currency="CNY",
            source="test_rates_v1",
        )

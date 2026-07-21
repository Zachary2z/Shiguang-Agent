"""Injectable Decimal pricing for provider-neutral TokenUsage values."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.config import Settings
from nanobot_core.providers import TokenUsage

_ONE_MILLION = Decimal(1_000_000)
_DATABASE_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """A known Decimal cost or one explicit reason why it is unknown."""

    amount: Decimal | None
    currency: str | None
    source: str
    unknown_reason: str | None


class PricingPolicy(Protocol):
    """Estimate one model response without relying on online prices."""

    def estimate(self, model_name: str, usage: TokenUsage) -> CostEstimate:
        """Return a deterministic configured estimate."""


class ConfiguredPricingPolicy:
    """Price only the configured model using explicitly supplied per-million rates."""

    def __init__(
        self,
        *,
        model_name: str | None,
        input_price_per_million_tokens: Decimal | None,
        output_price_per_million_tokens: Decimal | None,
        currency: str,
        source: str,
    ) -> None:
        for field_name, value in (
            ("input_price_per_million_tokens", input_price_per_million_tokens),
            ("output_price_per_million_tokens", output_price_per_million_tokens),
        ):
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite() or value < 0
            ):
                raise ValueError(f"{field_name} must be a finite non-negative Decimal or None")
        if (
            len(currency) != 3
            or not currency.isascii()
            or not currency.isalpha()
            or not currency.isupper()
        ):
            raise ValueError("currency must be a three-letter uppercase code")
        if not source or len(source) > 64 or not all(
            character.isalnum() or character in "._:-" for character in source
        ):
            raise ValueError("source must be a safe label up to 64 characters")
        self._model_name = model_name
        self._input_price = input_price_per_million_tokens
        self._output_price = output_price_per_million_tokens
        self._currency = currency
        self._source = source

    @classmethod
    def from_settings(cls, settings: Settings) -> ConfiguredPricingPolicy:
        model_name = settings.model_name.strip() if settings.model_name else None
        return cls(
            model_name=model_name,
            input_price_per_million_tokens=(
                settings.model_input_price_per_million_tokens
            ),
            output_price_per_million_tokens=(
                settings.model_output_price_per_million_tokens
            ),
            currency=settings.model_cost_currency,
            source=settings.model_pricing_source,
        )

    def estimate(self, model_name: str, usage: TokenUsage) -> CostEstimate:
        if self._model_name is None or model_name != self._model_name:
            return CostEstimate(None, None, self._source, "model_price_not_configured")
        if self._input_price is None or self._output_price is None:
            return CostEstimate(None, None, self._source, "model_price_incomplete")
        if usage.input_tokens is None or usage.output_tokens is None:
            return CostEstimate(None, None, self._source, "token_usage_incomplete")

        amount = (
            Decimal(usage.input_tokens) * self._input_price
            + Decimal(usage.output_tokens) * self._output_price
        ) / _ONE_MILLION
        rounded_amount = amount.quantize(_DATABASE_QUANTUM, rounding=ROUND_HALF_UP)
        return CostEstimate(rounded_amount, self._currency, self._source, None)

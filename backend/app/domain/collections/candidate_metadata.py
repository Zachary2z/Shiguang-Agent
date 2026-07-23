"""Shared candidate metadata used by extraction and persisted collections."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

PRICE_CURRENCY_CNY = "CNY"
_SENSITIVE_TEXT = re.compile(
    r"(?:authorization\s*[:=]|set-cookie\s*:|cookie\s*[:=]|bearer\s+\S+|"
    r"api[-_ ]?key\s*[:=]|\bsk-[a-z0-9]{8,})",
    re.IGNORECASE,
)


class CandidateField(StrEnum):
    """Provider-neutral fields that can be missing or uncertain."""

    TITLE = "title"
    CITY_HINT = "city_hint"
    DISTRICT = "district"
    ADDRESS = "address"
    BUSINESS_DISTRICT = "business_district"
    LANDMARK = "landmark"
    METRO_STATION = "metro_station"
    EVENT_START_AT = "event_start_at"
    EVENT_END_AT = "event_end_at"
    PRICE = "price"
    TAGS = "tags"


class Uncertainty(BaseModel):
    """A field whose value or interpretation still needs confirmation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    field: CandidateField
    reason: str = Field(min_length=1, max_length=240, repr=False)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return normalize_required_candidate_text(
            value,
            field_name="uncertainty reason",
        )


def default_cny_for_known_price(values: Mapping[str, Any]) -> dict[str, Any]:
    """Copy values and pair an already-recognized local amount with internal CNY."""

    normalized = dict(values)
    if (
        normalized.get("price_amount") is not None
        and normalized.get("price_currency") is None
    ):
        normalized["price_currency"] = PRICE_CURRENCY_CNY
    return normalized


def validate_cny_price_pair(
    price_amount: Decimal | None,
    price_currency: str | None,
) -> None:
    """Enforce the sole formal price representation used by the China-only product."""

    if (price_amount is None) is not (price_currency is None):
        raise PydanticCustomError(
            "price_pair_incomplete",
            "Price amount and currency must be provided together.",
        )
    if price_currency is not None and price_currency != PRICE_CURRENCY_CNY:
        raise PydanticCustomError(
            "price_currency_unsupported",
            "The price currency is unsupported.",
        )


def normalize_required_candidate_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")
    if _SENSITIVE_TEXT.search(normalized) is not None:
        raise ValueError(f"{field_name} contains disallowed sensitive text")
    return normalized


def normalize_optional_candidate_text(
    value: str | None,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return normalize_required_candidate_text(value, field_name=field_name)

"""Read-only plan-sharing contracts and the single token/expiry policy."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.places import TransportMode
from app.domain.time import require_aware_utc

SHARE_TOKEN_BYTES = 32
SHARE_TOKEN_LENGTH = 43
SHARE_LIFETIME_AFTER_PLAN = timedelta(days=7)


class ShareContract(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class OwnerShareStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    EXPIRED = "expired"


class PublicShareStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


class SharedPlanItem(ShareContract):
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime
    public_address: str | None = Field(default=None, max_length=500)
    visit_duration_seconds: int = Field(gt=0)
    transport_mode: TransportMode
    travel_duration_seconds: int = Field(ge=0)
    travel_distance_meters: int = Field(ge=0)
    buffer_after_seconds: int = Field(ge=0)
    price_amount: Decimal | None = Field(default=None, ge=0)
    price_currency: str | None = Field(default=None, pattern=r"^CNY$")
    source_label: str = Field(min_length=1, max_length=80)
    risks: tuple[str, ...] = ()
    queried_at: datetime | None = None
    map_url: str | None = Field(default=None, max_length=2048)

    @field_validator("start_at", "end_at", "queried_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @model_validator(mode="after")
    def validate_shape(self) -> SharedPlanItem:
        if self.end_at <= self.start_at:
            raise ValueError("shared item end must follow start")
        if (self.price_amount is None) is not (self.price_currency is None):
            raise ValueError("shared price amount and currency must be paired")
        return self


class SharedPlanSnapshot(ShareContract):
    version: int = Field(ge=1)
    confirmed_at: datetime
    updated_at: datetime
    start_at: datetime
    end_at: datetime
    origin_label: str = Field(min_length=1, max_length=100)
    items: tuple[SharedPlanItem, ...] = Field(min_length=1, max_length=2)
    total_cost_amount: Decimal | None = Field(default=None, ge=0)
    total_cost_currency: str | None = Field(default=None, pattern=r"^CNY$")
    risks: tuple[str, ...] = ()
    expires_at: datetime

    @field_validator(
        "confirmed_at",
        "updated_at",
        "start_at",
        "end_at",
        "expires_at",
    )
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @model_validator(mode="after")
    def validate_shape(self) -> SharedPlanSnapshot:
        if self.end_at <= self.start_at:
            raise ValueError("shared plan end must follow start")
        if self.expires_at != share_expiry_for(self.end_at):
            raise ValueError("shared plan expiry must be seven days after plan end")
        if (self.total_cost_amount is None) is not (
            self.total_cost_currency is None
        ):
            raise ValueError("shared total amount and currency must be paired")
        return self


def generate_share_token() -> str:
    """Generate a 256-bit bearer token suitable for a URL path segment."""

    token = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
    if len(token) != SHARE_TOKEN_LENGTH:  # pragma: no cover - stdlib invariant
        raise RuntimeError("share token encoding length is invalid")
    return token


def hash_share_token(token: str) -> str:
    """Hash every supplied token without retaining or echoing the bearer value."""

    return hashlib.sha256(token.encode("utf-8", errors="replace")).hexdigest()


def share_expiry_for(plan_end_at: datetime) -> datetime:
    return require_aware_utc(plan_end_at) + SHARE_LIFETIME_AFTER_PLAN


__all__ = [
    "OwnerShareStatus",
    "PublicShareStatus",
    "SHARE_LIFETIME_AFTER_PLAN",
    "SHARE_TOKEN_BYTES",
    "SHARE_TOKEN_LENGTH",
    "SharedPlanItem",
    "SharedPlanSnapshot",
    "generate_share_token",
    "hash_share_token",
    "share_expiry_for",
]

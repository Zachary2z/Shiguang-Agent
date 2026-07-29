"""Structured, user-controlled long-term memory contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.identifiers import (
    validate_feedback_id,
    validate_memory_id,
    validate_plan_id,
)
from app.domain.time import require_aware_utc


class MemoryContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class MemoryType(StrEnum):
    POSITIVE_PREFERENCE = "positive_preference"
    NEGATIVE_PREFERENCE = "negative_preference"
    PACE_PREFERENCE = "pace_preference"
    USUAL_AREA = "usual_area"


class MemorySourceType(StrEnum):
    EXPLICIT_USER = "explicit_user"
    FEEDBACK_INFERENCE = "feedback_inference"


class MemoryConfirmationStatus(StrEnum):
    CONFIRMED = "confirmed"


class MemorySuggestionDecision(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class MemorySource(MemoryContract):
    type: MemorySourceType
    summary: str = Field(min_length=1, max_length=500)
    feedback_id: str | None = None
    plan_id: str | None = None

    @field_validator("feedback_id")
    @classmethod
    def validate_feedback(cls, value: str | None) -> str | None:
        return None if value is None else validate_feedback_id(value)

    @field_validator("plan_id")
    @classmethod
    def validate_plan(cls, value: str | None) -> str | None:
        return None if value is None else validate_plan_id(value)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        inferred = self.type is MemorySourceType.FEEDBACK_INFERENCE
        if inferred != (self.feedback_id is not None and self.plan_id is not None):
            raise ValueError("feedback sources require feedback and plan ids")
        return self


class Memory(MemoryContract):
    id: str
    type: MemoryType
    content: str = Field(min_length=1, max_length=500)
    value: str = Field(min_length=1, max_length=100)
    source: MemorySource
    confirmation_status: MemoryConfirmationStatus = MemoryConfirmationStatus.CONFIRMED
    confidence: int = Field(ge=0, le=100)
    expires_at: datetime | None = None
    disabled_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    version: int = Field(ge=1)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_memory_id(value)

    @field_validator(
        "expires_at", "disabled_at", "deleted_at", "created_at", "updated_at", "last_used_at"
    )
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @field_validator("content", "value")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("memory text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_value(self) -> Self:
        if self.type is MemoryType.PACE_PREFERENCE:
            if self.value not in {"relaxed", "balanced", "packed"}:
                raise ValueError("pace memory value is invalid")
        if self.type is MemoryType.USUAL_AREA:
            # Import the plan-side coarse-area contract only when a location memory
            # is validated. Importing the ``plans`` package while this module is
            # defining MemoryType creates a genuine domain initialization cycle.
            from app.domain.plans.contracts import ActivityArea

            ActivityArea.from_memory_value(self.value)
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("memory expiry must follow creation")
        if self.updated_at < self.created_at:
            raise ValueError("memory update cannot precede creation")
        return self

    def is_effective(self, at: datetime) -> bool:
        current = require_aware_utc(at)
        return (
            self.confirmation_status is MemoryConfirmationStatus.CONFIRMED
            and self.disabled_at is None
            and self.deleted_at is None
            and (self.expires_at is None or current < self.expires_at)
        )


class MemoryUsage(MemoryContract):
    memory_id: str
    plan_id: str
    basis: str = Field(min_length=1, max_length=500)
    used_at: datetime

    @field_validator("memory_id")
    @classmethod
    def validate_memory(cls, value: str) -> str:
        return validate_memory_id(value)

    @field_validator("plan_id")
    @classmethod
    def validate_plan(cls, value: str) -> str:
        return validate_plan_id(value)

    @field_validator("used_at")
    @classmethod
    def normalize_used_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)


class MemorySuggestion(MemoryContract):
    id: str
    plan_id: str
    memory_type: MemoryType | None = None
    content: str = Field(min_length=1, max_length=500)
    value: str | None = Field(default=None, min_length=1, max_length=100)
    evidence_summary: str = Field(min_length=1, max_length=500)
    created_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_feedback_id(value)

    @field_validator("plan_id")
    @classmethod
    def validate_plan(cls, value: str) -> str:
        return validate_plan_id(value)

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)


class MemoryNotFoundError(LookupError):
    pass


class MemoryVersionConflictError(RuntimeError):
    pass


class MemorySuggestionUnavailableError(LookupError):
    pass


class SensitiveMemoryRejectedError(ValueError):
    """The submitted location scope is not safe for long-term memory."""


__all__ = [
    "Memory",
    "MemoryConfirmationStatus",
    "MemoryNotFoundError",
    "MemorySource",
    "MemorySourceType",
    "MemorySuggestion",
    "MemorySuggestionDecision",
    "MemorySuggestionUnavailableError",
    "MemoryType",
    "MemoryUsage",
    "MemoryVersionConflictError",
    "SensitiveMemoryRejectedError",
]

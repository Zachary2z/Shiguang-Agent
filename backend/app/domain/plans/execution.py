"""Confirmed-plan execution, feedback, and preference-suggestion contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from app.domain.identifiers import (
    validate_collection_item_id,
    validate_feedback_id,
    validate_plan_id,
    validate_plan_item_id,
)
from app.domain.memories import MemoryType
from app.domain.plans.contracts import PlanContract
from app.domain.time import require_aware_utc


class PlanCompletionStatus(StrEnum):
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    NOT_COMPLETED = "not_completed"


class PlanItemExecutionStatus(StrEnum):
    PENDING = "pending"
    VISITED = "visited"
    NOT_VISITED = "not_visited"


class PreferenceSuggestion(PlanContract):
    content: str = Field(min_length=1, max_length=500)
    memory_type: MemoryType
    value: str = Field(min_length=1, max_length=100)
    evidence_summary: str = Field(min_length=1, max_length=500)
    confirmation_status: str = Field(default="pending", pattern=r"^pending$")


class PlanFeedbackSelectionError(ValueError):
    """The selected items cannot represent the requested completion state."""


class PlanExecutionItem(PlanContract):
    id: str
    title: str
    start_at: datetime
    end_at: datetime
    address: str | None = None
    collection_item_ids: tuple[str, ...] = ()
    is_external: bool
    status: PlanItemExecutionStatus
    navigation_uri: str | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_plan_item_id(value)

    @field_validator("collection_item_ids")
    @classmethod
    def validate_collections(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_collection_item_id(item) for item in value)
        if len(set(validated)) != len(validated):
            raise ValueError("collection item ids must be unique")
        return validated

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return require_aware_utc(value)


class PlanFeedback(PlanContract):
    id: str
    plan_id: str
    revision: int = Field(ge=1)
    completion_status: PlanCompletionStatus
    reason: str | None = Field(default=None, max_length=500)
    visited_plan_item_ids: tuple[str, ...] = ()
    preference_suggestion: PreferenceSuggestion | None = None
    created_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_feedback_id(value)

    @field_validator("plan_id")
    @classmethod
    def validate_plan(cls, value: str) -> str:
        return validate_plan_id(value)

    @field_validator("visited_plan_item_ids")
    @classmethod
    def validate_items(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_plan_item_id(item) for item in value)
        if len(set(validated)) != len(validated):
            raise ValueError("visited plan item ids must be unique")
        return validated

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        has_items = bool(self.visited_plan_item_ids)
        if self.completion_status is PlanCompletionStatus.PARTIALLY_COMPLETED:
            if not has_items:
                raise ValueError("partial completion requires visited plan items")
        elif self.completion_status is PlanCompletionStatus.NOT_COMPLETED:
            if has_items:
                raise ValueError("not completed cannot include visited plan items")
        return self


__all__ = [
    "PlanCompletionStatus",
    "PlanExecutionItem",
    "PlanFeedback",
    "PlanFeedbackSelectionError",
    "PlanItemExecutionStatus",
    "PreferenceSuggestion",
]

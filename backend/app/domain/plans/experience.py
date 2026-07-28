"""Persistent M1-5 plan versions, confirmations, and approval records."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from app.domain.identifiers import (
    validate_approval_id,
    validate_plan_id,
    validate_trace_id,
    validate_user_id,
)
from app.domain.plans.contracts import PlanConstraints, PlanContract
from app.domain.plans.drafts import PlanDraftResult
from app.domain.time import require_aware_utc


class PlanStatus(StrEnum):
    GENERATING = "generating"
    WAITING_APPROVAL = "waiting_approval"
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    NOT_COMPLETED = "not_completed"


class PlanOperation(StrEnum):
    GENERATE = "generate"
    ADJUST = "adjust"


class ApprovalAction(StrEnum):
    EXTERNAL_PLACE_SUPPLEMENT = "external_place_supplement"
    CONFIRM_PLAN = "confirm_plan"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PlanVersion(PlanContract):
    id: str
    root_plan_id: str
    parent_plan_id: str | None = None
    user_id: str
    version: int = Field(ge=1)
    operation: PlanOperation
    status: PlanStatus
    constraints: PlanConstraints
    adjustment_text: str | None = Field(default=None, min_length=1, max_length=1000)
    draft: PlanDraftResult | None = None
    trace_id: str
    idempotency_key: str = Field(min_length=1, max_length=128, repr=False)
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
    error_code: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("id", "root_plan_id", "parent_plan_id")
    @classmethod
    def validate_plan_ids(cls, value: str | None) -> str | None:
        return None if value is None else validate_plan_id(value)

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("trace_id")
    @classmethod
    def validate_trace(cls, value: str) -> str:
        return validate_trace_id(value)

    @field_validator("created_at", "updated_at", "confirmed_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if self.version == 1:
            if self.id != self.root_plan_id or self.parent_plan_id is not None:
                raise ValueError("the first version must be its own root")
            if self.operation is not PlanOperation.GENERATE:
                raise ValueError("the first version must be a generation")
        elif (
            self.id == self.root_plan_id
            or self.parent_plan_id is None
            or self.operation is not PlanOperation.ADJUST
        ):
            raise ValueError("adjusted versions require a distinct root and parent")
        if (self.operation is PlanOperation.ADJUST) is (self.adjustment_text is None):
            raise ValueError("only adjustments carry adjustment text")
        if self.status in {
            PlanStatus.DRAFT,
            PlanStatus.CONFIRMED,
            PlanStatus.SUPERSEDED,
            PlanStatus.COMPLETED,
            PlanStatus.PARTIALLY_COMPLETED,
            PlanStatus.NOT_COMPLETED,
        } and self.draft is None:
            raise ValueError("viewable plan versions require a draft")
        if self.status in {
            PlanStatus.GENERATING,
            PlanStatus.WAITING_APPROVAL,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
        } and self.draft is not None:
            raise ValueError("non-viewable plan versions cannot carry a draft")
        if self.status is PlanStatus.CONFIRMED and self.confirmed_at is None:
            raise ValueError("confirmed versions require confirmed_at")
        if (
            self.status
            not in {
                PlanStatus.CONFIRMED,
                PlanStatus.SUPERSEDED,
                PlanStatus.COMPLETED,
                PlanStatus.PARTIALLY_COMPLETED,
                PlanStatus.NOT_COMPLETED,
            }
            and self.confirmed_at is not None
        ):
            raise ValueError("only confirmed history carries confirmed_at")
        if (self.status is PlanStatus.FAILED) is (self.error_code is None):
            raise ValueError("only failed versions carry an error code")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class PlanApproval(PlanContract):
    id: str
    user_id: str
    action: ApprovalAction
    target_plan_id: str
    external_requirement_id: str | None = Field(
        default=None,
        pattern=r"^approval_[0-9a-f]{32}$",
    )
    display_text: str = Field(min_length=1, max_length=500)
    status: ApprovalStatus
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_approval_id(value)

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("target_plan_id")
    @classmethod
    def validate_target(cls, value: str) -> str:
        return validate_plan_id(value)

    @field_validator("created_at", "expires_at", "decided_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if (
            self.action is ApprovalAction.EXTERNAL_PLACE_SUPPLEMENT
        ) is (self.external_requirement_id is None):
            raise ValueError(
                "only external supplement approvals carry a requirement id"
            )
        if self.expires_at <= self.created_at:
            raise ValueError("approval expiry must follow creation")
        if (self.status is ApprovalStatus.PENDING) is (self.decided_at is not None):
            raise ValueError("only decided approvals carry decided_at")
        if self.decided_at is not None and self.decided_at < self.created_at:
            raise ValueError("approval decision cannot precede creation")
        return self


class PlanVersionConflictError(RuntimeError):
    """The requested plan version is no longer the current valid version."""


class PlanNotReadyError(RuntimeError):
    """The requested plan has not reached a confirmable draft state."""


class PlanExecutionNotAllowedError(RuntimeError):
    """Execution surfaces are unavailable until a version is confirmed."""


__all__ = [
    "ApprovalAction",
    "ApprovalStatus",
    "PlanApproval",
    "PlanExecutionNotAllowedError",
    "PlanNotReadyError",
    "PlanOperation",
    "PlanStatus",
    "PlanVersion",
    "PlanVersionConflictError",
]

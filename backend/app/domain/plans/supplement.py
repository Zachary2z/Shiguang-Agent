"""Immutable contracts for one explicit M0-5D external Place gap."""

from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Self

from pydantic import Field, model_validator

from app.domain.collections import PlaceCandidate
from app.domain.places import PlaceMatchCandidate
from app.domain.plans.contracts import PlanContract
from app.domain.plans.drafts import PlanDraftResult
from app.domain.runs import AgentRunStatus


class RequiredGapKind(StrEnum):
    PLACE = "place"
    EVENT = "event"


class ExternalApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ExternalSupplementOutcome(StrEnum):
    DRAFT = "draft"
    WAITING_APPROVAL = "waiting_approval"
    NEEDS_SELECTION = "needs_selection"
    RECOVERY_REQUIRED = "recovery_required"


class ExternalRecoveryCode(StrEnum):
    ADD_COLLECTIONS = "ADD_COLLECTIONS"
    COLLECTION_ONLY = "COLLECTION_ONLY"
    EVENT_NOT_SEARCHABLE = "EVENT_NOT_SEARCHABLE"
    PLACE_NOT_FOUND = "PLACE_NOT_FOUND"
    PLACE_AMBIGUOUS = "PLACE_AMBIGUOUS"
    ROUTE_FACTS_MISSING = "ROUTE_FACTS_MISSING"
    MAP_TIMEOUT = "MAP_TIMEOUT"
    MAP_RATE_LIMITED = "MAP_RATE_LIMITED"
    MAP_UNAVAILABLE = "MAP_UNAVAILABLE"
    MAP_INVALID_RESPONSE = "MAP_INVALID_RESPONSE"
    NO_EXECUTABLE_DRAFT = "NO_EXECUTABLE_DRAFT"


RECOVERY_SUMMARIES: dict[ExternalRecoveryCode, str] = {
    ExternalRecoveryCode.ADD_COLLECTIONS: (
        "Add another usable collection item, then generate the plan again."
    ),
    ExternalRecoveryCode.COLLECTION_ONLY: (
        "External Place search is disabled for this collection-only plan."
    ),
    ExternalRecoveryCode.EVENT_NOT_SEARCHABLE: (
        "Add the Event by link or screenshot, or change the request to a fixed Place."
    ),
    ExternalRecoveryCode.PLACE_NOT_FOUND: (
        "No reliable Place candidate was found; add a collection or refine the Place."
    ),
    ExternalRecoveryCode.PLACE_AMBIGUOUS: (
        "Choose a specific Place candidate before it can enter the draft."
    ),
    ExternalRecoveryCode.ROUTE_FACTS_MISSING: (
        "A safe route to the external Place cannot be established from known facts."
    ),
    ExternalRecoveryCode.MAP_TIMEOUT: (
        "The map lookup timed out; use the collection-only draft or try again later."
    ),
    ExternalRecoveryCode.MAP_RATE_LIMITED: (
        "The map lookup is rate limited; use the collection-only draft or try again later."
    ),
    ExternalRecoveryCode.MAP_UNAVAILABLE: (
        "The map lookup is unavailable; use the collection-only draft or try again later."
    ),
    ExternalRecoveryCode.MAP_INVALID_RESPONSE: (
        "The map result could not be validated; no external Place was added."
    ),
    ExternalRecoveryCode.NO_EXECUTABLE_DRAFT: (
        "The known facts cannot form an executable plan; add a collection or adjust constraints."
    ),
}


class RequiredPlanGap(PlanContract):
    """A caller-supplied hard requirement; no free-text intent inference occurs here."""

    kind: RequiredGapKind
    place_candidate: PlaceCandidate | None = Field(default=None, repr=False)
    supplement_reason: str = Field(min_length=1, max_length=240)
    visit_duration_seconds: int = Field(gt=0, le=24 * 60 * 60)

    @model_validator(mode="after")
    def validate_gap_shape(self) -> Self:
        if (self.kind is RequiredGapKind.PLACE) is (self.place_candidate is None):
            raise ValueError("Place gaps require one structured Place candidate")
        return self


class ExternalPlaceApprovalRequirement(PlanContract):
    approval_id: str = Field(pattern=r"^approval_[0-9a-f]{32}$")
    action: str = "use_external_place_recommendation"
    display_text: str = (
        "Allow one read-only external Place recommendation search in Shenzhen."
    )

    @classmethod
    def for_gap(cls, gap: RequiredPlanGap) -> ExternalPlaceApprovalRequirement:
        assert gap.place_candidate is not None
        semantic = json.dumps(
            {
                "city": "shenzhen",
                "kind": gap.kind.value,
                "candidate": gap.place_candidate.model_dump(mode="json"),
                "reason": gap.supplement_reason,
                "visit_duration_seconds": gap.visit_duration_seconds,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = sha256(semantic.encode("utf-8")).hexdigest()[:32]
        return cls(approval_id=f"approval_{digest}")


class ExternalPlaceApprovalDecision(PlanContract):
    """One decision bound to the exact deterministic requirement it answers."""

    approval_id: str = Field(pattern=r"^approval_[0-9a-f]{32}$")
    decision: ExternalApprovalDecision


class ExternalPlaceSupplementResult(PlanContract):
    outcome: ExternalSupplementOutcome
    run_status: AgentRunStatus
    draft: PlanDraftResult | None = None
    approval: ExternalPlaceApprovalRequirement | None = None
    candidates: tuple[PlaceMatchCandidate, ...] = Field(default_factory=tuple, max_length=3)
    recovery_code: ExternalRecoveryCode | None = None
    recovery_summary: str | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> Self:
        if self.outcome is ExternalSupplementOutcome.WAITING_APPROVAL:
            if (
                self.run_status is not AgentRunStatus.WAITING_USER
                or self.approval is None
                or self.draft is not None
                or self.candidates
                or self.recovery_code is not None
            ):
                raise ValueError("waiting approval requires only one safe requirement")
            return self
        if self.run_status is not AgentRunStatus.SUCCEEDED or self.approval is not None:
            raise ValueError("completed supplement outcomes must use succeeded run status")
        if self.recovery_code is not None:
            if self.recovery_summary != RECOVERY_SUMMARIES[self.recovery_code]:
                raise ValueError("recovery summary does not match its code")
        elif self.recovery_summary is not None:
            raise ValueError("recovery summary requires a recovery code")
        if self.outcome is ExternalSupplementOutcome.DRAFT and self.draft is None:
            raise ValueError("draft outcomes require a draft")
        if self.outcome is ExternalSupplementOutcome.NEEDS_SELECTION and not self.candidates:
            raise ValueError("selection outcomes require candidates")
        return self

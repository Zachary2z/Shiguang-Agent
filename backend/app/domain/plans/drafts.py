"""Immutable, provider-neutral contracts for deterministic M0-5C plan drafts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from app.domain.collections import CollectionKind, validate_cny_price_pair
from app.domain.identifiers import validate_collection_item_id
from app.domain.places import Poi, PoiProvider, TransportMode
from app.domain.plans.contracts import PlanContract
from app.domain.plans.retrieval import CandidateReasonCode
from app.domain.time import require_aware_utc

MIN_SWITCH_BUFFER_SECONDS = 10 * 60
MAX_SWITCH_BUFFER_SECONDS = 20 * 60
MIN_END_BUFFER_SECONDS = 15 * 60
MAX_END_BUFFER_SECONDS = 30 * 60


def _collection_ids(value: tuple[str, ...], *, allow_empty: bool = False) -> tuple[str, ...]:
    if not value and not allow_empty:
        raise ValueError("collection item ids are required")
    validated = tuple(validate_collection_item_id(item_id) for item_id in value)
    if tuple(sorted(set(validated))) != validated:
        raise ValueError("collection item ids must be unique and sorted")
    return validated


class DraftCandidateFacts(PlanContract):
    """Known visit and query facts for one already retrieved candidate."""

    collection_item_ids: tuple[str, ...]
    visit_duration_seconds: int = Field(gt=0, le=24 * 60 * 60)
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    poi_queried_at: datetime | None = None

    @field_validator("collection_item_ids")
    @classmethod
    def validate_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _collection_ids(value)

    @field_validator("event_start_at", "event_end_at", "poi_queried_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @model_validator(mode="after")
    def validate_event_window(self) -> Self:
        if (self.event_start_at is None) is not (self.event_end_at is None):
            raise ValueError("event start and end must be provided together")
        if (
            self.event_start_at is not None
            and self.event_end_at is not None
            and self.event_end_at <= self.event_start_at
        ):
            raise ValueError("event end must be after event start")
        return self


class DraftRouteFacts(PlanContract):
    """One explicit inbound route; an empty source means the plan origin."""

    from_collection_item_ids: tuple[str, ...] = Field(default_factory=tuple)
    to_collection_item_ids: tuple[str, ...]
    duration_seconds: int = Field(ge=0, le=24 * 60 * 60)
    distance_meters: int = Field(ge=0)
    transport_mode: TransportMode

    @field_validator("from_collection_item_ids")
    @classmethod
    def validate_from_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _collection_ids(value, allow_empty=True)

    @field_validator("to_collection_item_ids")
    @classmethod
    def validate_to_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _collection_ids(value)

    @model_validator(mode="after")
    def reject_self_route(self) -> Self:
        if self.from_collection_item_ids == self.to_collection_item_ids:
            raise ValueError("route endpoints must differ")
        return self

    @property
    def identity(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (self.from_collection_item_ids, self.to_collection_item_ids)


class PlanDraftFactSnapshot(PlanContract):
    """All request-local facts required to schedule visits without guessing."""

    candidates: tuple[DraftCandidateFacts, ...] = Field(default_factory=tuple)
    routes: tuple[DraftRouteFacts, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_unique_facts(self) -> Self:
        candidate_ids = tuple(item.collection_item_ids for item in self.candidates)
        route_ids = tuple(item.identity for item in self.routes)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate facts must be unique")
        if len(set(route_ids)) != len(route_ids):
            raise ValueError("route facts must be unique")
        return self


class PlanDraftOutcome(StrEnum):
    GENERATED = "generated"
    NOT_GENERATED = "not_generated"


class PlanDraftFailureCode(StrEnum):
    NO_INCLUDED_CANDIDATES = "NO_INCLUDED_CANDIDATES"
    NO_EXECUTABLE_OPTION = "NO_EXECUTABLE_OPTION"
    POST_GENERATION_VALIDATION_FAILED = "POST_GENERATION_VALIDATION_FAILED"


FAILURE_SUMMARIES: dict[PlanDraftFailureCode, str] = {
    PlanDraftFailureCode.NO_INCLUDED_CANDIDATES: "No included collection candidate is available.",
    PlanDraftFailureCode.NO_EXECUTABLE_OPTION: (
        "No executable option can be formed from the known visit and route facts."
    ),
    PlanDraftFailureCode.POST_GENERATION_VALIDATION_FAILED: (
        "The generated draft did not pass deterministic validation."
    ),
}


class PlanOptionRole(StrEnum):
    MAIN = "main"
    ALTERNATIVE = "alternative"


class PlanItemRole(StrEnum):
    CORE = "core"
    AUXILIARY = "auxiliary"


class PlanItemSourceKind(StrEnum):
    COLLECTION_DERIVED = "collection_derived"
    EXTERNAL_PLACE = "external_place"


class PlanSelectionReasonCode(StrEnum):
    PRIMARY_STABLE_RANK = "PRIMARY_STABLE_RANK"
    STABLE_ALTERNATIVE = "STABLE_ALTERNATIVE"
    AUXILIARY_FITS_KNOWN_ROUTE = "AUXILIARY_FITS_KNOWN_ROUTE"


SELECTION_REASON_SUMMARIES: dict[PlanSelectionReasonCode, str] = {
    PlanSelectionReasonCode.PRIMARY_STABLE_RANK: (
        "Selected first by known route duration and stable candidate fields."
    ),
    PlanSelectionReasonCode.STABLE_ALTERNATIVE: (
        "Selected as a deterministic alternative from the remaining candidates."
    ),
    PlanSelectionReasonCode.AUXILIARY_FITS_KNOWN_ROUTE: (
        "Added because its visit and inter-place route fit the remaining window."
    ),
}


class PlanRiskCode(StrEnum):
    PRICE_UNKNOWN = "PRICE_UNKNOWN"
    OPENING_HOURS_UNKNOWN = "OPENING_HOURS_UNKNOWN"


RISK_SUMMARIES: dict[PlanRiskCode, str] = {
    PlanRiskCode.PRICE_UNKNOWN: "The item price needs confirmation.",
    PlanRiskCode.OPENING_HOURS_UNKNOWN: "The opening hours need confirmation.",
}


class PlanDraftExclusion(PlanContract):
    collection_item_ids: tuple[str, ...]
    reason_codes: tuple[CandidateReasonCode, ...]
    summaries: tuple[str, ...]

    @field_validator("collection_item_ids")
    @classmethod
    def validate_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _collection_ids(value)


class PlanRouteLeg(PlanContract):
    from_collection_item_ids: tuple[str, ...] = Field(default_factory=tuple)
    to_collection_item_ids: tuple[str, ...] = Field(default_factory=tuple)
    to_external_provider: PoiProvider | None = None
    to_external_poi_id: str | None = Field(default=None, min_length=1, max_length=128)
    duration_seconds: int = Field(ge=0)
    distance_meters: int = Field(ge=0)
    transport_mode: TransportMode

    @field_validator("from_collection_item_ids")
    @classmethod
    def validate_from_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _collection_ids(value, allow_empty=True)

    @field_validator("to_collection_item_ids")
    @classmethod
    def validate_to_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _collection_ids(value, allow_empty=True)

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        has_external = (
            self.to_external_provider is not None and self.to_external_poi_id is not None
        )
        if (not self.to_collection_item_ids) is not has_external:
            raise ValueError("route requires exactly one collection or external target")
        return self


class PlanItemSource(PlanContract):
    kind: PlanItemSourceKind = PlanItemSourceKind.COLLECTION_DERIVED
    collection_item_ids: tuple[str, ...] = Field(default_factory=tuple)
    any_branch_collection_item_ids: tuple[str, ...] = Field(default_factory=tuple)
    concrete_poi: Poi | None = None
    poi_queried_at: datetime | None = None
    supplement_reason: str | None = Field(default=None, min_length=1, max_length=240)
    source_label: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("collection_item_ids")
    @classmethod
    def validate_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _collection_ids(value, allow_empty=True)

    @field_validator("any_branch_collection_item_ids")
    @classmethod
    def validate_branch_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _collection_ids(value, allow_empty=True)

    @field_validator("poi_queried_at")
    @classmethod
    def normalize_query_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @model_validator(mode="after")
    def validate_branch_snapshot(self) -> Self:
        if self.kind is PlanItemSourceKind.COLLECTION_DERIVED:
            if not self.collection_item_ids:
                raise ValueError("collection-derived sources require collection ids")
            if self.supplement_reason is not None or self.source_label is not None:
                raise ValueError("collection-derived sources cannot carry external metadata")
        else:
            if (
                self.collection_item_ids
                or self.any_branch_collection_item_ids
                or self.concrete_poi is None
                or self.poi_queried_at is None
                or self.supplement_reason is None
                or self.source_label != "高德补充 · 未收藏"
            ):
                raise ValueError("external sources require one uncollected POI snapshot")
        if not set(self.any_branch_collection_item_ids).issubset(self.collection_item_ids):
            raise ValueError("any-branch source ids must be collection sources")
        if self.any_branch_collection_item_ids and (
            self.concrete_poi is None or self.poi_queried_at is None
        ):
            raise ValueError("any-branch sources require a concrete queried POI snapshot")
        return self


class ExternalDraftCandidate(PlanContract):
    """One explicit external Place and the known facts needed by the sole scheduler."""

    poi: Poi
    queried_at: datetime
    supplement_reason: str = Field(min_length=1, max_length=240)
    visit_duration_seconds: int = Field(gt=0, le=24 * 60 * 60)
    inbound_route: PlanRouteLeg
    price_amount: Decimal | None = None
    price_currency: str | None = None

    @field_validator("queried_at")
    @classmethod
    def normalize_queried_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @model_validator(mode="after")
    def validate_external_route(self) -> Self:
        if (
            self.inbound_route.to_collection_item_ids
            or self.inbound_route.to_external_provider is not self.poi.provider
            or self.inbound_route.to_external_poi_id != self.poi.poi_id
        ):
            raise ValueError("external inbound routes cannot target a collection id")
        validate_cny_price_pair(self.price_amount, self.price_currency)
        return self


class PlanItem(PlanContract):
    role: PlanItemRole
    title: str = Field(min_length=1, max_length=200)
    kind: CollectionKind
    start_at: datetime
    end_at: datetime
    visit_duration_seconds: int = Field(gt=0)
    inbound_route: PlanRouteLeg
    price_amount: Decimal | None = None
    price_currency: str | None = None
    source: PlanItemSource
    selection_reason_code: PlanSelectionReasonCode
    selection_reason: str
    risk_codes: tuple[PlanRiskCode, ...] = Field(default_factory=tuple)
    risks: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @model_validator(mode="after")
    def validate_display_fields(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("plan item end must be after start")
        validate_cny_price_pair(self.price_amount, self.price_currency)
        if self.selection_reason != SELECTION_REASON_SUMMARIES[self.selection_reason_code]:
            raise ValueError("selection reason does not match its code")
        if self.risks != tuple(RISK_SUMMARIES[code] for code in self.risk_codes):
            raise ValueError("risk summaries do not match their codes")
        if len(set(self.risk_codes)) != len(self.risk_codes):
            raise ValueError("risk codes must be unique")
        return self


class PlanOption(PlanContract):
    role: PlanOptionRole
    items: tuple[PlanItem, ...] = Field(min_length=1, max_length=2)
    switch_buffer_seconds: int | None = Field(
        default=None,
        ge=MIN_SWITCH_BUFFER_SECONDS,
        le=MAX_SWITCH_BUFFER_SECONDS,
    )
    end_buffer_seconds: int = Field(ge=MIN_END_BUFFER_SECONDS, le=MAX_END_BUFFER_SECONDS)
    total_cost_amount: Decimal | None = None
    total_cost_currency: str | None = None
    risk_codes: tuple[PlanRiskCode, ...] = Field(default_factory=tuple)
    risks: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_option_shape(self) -> Self:
        if len(self.items) == 1 and self.switch_buffer_seconds is not None:
            raise ValueError("single-item options do not have a switch buffer")
        if len(self.items) == 2 and self.switch_buffer_seconds is None:
            raise ValueError("two-item options require a switch buffer")
        validate_cny_price_pair(self.total_cost_amount, self.total_cost_currency)
        if self.risks != tuple(RISK_SUMMARIES[code] for code in self.risk_codes):
            raise ValueError("option risk summaries do not match their codes")
        return self


class PlanDraftResult(PlanContract):
    outcome: PlanDraftOutcome
    options: tuple[PlanOption, ...] = Field(default_factory=tuple, max_length=3)
    exclusions: tuple[PlanDraftExclusion, ...] = Field(default_factory=tuple)
    failure_code: PlanDraftFailureCode | None = None
    failure_summary: str | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> Self:
        if self.outcome is PlanDraftOutcome.GENERATED:
            if (
                not self.options
                or self.failure_code is not None
                or self.failure_summary is not None
            ):
                raise ValueError("generated drafts require options and no failure")
        else:
            if self.options or self.failure_code is None:
                raise ValueError("non-generated drafts require one failure and no options")
            if self.failure_summary != FAILURE_SUMMARIES[self.failure_code]:
                raise ValueError("failure summary does not match its code")
        return self


class PlanDraftViolationCode(StrEnum):
    RESULT_SHAPE_INVALID = "RESULT_SHAPE_INVALID"
    OPTION_ROLE_INVALID = "OPTION_ROLE_INVALID"
    OPTION_DUPLICATED = "OPTION_DUPLICATED"
    ITEM_ROLE_INVALID = "ITEM_ROLE_INVALID"
    SOURCE_NOT_INCLUDED = "SOURCE_NOT_INCLUDED"
    FACTS_MISSING_OR_MISMATCHED = "FACTS_MISSING_OR_MISMATCHED"
    ROUTE_MISSING_OR_MISMATCHED = "ROUTE_MISSING_OR_MISMATCHED"
    TIME_WINDOW_VIOLATED = "TIME_WINDOW_VIOLATED"
    EVENT_WINDOW_VIOLATED = "EVENT_WINDOW_VIOLATED"
    SWITCH_BUFFER_INVALID = "SWITCH_BUFFER_INVALID"
    END_BUFFER_INVALID = "END_BUFFER_INVALID"
    BUDGET_VIOLATED = "BUDGET_VIOLATED"
    COST_TOTAL_INVALID = "COST_TOTAL_INVALID"
    RISK_INVALID = "RISK_INVALID"
    DUPLICATE_POI = "DUPLICATE_POI"
    BRANCH_SNAPSHOT_INVALID = "BRANCH_SNAPSHOT_INVALID"


class PlanDraftValidation(PlanContract):
    is_valid: bool
    violations: tuple[PlanDraftViolationCode, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        if self.is_valid is bool(self.violations):
            raise ValueError("validation status must match violations")
        if len(set(self.violations)) != len(self.violations):
            raise ValueError("validation violations must be unique")
        return self

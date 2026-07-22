"""Deterministic M0-5B collection-candidate facts and result contracts."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.collections import CollectionKind
from app.domain.identifiers import validate_collection_item_id
from app.domain.places import CityScope, Coordinate, Poi, PoiProvider


class RetrievalContract(BaseModel):
    """Strict immutable base for caller-provided facts and public decisions."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class RouteAssessment(StrEnum):
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"
    PROVIDER_FAILED = "provider_failed"


class WeatherAssessment(StrEnum):
    COMPATIBLE = "compatible"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"
    PROVIDER_FAILED = "provider_failed"


class AvailabilityAssessment(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    PROVIDER_FAILED = "provider_failed"


class CandidateFactValues(RetrievalContract):
    """Explicit, provider-neutral facts; missing evidence remains unknown."""

    route: RouteAssessment = RouteAssessment.UNKNOWN
    route_duration_seconds: int | None = Field(default=None, ge=0)
    route_distance_meters: int | None = Field(default=None, ge=0)
    weather: WeatherAssessment = WeatherAssessment.UNKNOWN
    availability: AvailabilityAssessment = AvailabilityAssessment.UNKNOWN

    @model_validator(mode="after")
    def validate_route_totals(self) -> Self:
        has_totals = (
            self.route_duration_seconds is not None
            or self.route_distance_meters is not None
        )
        if self.route is RouteAssessment.REACHABLE and self.route_duration_seconds is None:
            raise ValueError("reachable route facts require a duration")
        if self.route is not RouteAssessment.REACHABLE and has_totals:
            raise ValueError("only reachable route facts may carry route totals")
        return self


class CollectionPlanningFacts(CandidateFactValues):
    """Verified location and dynamic facts for one Event collection."""

    collection_item_id: str
    formal_city: CityScope | None = None
    location_confirmed: bool = False
    coordinate: Coordinate | None = Field(default=None, repr=False)

    @field_validator("collection_item_id")
    @classmethod
    def validate_item_id(cls, value: str) -> str:
        return validate_collection_item_id(value)

    @model_validator(mode="after")
    def validate_location(self) -> Self:
        if self.location_confirmed and self.formal_city is None:
            raise ValueError("confirmed locations require a formal city")
        if not self.location_confirmed and (
            self.formal_city is not None or self.coordinate is not None
        ):
            raise ValueError("unconfirmed locations cannot carry formal location facts")
        return self


class PoiPlanningFacts(CandidateFactValues):
    """Dynamic facts for one already normalized concrete POI."""

    provider: PoiProvider
    poi_id: str = Field(min_length=1, max_length=128)

    @field_validator("poi_id")
    @classmethod
    def normalize_poi_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("poi_id cannot be blank")
        return normalized

    @property
    def identity(self) -> tuple[PoiProvider, str]:
        return (self.provider, self.poi_id)


class PlanningFactSnapshot(RetrievalContract):
    """One request-local immutable fact set with unique lookup identities."""

    collections: tuple[CollectionPlanningFacts, ...] = Field(default_factory=tuple)
    pois: tuple[PoiPlanningFacts, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_unique_identities(self) -> Self:
        collection_ids = tuple(item.collection_item_id for item in self.collections)
        poi_ids = tuple(item.identity for item in self.pois)
        if len(set(collection_ids)) != len(collection_ids):
            raise ValueError("collection planning facts must be unique")
        if len(set(poi_ids)) != len(poi_ids):
            raise ValueError("POI planning facts must be unique")
        return self


class CandidateOutcome(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    VERIFICATION_REQUIRED = "verification_required"


class CandidateReasonCode(StrEnum):
    STATUS_NOT_ACTIVE = "STATUS_NOT_ACTIVE"
    CITY_UNCONFIRMED = "CITY_UNCONFIRMED"
    CITY_MISMATCH = "CITY_MISMATCH"
    LOCATION_UNCONFIRMED = "LOCATION_UNCONFIRMED"
    EVENT_ENDED = "EVENT_ENDED"
    EVENT_TIME_UNKNOWN = "EVENT_TIME_UNKNOWN"
    TIME_WINDOW_CONFLICT = "TIME_WINDOW_CONFLICT"
    DISTRICT_UNKNOWN = "DISTRICT_UNKNOWN"
    DISTRICT_MISMATCH = "DISTRICT_MISMATCH"
    AREA_MISMATCH = "AREA_MISMATCH"
    INCLUDE_NOT_MATCHED = "INCLUDE_NOT_MATCHED"
    EXCLUDED_BY_USER = "EXCLUDED_BY_USER"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    PRICE_UNKNOWN = "PRICE_UNKNOWN"
    ROUTE_UNREACHABLE = "ROUTE_UNREACHABLE"
    ROUTE_EXCEEDS_TIME_WINDOW = "ROUTE_EXCEEDS_TIME_WINDOW"
    ROUTE_UNKNOWN = "ROUTE_UNKNOWN"
    ROUTE_PROVIDER_FAILED = "ROUTE_PROVIDER_FAILED"
    WEATHER_CONFLICT = "WEATHER_CONFLICT"
    WEATHER_UNKNOWN = "WEATHER_UNKNOWN"
    WEATHER_PROVIDER_FAILED = "WEATHER_PROVIDER_FAILED"
    PLACE_UNAVAILABLE = "PLACE_UNAVAILABLE"
    AVAILABILITY_UNKNOWN = "AVAILABILITY_UNKNOWN"
    AVAILABILITY_PROVIDER_FAILED = "AVAILABILITY_PROVIDER_FAILED"
    BRANCH_NOT_FOUND = "BRANCH_NOT_FOUND"
    BRANCH_EVIDENCE_INSUFFICIENT = "BRANCH_EVIDENCE_INSUFFICIENT"
    BRANCH_PROVIDER_FAILED = "BRANCH_PROVIDER_FAILED"
    BRANCH_NO_HARD_CONSTRAINT_MATCH = "BRANCH_NO_HARD_CONSTRAINT_MATCH"


REASON_SUMMARIES: dict[CandidateReasonCode, str] = {
    CandidateReasonCode.STATUS_NOT_ACTIVE: "The collection is not active.",
    CandidateReasonCode.CITY_UNCONFIRMED: "The collection city is not confirmed.",
    CandidateReasonCode.CITY_MISMATCH: "The collection is in another city.",
    CandidateReasonCode.LOCATION_UNCONFIRMED: "The collection location is not confirmed.",
    CandidateReasonCode.EVENT_ENDED: "The event has already ended.",
    CandidateReasonCode.EVENT_TIME_UNKNOWN: "The event time needs confirmation.",
    CandidateReasonCode.TIME_WINDOW_CONFLICT: "The item is outside the available time.",
    CandidateReasonCode.DISTRICT_UNKNOWN: "The item district needs confirmation.",
    CandidateReasonCode.DISTRICT_MISMATCH: "The item is outside the requested district.",
    CandidateReasonCode.AREA_MISMATCH: "The item is outside the requested activity area.",
    CandidateReasonCode.INCLUDE_NOT_MATCHED: "The item does not match every required term.",
    CandidateReasonCode.EXCLUDED_BY_USER: "The item matches an explicit exclusion.",
    CandidateReasonCode.BUDGET_EXCEEDED: "The known price exceeds the budget.",
    CandidateReasonCode.PRICE_UNKNOWN: "The price needs confirmation.",
    CandidateReasonCode.ROUTE_UNREACHABLE: "The route is explicitly unreachable.",
    CandidateReasonCode.ROUTE_EXCEEDS_TIME_WINDOW: (
        "The route cannot arrive within the available time."
    ),
    CandidateReasonCode.ROUTE_UNKNOWN: "Route reachability needs confirmation.",
    CandidateReasonCode.ROUTE_PROVIDER_FAILED: "Route evidence is temporarily unavailable.",
    CandidateReasonCode.WEATHER_CONFLICT: "The item conflicts with the weather facts.",
    CandidateReasonCode.WEATHER_UNKNOWN: "Weather suitability needs confirmation.",
    CandidateReasonCode.WEATHER_PROVIDER_FAILED: "Weather evidence is temporarily unavailable.",
    CandidateReasonCode.PLACE_UNAVAILABLE: "The place is explicitly unavailable.",
    CandidateReasonCode.AVAILABILITY_UNKNOWN: "Opening information needs confirmation.",
    CandidateReasonCode.AVAILABILITY_PROVIDER_FAILED: (
        "Opening information is temporarily unavailable."
    ),
    CandidateReasonCode.BRANCH_NOT_FOUND: "No branch was found in the plan city.",
    CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT: (
        "No branch has enough evidence for this plan."
    ),
    CandidateReasonCode.BRANCH_PROVIDER_FAILED: "Branch lookup is temporarily unavailable.",
    CandidateReasonCode.BRANCH_NO_HARD_CONSTRAINT_MATCH: (
        "No branch satisfies the known hard constraints."
    ),
}

_EXCLUSION_REASONS = frozenset(
    {
        CandidateReasonCode.STATUS_NOT_ACTIVE,
        CandidateReasonCode.CITY_MISMATCH,
        CandidateReasonCode.EVENT_ENDED,
        CandidateReasonCode.TIME_WINDOW_CONFLICT,
        CandidateReasonCode.DISTRICT_MISMATCH,
        CandidateReasonCode.AREA_MISMATCH,
        CandidateReasonCode.INCLUDE_NOT_MATCHED,
        CandidateReasonCode.EXCLUDED_BY_USER,
        CandidateReasonCode.BUDGET_EXCEEDED,
        CandidateReasonCode.ROUTE_UNREACHABLE,
        CandidateReasonCode.ROUTE_EXCEEDS_TIME_WINDOW,
        CandidateReasonCode.WEATHER_CONFLICT,
        CandidateReasonCode.PLACE_UNAVAILABLE,
        CandidateReasonCode.BRANCH_NOT_FOUND,
        CandidateReasonCode.BRANCH_PROVIDER_FAILED,
        CandidateReasonCode.BRANCH_NO_HARD_CONSTRAINT_MATCH,
    }
)


def outcome_for_reasons(reasons: tuple[CandidateReasonCode, ...]) -> CandidateOutcome:
    if any(reason in _EXCLUSION_REASONS for reason in reasons):
        return CandidateOutcome.EXCLUDED
    if reasons:
        return CandidateOutcome.VERIFICATION_REQUIRED
    return CandidateOutcome.INCLUDED


class CollectionCandidateDecision(RetrievalContract):
    """One stable decision; it is deliberately not a Plan or PlanItem."""

    outcome: CandidateOutcome
    reason_codes: tuple[CandidateReasonCode, ...] = Field(default_factory=tuple)
    summaries: tuple[str, ...] = Field(default_factory=tuple)
    collection_item_ids: tuple[str, ...] = Field(min_length=1)
    kind: CollectionKind
    title: str = Field(min_length=1, max_length=200)
    poi: Poi | None = None
    price_amount: Decimal | None = None
    price_currency: str | None = None
    route_duration_seconds: int | None = Field(default=None, ge=0)
    route_distance_meters: int | None = Field(default=None, ge=0)
    any_branch_collection_item_ids: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("collection_item_ids")
    @classmethod
    def validate_item_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_collection_item_id(item) for item in value)
        if tuple(sorted(set(validated))) != validated:
            raise ValueError("collection item ids must be unique and sorted")
        return validated

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        expected = outcome_for_reasons(self.reason_codes)
        if self.outcome is not expected:
            raise ValueError("candidate outcome does not match its reasons")
        if self.summaries != tuple(REASON_SUMMARIES[code] for code in self.reason_codes):
            raise ValueError("candidate summaries do not match their reason codes")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("candidate reasons must be unique")
        if self.poi is not None and self.kind is not CollectionKind.PLACE:
            raise ValueError("only Place decisions may carry a POI")
        if (self.price_amount is None) is not (self.price_currency is None):
            raise ValueError("price amount and currency must be provided together")
        branch_ids = tuple(
            validate_collection_item_id(item)
            for item in self.any_branch_collection_item_ids
        )
        if tuple(sorted(set(branch_ids))) != branch_ids:
            raise ValueError("any-branch source ids must be unique and sorted")
        if not set(branch_ids).issubset(self.collection_item_ids):
            raise ValueError("any-branch source ids must be candidate sources")
        return self

    @property
    def poi_identity(self) -> tuple[PoiProvider, str] | None:
        if self.poi is None:
            return None
        return (self.poi.provider, self.poi.poi_id)


class StructuredCollectionResult(RetrievalContract):
    """Stable, read-only M0-5B retrieval result."""

    decisions: tuple[CollectionCandidateDecision, ...] = Field(default_factory=tuple)

    @property
    def included(self) -> tuple[CollectionCandidateDecision, ...]:
        return tuple(
            item for item in self.decisions if item.outcome is CandidateOutcome.INCLUDED
        )

    @property
    def excluded(self) -> tuple[CollectionCandidateDecision, ...]:
        return tuple(
            item for item in self.decisions if item.outcome is CandidateOutcome.EXCLUDED
        )

    @property
    def verification_required(self) -> tuple[CollectionCandidateDecision, ...]:
        return tuple(
            item
            for item in self.decisions
            if item.outcome is CandidateOutcome.VERIFICATION_REQUIRED
        )

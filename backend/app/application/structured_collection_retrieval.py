"""The single read-only M0-5B structured collection retrieval workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import ClassVar
from unicodedata import normalize
from zoneinfo import ZoneInfo

from app.application.collection_queries import (
    CollectionPlanningBlocker,
    collection_planning_blockers,
)
from app.domain.collections import (
    CandidateField,
    CollectionItem,
    CollectionKind,
    CollectionRepository,
    PlaceCandidate,
    event_schedule_is_confirmed,
)
from app.domain.memories import Memory, MemoryType
from app.domain.places import (
    PlaceScope,
    Poi,
    PoiProvider,
    ResolvedPlaceTargetKind,
    resolve_place_target,
)
from app.domain.plans import ActivityArea, PlanConstraints
from app.domain.plans.retrieval import (
    REASON_SUMMARIES,
    AvailabilityAssessment,
    CandidateFactValues,
    CandidateOutcome,
    CandidateReasonCode,
    CollectionCandidateDecision,
    CollectionPlanningFacts,
    PlanningFactSnapshot,
    PoiPlanningFacts,
    RouteAssessment,
    StructuredCollectionResult,
    WeatherAssessment,
    outcome_for_reasons,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class StructuredCollectionRetrievalError(RuntimeError):
    """The single fixed, safe public failure for the retrieval boundary."""

    __slots__ = ("code", "summary")
    _SUMMARIES: ClassVar[dict[str, str]] = {
        "COLLECTION_RETRIEVAL_FAILED": "Collection retrieval failed.",
        "PLAN_CONSTRAINTS_EXPIRED": "Plan constraints have expired.",
        "INVALID_RETRIEVAL_TIME": "Retrieval time is invalid.",
    }

    def __init__(self, code: str = "COLLECTION_RETRIEVAL_FAILED") -> None:
        self.code = code
        self.summary = self._SUMMARIES[code]
        super().__init__(self.summary)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "summary": self.summary}


def _text_identity(value: str) -> str:
    return "".join(normalize("NFKC", value).casefold().split())


def _searchable_values(item: CollectionItem, poi: Poi | None) -> tuple[str, ...]:
    values: list[str] = [item.title, *item.tags]
    if item.place_target is None or item.place_target.scope is not PlaceScope.ANY_BRANCH:
        values.extend(
            value
            for value in (
                item.district,
                item.address,
                item.business_district,
                item.landmark,
                item.metro_station,
            )
            if value is not None
        )
    if poi is not None:
        values.extend(
            value
            for value in (
                poi.name,
                poi.branch_name,
                poi.district,
                poi.business_area,
                poi.address,
                poi.poi_type.value,
            )
            if value is not None
        )
    return tuple(_text_identity(value) for value in values)


def _matches_term(term: str, values: tuple[str, ...]) -> bool:
    needle = _text_identity(term)
    return any(needle in value for value in values)


def _ordered_reasons(
    reasons: Iterable[CandidateReasonCode],
) -> tuple[CandidateReasonCode, ...]:
    selected = set(reasons)
    return tuple(code for code in CandidateReasonCode if code in selected)


def _dynamic_reasons(
    facts: CandidateFactValues,
    *,
    is_place: bool,
) -> set[CandidateReasonCode]:
    reasons: set[CandidateReasonCode] = set()
    if facts.route is RouteAssessment.UNREACHABLE:
        reasons.add(CandidateReasonCode.ROUTE_UNREACHABLE)
    elif facts.route is RouteAssessment.UNKNOWN:
        reasons.add(CandidateReasonCode.ROUTE_UNKNOWN)
    elif facts.route is RouteAssessment.PROVIDER_FAILED:
        reasons.add(CandidateReasonCode.ROUTE_PROVIDER_FAILED)

    if facts.weather is WeatherAssessment.CONFLICT:
        reasons.add(CandidateReasonCode.WEATHER_CONFLICT)
    elif facts.weather is WeatherAssessment.UNKNOWN:
        reasons.add(CandidateReasonCode.WEATHER_UNKNOWN)
    elif facts.weather is WeatherAssessment.PROVIDER_FAILED:
        reasons.add(CandidateReasonCode.WEATHER_PROVIDER_FAILED)

    if is_place:
        if facts.availability is AvailabilityAssessment.UNAVAILABLE:
            reasons.add(CandidateReasonCode.PLACE_UNAVAILABLE)
        elif facts.availability is AvailabilityAssessment.UNKNOWN:
            reasons.add(CandidateReasonCode.AVAILABILITY_UNKNOWN)
        elif facts.availability is AvailabilityAssessment.PROVIDER_FAILED:
            reasons.add(CandidateReasonCode.AVAILABILITY_PROVIDER_FAILED)
    return reasons


def _route_misses_arrival_deadline(
    *,
    item: CollectionItem,
    constraints: PlanConstraints,
    facts: CandidateFactValues,
) -> bool:
    """Apply the sole route-duration deadline rule for Place and Event."""

    if (
        facts.route is not RouteAssessment.REACHABLE
        or facts.route_duration_seconds is None
    ):
        return False
    arrival_at = constraints.start_at + timedelta(
        seconds=facts.route_duration_seconds
    )
    arrival_deadline = constraints.end_at
    if item.kind is CollectionKind.EVENT and item.event_end_at is not None:
        arrival_deadline = min(arrival_deadline, item.event_end_at)
    return arrival_at >= arrival_deadline


def assess_collection_candidate(
    *,
    item: CollectionItem,
    constraints: PlanConstraints,
    formal_city_code: str | None,
    location_confirmed: bool,
    poi: Poi | None,
    facts: CandidateFactValues,
    additional_reasons: Iterable[CandidateReasonCode] = (),
    apply_dynamic_facts: bool = True,
    resolved_from_any_branch: bool = False,
    memories: tuple[Memory, ...] = (),
) -> CollectionCandidateDecision:
    reasons = set(additional_reasons)
    blocker_reasons = {
        CollectionPlanningBlocker.INACTIVE: CandidateReasonCode.STATUS_NOT_ACTIVE,
        CollectionPlanningBlocker.LOCATION_UNCONFIRMED: (
            CandidateReasonCode.LOCATION_UNCONFIRMED
        ),
        CollectionPlanningBlocker.CITY_UNCONFIRMED: CandidateReasonCode.CITY_UNCONFIRMED,
        CollectionPlanningBlocker.OTHER_CITY: CandidateReasonCode.CITY_MISMATCH,
        CollectionPlanningBlocker.EVENT_TIME_UNCONFIRMED: (
            CandidateReasonCode.EVENT_TIME_UNKNOWN
        ),
    }
    reasons.update(
        blocker_reasons[blocker]
        for blocker in collection_planning_blockers(
            item,
            plan_city_code=constraints.city_code.value,
            formal_city_code=formal_city_code,
            location_confirmed=location_confirmed,
            flexible_brand_target=resolved_from_any_branch,
        )
    )

    if item.kind is CollectionKind.EVENT:
        if event_schedule_is_confirmed(
            event_start_date=item.event_start_date,
            event_end_date=item.event_end_date,
            event_start_at=item.event_start_at,
            event_end_at=item.event_end_at,
            uncertainties=item.uncertainties,
        ):
            if item.event_start_at is not None and item.event_end_at is not None:
                if item.event_end_at <= constraints.start_at:
                    reasons.add(CandidateReasonCode.EVENT_ENDED)
                elif (
                    item.event_start_at >= constraints.end_at
                    or item.event_end_at <= constraints.start_at
                ):
                    reasons.add(CandidateReasonCode.TIME_WINDOW_CONFLICT)
            else:
                assert item.event_start_date is not None
                assert item.event_end_date is not None
                plan_start_date = constraints.start_at.astimezone(_SHANGHAI).date()
                plan_end_date = (
                    constraints.end_at - timedelta(microseconds=1)
                ).astimezone(_SHANGHAI).date()
                if item.event_end_date < plan_start_date:
                    reasons.add(CandidateReasonCode.EVENT_ENDED)
                elif item.event_start_date > plan_end_date:
                    reasons.add(CandidateReasonCode.TIME_WINDOW_CONFLICT)

    if constraints.area is not None:
        if constraints.area.districts:
            district = (
                poi.district
                if poi is not None
                else None if resolved_from_any_branch else item.district
            )
            allowed = {_text_identity(value) for value in constraints.area.districts}
            if district is None:
                reasons.add(CandidateReasonCode.DISTRICT_UNKNOWN)
            elif _text_identity(district) not in allowed:
                reasons.add(CandidateReasonCode.DISTRICT_MISMATCH)
        if constraints.area.labels:
            values = _searchable_values(item, poi)
            if not any(_matches_term(label, values) for label in constraints.area.labels):
                reasons.add(CandidateReasonCode.AREA_MISMATCH)

    searchable = _searchable_values(item, poi)
    if any(not _matches_term(term, searchable) for term in constraints.include):
        reasons.add(CandidateReasonCode.INCLUDE_NOT_MATCHED)
    if any(_matches_term(term, searchable) for term in constraints.exclude):
        reasons.add(CandidateReasonCode.EXCLUDED_BY_USER)

    if constraints.budget is not None:
        if item.price_amount is None:
            reasons.add(CandidateReasonCode.PRICE_UNKNOWN)
        elif item.price_amount > constraints.budget:
            reasons.add(CandidateReasonCode.BUDGET_EXCEEDED)

    if apply_dynamic_facts:
        reasons.update(_dynamic_reasons(facts, is_place=item.kind is CollectionKind.PLACE))
        if _route_misses_arrival_deadline(
            item=item,
            constraints=constraints,
            facts=facts,
        ):
            reasons.add(CandidateReasonCode.ROUTE_EXCEEDS_TIME_WINDOW)
    ordered = _ordered_reasons(reasons)
    positive_matches: list[str] = []
    negative_matches: list[str] = []
    for memory in memories:
        if memory.type is MemoryType.PACE_PREFERENCE:
            continue
        memory_terms: tuple[str, ...] = (memory.value,)
        if memory.type is MemoryType.USUAL_AREA:
            area = ActivityArea.from_memory_value(memory.value)
            memory_terms = (*area.districts, *area.labels)
        if not any(_matches_term(term, searchable) for term in memory_terms):
            continue
        target = (
            negative_matches
            if memory.type is MemoryType.NEGATIVE_PREFERENCE
            else positive_matches
        )
        target.append(memory.id)
    # One deterministic tier is enough to influence the sole downstream sorter.
    # Negative evidence wins a conflict; duplicate memories are redundant bases.
    applied: tuple[str, ...]
    if negative_matches:
        preference_score = -1
        applied = (min(negative_matches),)
    elif positive_matches:
        preference_score = 1
        applied = (min(positive_matches),)
    else:
        preference_score = 0
        applied = ()
    return CollectionCandidateDecision(
        outcome=outcome_for_reasons(ordered),
        reason_codes=ordered,
        summaries=tuple(REASON_SUMMARIES[reason] for reason in ordered),
        collection_item_ids=(item.id,),
        kind=item.kind,
        title=item.title,
        tags=item.tags[:16],
        poi=(
            poi.model_copy(deep=True)
            if poi is not None and item.kind is CollectionKind.PLACE
            else None
        ),
        price_amount=item.price_amount,
        price_currency=item.price_currency,
        route_duration_seconds=facts.route_duration_seconds,
        route_distance_meters=facts.route_distance_meters,
        any_branch_collection_item_ids=(item.id,) if resolved_from_any_branch else (),
        preference_score=preference_score,
        applied_memory_ids=applied,
    )


def branch_match_candidate(brand_name: str) -> PlaceCandidate:
    """Build brand-only matching input without stale source-branch clues."""

    return PlaceCandidate(
        title=brand_name,
        city_hint=None,
        missing_fields=(
            CandidateField.CITY_HINT,
            CandidateField.DISTRICT,
            CandidateField.ADDRESS,
            CandidateField.BUSINESS_DISTRICT,
            CandidateField.LANDMARK,
            CandidateField.METRO_STATION,
            CandidateField.PRICE,
            CandidateField.TAGS,
        ),
    )


def _merge_duplicate_pois(
    decisions: Iterable[CollectionCandidateDecision],
) -> tuple[CollectionCandidateDecision, ...]:
    merged: list[CollectionCandidateDecision] = []
    poi_indexes: dict[tuple[PoiProvider, str], int] = {}
    for decision in decisions:
        identity = decision.poi_identity
        if identity is None or decision.outcome is not CandidateOutcome.INCLUDED:
            merged.append(decision)
            continue
        previous_index = poi_indexes.get(identity)
        if previous_index is None:
            poi_indexes[identity] = len(merged)
            merged.append(decision)
            continue
        previous = merged[previous_index]
        source_ids = tuple(sorted((*previous.collection_item_ids, *decision.collection_item_ids)))
        branch_source_ids = tuple(
            sorted(
                (
                    *previous.any_branch_collection_item_ids,
                    *decision.any_branch_collection_item_ids,
                )
            )
        )
        preferred = min(
            (previous, decision),
            key=lambda item: (
                bool(item.any_branch_collection_item_ids),
                item.collection_item_ids,
            ),
        )
        scores = {previous.preference_score, decision.preference_score}
        preference_score = -1 if -1 in scores else 1 if 1 in scores else 0
        contributing_ids = tuple(
            sorted(
                {
                    memory_id
                    for candidate in (previous, decision)
                    if candidate.preference_score == preference_score
                    for memory_id in candidate.applied_memory_ids
                }
            )
        )
        merged[previous_index] = preferred.model_copy(
            update={
                "collection_item_ids": source_ids,
                "any_branch_collection_item_ids": branch_source_ids,
                "tags": tuple(dict.fromkeys((*previous.tags, *decision.tags)))[:16],
                "preference_score": preference_score,
                "applied_memory_ids": contributing_ids[:1],
            },
            deep=True,
        )
    return tuple(merged)


class StructuredCollectionRetrievalService:
    """Retrieve one user's collections and apply the sole M0-5B rule path."""

    def __init__(
        self,
        *,
        repository: CollectionRepository,
    ) -> None:
        self._repository = repository

    async def retrieve(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
        facts: PlanningFactSnapshot,
        now: datetime,
        memories: tuple[Memory, ...] = (),
    ) -> StructuredCollectionResult:
        invalid_time = False
        try:
            constraints_active = constraints.is_active(now)
        except ValueError:
            invalid_time = True
            constraints_active = False
        if invalid_time:
            raise StructuredCollectionRetrievalError("INVALID_RETRIEVAL_TIME") from None
        if not constraints_active:
            code = (
                "PLAN_CONSTRAINTS_EXPIRED"
                if now >= constraints.expires_at
                else "INVALID_RETRIEVAL_TIME"
            )
            raise StructuredCollectionRetrievalError(code) from None

        retrieval_failed = False
        try:
            items = await self._repository.list_collection_items(
                user_id=user_id,
                include_inactive=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            retrieval_failed = True
            items = []
        if retrieval_failed:
            raise StructuredCollectionRetrievalError() from None
        if any(item.user_id != user_id for item in items):
            raise StructuredCollectionRetrievalError() from None
        if constraints.selected_collection_item_ids:
            by_id = {item.id: item for item in items}
            if any(
                identifier not in by_id
                for identifier in constraints.selected_collection_item_ids
            ):
                raise StructuredCollectionRetrievalError() from None
            if constraints.collection_only:
                items = [
                    by_id[identifier]
                    for identifier in constraints.selected_collection_item_ids
                ]
        effective_memories = tuple(memory for memory in memories if memory.is_effective(now))

        collection_facts = {item.collection_item_id: item for item in facts.collections}
        poi_facts = {item.identity: item for item in facts.pois}
        decisions: list[CollectionCandidateDecision] = []
        for item in items:
            resolved = resolve_place_target(
                item.place_target,
                collection_status=item.status.value,
            )
            if item.kind is CollectionKind.EVENT:
                event_facts = collection_facts.get(
                    item.id,
                    CollectionPlanningFacts(collection_item_id=item.id),
                )
                event_poi = resolved.poi
                decisions.append(
                    assess_collection_candidate(
                        item=item,
                        constraints=constraints,
                        formal_city_code=(
                            None if event_poi is None else event_poi.city_code
                        ),
                        location_confirmed=event_poi is not None,
                        poi=event_poi,
                        facts=event_facts,
                        memories=effective_memories,
                    )
                )
            elif resolved.kind is ResolvedPlaceTargetKind.EXACT:
                assert resolved.poi is not None
                poi = resolved.poi
                dynamic = poi_facts.get(
                    (poi.provider, poi.poi_id),
                    PoiPlanningFacts(provider=poi.provider, poi_id=poi.poi_id),
                )
                decisions.append(
                    assess_collection_candidate(
                        item=item,
                        constraints=constraints,
                        formal_city_code=poi.city_code,
                        location_confirmed=True,
                        poi=poi,
                        facts=dynamic,
                        memories=effective_memories,
                    )
                )
            elif resolved.kind is ResolvedPlaceTargetKind.ANY_BRANCH:
                branch_facts = collection_facts.get(
                    item.id,
                    CollectionPlanningFacts(collection_item_id=item.id),
                )
                branch_poi = branch_facts.resolved_poi
                decisions.append(
                    assess_collection_candidate(
                        item=item,
                        constraints=constraints,
                        formal_city_code=(
                            None if branch_poi is None else branch_poi.city_code
                        ),
                        location_confirmed=branch_poi is not None,
                        poi=branch_poi,
                        facts=branch_facts,
                        additional_reasons=(
                            ()
                            if branch_poi is not None
                            else (
                                branch_facts.branch_failure_reason
                                or CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT,
                            )
                        ),
                        apply_dynamic_facts=branch_poi is not None,
                        resolved_from_any_branch=True,
                        memories=effective_memories,
                    )
                )
            else:
                decisions.append(
                    assess_collection_candidate(
                        item=item,
                        constraints=constraints,
                        formal_city_code=None,
                        location_confirmed=False,
                        poi=None,
                        facts=CandidateFactValues(),
                        memories=effective_memories,
                    )
                )

        deduplicated = _merge_duplicate_pois(decisions)
        included_scores = {
            item.preference_score
            for item in deduplicated
            if item.outcome is CandidateOutcome.INCLUDED
        }
        ranking_aware = (
            tuple(
                item.model_copy(update={"applied_memory_ids": ()})
                if item.outcome is CandidateOutcome.INCLUDED
                and len(included_scores) < 2
                else item
                for item in deduplicated
            )
        )
        ordered = tuple(
            sorted(
                ranking_aware,
                key=lambda item: (
                    list(CandidateOutcome).index(item.outcome),
                    _text_identity(item.title),
                    item.collection_item_ids,
                ),
            )
        )
        return StructuredCollectionResult(decisions=ordered)

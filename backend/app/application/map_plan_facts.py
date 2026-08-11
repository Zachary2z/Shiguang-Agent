"""Acquire a bounded set of provider-neutral facts for the existing planner."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.place_matching import PlaceMatchingService
from app.application.plan_experience import PlanGenerationFacts
from app.application.structured_collection_retrieval import (
    assess_collection_candidate,
    branch_match_candidate,
)
from app.domain.collections import CollectionItem, CollectionKind, event_schedule_is_confirmed
from app.domain.places import (
    Coordinate,
    MatchStatus,
    PlaceMatchingPolicy,
    PlaceMatchRequest,
    Poi,
    RouteRequest,
    TransportMode,
    WeatherRequest,
    poi_from_match_candidate,
    resolve_place_target,
)
from app.domain.plans import (
    AvailabilityAssessment,
    CandidateFactValues,
    CandidateOutcome,
    CandidateReasonCode,
    CollectionPlanningFacts,
    DraftCandidateFacts,
    DraftRouteFacts,
    ExternalDraftCandidate,
    ExternalPlaceCandidate,
    PlanConstraints,
    PlanDraftFactSnapshot,
    PlanningFactSnapshot,
    PlanProposalSet,
    PoiPlanningFacts,
    RouteAssessment,
    WeatherAssessment,
)
from app.domain.plans.drafts import PlanRouteLeg
from app.domain.time import utc_now
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.providers.map import MapProvider, MapProviderError

MAX_PLAN_ROUTE_CALLS = 48


def proposal_route_edges(proposals: PlanProposalSet) -> tuple[tuple[str | None, str], ...]:
    """Return actual origin and adjacent proposal edges once."""

    return tuple(
        dict.fromkeys(
            (None if index == 0 else option.items[index - 1].candidate_key, item.candidate_key)
            for option in proposals.options
            for index, item in enumerate(option.items)
        )
    )


@dataclass(frozen=True, slots=True)
class _ExecutableCandidate:
    item: CollectionItem
    poi: Poi
    route: tuple[int, int] | None
    resolved_from_any_branch: bool = False


class MapPlanFactResolver:
    """Qualify first through M0-5 rules, then fetch a bounded dynamic fact set."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        map_provider: MapProvider,
        matching_policy: PlaceMatchingPolicy,
    ) -> None:
        self._repository = SqlAlchemyCollectionRepository(session)
        self._map = map_provider
        self._matching = PlaceMatchingService(
            map_provider=map_provider,
            policy=matching_policy,
        )
        self._route_calls = 0
        self._weather_assessment: WeatherAssessment | None = None
        self._weather_queried_at: datetime | None = None
        self._weather_summary: str | None = None
        self._selected: dict[tuple[str, ...], _ExecutableCandidate] = {}
        self._constraints: PlanConstraints | None = None
        self._mode = TransportMode.TRANSIT

    async def resolve(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
    ) -> PlanGenerationFacts:
        self._route_calls = 0
        self._weather_assessment = None
        self._weather_queried_at = None
        self._weather_summary = None
        queried_at = utc_now()
        items = await self._repository.list_collection_items(
            user_id=user_id,
            include_inactive=True,
        )
        if constraints.selected_collection_item_ids:
            by_id = {item.id: item for item in items}
            items = [
                by_id[identifier]
                for identifier in constraints.selected_collection_item_ids
                if identifier in by_id
            ]
        mode = (
            constraints.transport_modes[0] if constraints.transport_modes else TransportMode.TRANSIT
        )
        self._constraints = constraints
        self._mode = mode
        selected: list[_ExecutableCandidate] = []
        collection_facts: list[CollectionPlanningFacts] = []
        poi_facts: list[PoiPlanningFacts] = []
        candidate_facts: list[DraftCandidateFacts] = []
        origin_routes: list[DraftRouteFacts] = []

        for item in items:
            resolved = resolve_place_target(
                item.place_target,
                collection_status=item.status.value,
            )
            if item.kind is CollectionKind.EVENT:
                if resolved.poi is None or not event_schedule_is_confirmed(
                    event_start_date=item.event_start_date,
                    event_end_date=item.event_end_date,
                    event_start_at=item.event_start_at,
                    event_end_at=item.event_end_at,
                    uncertainties=item.uncertainties,
                ):
                    continue
                candidate = await self._qualify_concrete(
                    item=item,
                    poi=resolved.poi,
                    constraints=constraints,
                    mode=mode,
                )
                if candidate is None:
                    continue
                selected.append(candidate)
                route = candidate.route
                collection_facts.append(
                    CollectionPlanningFacts(
                        collection_item_id=item.id,
                        formal_city=constraints.city_scope,
                        location_confirmed=True,
                        coordinate=candidate.poi.coordinate,
                        resolved_poi=candidate.poi,
                        route=_route_assessment(
                            route,
                            origin_known=False,
                        ),
                        route_duration_seconds=None if route is None else route[0],
                        route_distance_meters=None if route is None else route[1],
                        weather=(self._weather_assessment or WeatherAssessment.UNKNOWN),
                        availability=AvailabilityAssessment.AVAILABLE,
                    )
                )
            elif resolved.poi is not None:
                candidate = await self._qualify_concrete(
                    item=item,
                    poi=resolved.poi,
                    constraints=constraints,
                    mode=mode,
                )
                if candidate is None:
                    continue
                selected.append(candidate)
                poi_facts.append(
                    self._poi_facts(
                        candidate,
                        self._weather_assessment or WeatherAssessment.UNKNOWN,
                        origin_known=False,
                    )
                )
            elif resolved.brand_identity is not None:
                candidate, failure_reason = await self._resolve_branch(
                    item=item,
                    brand_name=resolved.brand_identity.display_name,
                    constraints=constraints,
                    mode=mode,
                )
                if candidate is None:
                    if failure_reason is not None:
                        collection_facts.append(
                            CollectionPlanningFacts(
                                collection_item_id=item.id,
                                branch_failure_reason=failure_reason,
                            )
                        )
                    continue
                selected.append(candidate)
                route = candidate.route
                collection_facts.append(
                    CollectionPlanningFacts(
                        collection_item_id=item.id,
                        formal_city=constraints.city_scope,
                        location_confirmed=True,
                        coordinate=candidate.poi.coordinate,
                        resolved_poi=candidate.poi,
                        route=_route_assessment(
                            route,
                            origin_known=constraints.origin is not None,
                        ),
                        route_duration_seconds=None if route is None else route[0],
                        route_distance_meters=None if route is None else route[1],
                        weather=self._weather_assessment or WeatherAssessment.UNKNOWN,
                        availability=(
                            AvailabilityAssessment.AVAILABLE
                            if candidate.poi.opening_hours_summary
                            else AvailabilityAssessment.UNKNOWN
                        ),
                    )
                )

        for candidate in selected:
            item = candidate.item
            candidate_facts.append(
                DraftCandidateFacts(
                    collection_item_ids=(item.id,),
                    poi_queried_at=(queried_at if candidate.resolved_from_any_branch else None),
                    event_start_at=(
                        item.event_start_at if item.kind is CollectionKind.EVENT else None
                    ),
                    event_end_at=(item.event_end_at if item.kind is CollectionKind.EVENT else None),
                )
            )
            if candidate.resolved_from_any_branch and candidate.route is not None:
                origin_routes.append(
                    DraftRouteFacts(
                        to_collection_item_ids=(item.id,),
                        duration_seconds=candidate.route[0],
                        distance_meters=candidate.route[1],
                        transport_mode=mode,
                    )
                )
        self._selected = {(candidate.item.id,): candidate for candidate in selected}

        return PlanGenerationFacts(
            retrieval=PlanningFactSnapshot(
                collections=tuple(collection_facts),
                pois=tuple(_unique_poi_facts(poi_facts)),
            ),
            draft=PlanDraftFactSnapshot(
                candidates=tuple(candidate_facts),
                routes=tuple(origin_routes),
                weather_status=self._weather_assessment,
                weather_source=("amap" if self._weather_assessment is not None else None),
                weather_queried_at=self._weather_queried_at,
                weather_summary=self._weather_summary,
            ),
        )

    async def resolve_proposal_routes(
        self,
        *,
        proposals: PlanProposalSet,
        candidate_keys: dict[str, tuple[str, ...]],
        base: PlanDraftFactSnapshot,
    ) -> PlanDraftFactSnapshot:
        """Fetch only origin and adjacent edges referenced by model proposals."""

        constraints = self._constraints
        if constraints is None:
            raise RuntimeError("candidate facts must be resolved before proposal routes")
        await self._ensure_weather(constraints)
        routes: list[DraftRouteFacts] = []
        known_routes = {route.identity: route for route in base.routes}
        for source_key, target_key in proposal_route_edges(proposals):
            if target_key not in candidate_keys or (
                source_key is not None and source_key not in candidate_keys
            ):
                continue
            target_ids = candidate_keys[target_key]
            target = self._candidate(target_ids)
            source_ids = () if source_key is None else candidate_keys[source_key]
            known = known_routes.get((source_ids, target_ids))
            if known is None and not source_ids:
                for item_id in target_ids:
                    stored = known_routes.get(((), (item_id,)))
                    if stored is not None:
                        known = stored.model_copy(
                            update={"to_collection_item_ids": target_ids}
                        )
                        break
            if known is not None:
                routes.append(known)
                continue
            origin = (
                constraints.origin
                if source_key is None
                else self._candidate(source_ids).poi.coordinate
            )
            route = await self._route(
                constraints=constraints,
                origin=origin,
                destination=target.poi.coordinate,
                mode=self._mode,
            )
            if route is not None:
                routes.append(
                    DraftRouteFacts(
                        from_collection_item_ids=source_ids,
                        to_collection_item_ids=target_ids,
                        duration_seconds=route[0],
                        distance_meters=route[1],
                        transport_mode=self._mode,
                    )
                )
        facts_by_id = {
            item.collection_item_ids[0]: item
            for item in base.candidates
            if len(item.collection_item_ids) == 1
        }
        candidates = tuple(
            _merged_candidate_facts(ids, facts_by_id)
            for ids in dict.fromkeys(candidate_keys.values())
        )
        return base.model_copy(
            update={
                "candidates": candidates,
                "routes": tuple(routes),
                "weather_status": self._weather_assessment,
                "weather_source": "amap",
                "weather_queried_at": self._weather_queried_at,
                "weather_summary": self._weather_summary,
            }
        )

    async def resolve_external_routes(
        self,
        *,
        proposals: PlanProposalSet,
        external_key: str,
        candidate: ExternalPlaceCandidate,
        candidate_keys: dict[str, tuple[str, ...]],
    ) -> ExternalDraftCandidate:
        """Resolve every actual inbound edge for the one supplemented Place."""

        constraints = self._constraints
        if constraints is None:
            raise RuntimeError("candidate facts must be resolved before proposal routes")
        routes: list[PlanRouteLeg] = []
        for source_key, target_key in proposal_route_edges(proposals):
            if target_key != external_key:
                continue
            from_ids = () if source_key is None else candidate_keys[source_key]
            origin = (
                constraints.origin
                if source_key is None
                else self._candidate(from_ids).poi.coordinate
            )
            route = await self._route(
                constraints=constraints,
                origin=origin,
                destination=candidate.poi.coordinate,
                mode=self._mode,
            )
            routes.append(
                PlanRouteLeg(
                    from_collection_item_ids=from_ids,
                    to_external_provider=candidate.poi.provider,
                    to_external_poi_id=candidate.poi.poi_id,
                    duration_seconds=None if route is None else route[0],
                    distance_meters=None if route is None else route[1],
                    transport_mode=self._mode,
                )
            )
        return ExternalDraftCandidate(
            poi=candidate.poi,
            queried_at=candidate.queried_at,
            supplement_reason=candidate.supplement_reason,
            price_amount=candidate.price_amount,
            price_currency=candidate.price_currency,
            inbound_routes=tuple(routes),
        )

    def _candidate(self, collection_item_ids: tuple[str, ...]) -> _ExecutableCandidate:
        candidates = tuple(
            self._selected[(item_id,)]
            for item_id in collection_item_ids
            if (item_id,) in self._selected
        )
        identities = {(item.poi.provider, item.poi.poi_id) for item in candidates}
        if not candidates or len(identities) != 1:
            raise RuntimeError("proposal collection sources do not resolve to one POI")
        return candidates[0]

    async def _qualify_concrete(
        self,
        *,
        item: CollectionItem,
        poi: Poi,
        constraints: PlanConstraints,
        mode: TransportMode,
        resolved_from_any_branch: bool = False,
        resolve_route: bool = False,
    ) -> _ExecutableCandidate | None:
        static = assess_collection_candidate(
            item=item,
            constraints=constraints,
            formal_city_code=poi.city_code,
            location_confirmed=True,
            poi=poi,
            facts=CandidateFactValues(),
            apply_dynamic_facts=False,
            resolved_from_any_branch=resolved_from_any_branch,
        )
        if static.outcome is not CandidateOutcome.INCLUDED:
            return None
        route = (
            await self._route(
                constraints=constraints,
                origin=constraints.origin,
                destination=poi.coordinate,
                mode=mode,
            )
            if resolve_route
            else None
        )
        return _ExecutableCandidate(
            item=item,
            poi=poi,
            route=route,
            resolved_from_any_branch=resolved_from_any_branch,
        )

    async def _resolve_branch(
        self,
        *,
        item: CollectionItem,
        brand_name: str,
        constraints: PlanConstraints,
        mode: TransportMode,
    ) -> tuple[_ExecutableCandidate | None, CandidateReasonCode | None]:
        probe = assess_collection_candidate(
            item=item,
            constraints=constraints,
            formal_city_code=constraints.city_code.value,
            location_confirmed=True,
            poi=None,
            facts=CandidateFactValues(),
            apply_dynamic_facts=False,
            resolved_from_any_branch=True,
        )
        if probe.outcome is CandidateOutcome.EXCLUDED:
            return (None, None)
        try:
            result = await self._matching.match(
                PlaceMatchRequest(
                    candidate=branch_match_candidate(brand_name),
                    city=constraints.city_scope,
                    search_district=(
                        constraints.area.districts[0]
                        if constraints.area is not None and len(constraints.area.districts) == 1
                        else None
                    ),
                    search_location=constraints.origin,
                )
            )
        except asyncio.CancelledError:
            raise
        except MapProviderError:
            return (None, CandidateReasonCode.BRANCH_PROVIDER_FAILED)
        if result.status is MatchStatus.NOT_FOUND:
            return (None, CandidateReasonCode.BRANCH_NOT_FOUND)

        candidates: list[_ExecutableCandidate] = []
        for match in result.candidates:
            poi = poi_from_match_candidate(match)
            candidate = await self._qualify_concrete(
                item=item,
                poi=poi,
                constraints=constraints,
                mode=mode,
                resolved_from_any_branch=True,
                resolve_route=True,
            )
            if candidate is None:
                continue
            candidates.append(candidate)
        if not candidates:
            return (None, CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT)
        chosen = min(
            candidates,
            key=lambda candidate: (
                candidate.route is None,
                2**63 if candidate.route is None else candidate.route[0],
                2**63 if candidate.route is None else candidate.route[1],
                candidate.poi.provider.value,
                candidate.poi.poi_id,
            ),
        )
        return (chosen, None)

    @staticmethod
    def _poi_facts(
        candidate: _ExecutableCandidate,
        weather: WeatherAssessment,
        *,
        origin_known: bool,
    ) -> PoiPlanningFacts:
        route = candidate.route
        return PoiPlanningFacts(
            provider=candidate.poi.provider,
            poi_id=candidate.poi.poi_id,
            route=_route_assessment(route, origin_known=origin_known),
            route_duration_seconds=None if route is None else route[0],
            route_distance_meters=None if route is None else route[1],
            weather=weather,
            availability=(
                AvailabilityAssessment.AVAILABLE
                if candidate.poi.opening_hours_summary
                else AvailabilityAssessment.UNKNOWN
            ),
        )

    async def _weather(self, constraints: PlanConstraints) -> WeatherAssessment:
        self._weather_queried_at = utc_now()
        try:
            result = await self._map.weather(
                WeatherRequest(
                    city=constraints.city_scope,
                    on_date=constraints.start_at.date(),
                )
            )
        except asyncio.CancelledError:
            raise
        except MapProviderError as error:
            self._weather_summary = error.summary
            return WeatherAssessment.PROVIDER_FAILED
        self._weather_summary = result.summary or result.condition
        return WeatherAssessment.COMPATIBLE

    async def _ensure_weather(self, constraints: PlanConstraints) -> None:
        if self._weather_assessment is None:
            self._weather_assessment = await self._weather(constraints)

    async def _route(
        self,
        *,
        constraints: PlanConstraints,
        origin: Coordinate | None,
        destination: Coordinate,
        mode: TransportMode,
    ) -> tuple[int, int] | None:
        if origin is None:
            return None
        if self._route_calls >= MAX_PLAN_ROUTE_CALLS:
            return None
        self._route_calls += 1
        try:
            result = await self._map.route(
                RouteRequest(
                    city=constraints.city_scope,
                    origin=origin,
                    destination=destination,
                    mode=mode,
                )
            )
        except asyncio.CancelledError:
            raise
        except MapProviderError:
            return None
        return (result.duration_seconds, result.distance_meters)


def _route_assessment(
    route: tuple[int, int] | None,
    *,
    origin_known: bool,
) -> RouteAssessment:
    if route is not None:
        return RouteAssessment.REACHABLE
    return RouteAssessment.PROVIDER_FAILED if origin_known else RouteAssessment.UNKNOWN


def _merged_candidate_facts(
    collection_item_ids: tuple[str, ...],
    facts_by_id: dict[str, DraftCandidateFacts],
) -> DraftCandidateFacts:
    facts = tuple(facts_by_id[item_id] for item_id in collection_item_ids)
    first = facts[0]
    return first.model_copy(
        update={
            "collection_item_ids": collection_item_ids,
            "poi_queried_at": next(
                (item.poi_queried_at for item in facts if item.poi_queried_at is not None),
                None,
            ),
        }
    )


def _unique_poi_facts(
    values: list[PoiPlanningFacts],
) -> tuple[PoiPlanningFacts, ...]:
    selected: dict[tuple[object, str], PoiPlanningFacts] = {}
    for value in values:
        selected[value.identity] = value
    return tuple(selected[key] for key in sorted(selected, key=lambda item: str(item)))


__all__ = [
    "MAX_PLAN_ROUTE_CALLS",
    "MapPlanFactResolver",
    "proposal_route_edges",
]

"""Acquire provider-neutral planning facts for the existing deterministic planner."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.plan_experience import PlanGenerationFacts
from app.domain.collections import (
    CandidateField,
    CollectionKind,
    CollectionStatus,
    PlaceCandidate,
)
from app.domain.places import Coordinate, RouteRequest, TransportMode, WeatherRequest
from app.domain.plans import (
    AvailabilityAssessment,
    DraftCandidateFacts,
    DraftRouteFacts,
    PlanConstraints,
    PlanDraftFactSnapshot,
    PlanningFactSnapshot,
    PoiPlanningFacts,
    RequiredGapKind,
    RequiredPlanGap,
    RouteAssessment,
    WeatherAssessment,
)
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.providers.map import MapProvider, MapProviderError

_VISIT_SECONDS = 60 * 60


class MapPlanFactResolver:
    """Resolve dynamic inputs once; planning and ranking stay in M0-5 services."""

    def __init__(self, *, session: AsyncSession, map_provider: MapProvider) -> None:
        self._repository = SqlAlchemyCollectionRepository(session)
        self._map = map_provider

    async def resolve(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
    ) -> PlanGenerationFacts:
        items = await self._repository.list_collection_items(
            user_id=user_id,
            include_inactive=True,
        )
        exact = tuple(
            item
            for item in items
            if item.kind is CollectionKind.PLACE
            and item.status is CollectionStatus.ACTIVE
            and item.place_target is not None
            and item.place_target.poi is not None
        )
        weather = await self._weather(constraints)
        mode = (
            constraints.transport_modes[0]
            if constraints.transport_modes
            else TransportMode.TRANSIT
        )
        poi_facts = []
        candidates = []
        routes = []
        for item in exact:
            assert item.place_target is not None and item.place_target.poi is not None
            poi = item.place_target.poi
            route = await self._route(
                constraints=constraints,
                origin=constraints.origin,
                destination=poi.coordinate,
                mode=mode,
            )
            poi_facts.append(
                PoiPlanningFacts(
                    provider=poi.provider,
                    poi_id=poi.poi_id,
                    route=(
                        RouteAssessment.REACHABLE
                        if route is not None
                        else RouteAssessment.PROVIDER_FAILED
                    ),
                    route_duration_seconds=None if route is None else route[0],
                    route_distance_meters=None if route is None else route[1],
                    weather=weather,
                    availability=(
                        AvailabilityAssessment.AVAILABLE
                        if poi.opening_hours_summary
                        else AvailabilityAssessment.UNKNOWN
                    ),
                )
            )
            candidates.append(
                DraftCandidateFacts(
                    collection_item_ids=(item.id,),
                    visit_duration_seconds=_VISIT_SECONDS,
                )
            )
            if route is not None:
                routes.append(
                    DraftRouteFacts(
                        to_collection_item_ids=(item.id,),
                        duration_seconds=route[0],
                        distance_meters=route[1],
                        transport_mode=mode,
                    )
                )

        for source in exact:
            for target in exact:
                if source.id == target.id:
                    continue
                assert source.place_target is not None
                assert source.place_target.poi is not None
                assert target.place_target is not None
                assert target.place_target.poi is not None
                route = await self._route(
                    constraints=constraints,
                    origin=source.place_target.poi.coordinate,
                    destination=target.place_target.poi.coordinate,
                    mode=mode,
                )
                if route is not None:
                    routes.append(
                        DraftRouteFacts(
                            from_collection_item_ids=(source.id,),
                            to_collection_item_ids=(target.id,),
                            duration_seconds=route[0],
                            distance_meters=route[1],
                            transport_mode=mode,
                        )
                    )

        required_gap = None
        if len(exact) == 1 and constraints.include:
            required_gap = _required_place_gap(
                constraints=constraints,
                title=constraints.include[0],
            )
        return PlanGenerationFacts(
            retrieval=PlanningFactSnapshot(pois=tuple(poi_facts)),
            draft=PlanDraftFactSnapshot(
                candidates=tuple(candidates),
                routes=tuple(routes),
            ),
            required_gap=required_gap,
        )

    async def _weather(self, constraints: PlanConstraints) -> WeatherAssessment:
        try:
            await self._map.weather(
                WeatherRequest(
                    city=constraints.city_scope,
                    on_date=constraints.start_at.date(),
                )
            )
        except asyncio.CancelledError:
            raise
        except MapProviderError:
            return WeatherAssessment.PROVIDER_FAILED
        return WeatherAssessment.COMPATIBLE

    async def _route(
        self,
        *,
        constraints: PlanConstraints,
        origin: Coordinate | None,
        destination: Coordinate,
        mode: TransportMode,
    ) -> tuple[int, int] | None:
        if origin is None:
            # An activity range means the user starts inside that range; no exact
            # inbound distance is claimed or persisted.
            return (0, 0)
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


def _required_place_gap(
    *,
    constraints: PlanConstraints,
    title: str,
) -> RequiredPlanGap:
    district = (
        constraints.area.districts[0]
        if constraints.area is not None and len(constraints.area.districts) == 1
        else None
    )
    missing = [
        CandidateField.ADDRESS,
        CandidateField.BUSINESS_DISTRICT,
        CandidateField.LANDMARK,
        CandidateField.METRO_STATION,
        CandidateField.PRICE,
        CandidateField.TAGS,
    ]
    if district is None:
        missing.append(CandidateField.DISTRICT)
    return RequiredPlanGap(
        kind=RequiredGapKind.PLACE,
        place_candidate=PlaceCandidate(
            title=title,
            city_hint="深圳",
            district=district,
            missing_fields=tuple(missing),
        ),
        supplement_reason="The requested included Place is not covered by one collection.",
        visit_duration_seconds=_VISIT_SECONDS,
    )


__all__ = ["MapPlanFactResolver"]

"""Offline M0-5D coverage for controlled external Place supplementation."""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.application import (
    ExternalPlaceSupplementService,
    PlaceMatchingService,
    PlanDraftService,
    StructuredCollectionRetrievalService,
)
from app.domain.collections import CandidateField, CollectionKind, PlaceCandidate, PlanCity
from app.domain.places import (
    Coordinate,
    CoordinateSystem,
    PlaceMatchingPolicy,
    Poi,
    PoiProvider,
    PoiSearchResult,
    PoiType,
    RouteRequest,
    RouteResult,
    SearchPoiRequest,
    TransportMode,
)
from app.domain.plans import ActivityArea, PlanConstraints, PlanPace
from app.domain.plans.drafts import (
    DraftCandidateFacts,
    DraftRouteFacts,
    PlanDraftFactSnapshot,
    PlanDraftOutcome,
    PlanItemSourceKind,
    PlanRiskCode,
)
from app.domain.plans.retrieval import (
    CandidateOutcome,
    CollectionCandidateDecision,
    PlanningFactSnapshot,
    StructuredCollectionResult,
)
from app.domain.plans.supplement import (
    ExternalApprovalDecision,
    ExternalPlaceApprovalDecision,
    ExternalPlaceApprovalRequirement,
    ExternalRecoveryCode,
    ExternalSupplementOutcome,
    RequiredGapKind,
    RequiredPlanGap,
)
from app.domain.runs import AgentRunStatus
from app.providers import StubMapProvider
from app.providers.map import MapProviderError, MapProviderErrorCode

NOW = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
START = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
CORE_ID = "col_00000000000000000000000000000001"
CORE_COORDINATE = Coordinate(
    latitude=22.541174,
    longitude=114.057701,
    coordinate_system=CoordinateSystem.GCJ_02,
)
EXTERNAL_COORDINATE = Coordinate(
    latitude=22.540325,
    longitude=114.059322,
    coordinate_system=CoordinateSystem.GCJ_02,
)
CORE_POI = Poi(
    provider=PoiProvider.AMAP,
    poi_id="core-poi",
    name="收藏美术馆",
    city_code="shenzhen",
    district="福田区",
    address="福中路 1 号",
    coordinate=CORE_COORDINATE,
    poi_type=PoiType.MUSEUM,
)
EXTERNAL_POI = Poi(
    provider=PoiProvider.AMAP,
    poi_id="external-cafe",
    name="明确咖啡店",
    city_code="shenzhen",
    district="福田区",
    address="福中路 2 号",
    coordinate=EXTERNAL_COORDINATE,
    poi_type=PoiType.CAFE,
)


def _constraints(
    *,
    collection_only: bool = False,
    origin: Coordinate | None = None,
    minutes: int = 240,
    budget: Decimal | None = None,
) -> PlanConstraints:
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=START,
        end_at=START + timedelta(minutes=minutes),
        area=ActivityArea(districts=("福田区",)),
        origin=origin,
        pace=PlanPace.BALANCED,
        budget=budget,
        transport_modes=(TransportMode.WALKING,),
        collection_only=collection_only,
        created_at=NOW,
        expires_at=START,
    )


def _collections(*, include_core: bool = True) -> StructuredCollectionResult:
    if not include_core:
        return StructuredCollectionResult()
    return StructuredCollectionResult(
        decisions=(
            CollectionCandidateDecision(
                outcome=CandidateOutcome.INCLUDED,
                collection_item_ids=(CORE_ID,),
                kind=CollectionKind.PLACE,
                title=CORE_POI.name,
                poi=CORE_POI,
                price_amount=Decimal("30"),
                price_currency="CNY",
                route_duration_seconds=10 * 60,
                route_distance_meters=800,
            ),
        )
    )


def _facts(*, include_core: bool = True) -> PlanDraftFactSnapshot:
    if not include_core:
        return PlanDraftFactSnapshot()
    return PlanDraftFactSnapshot(
        candidates=(
            DraftCandidateFacts(
                collection_item_ids=(CORE_ID,),
                visit_duration_seconds=60 * 60,
            ),
        ),
        routes=(
            DraftRouteFacts(
                to_collection_item_ids=(CORE_ID,),
                duration_seconds=10 * 60,
                distance_meters=800,
                transport_mode=TransportMode.WALKING,
            ),
        ),
    )


def _place_candidate(
    title: str = EXTERNAL_POI.name,
    *,
    price: Decimal | None = None,
) -> PlaceCandidate:
    missing = [
        CandidateField.CITY_HINT,
        CandidateField.DISTRICT,
        CandidateField.ADDRESS,
        CandidateField.BUSINESS_DISTRICT,
        CandidateField.LANDMARK,
        CandidateField.METRO_STATION,
        CandidateField.TAGS,
    ]
    if price is None:
        missing.append(CandidateField.PRICE)
    return PlaceCandidate(
        title=title,
        price_amount=price,
        price_currency=None if price is None else "CNY",
        missing_fields=tuple(missing),
    )


def _place_gap(
    title: str = EXTERNAL_POI.name,
    *,
    price: Decimal | None = None,
) -> RequiredPlanGap:
    return RequiredPlanGap(
        kind=RequiredGapKind.PLACE,
        place_candidate=_place_candidate(title, price=price),
        supplement_reason="The user explicitly requires one cafe after the core visit.",
        visit_duration_seconds=45 * 60,
    )


def _event_gap() -> RequiredPlanGap:
    return RequiredPlanGap(
        kind=RequiredGapKind.EVENT,
        supplement_reason="The user explicitly requires a saved exhibition.",
        visit_duration_seconds=60 * 60,
    )


def _approval(
    gap: RequiredPlanGap,
    decision: ExternalApprovalDecision,
) -> ExternalPlaceApprovalDecision:
    return ExternalPlaceApprovalDecision(
        approval_id=ExternalPlaceApprovalRequirement.for_gap(gap).approval_id,
        decision=decision,
    )


def _search_request(
    title: str = EXTERNAL_POI.name,
    *,
    origin: Coordinate | None = None,
) -> SearchPoiRequest:
    return SearchPoiRequest(
        query=title,
        city=_constraints().city_scope,
        district="福田区",
        location=origin,
    )


def _route_request(origin: Coordinate = CORE_COORDINATE) -> RouteRequest:
    return RouteRequest(
        city=_constraints().city_scope,
        origin=origin,
        destination=EXTERNAL_COORDINATE,
        mode=TransportMode.WALKING,
    )


def _route_result(origin: Coordinate = CORE_COORDINATE) -> RouteResult:
    return RouteResult(
        city_code="shenzhen",
        origin=origin,
        destination=EXTERNAL_COORDINATE,
        mode=TransportMode.WALKING,
        distance_meters=500,
        duration_seconds=8 * 60,
    )


def _service(provider: StubMapProvider) -> ExternalPlaceSupplementService:
    return ExternalPlaceSupplementService(
        map_provider=provider,
        place_matching=PlaceMatchingService(
            map_provider=provider,
            policy=PlaceMatchingPolicy(
                unique_match_score=30,
                minimum_score_gap=5,
                candidate_score=20,
            ),
        ),
        plan_drafts=PlanDraftService(),
    )


def _provider(
    calls: list[object],
    *,
    pois: tuple[Poi, ...] = (EXTERNAL_POI,),
    origin: Coordinate = CORE_COORDINATE,
) -> StubMapProvider:
    async def record(request: object) -> None:
        calls.append(request)

    return StubMapProvider(
        search_results={
            _search_request(origin=None): PoiSearchResult(
                city_code="shenzhen",
                pois=pois,
            ),
            _search_request(origin=origin): PoiSearchResult(
                city_code="shenzhen",
                pois=pois,
            ),
        },
        route_results={_route_request(origin): _route_result(origin)},
        call_hook=record,
    )


async def _generate(
    service: ExternalPlaceSupplementService,
    *,
    constraints: PlanConstraints | None = None,
    collections: StructuredCollectionResult | None = None,
    facts: PlanDraftFactSnapshot | None = None,
    gap: RequiredPlanGap | None = None,
    decision: ExternalPlaceApprovalDecision | None = None,
):
    return await service.generate(
        constraints=constraints or _constraints(),
        collections=collections or _collections(),
        facts=facts or _facts(),
        required_gap=gap,
        approval_decision=decision,
        queried_at=NOW,
    )


@pytest.mark.asyncio
async def test_sufficient_collections_generate_without_any_map_call() -> None:
    calls: list[object] = []
    result = await _generate(_service(_provider(calls)))

    assert result.outcome is ExternalSupplementOutcome.DRAFT
    assert result.draft is not None
    assert result.draft.outcome is PlanDraftOutcome.GENERATED
    assert calls == []


@pytest.mark.asyncio
async def test_explicit_local_place_gap_searches_once_and_adds_one_external_item() -> None:
    calls: list[object] = []
    result = await _generate(_service(_provider(calls)), gap=_place_gap())

    assert [type(call) for call in calls] == [SearchPoiRequest, RouteRequest]
    assert result.draft is not None
    external_items = [
        item
        for option in result.draft.options
        for item in option.items
        if item.source.kind is PlanItemSourceKind.EXTERNAL_PLACE
    ]
    assert len(external_items) == 1
    external = external_items[0]
    assert external.source.collection_item_ids == ()
    assert external.source.source_label == "高德补充 · 未收藏"
    assert external.source.concrete_poi == EXTERNAL_POI.model_copy(
        update={"opening_hours_summary": None, "phone": None},
        deep=True,
    )
    assert external.source.poi_queried_at == NOW
    assert external.source.supplement_reason == _place_gap().supplement_reason
    assert external.risk_codes == (
        PlanRiskCode.PRICE_UNKNOWN,
        PlanRiskCode.OPENING_HOURS_UNKNOWN,
    )


@pytest.mark.asyncio
async def test_known_cny_price_is_preserved_and_shared_budget_rule_can_reject_it() -> None:
    calls: list[object] = []
    priced_gap = _place_gap(price=Decimal("20"))
    included = await _generate(
        _service(_provider(calls)),
        gap=priced_gap,
    )
    blocked = await _generate(
        _service(_provider(calls)),
        constraints=_constraints(budget=Decimal("40")),
        gap=priced_gap,
    )

    assert included.draft is not None
    external = included.draft.options[0].items[1]
    assert external.price_amount == Decimal("20")
    assert external.price_currency == "CNY"
    assert external.risk_codes == (PlanRiskCode.OPENING_HOURS_UNKNOWN,)
    assert included.draft.options[0].total_cost_amount == Decimal("50")
    assert blocked.recovery_code is ExternalRecoveryCode.NO_EXECUTABLE_DRAFT
    assert blocked.draft is not None
    assert all(
        item.source.kind is PlanItemSourceKind.COLLECTION_DERIVED
        for option in blocked.draft.options
        for item in option.items
    )


@pytest.mark.asyncio
async def test_approved_external_only_known_price_uses_shared_option_cost() -> None:
    calls: list[object] = []
    gap = _place_gap(price=Decimal("20"))

    result = await _generate(
        _service(_provider(calls, origin=CORE_COORDINATE)),
        constraints=_constraints(origin=CORE_COORDINATE),
        collections=StructuredCollectionResult(),
        facts=PlanDraftFactSnapshot(),
        gap=gap,
        decision=_approval(gap, ExternalApprovalDecision.APPROVED),
    )

    assert result.outcome is ExternalSupplementOutcome.DRAFT
    assert result.draft is not None
    assert result.draft.outcome is PlanDraftOutcome.GENERATED
    assert result.draft.options[0].total_cost_amount == Decimal("20")
    assert result.draft.options[0].total_cost_currency == "CNY"
    assert [type(call) for call in calls] == [SearchPoiRequest, RouteRequest]


@pytest.mark.asyncio
async def test_approved_external_only_known_price_respects_shared_budget_rule() -> None:
    calls: list[object] = []
    gap = _place_gap(price=Decimal("20"))

    result = await _generate(
        _service(_provider(calls, origin=CORE_COORDINATE)),
        constraints=_constraints(origin=CORE_COORDINATE, budget=Decimal("19")),
        collections=StructuredCollectionResult(),
        facts=PlanDraftFactSnapshot(),
        gap=gap,
        decision=_approval(gap, ExternalApprovalDecision.APPROVED),
    )

    assert result.outcome is ExternalSupplementOutcome.RECOVERY_REQUIRED
    assert result.recovery_code is ExternalRecoveryCode.NO_EXECUTABLE_DRAFT
    assert result.draft is None
    assert [type(call) for call in calls] == [SearchPoiRequest, RouteRequest]


@pytest.mark.asyncio
async def test_no_collection_requires_approval_before_any_map_call_then_searches_once() -> None:
    calls: list[object] = []
    origin = CORE_COORDINATE
    provider = _provider(calls, origin=origin)
    constraints = _constraints(origin=origin)
    empty = StructuredCollectionResult()
    facts = PlanDraftFactSnapshot()

    waiting = await _generate(
        _service(provider),
        constraints=constraints,
        collections=empty,
        facts=facts,
        gap=_place_gap(),
    )
    approved = await _generate(
        _service(provider),
        constraints=constraints,
        collections=empty,
        facts=facts,
        gap=_place_gap(),
        decision=_approval(_place_gap(), ExternalApprovalDecision.APPROVED),
    )

    assert waiting.outcome is ExternalSupplementOutcome.WAITING_APPROVAL
    assert waiting.run_status is AgentRunStatus.WAITING_USER
    assert waiting.approval is not None
    assert "22." not in waiting.approval.model_dump_json()
    assert [type(call) for call in calls] == [SearchPoiRequest, RouteRequest]
    assert approved.draft is not None
    assert approved.draft.options[0].items[0].source.kind is PlanItemSourceKind.EXTERNAL_PLACE
    assert approved.draft.options[0].total_cost_amount is None
    assert approved.draft.options[0].total_cost_currency is None
    assert PlanRiskCode.PRICE_UNKNOWN in approved.draft.options[0].risk_codes


@pytest.mark.asyncio
async def test_rejection_is_stable_and_never_searches_or_reissues_approval() -> None:
    calls: list[object] = []
    kwargs = {
        "collections": StructuredCollectionResult(),
        "facts": PlanDraftFactSnapshot(),
        "gap": _place_gap(),
        "decision": _approval(_place_gap(), ExternalApprovalDecision.REJECTED),
    }
    first = await _generate(_service(_provider(calls)), **kwargs)
    second = await _generate(_service(_provider(calls)), **kwargs)

    assert first == second
    assert first.approval is None
    assert first.recovery_code is ExternalRecoveryCode.ADD_COLLECTIONS
    assert calls == []


@pytest.mark.asyncio
async def test_decision_for_another_gap_cannot_authorize_search() -> None:
    calls: list[object] = []
    gap = _place_gap()
    other_decision = _approval(
        _place_gap("另一个地点"),
        ExternalApprovalDecision.APPROVED,
    )
    result = await _generate(
        _service(_provider(calls)),
        collections=StructuredCollectionResult(),
        facts=PlanDraftFactSnapshot(),
        gap=gap,
        decision=other_decision,
    )

    assert result.outcome is ExternalSupplementOutcome.WAITING_APPROVAL
    assert result.approval == ExternalPlaceApprovalRequirement.for_gap(gap)
    assert calls == []


@pytest.mark.asyncio
async def test_collection_only_and_event_gap_never_search() -> None:
    calls: list[object] = []
    provider = _provider(calls)
    collection_only = await _generate(
        _service(provider),
        constraints=_constraints(collection_only=True),
        gap=_place_gap(),
    )
    event = await _generate(_service(provider), gap=_event_gap())
    empty_collection_only = await _generate(
        _service(provider),
        constraints=_constraints(collection_only=True),
        collections=StructuredCollectionResult(),
        facts=PlanDraftFactSnapshot(),
        gap=_place_gap(),
        decision=_approval(_place_gap(), ExternalApprovalDecision.APPROVED),
    )
    empty_event = await _generate(
        _service(provider),
        collections=StructuredCollectionResult(),
        facts=PlanDraftFactSnapshot(),
        gap=_event_gap(),
        decision=_approval(_place_gap(), ExternalApprovalDecision.APPROVED),
    )

    assert collection_only.draft is not None
    assert event.recovery_code is ExternalRecoveryCode.EVENT_NOT_SEARCHABLE
    assert empty_collection_only.recovery_code is ExternalRecoveryCode.COLLECTION_ONLY
    assert empty_event.recovery_code is ExternalRecoveryCode.EVENT_NOT_SEARCHABLE
    assert calls == []


@pytest.mark.asyncio
async def test_ambiguous_branches_return_at_most_three_candidates_without_route_call() -> None:
    calls: list[object] = []
    pois = tuple(
        EXTERNAL_POI.model_copy(
            update={
                "poi_id": f"branch-{index}",
                "branch_name": f"{index} 店",
                "address": f"福中路 {index} 号",
            },
            deep=True,
        )
        for index in range(4)
    )
    result = await _generate(_service(_provider(calls, pois=pois)), gap=_place_gap())

    assert result.outcome is ExternalSupplementOutcome.NEEDS_SELECTION
    assert result.recovery_code is ExternalRecoveryCode.PLACE_AMBIGUOUS
    assert 1 < len(result.candidates) <= 3
    assert [type(call) for call in calls] == [SearchPoiRequest]


@pytest.mark.asyncio
async def test_matched_original_top_is_used_even_with_a_weaker_candidate() -> None:
    calls: list[object] = []
    weaker = EXTERNAL_POI.model_copy(
        update={
            "poi_id": "external-cafe-weaker",
            "name": "明确咖啡店分店",
        },
        deep=True,
    )

    result = await _generate(
        _service(_provider(calls, pois=(EXTERNAL_POI, weaker))),
        gap=_place_gap(),
    )

    assert result.outcome is ExternalSupplementOutcome.DRAFT
    assert result.draft is not None
    external = result.draft.options[0].items[1]
    assert external.source.concrete_poi is not None
    assert external.source.concrete_poi.poi_id == EXTERNAL_POI.poi_id
    assert [type(call) for call in calls] == [SearchPoiRequest, RouteRequest]


@pytest.mark.asyncio
async def test_filtered_original_top_is_not_replaced_by_a_weaker_candidate() -> None:
    calls: list[object] = []
    title = "重复核心地点"
    existing_top = CORE_POI.model_copy(update={"name": title}, deep=True)
    weaker = EXTERNAL_POI.model_copy(
        update={
            "poi_id": "external-weaker",
            "name": f"{title}分店",
        },
        deep=True,
    )
    provider = StubMapProvider(
        search_results={
            _search_request(title): PoiSearchResult(
                city_code="shenzhen",
                pois=(existing_top, weaker),
            )
        },
        route_results={_route_request(): _route_result()},
        call_hook=lambda request: _record(calls, request),
    )

    result = await _generate(
        _service(provider),
        gap=_place_gap(title),
    )

    assert result.outcome is ExternalSupplementOutcome.NEEDS_SELECTION
    assert tuple(candidate.poi_id for candidate in result.candidates) == (
        weaker.poi_id,
    )
    assert [type(call) for call in calls] == [SearchPoiRequest]


@pytest.mark.asyncio
async def test_out_of_scope_original_top_is_not_replaced_by_a_weaker_candidate() -> None:
    calls: list[object] = []
    title = "范围地点"
    outside_top = EXTERNAL_POI.model_copy(
        update={
            "poi_id": "outside-original-top",
            "name": title,
            "business_area": "会展中心",
        },
        deep=True,
    )
    in_scope_weaker = EXTERNAL_POI.model_copy(
        update={
            "poi_id": "in-scope-weaker",
            "name": f"{title}分店",
            "business_area": "市民中心",
        },
        deep=True,
    )
    constraints = _constraints().model_copy(
        update={
            "area": ActivityArea(
                districts=("福田区",),
                labels=("市民中心",),
            )
        },
        deep=True,
    )
    provider = StubMapProvider(
        search_results={
            _search_request(title): PoiSearchResult(
                city_code="shenzhen",
                pois=(outside_top, in_scope_weaker),
            )
        },
        route_results={_route_request(): _route_result()},
        call_hook=lambda request: _record(calls, request),
    )

    result = await _generate(
        _service(provider),
        constraints=constraints,
        gap=_place_gap(title),
    )

    assert result.outcome is ExternalSupplementOutcome.NEEDS_SELECTION
    assert tuple(candidate.poi_id for candidate in result.candidates) == (
        in_scope_weaker.poi_id,
    )
    assert [type(call) for call in calls] == [SearchPoiRequest]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "recovery_code"),
    [
        (MapProviderErrorCode.TIMEOUT, ExternalRecoveryCode.MAP_TIMEOUT),
        (MapProviderErrorCode.RATE_LIMITED, ExternalRecoveryCode.MAP_RATE_LIMITED),
        (MapProviderErrorCode.UNAVAILABLE, ExternalRecoveryCode.MAP_UNAVAILABLE),
        (MapProviderErrorCode.INVALID_RESPONSE, ExternalRecoveryCode.MAP_INVALID_RESPONSE),
    ],
)
async def test_map_search_failures_have_stable_recovery(
    error_code: MapProviderErrorCode,
    recovery_code: ExternalRecoveryCode,
) -> None:
    class FailingSearchProvider(StubMapProvider):
        async def search_poi(self, request: SearchPoiRequest) -> PoiSearchResult:
            raise MapProviderError(code=error_code)

    result = await _generate(_service(FailingSearchProvider()), gap=_place_gap())
    assert result.recovery_code is recovery_code


@pytest.mark.asyncio
async def test_empty_result_and_missing_route_facts_have_recovery_paths() -> None:
    empty_calls: list[object] = []
    empty = await _generate(
        _service(_provider(empty_calls, pois=())),
        gap=_place_gap(),
    )
    route_calls: list[object] = []
    no_route = await _generate(
        _service(_provider(route_calls)),
        collections=StructuredCollectionResult(),
        facts=PlanDraftFactSnapshot(),
        gap=_place_gap(),
        decision=_approval(_place_gap(), ExternalApprovalDecision.APPROVED),
    )

    assert empty.recovery_code is ExternalRecoveryCode.PLACE_NOT_FOUND
    assert no_route.recovery_code is ExternalRecoveryCode.ROUTE_FACTS_MISSING
    assert [type(call) for call in route_calls] == [SearchPoiRequest]


@pytest.mark.asyncio
async def test_event_core_without_poi_does_not_substitute_private_origin_for_route() -> None:
    event_id = "col_00000000000000000000000000000002"
    event_collections = StructuredCollectionResult(
        decisions=(
            CollectionCandidateDecision(
                outcome=CandidateOutcome.INCLUDED,
                collection_item_ids=(event_id,),
                kind=CollectionKind.EVENT,
                title="已收藏活动",
                price_amount=Decimal("20"),
                price_currency="CNY",
                route_duration_seconds=10 * 60,
                route_distance_meters=800,
            ),
        )
    )
    event_facts = PlanDraftFactSnapshot(
        candidates=(
            DraftCandidateFacts(
                collection_item_ids=(event_id,),
                visit_duration_seconds=60 * 60,
                event_start_at=START + timedelta(minutes=20),
                event_end_at=START + timedelta(hours=2),
            ),
        ),
        routes=(
            DraftRouteFacts(
                to_collection_item_ids=(event_id,),
                duration_seconds=10 * 60,
                distance_meters=800,
                transport_mode=TransportMode.WALKING,
            ),
        ),
    )
    calls: list[object] = []
    result = await _generate(
        _service(_provider(calls)),
        constraints=_constraints(origin=CORE_COORDINATE),
        collections=event_collections,
        facts=event_facts,
        gap=_place_gap(),
    )

    assert result.recovery_code is ExternalRecoveryCode.ROUTE_FACTS_MISSING
    assert [type(call) for call in calls] == [SearchPoiRequest]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["wrong_city", "duplicate"])
async def test_invalid_provider_candidates_are_rejected_without_route(
    invalid_kind: str,
) -> None:
    class InvalidSearchProvider(StubMapProvider):
        async def search_poi(self, request: SearchPoiRequest) -> PoiSearchResult:
            pois = (
                (
                    EXTERNAL_POI.model_copy(
                        update={"city_code": "guangzhou"},
                        deep=True,
                    ),
                )
                if invalid_kind == "wrong_city"
                else (EXTERNAL_POI, EXTERNAL_POI)
            )
            return PoiSearchResult.model_construct(city_code="shenzhen", pois=pois)

    result = await _generate(_service(InvalidSearchProvider()), gap=_place_gap())
    assert result.recovery_code is ExternalRecoveryCode.MAP_INVALID_RESPONSE


@pytest.mark.asyncio
async def test_out_of_scope_and_existing_poi_candidates_do_not_enter_the_draft() -> None:
    calls: list[object] = []
    outside = EXTERNAL_POI.model_copy(
        update={"district": "南山区"},
        deep=True,
    )
    out_of_scope = await _generate(
        _service(_provider(calls, pois=(outside,))),
        gap=_place_gap(),
    )

    same_poi = CORE_POI.model_copy(
        update={"name": "重复核心地点"},
        deep=True,
    )
    duplicate_calls: list[object] = []
    duplicate = await _generate(
        _service(
            StubMapProvider(
                search_results={
                    _search_request("重复核心地点"): PoiSearchResult(
                        city_code="shenzhen",
                        pois=(same_poi,),
                    )
                },
                call_hook=lambda request: _record(duplicate_calls, request),
            )
        ),
        gap=_place_gap("重复核心地点"),
    )

    assert out_of_scope.recovery_code is ExternalRecoveryCode.PLACE_NOT_FOUND
    assert duplicate.recovery_code is ExternalRecoveryCode.PLACE_NOT_FOUND
    assert [type(call) for call in calls] == [SearchPoiRequest]
    assert [type(call) for call in duplicate_calls] == [SearchPoiRequest]


async def _record(calls: list[object], request: object) -> None:
    calls.append(request)


@pytest.mark.asyncio
async def test_route_failure_and_route_cancellation_do_not_leave_a_partial_draft() -> None:
    class RouteFailureProvider(StubMapProvider):
        async def route(self, request: RouteRequest) -> RouteResult:
            raise MapProviderError(code=MapProviderErrorCode.TIMEOUT)

    failing = RouteFailureProvider(
        search_results={
            _search_request(): PoiSearchResult(
                city_code="shenzhen",
                pois=(EXTERNAL_POI,),
            )
        }
    )
    failed = await _generate(_service(failing), gap=_place_gap())

    class RouteCancelledProvider(StubMapProvider):
        async def route(self, request: RouteRequest) -> RouteResult:
            raise asyncio.CancelledError

    cancelled = RouteCancelledProvider(
        search_results={
            _search_request(): PoiSearchResult(
                city_code="shenzhen",
                pois=(EXTERNAL_POI,),
            )
        }
    )
    with pytest.raises(asyncio.CancelledError):
        await _generate(_service(cancelled), gap=_place_gap())

    assert failed.recovery_code is ExternalRecoveryCode.MAP_TIMEOUT
    assert failed.draft is not None
    assert all(
        item.source.kind is PlanItemSourceKind.COLLECTION_DERIVED
        for option in failed.draft.options
        for item in option.items
    )


def test_external_contract_rejects_price_payload_and_source_spoofing() -> None:
    with pytest.raises(ValidationError):
        RequiredPlanGap.model_validate(
            {
                **_place_gap().model_dump(),
                "price_amount": "20",
            }
        )

    candidate_payload = _place_candidate().model_dump()
    missing_without_price = tuple(
        field
        for field in candidate_payload["missing_fields"]
        if field != CandidateField.PRICE
    )
    for amount, currency in (
        (Decimal("20"), None),
        (None, "CNY"),
        (Decimal("20"), "USD"),
    ):
        with pytest.raises(ValidationError):
            PlaceCandidate.model_validate(
                {
                    **candidate_payload,
                    "price_amount": amount,
                    "price_currency": currency,
                    "missing_fields": missing_without_price,
                }
            )

    result = PlanDraftService().generate(
        constraints=_constraints(),
        collections=_collections(),
        facts=_facts(),
    )
    source = result.options[0].items[0].source
    with pytest.raises(ValidationError):
        source.model_copy(
            update={
                "kind": PlanItemSourceKind.EXTERNAL_PLACE,
                "source_label": "高德补充 · 未收藏",
                "supplement_reason": "spoof",
            }
        ).__class__.model_validate(
            {
                **source.model_dump(),
                "kind": PlanItemSourceKind.EXTERNAL_PLACE,
                "source_label": "高德补充 · 未收藏",
                "supplement_reason": "spoof",
            }
        )


@pytest.mark.asyncio
async def test_cancelled_search_is_not_swallowed() -> None:
    class CancelledSearchProvider(StubMapProvider):
        async def search_poi(self, request: SearchPoiRequest) -> PoiSearchResult:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _generate(_service(CancelledSearchProvider()), gap=_place_gap())


@pytest.mark.asyncio
async def test_inputs_are_unchanged_and_repeated_approved_calls_are_deterministic() -> None:
    calls: list[object] = []
    provider = _provider(calls)
    constraints = _constraints()
    collections = _collections()
    facts = _facts()
    gap = _place_gap()
    before = copy.deepcopy((constraints, collections, facts, gap))

    first = await _generate(
        _service(provider),
        constraints=constraints,
        collections=collections,
        facts=facts,
        gap=gap,
        decision=_approval(gap, ExternalApprovalDecision.APPROVED),
    )
    second = await _generate(
        _service(provider),
        constraints=constraints,
        collections=collections,
        facts=facts,
        gap=gap,
        decision=_approval(gap, ExternalApprovalDecision.APPROVED),
    )

    assert first == second
    assert (constraints, collections, facts, gap) == before
    assert sum(isinstance(call, SearchPoiRequest) for call in calls) == 2
    assert sum(isinstance(call, RouteRequest) for call in calls) == 2


@pytest.mark.asyncio
async def test_structured_retrieval_output_flows_into_approval_boundary() -> None:
    class EmptyReadOnlyRepository:
        async def list_collection_items(
            self,
            *,
            user_id: str,
            include_inactive: bool = False,
        ) -> list[object]:
            return []

    calls: list[object] = []
    provider = _provider(calls)
    matching = PlaceMatchingService(
        map_provider=provider,
        policy=PlaceMatchingPolicy(
            unique_match_score=30,
            minimum_score_gap=5,
            candidate_score=20,
        ),
    )
    retrieved = await StructuredCollectionRetrievalService(
        repository=EmptyReadOnlyRepository(),  # type: ignore[arg-type]
        place_matching=matching,
    ).retrieve(
        user_id="usr_00000000000000000000000000000001",
        constraints=_constraints(),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )
    result = await _generate(
        ExternalPlaceSupplementService(
            map_provider=provider,
            place_matching=matching,
            plan_drafts=PlanDraftService(),
        ),
        collections=retrieved,
        facts=PlanDraftFactSnapshot(),
        gap=_place_gap(),
    )

    assert retrieved == StructuredCollectionResult()
    assert result.outcome is ExternalSupplementOutcome.WAITING_APPROVAL
    assert calls == []

"""Offline rules for the sole external Place supplement boundary."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.application import ExternalPlaceSupplementService, PlaceMatchingService
from app.domain.collections import CandidateField, CollectionKind, PlaceCandidate, PlanCity
from app.domain.places import (
    Coordinate,
    CoordinateSystem,
    PlaceMatchingPolicy,
    Poi,
    PoiProvider,
    PoiSearchResult,
    PoiType,
    SearchPoiRequest,
)
from app.domain.plans import ActivityArea, PlanConstraints
from app.domain.plans.retrieval import (
    CandidateOutcome,
    CollectionCandidateDecision,
    StructuredCollectionResult,
)
from app.domain.plans.supplement import (
    ExternalApprovalDecision,
    ExternalPlaceApprovalDecision,
    ExternalPlaceApprovalRequirement,
    ExternalSupplementOutcome,
    RequiredGapKind,
    RequiredPlanGap,
)
from app.providers import StubMapProvider

NOW = datetime(2026, 8, 11, tzinfo=UTC)
POI = Poi(
    provider=PoiProvider.AMAP,
    poi_id="external-cafe",
    name="明确咖啡店",
    city_code="shenzhen",
    district="福田区",
    address="福中路 2 号",
    coordinate=Coordinate(
        latitude=22.54,
        longitude=114.05,
        coordinate_system=CoordinateSystem.GCJ_02,
    ),
    poi_type=PoiType.CAFE,
)


def _constraints(
    *,
    collection_only: bool = False,
    include: tuple[str, ...] = (),
) -> PlanConstraints:
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=NOW + timedelta(days=1),
        end_at=NOW + timedelta(days=1, hours=4),
        area=ActivityArea(districts=("福田区",)),
        collection_only=collection_only,
        include=include,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _gap(kind: RequiredGapKind = RequiredGapKind.PLACE) -> RequiredPlanGap:
    return RequiredPlanGap(
        kind=kind,
        place_candidate=(
            PlaceCandidate(title=POI.name, missing_fields=(CandidateField.ADDRESS,))
            if kind is RequiredGapKind.PLACE
            else None
        ),
        supplement_reason="明确缺少咖啡环节",
        visit_duration_seconds=1,
    )


def _service(calls: list[object]) -> ExternalPlaceSupplementService:
    request = SearchPoiRequest(
        query=POI.name,
        city=_constraints().city_scope,
        district="福田区",
    )

    async def record(value: object) -> None:
        calls.append(value)

    provider = StubMapProvider(
        search_results={request: PoiSearchResult(city_code="shenzhen", pois=(POI,))},
        call_hook=record,
    )
    return ExternalPlaceSupplementService(
        place_matching=PlaceMatchingService(
            map_provider=provider,
            policy=PlaceMatchingPolicy(
                unique_match_score=30,
                minimum_score_gap=5,
                candidate_score=20,
            ),
        )
    )


@pytest.mark.asyncio
async def test_collection_only_and_event_gaps_never_search() -> None:
    calls: list[object] = []
    service = _service(calls)
    collection_only = await service.generate(
        constraints=_constraints(collection_only=True),
        collections=StructuredCollectionResult(),
        required_gap=_gap(),
        approval_decision=None,
        queried_at=NOW,
    )
    event = await service.generate(
        constraints=_constraints(),
        collections=StructuredCollectionResult(),
        required_gap=_gap(RequiredGapKind.EVENT),
        approval_decision=None,
        queried_at=NOW,
    )
    assert collection_only.outcome is ExternalSupplementOutcome.RECOVERY_REQUIRED
    assert event.outcome is ExternalSupplementOutcome.RECOVERY_REQUIRED
    assert calls == []


@pytest.mark.asyncio
async def test_no_collection_core_requires_approval_before_search() -> None:
    calls: list[object] = []
    result = await _service(calls).generate(
        constraints=_constraints(),
        collections=StructuredCollectionResult(),
        required_gap=_gap(),
        approval_decision=None,
        queried_at=NOW,
    )
    assert result.outcome is ExternalSupplementOutcome.WAITING_APPROVAL
    assert calls == []


@pytest.mark.asyncio
async def test_collection_core_allows_one_read_only_search_and_returns_uncollected_candidate() -> (
    None
):
    calls: list[object] = []
    core = POI.model_copy(update={"poi_id": "saved-core", "name": "收藏展馆"})
    collections = StructuredCollectionResult(
        decisions=(
            CollectionCandidateDecision(
                outcome=CandidateOutcome.INCLUDED,
                collection_item_ids=("col_00000000000000000000000000000001",),
                kind=CollectionKind.PLACE,
                title=core.name,
                poi=core,
                price_amount=Decimal("0"),
                price_currency="CNY",
            ),
        )
    )
    result = await _service(calls).generate(
        constraints=_constraints(),
        collections=collections,
        required_gap=_gap(),
        approval_decision=None,
        queried_at=NOW,
    )
    assert result.outcome is ExternalSupplementOutcome.CANDIDATE
    assert result.candidate is not None
    assert result.candidate.poi == POI
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_external_place_does_not_have_to_match_every_plan_include_goal() -> None:
    calls: list[object] = []
    result = await _service(calls).generate(
        constraints=_constraints(include=("看展", "逛公园", "喝咖啡")),
        collections=StructuredCollectionResult(),
        required_gap=_gap(),
        approval_decision=ExternalPlaceApprovalDecision(
            approval_id=ExternalPlaceApprovalRequirement.for_gap(_gap()).approval_id,
            decision=ExternalApprovalDecision.APPROVED,
        ),
        queried_at=NOW,
    )

    assert result.outcome is ExternalSupplementOutcome.CANDIDATE
    assert result.candidate is not None
    assert result.candidate.poi == POI
    assert len(calls) == 1

"""Model-proposal scheduling tests for the sole deterministic draft service."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.application import PlanDraftService
from app.domain.collections import CollectionKind, PlanCity
from app.domain.places import (
    Coordinate,
    CoordinateSystem,
    Poi,
    PoiProvider,
    PoiType,
    TransportMode,
)
from app.domain.plans import ActivityArea, PlanConstraints
from app.domain.plans.drafts import (
    DraftCandidateFacts,
    DraftRouteFacts,
    ExternalDraftCandidate,
    PlanDraftFactSnapshot,
    PlanDraftOutcome,
    PlanOptionProposal,
    PlanOptionRole,
    PlanProposalItem,
    PlanProposalSet,
    PlanRiskCode,
    PlanRouteLeg,
)
from app.domain.plans.retrieval import (
    CandidateOutcome,
    CollectionCandidateDecision,
    StructuredCollectionResult,
)

NOW = datetime(2026, 8, 11, tzinfo=UTC)
START = NOW + timedelta(days=1)


def _id(index: int) -> str:
    return f"col_{index:032x}"


def _decision(index: int, *, kind: CollectionKind = CollectionKind.PLACE):
    poi = Poi(
        provider=PoiProvider.AMAP,
        poi_id=f"poi-{index}",
        name=f"地点 {index}",
        city_code="shenzhen",
        district="福田区",
        address=f"福中路 {index} 号",
        coordinate=Coordinate(
            latitude=22.54 + index / 1000,
            longitude=114.05,
            coordinate_system=CoordinateSystem.GCJ_02,
        ),
        poi_type=PoiType.MUSEUM,
    )
    return CollectionCandidateDecision(
        outcome=CandidateOutcome.INCLUDED,
        collection_item_ids=(_id(index),),
        kind=kind,
        title=poi.name,
        poi=poi if kind is CollectionKind.PLACE else None,
        price_amount=Decimal("10"),
        price_currency="CNY",
        route_duration_seconds=600,
        route_distance_meters=800,
    )


def _constraints(*, origin: bool = True, minutes: int = 360) -> PlanConstraints:
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=START,
        end_at=START + timedelta(minutes=minutes),
        area=ActivityArea(districts=("福田区",)),
        origin=(
            Coordinate(
                latitude=22.54,
                longitude=114.05,
                coordinate_system=CoordinateSystem.GCJ_02,
            )
            if origin
            else None
        ),
        transport_modes=(TransportMode.TRANSIT,),
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _facts(decisions, *, origin: bool = True, event_window=None, omit_edge=None):
    candidates = tuple(
        DraftCandidateFacts(
            collection_item_ids=decision.collection_item_ids,
            event_start_at=None if event_window is None else event_window[0],
            event_end_at=None if event_window is None else event_window[1],
        )
        for decision in decisions
    )
    routes = []
    if origin:
        routes.extend(
            DraftRouteFacts(
                to_collection_item_ids=decision.collection_item_ids,
                duration_seconds=600,
                distance_meters=800,
                transport_mode=TransportMode.TRANSIT,
            )
            for decision in decisions
        )
    for left in decisions:
        for right in decisions:
            edge = (left.collection_item_ids, right.collection_item_ids)
            if left is right or edge == omit_edge:
                continue
            routes.append(
                DraftRouteFacts(
                    from_collection_item_ids=edge[0],
                    to_collection_item_ids=edge[1],
                    duration_seconds=600,
                    distance_meters=800,
                    transport_mode=TransportMode.TRANSIT,
                )
            )
    return PlanDraftFactSnapshot(candidates=candidates, routes=tuple(routes))


def _proposals(options):
    return PlanProposalSet(
        options=tuple(
            PlanOptionProposal(
                role=PlanOptionRole.MAIN if index == 0 else PlanOptionRole.ALTERNATIVE,
                items=tuple(
                    PlanProposalItem(candidate_key=key, visit_duration_seconds=duration)
                    for key, duration in items
                ),
                reason=f"proposal {index}",
            )
            for index, items in enumerate(options)
        )
    )


def _generate(decisions, proposals, *, facts=None, constraints=None):
    keys = {
        f"candidate_{index}": decision.collection_item_ids
        for index, decision in enumerate(decisions)
    }
    return PlanDraftService().generate(
        constraints=constraints or _constraints(),
        collections=StructuredCollectionResult(decisions=tuple(decisions)),
        facts=facts or _facts(decisions),
        proposals=proposals,
        candidate_keys=keys,
    )


def test_model_order_and_durations_schedule_more_than_two_places() -> None:
    decisions = tuple(_decision(index) for index in range(1, 4))
    proposals = _proposals(
        (
            (("candidate_2", 1800), ("candidate_0", 2700), ("candidate_1", 3600)),
            (("candidate_0", 2400),),
            (("candidate_1", 3000),),
        )
    )
    draft = _generate(decisions, proposals)
    assert [item.source.collection_item_ids for item in draft.options[0].items] == [
        decisions[2].collection_item_ids,
        decisions[0].collection_item_ids,
        decisions[1].collection_item_ids,
    ]
    assert [item.visit_duration_seconds for item in draft.options[0].items] == [
        1800,
        2700,
        3600,
    ]


def test_missing_origin_keeps_first_leg_unknown_not_zero() -> None:
    decisions = (_decision(1),)
    proposals = _proposals(
        (
            (("candidate_0", 1800),),
            (("candidate_0", 2400),),
            (("candidate_0", 3000),),
        )
    )
    draft = _generate(
        decisions,
        proposals,
        facts=_facts(decisions, origin=False),
        constraints=_constraints(origin=False),
    )
    leg = draft.options[0].items[0].inbound_route
    assert leg.duration_seconds is None and leg.distance_meters is None
    assert PlanRiskCode.ROUTE_UNKNOWN in draft.options[0].items[0].risk_codes


def test_invalid_proposal_is_dropped_without_replacing_its_missing_edge() -> None:
    decisions = (_decision(1), _decision(2))
    missing = (decisions[0].collection_item_ids, decisions[1].collection_item_ids)
    proposals = _proposals(
        (
            (("candidate_0", 1800), ("candidate_1", 1800)),
            (("candidate_0", 2400),),
            (("candidate_1", 3000),),
        )
    )
    draft = _generate(decisions, proposals, facts=_facts(decisions, omit_edge=missing))
    assert draft.outcome is PlanDraftOutcome.GENERATED
    assert [len(option.items) for option in draft.options] == [1, 1]
    assert all(option.role is PlanOptionRole.ALTERNATIVE for option in draft.options)


def test_event_window_remains_a_hard_constraint() -> None:
    decisions = (_decision(1, kind=CollectionKind.EVENT),)
    proposals = _proposals(
        (
            (("candidate_0", 3600),),
            (("candidate_0", 4200),),
            (("candidate_0", 4800),),
        )
    )
    facts = _facts(
        decisions,
        event_window=(START + timedelta(minutes=30), START + timedelta(minutes=60)),
    )
    draft = _generate(decisions, proposals, facts=facts)
    assert draft.outcome is PlanDraftOutcome.NOT_GENERATED


def test_external_candidate_keeps_uncollected_source_label() -> None:
    decisions = (_decision(1),)
    external_poi = _decision(2).poi
    assert external_poi is not None
    proposals = _proposals(
        (
            (("candidate_0", 1800), ("external_0", 2400)),
            (("candidate_0", 2700),),
            (("candidate_0", 3000),),
        )
    )
    keys = {"candidate_0": decisions[0].collection_item_ids}
    draft = PlanDraftService().generate(
        constraints=_constraints(),
        collections=StructuredCollectionResult(decisions=decisions),
        facts=_facts(decisions),
        proposals=proposals,
        candidate_keys=keys,
        external_candidates={
            "external_0": ExternalDraftCandidate(
                poi=external_poi,
                queried_at=NOW,
                supplement_reason="明确缺少咖啡环节",
                visit_duration_seconds=2400,
                inbound_route=PlanRouteLeg(
                    from_collection_item_ids=decisions[0].collection_item_ids,
                    to_external_provider=external_poi.provider,
                    to_external_poi_id=external_poi.poi_id,
                    duration_seconds=600,
                    distance_meters=800,
                    transport_mode=TransportMode.TRANSIT,
                ),
                price_amount=Decimal("10"),
                price_currency="CNY",
            )
        },
    )
    source = draft.options[0].items[1].source
    assert source.source_label == "高德补充 · 未收藏"
    assert source.collection_item_ids == ()

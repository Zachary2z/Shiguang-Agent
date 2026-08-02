"""Deterministic, fully offline M0-5C plan draft tests."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

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
from app.domain.plans import ActivityArea, PlanConstraints, PlanPace, WeatherAssessment
from app.domain.plans.drafts import (
    DraftCandidateFacts,
    DraftRouteFacts,
    PlanDraftFactSnapshot,
    PlanDraftFailureCode,
    PlanDraftOutcome,
    PlanDraftViolationCode,
    PlanItemSourceKind,
    PlanRiskCode,
)
from app.domain.plans.retrieval import (
    REASON_SUMMARIES,
    CandidateOutcome,
    CandidateReasonCode,
    CollectionCandidateDecision,
    StructuredCollectionResult,
)
from tests.fixtures.plans import PLAN_FIXTURE_SPECS, PlanFixtureSpec

NOW = datetime(2026, 7, 23, 6, 0, tzinfo=UTC)
START = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
QUERY_TIME = datetime(2026, 7, 23, 7, 0, tzinfo=UTC)
COORDINATE = Coordinate(
    latitude=22.541174,
    longitude=114.057701,
    coordinate_system=CoordinateSystem.GCJ_02,
)


def _id(index: int) -> str:
    return f"col_{index:032x}"


def _poi(index: int) -> Poi:
    return Poi(
        provider=PoiProvider.AMAP,
        poi_id=f"poi-{index:03d}",
        name=f"地点 {index:03d}",
        city_code="shenzhen",
        district="福田区",
        address=f"福中路 {index} 号",
        coordinate=COORDINATE,
        poi_type=PoiType.MUSEUM,
    )


def _decision(
    index: int,
    *,
    title: str | None = None,
    price: Decimal | None = Decimal("30"),
    route_minutes: int = 10,
    kind: CollectionKind = CollectionKind.PLACE,
    collection_ids: tuple[str, ...] | None = None,
    branch_ids: tuple[str, ...] = (),
    poi: Poi | None = None,
    preference_score: int = 0,
    applied_memory_ids: tuple[str, ...] = (),
) -> CollectionCandidateDecision:
    ids = collection_ids or (_id(index),)
    return CollectionCandidateDecision(
        outcome=CandidateOutcome.INCLUDED,
        collection_item_ids=ids,
        kind=kind,
        title=title or f"地点 {index:03d}",
        poi=(_poi(index) if poi is None and kind is CollectionKind.PLACE else poi),
        price_amount=price,
        price_currency=None if price is None else "CNY",
        route_duration_seconds=route_minutes * 60,
        route_distance_meters=route_minutes * 80,
        any_branch_collection_item_ids=branch_ids,
        preference_score=preference_score,
        applied_memory_ids=applied_memory_ids,
    )


def _excluded(index: int) -> CollectionCandidateDecision:
    code = CandidateReasonCode.STATUS_NOT_ACTIVE
    return CollectionCandidateDecision(
        outcome=CandidateOutcome.EXCLUDED,
        reason_codes=(code,),
        summaries=(REASON_SUMMARIES[code],),
        collection_item_ids=(_id(index),),
        kind=CollectionKind.PLACE,
        title=f"排除地点 {index}",
        poi=_poi(index),
        price_amount=Decimal("10"),
        price_currency="CNY",
    )


def _constraints(
    *,
    minutes: int = 300,
    budget: Decimal | None = None,
    pace: PlanPace = PlanPace.BALANCED,
) -> PlanConstraints:
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=START,
        end_at=START + timedelta(minutes=minutes),
        area=ActivityArea(districts=("福田区",)),
        budget=budget,
        pace=pace,
        transport_modes=(TransportMode.TRANSIT,),
        created_at=NOW,
        expires_at=START,
    )


def _facts(
    decisions: tuple[CollectionCandidateDecision, ...],
    *,
    visit_minutes: int = 60,
    route_minutes: int = 10,
    inter_route_minutes: int = 10,
    event_windows: dict[tuple[str, ...], tuple[datetime, datetime]] | None = None,
) -> PlanDraftFactSnapshot:
    included = tuple(item for item in decisions if item.outcome is CandidateOutcome.INCLUDED)
    candidate_facts = []
    routes = []
    for decision in included:
        event_window = (event_windows or {}).get(decision.collection_item_ids)
        candidate_facts.append(
            DraftCandidateFacts(
                collection_item_ids=decision.collection_item_ids,
                visit_duration_seconds=visit_minutes * 60,
                event_start_at=None if event_window is None else event_window[0],
                event_end_at=None if event_window is None else event_window[1],
                poi_queried_at=(QUERY_TIME if decision.any_branch_collection_item_ids else None),
            )
        )
        duration = (
            decision.route_duration_seconds
            if decision.route_duration_seconds is not None
            else route_minutes * 60
        )
        routes.append(
            DraftRouteFacts(
                to_collection_item_ids=decision.collection_item_ids,
                duration_seconds=duration,
                distance_meters=(
                    decision.route_distance_meters
                    if decision.route_distance_meters is not None
                    else duration
                ),
                transport_mode=TransportMode.TRANSIT,
            )
        )
    for source in included:
        for target in included:
            if source.collection_item_ids == target.collection_item_ids:
                continue
            routes.append(
                DraftRouteFacts(
                    from_collection_item_ids=source.collection_item_ids,
                    to_collection_item_ids=target.collection_item_ids,
                    duration_seconds=inter_route_minutes * 60,
                    distance_meters=inter_route_minutes * 80,
                    transport_mode=TransportMode.TRANSIT,
                )
            )
    return PlanDraftFactSnapshot(candidates=tuple(candidate_facts), routes=tuple(routes))


def _generate(
    decisions: tuple[CollectionCandidateDecision, ...],
    *,
    constraints: PlanConstraints | None = None,
    facts: PlanDraftFactSnapshot | None = None,
):
    result = StructuredCollectionResult(decisions=decisions)
    active_constraints = constraints or _constraints()
    active_facts = facts or _facts(decisions)
    draft = PlanDraftService().generate(
        constraints=active_constraints,
        collections=result,
        facts=active_facts,
    )
    return draft, result, active_constraints, active_facts


def test_no_included_candidate_returns_stable_failure() -> None:
    draft, _, _, _ = _generate((_excluded(1),), facts=PlanDraftFactSnapshot())
    assert draft.outcome is PlanDraftOutcome.NOT_GENERATED
    assert draft.failure_code is PlanDraftFailureCode.NO_INCLUDED_CANDIDATES
    assert draft.exclusions[0].reason_codes == (CandidateReasonCode.STATUS_NOT_ACTIVE,)


def test_single_candidate_generates_one_single_location_main_option() -> None:
    draft, _, constraints, _ = _generate((_decision(1),))
    assert draft.outcome is PlanDraftOutcome.GENERATED
    assert len(draft.options) == 1
    assert draft.options[0].role.value == "main"
    assert len(draft.options[0].items) == 1
    assert draft.options[0].items[0].end_at < constraints.end_at


def test_many_candidates_generate_one_main_and_at_most_two_alternatives() -> None:
    decisions = tuple(_decision(index, route_minutes=10 + index) for index in range(1, 6))
    draft, _, _, _ = _generate(decisions, facts=_facts(decisions))
    assert len(draft.options) == 3
    assert [option.role.value for option in draft.options] == [
        "main",
        "alternative",
        "alternative",
    ]
    assert all(len(option.items) <= 2 for option in draft.options)


def test_short_window_does_not_force_an_auxiliary_location() -> None:
    decisions = (_decision(1), _decision(2))
    constraints = _constraints(minutes=95, pace=PlanPace.PACKED)
    draft, _, _, _ = _generate(decisions, constraints=constraints, facts=_facts(decisions))
    assert draft.outcome is PlanDraftOutcome.GENERATED
    assert all(len(option.items) == 1 for option in draft.options)


@pytest.mark.parametrize(
    ("pace", "switch_seconds", "end_seconds"),
    [
        (PlanPace.PACKED, 600, 900),
        (PlanPace.BALANCED, 900, 1200),
        (PlanPace.RELAXED, 1200, 1800),
    ],
)
def test_switch_and_end_buffers_cover_minimum_maximum_and_equal_boundaries(
    pace: PlanPace,
    switch_seconds: int,
    end_seconds: int,
) -> None:
    decisions = (_decision(1), _decision(2))
    draft, _, _, _ = _generate(
        decisions,
        constraints=_constraints(minutes=300, pace=pace),
        facts=_facts(decisions),
    )
    option = draft.options[0]
    assert len(option.items) == 2
    assert option.switch_buffer_seconds == switch_seconds
    assert option.end_buffer_seconds == end_seconds


def test_event_route_arrival_equal_to_start_is_allowed_and_end_boundary_is_enforced() -> None:
    event = _decision(1, kind=CollectionKind.EVENT, poi=None, route_minutes=30)
    window = (START + timedelta(minutes=30), START + timedelta(minutes=90))
    facts = _facts((event,), visit_minutes=60, event_windows={event.collection_item_ids: window})
    draft, _, _, _ = _generate((event,), constraints=_constraints(minutes=120), facts=facts)
    assert draft.outcome is PlanDraftOutcome.GENERATED
    assert draft.options[0].items[0].start_at == window[0]
    assert draft.options[0].items[0].end_at == window[1]

    too_late = event.model_copy(update={"route_duration_seconds": 90 * 60})
    late_facts = _facts(
        (too_late,),
        visit_minutes=1,
        event_windows={too_late.collection_item_ids: window},
    )
    late, _, _, _ = _generate((too_late,), constraints=_constraints(minutes=120), facts=late_facts)
    assert late.failure_code is PlanDraftFailureCode.NO_EXECUTABLE_OPTION


def test_budget_none_allows_generation_and_known_total_is_explainable() -> None:
    decisions = (_decision(1, price=Decimal("45")), _decision(2, price=Decimal("35")))
    draft, _, _, _ = _generate(decisions, constraints=_constraints(budget=None))
    assert draft.options[0].total_cost_amount == Decimal("80")
    assert draft.options[0].total_cost_currency == "CNY"


def test_known_budget_rejects_over_budget_combination_but_keeps_legal_single_option() -> None:
    decisions = (_decision(1, price=Decimal("60")), _decision(2, price=Decimal("50")))
    draft, _, _, _ = _generate(decisions, constraints=_constraints(budget=Decimal("100")))
    assert draft.outcome is PlanDraftOutcome.GENERATED
    assert all(len(option.items) == 1 for option in draft.options)
    assert all(option.total_cost_amount <= Decimal("100") for option in draft.options)


def test_unknown_price_is_never_rewritten_as_zero() -> None:
    decision = _decision(1, price=None)
    draft, collections, constraints, facts = _generate(
        (decision,),
        constraints=_constraints(budget=None),
    )
    item = draft.options[0].items[0]
    assert item.price_amount is None
    assert draft.options[0].total_cost_amount is None
    assert item.risk_codes == (PlanRiskCode.PRICE_UNKNOWN,)

    tampered_item = item.model_copy(update={"risk_codes": (), "risks": ()})
    tampered_option = draft.options[0].model_copy(update={"items": (tampered_item,)})
    tampered = draft.model_copy(update={"options": (tampered_option,)})
    validation = PlanDraftService().validate(
        draft=tampered,
        constraints=constraints,
        collections=collections,
        facts=facts,
    )
    assert PlanDraftViolationCode.RISK_INVALID in validation.violations


def test_free_price_remains_known_zero_cny() -> None:
    draft, _, _, _ = _generate((_decision(1, price=Decimal("0")),))

    item = draft.options[0].items[0]
    assert item.price_amount == Decimal("0")
    assert item.price_currency == "CNY"
    assert draft.options[0].total_cost_amount == Decimal("0")
    assert draft.options[0].risk_codes == ()


@pytest.mark.parametrize(
    ("status", "risk"),
    [
        (WeatherAssessment.UNKNOWN, PlanRiskCode.WEATHER_UNKNOWN),
        (WeatherAssessment.PROVIDER_FAILED, PlanRiskCode.WEATHER_PROVIDER_FAILED),
    ],
)
def test_weather_unknown_and_failure_are_snapshotted_non_blocking_risks(
    status: WeatherAssessment,
    risk: PlanRiskCode,
) -> None:
    decision = _decision(1)
    facts = _facts((decision,)).model_copy(
        update={
            "weather_status": status,
            "weather_source": "amap",
            "weather_queried_at": QUERY_TIME,
            "weather_summary": "The map provider request timed out.",
        }
    )
    draft, collections, constraints, _ = _generate(
        (decision,),
        facts=facts,
    )

    assert draft.outcome is PlanDraftOutcome.GENERATED
    assert draft.weather_status is status
    assert draft.weather_source == "amap"
    assert draft.weather_queried_at == QUERY_TIME
    assert draft.weather_summary == "The map provider request timed out."
    assert risk in draft.options[0].risk_codes
    assert PlanDraftService().validate(
        draft=draft,
        constraints=constraints,
        collections=collections,
        facts=facts,
    ).is_valid


def test_old_draft_json_without_weather_fields_reads_as_none() -> None:
    draft, _, _, _ = _generate((_decision(1),))
    payload = draft.model_dump(mode="json", exclude_none=True)

    restored = type(draft).model_validate_json(json.dumps(payload))

    assert restored.weather_status is None
    assert restored.weather_source is None
    assert restored.weather_queried_at is None
    assert restored.weather_summary is None


def test_area_only_plan_keeps_first_route_unknown_without_zero_facts() -> None:
    decision = _decision(1).model_copy(
        update={"route_duration_seconds": None, "route_distance_meters": None}
    )
    facts = PlanDraftFactSnapshot(
        candidates=(
            DraftCandidateFacts(
                collection_item_ids=decision.collection_item_ids,
                visit_duration_seconds=3600,
            ),
        ),
    )
    draft, collections, constraints, _ = _generate((decision,), facts=facts)

    item = draft.options[0].items[0]
    assert draft.outcome is PlanDraftOutcome.GENERATED
    assert item.inbound_route.duration_seconds is None
    assert item.inbound_route.distance_meters is None
    assert PlanRiskCode.ROUTE_UNKNOWN in item.risk_codes
    assert PlanDraftService().validate(
        draft=draft,
        constraints=constraints,
        collections=collections,
        facts=facts,
    ).is_valid


@pytest.mark.parametrize(
    ("price_amount", "price_currency"),
    [(None, "CNY"), (Decimal("35"), None), (Decimal("35"), "USD")],
)
def test_retrieval_decisions_and_plan_items_reject_noncanonical_price_pairs(
    price_amount: Decimal | None,
    price_currency: str | None,
) -> None:
    decision_payload = _decision(1).model_dump(mode="python")
    decision_payload.update(
        price_amount=price_amount,
        price_currency=price_currency,
    )
    with pytest.raises(ValidationError):
        CollectionCandidateDecision.model_validate(decision_payload)

    draft, _, _, _ = _generate((_decision(1),))
    item_payload = draft.options[0].items[0].model_dump(mode="python")
    item_payload.update(
        price_amount=price_amount,
        price_currency=price_currency,
    )
    with pytest.raises(ValidationError):
        type(draft.options[0].items[0]).model_validate(item_payload)


def test_excluded_and_verification_required_candidates_never_enter_options() -> None:
    included = _decision(1)
    excluded = _excluded(2)
    verification_code = CandidateReasonCode.AVAILABILITY_UNKNOWN
    verification = CollectionCandidateDecision(
        outcome=CandidateOutcome.VERIFICATION_REQUIRED,
        reason_codes=(verification_code,),
        summaries=(REASON_SUMMARIES[verification_code],),
        collection_item_ids=(_id(3),),
        kind=CollectionKind.PLACE,
        title="待核验地点",
        poi=_poi(3),
    )
    draft, _, _, _ = _generate((verification, excluded, included), facts=_facts((included,)))
    used = {
        source_id
        for option in draft.options
        for item in option.items
        for source_id in item.source.collection_item_ids
    }
    assert used == {_id(1)}
    assert len(draft.exclusions) == 2


def test_any_branch_preserves_concrete_poi_sources_query_time_reason_and_marker() -> None:
    exact_id = _id(1)
    branch_id = _id(2)
    decision = _decision(
        1,
        collection_ids=(exact_id, branch_id),
        branch_ids=(branch_id,),
        poi=_poi(1),
    )
    draft, _, _, _ = _generate((decision,), facts=_facts((decision,)))
    item = draft.options[0].items[0]
    assert item.source.collection_item_ids == (exact_id, branch_id)
    assert item.source.any_branch_collection_item_ids == (branch_id,)
    assert item.source.concrete_poi == decision.poi
    assert item.source.poi_queried_at == QUERY_TIME
    assert item.source.kind is PlanItemSourceKind.COLLECTION_DERIVED
    assert item.selection_reason


def test_exact_and_any_branch_same_poi_remain_one_plan_item() -> None:
    decision = _decision(
        1,
        collection_ids=(_id(1), _id(2)),
        branch_ids=(_id(2),),
        poi=_poi(1),
    )
    draft, _, _, _ = _generate((decision,))
    assert len(draft.options[0].items) == 1
    assert draft.options[0].items[0].source.collection_item_ids == (_id(1), _id(2))


def test_equal_rank_uses_title_poi_and_collection_id_stable_tiebreakers() -> None:
    decisions = (
        _decision(2, title="Beta", route_minutes=10),
        _decision(1, title="Alpha", route_minutes=10),
    )
    draft, _, _, _ = _generate(decisions, facts=_facts(decisions))
    assert draft.options[0].items[0].title == "Alpha"


def test_confirmed_memory_score_precedes_route_and_stable_tiebreakers() -> None:
    decisions = (
        _decision(1, title="较近的普通地点", route_minutes=5),
        _decision(
            2,
            title="已确认偏好地点",
            route_minutes=20,
            preference_score=1,
            applied_memory_ids=("mem_0123456789abcdef0123456789abcdef",),
        ),
    )
    draft, _, _, _ = _generate(decisions, facts=_facts(decisions))
    assert draft.options[0].items[0].title == "已确认偏好地点"


def test_input_objects_are_unchanged_and_repeated_calls_are_identical() -> None:
    decisions = (_decision(1), _decision(2))
    collections = StructuredCollectionResult(decisions=decisions)
    constraints = _constraints()
    facts = _facts(decisions)
    before = copy.deepcopy((constraints, collections, facts))
    service = PlanDraftService()
    first = service.generate(constraints=constraints, collections=collections, facts=facts)
    second = service.generate(constraints=constraints, collections=collections, facts=facts)
    assert (constraints, collections, facts) == before
    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_missing_inter_place_route_degrades_to_single_location() -> None:
    decisions = (_decision(1), _decision(2))
    complete = _facts(decisions)
    origin_only = PlanDraftFactSnapshot(
        candidates=complete.candidates,
        routes=tuple(route for route in complete.routes if not route.from_collection_item_ids),
    )
    draft, _, _, _ = _generate(decisions, facts=origin_only)
    assert all(len(option.items) == 1 for option in draft.options)


def test_missing_visit_or_origin_route_returns_stable_not_generated_result() -> None:
    decision = _decision(1)
    draft, _, _, _ = _generate((decision,), facts=PlanDraftFactSnapshot())
    assert draft.failure_code is PlanDraftFailureCode.NO_EXECUTABLE_OPTION


def test_date_range_event_uses_visit_duration_and_disallowed_route_mode_is_rejected() -> None:
    event = _decision(1, kind=CollectionKind.EVENT, poi=None)
    date_range, _, _, _ = _generate((event,), facts=_facts((event,)))
    assert date_range.outcome is PlanDraftOutcome.GENERATED
    assert date_range.options[0].items[0].start_at == START + timedelta(minutes=10)
    assert date_range.options[0].items[0].end_at == START + timedelta(minutes=70)

    place = _decision(2)
    base_facts = _facts((place,))
    walking_facts = PlanDraftFactSnapshot(
        candidates=base_facts.candidates,
        routes=tuple(
            route.model_copy(update={"transport_mode": TransportMode.WALKING})
            for route in base_facts.routes
        ),
    )
    disallowed, _, _, _ = _generate(
        (place,),
        constraints=_constraints(),
        facts=walking_facts,
    )
    assert disallowed.failure_code is PlanDraftFailureCode.NO_EXECUTABLE_OPTION


def test_tampered_time_and_budget_fail_post_generation_validation() -> None:
    decision = _decision(1, price=Decimal("40"))
    draft, collections, constraints, facts = _generate(
        (decision,),
        constraints=_constraints(budget=Decimal("50")),
    )
    item = draft.options[0].items[0]
    tampered_item = item.model_copy(
        update={
            "end_at": constraints.end_at + timedelta(minutes=1),
            "price_amount": Decimal("80"),
        }
    )
    tampered_option = draft.options[0].model_copy(
        update={"items": (tampered_item,), "total_cost_amount": Decimal("80")}
    )
    tampered = draft.model_copy(update={"options": (tampered_option,)})
    validation = PlanDraftService().validate(
        draft=tampered,
        constraints=constraints,
        collections=collections,
        facts=facts,
    )
    assert not validation.is_valid
    assert PlanDraftViolationCode.TIME_WINDOW_VIOLATED in validation.violations
    assert PlanDraftViolationCode.BUDGET_VIOLATED in validation.violations
    assert PlanDraftViolationCode.FACTS_MISSING_OR_MISMATCHED in validation.violations


@pytest.mark.parametrize("spec", PLAN_FIXTURE_SPECS, ids=lambda spec: spec.name)
def test_twenty_plan_fixtures_have_zero_hard_constraint_violations(
    spec: PlanFixtureSpec,
) -> None:
    decisions = tuple(
        _decision(
            100 + index,
            route_minutes=spec.route_minutes + index,
            price=Decimal("20"),
        )
        for index in range(spec.candidate_count)
    )
    constraints = _constraints(minutes=spec.window_minutes, pace=spec.pace)
    facts = _facts(
        decisions,
        visit_minutes=spec.visit_minutes,
        inter_route_minutes=10,
    )
    draft, collections, _, _ = _generate(
        decisions,
        constraints=constraints,
        facts=facts,
    )
    assert draft.outcome is PlanDraftOutcome.GENERATED
    validation = PlanDraftService().validate(
        draft=draft,
        constraints=constraints,
        collections=collections,
        facts=facts,
    )
    assert validation.is_valid
    assert validation.violations == ()

"""Strict M0-2B candidate and extraction-result contract tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.collections import (
    MAX_EXTRACTION_CANDIDATES,
    CandidateField,
    CollectionKind,
    EventCandidate,
    ExtractionOutcome,
    ExtractionReasonCode,
    ExtractionResult,
    PlaceCandidate,
    Uncertainty,
    UnsupportedReason,
)

START = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def _full_place(**updates: object) -> PlaceCandidate:
    payload: dict[str, object] = {
        "kind": CollectionKind.PLACE,
        "title": "深圳当代艺术与城市规划馆",
        "city_hint": "深圳",
        "district": "福田区",
        "address": "福中路184号",
        "business_district": "市民中心",
        "landmark": "深圳市民中心",
        "metro_station": "市民中心站",
        "price_amount": Decimal("0.00"),
        "price_currency": "CNY",
        "tags": ("室内", "博物馆"),
    }
    payload.update(updates)
    return PlaceCandidate.model_validate(payload)


def _full_event(**updates: object) -> EventCandidate:
    payload: dict[str, object] = {
        "kind": CollectionKind.EVENT,
        "title": "深圳设计周主题展",
        "city_hint": "深圳市",
        "district": "南山区",
        "address": "海上世界文化艺术中心",
        "business_district": "海上世界",
        "landmark": "海上世界文化艺术中心",
        "metro_station": "海上世界站",
        "price_amount": Decimal("68.00"),
        "price_currency": "CNY",
        "tags": ("展览", "室内"),
        "event_start_at": START,
        "event_end_at": START + timedelta(hours=3),
        "event_start_clue": "7月25日14:00",
        "event_end_clue": "7月25日17:00",
    }
    payload.update(updates)
    return EventCandidate.model_validate(payload)


def test_complete_place_candidate_uses_city_hint_without_planning_contract() -> None:
    candidate = _full_place()

    assert candidate.kind is CollectionKind.PLACE
    assert candidate.city_hint == "深圳"
    assert candidate.price_amount == Decimal("0.00")
    assert candidate.missing_fields == ()

    schema = PlaceCandidate.model_json_schema()
    city_schema = schema["properties"]["city_hint"]["anyOf"][0]
    assert city_schema["maxLength"] == 100
    assert "search_scope_city" not in schema["properties"]
    assert "city" not in schema["properties"]


def test_complete_event_candidate_normalizes_aware_times_to_utc() -> None:
    candidate = _full_event()

    assert candidate.kind is CollectionKind.EVENT
    assert candidate.event_start_at == START
    assert candidate.event_end_at == START + timedelta(hours=3)
    assert candidate.event_start_at is not None
    assert candidate.event_start_at.tzinfo is UTC


def test_place_candidate_forbids_event_only_fields_and_metadata() -> None:
    payload = _full_place().model_dump()
    payload["event_start_at"] = START
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PlaceCandidate.model_validate(payload)

    payload = _full_place().model_dump()
    payload["missing_fields"] = (CandidateField.EVENT_START_AT,)
    with pytest.raises(ValidationError, match="place_has_event_metadata"):
        PlaceCandidate.model_validate(payload)


def test_event_rejects_invalid_time_order_and_naive_times() -> None:
    with pytest.raises(ValidationError, match="event_time_order_invalid"):
        _full_event(event_end_at=START)
    with pytest.raises(ValidationError, match="timezone-aware"):
        _full_event(event_start_at=START.replace(tzinfo=None))


def test_missing_fields_and_uncertainties_are_explicit_and_non_overlapping() -> None:
    candidate = PlaceCandidate(
        title="M Stand",
        city_hint=None,
        missing_fields=(
            CandidateField.DISTRICT,
            CandidateField.ADDRESS,
            CandidateField.BUSINESS_DISTRICT,
            CandidateField.LANDMARK,
            CandidateField.METRO_STATION,
            CandidateField.PRICE,
            CandidateField.TAGS,
        ),
        uncertainties=(
            Uncertainty(field=CandidateField.CITY_HINT, reason="输入没有明确城市线索。"),
        ),
    )

    assert candidate.city_hint is None
    assert CandidateField.DISTRICT in candidate.missing_fields
    assert candidate.uncertainties[0].field is CandidateField.CITY_HINT

    payload = candidate.model_dump()
    payload["missing_fields"] = (*candidate.missing_fields, CandidateField.CITY_HINT)
    with pytest.raises(ValidationError, match="missing_and_uncertain_conflict"):
        PlaceCandidate.model_validate(payload)


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_candidate_rejects_empty_and_overlong_titles(title: str) -> None:
    with pytest.raises(ValidationError):
        _full_place(title=title)


@pytest.mark.parametrize(
    "updates",
    [
        {"price_amount": Decimal("-0.01")},
        {"price_amount": True},
        {"price_amount": Decimal("NaN")},
        {"price_amount": Decimal("1.001")},
        {"price_amount": None, "price_currency": "CNY"},
        {"price_amount": Decimal("10.00"), "price_currency": None},
        {"price_amount": Decimal("10.00"), "price_currency": "USD"},
        {"price_currency": "cny"},
        {"price_currency": "CN"},
        {"tags": ("室内", "室内")},
        {"tags": ("室内", "室内 ")},
        {"tags": ("",)},
        {"tags": tuple(f"tag-{index}" for index in range(21))},
    ],
)
def test_candidate_rejects_invalid_price_currency_and_tags(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _full_place(**updates)


def test_candidate_rejects_extra_fields_and_is_immutable() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PlaceCandidate.model_validate({**_full_place().model_dump(), "vendor_id": "raw"})

    candidate = _full_place()
    with pytest.raises(ValidationError, match="frozen"):
        candidate.title = "changed"


def test_city_hint_is_trimmed_bounded_and_not_a_plan_city_enum() -> None:
    assert _full_place(city_hint="  广州市  ").city_hint == "广州市"
    assert _full_place(city_hint="上海").city_hint == "上海"

    with pytest.raises(ValidationError, match="city_hint cannot be blank"):
        _full_place(city_hint="   ")
    with pytest.raises(ValidationError, match="at most 100"):
        _full_place(city_hint="城" * 101)
    with pytest.raises(ValidationError, match="string_type"):
        _full_place(city_hint=1)


def test_absent_city_hint_must_be_missing_or_uncertain_and_present_hint_is_not_missing() -> None:
    payload = _full_place().model_dump()
    payload["city_hint"] = None
    with pytest.raises(ValidationError, match="absent_field_not_classified"):
        PlaceCandidate.model_validate(payload)

    payload = _full_place().model_dump()
    payload["missing_fields"] = (CandidateField.CITY_HINT,)
    with pytest.raises(ValidationError, match="present_field_marked_missing"):
        PlaceCandidate.model_validate(payload)


def test_event_without_exact_times_requires_explicit_gaps() -> None:
    event = _full_event(
        event_start_at=None,
        event_end_at=None,
        event_start_clue="周六下午",
        event_end_clue=None,
        missing_fields=(CandidateField.EVENT_START_AT, CandidateField.EVENT_END_AT),
    )
    assert event.event_start_at is None
    assert event.event_start_clue == "周六下午"

    payload = event.model_dump()
    payload["missing_fields"] = ()
    with pytest.raises(ValidationError, match="event_time_absent_not_classified"):
        EventCandidate.model_validate(payload)


def test_candidate_and_result_repr_hide_extracted_user_text() -> None:
    sensitive_original = "private original wording only for this test"
    candidate = _full_place(title=sensitive_original, address=sensitive_original)
    result = ExtractionResult.with_candidates((candidate,))

    assert sensitive_original not in repr(candidate)
    assert sensitive_original not in str(candidate)
    assert sensitive_original not in repr(result)
    assert sensitive_original not in str(result)


def test_extraction_result_distinguishes_all_four_outcomes() -> None:
    candidate_result = ExtractionResult.with_candidates((_full_place(),))
    insufficient = ExtractionResult.insufficient(
        missing_fields=(CandidateField.TITLE,),
        recovery_suggestions=("请补充具体名称。",),
    )
    unsupported = ExtractionResult.unsupported(
        reason_code=ExtractionReasonCode.INPUT_UNSUPPORTED,
        unsupported_reason=UnsupportedReason.RECIPE,
        recovery_suggestions=("请改发深圳地点。",),
    )
    invalid = ExtractionResult.model_invalid()

    assert candidate_result.outcome is ExtractionOutcome.CANDIDATES
    assert insufficient.outcome is ExtractionOutcome.INSUFFICIENT_INFORMATION
    assert unsupported.outcome is ExtractionOutcome.UNSUPPORTED
    assert invalid.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT
    assert invalid.reason_code is ExtractionReasonCode.MODEL_INVALID_OUTPUT

    with pytest.raises(ValidationError, match="frozen"):
        invalid.outcome = ExtractionOutcome.CANDIDATES


def test_error_outcome_cannot_disguise_itself_as_empty_candidate_success() -> None:
    with pytest.raises(ValidationError, match="candidates_required"):
        ExtractionResult(outcome=ExtractionOutcome.CANDIDATES)
    with pytest.raises(ValidationError, match="candidates_forbidden_for_outcome"):
        ExtractionResult(
            outcome=ExtractionOutcome.UNSUPPORTED,
            candidates=(_full_place(),),
            reason_code=ExtractionReasonCode.INPUT_EMPTY,
        )


def _first_error_type(
    model: type[PlaceCandidate | EventCandidate | ExtractionResult],
    payload: dict[str, object],
) -> str:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload)
    return str(caught.value.errors(include_context=False, include_input=False)[0]["type"])


def test_candidate_semantic_errors_have_stable_value_free_types() -> None:
    payload = _full_place().model_dump()
    payload.update(price_amount=None, price_currency="CNY")
    assert _first_error_type(PlaceCandidate, payload) == "price_pair_incomplete"

    payload = _full_place().model_dump()
    payload["price_currency"] = "USD"
    assert _first_error_type(PlaceCandidate, payload) == "price_currency_unsupported"

    payload = _full_place().model_dump()
    payload["missing_fields"] = (CandidateField.CITY_HINT, CandidateField.CITY_HINT)
    assert _first_error_type(PlaceCandidate, payload) == "duplicate_missing_field"

    uncertainty = Uncertainty(field=CandidateField.CITY_HINT, reason="需要确认。")
    payload = _full_place().model_dump()
    payload["uncertainties"] = (uncertainty, uncertainty)
    assert _first_error_type(PlaceCandidate, payload) == "duplicate_uncertainty_field"

    payload = _full_place().model_dump()
    payload["missing_fields"] = (CandidateField.CITY_HINT,)
    payload["uncertainties"] = (uncertainty,)
    assert _first_error_type(PlaceCandidate, payload) == "missing_and_uncertain_conflict"

    payload = _full_place().model_dump()
    payload["missing_fields"] = (CandidateField.CITY_HINT,)
    assert _first_error_type(PlaceCandidate, payload) == "present_field_marked_missing"

    payload = _full_place().model_dump()
    payload["city_hint"] = None
    assert _first_error_type(PlaceCandidate, payload) == "absent_field_not_classified"

    payload = _full_place().model_dump()
    payload["missing_fields"] = (CandidateField.EVENT_START_AT,)
    assert _first_error_type(PlaceCandidate, payload) == "place_has_event_metadata"

    payload = _full_event().model_dump()
    payload["event_end_at"] = payload["event_start_at"]
    assert _first_error_type(EventCandidate, payload) == "event_time_order_invalid"

    payload = _full_event().model_dump()
    payload["event_start_at"] = None
    assert _first_error_type(EventCandidate, payload) == "event_time_absent_not_classified"


def test_outcome_semantic_errors_have_stable_value_free_types() -> None:
    assert (
        _first_error_type(
            ExtractionResult,
            {"outcome": ExtractionOutcome.CANDIDATES},
        )
        == "candidates_required"
    )
    assert (
        _first_error_type(
            ExtractionResult,
            {
                "outcome": ExtractionOutcome.UNSUPPORTED,
                "candidates": (_full_place(),),
                "reason_code": ExtractionReasonCode.INPUT_EMPTY,
            },
        )
        == "candidates_forbidden_for_outcome"
    )
    assert (
        _first_error_type(
            ExtractionResult,
            {
                "outcome": ExtractionOutcome.INSUFFICIENT_INFORMATION,
                "reason_code": ExtractionReasonCode.INPUT_EMPTY,
                "missing_fields": (CandidateField.TITLE,),
                "recovery_suggestions": ("请补充名称。",),
            },
        )
        == "reason_code_invalid_for_outcome"
    )
    assert (
        _first_error_type(
            ExtractionResult,
            {
                "outcome": ExtractionOutcome.INSUFFICIENT_INFORMATION,
                "reason_code": ExtractionReasonCode.INSUFFICIENT_INFORMATION,
                "unsupported_reason": UnsupportedReason.OTHER,
                "missing_fields": (CandidateField.TITLE,),
                "recovery_suggestions": ("请补充名称。",),
            },
        )
        == "unsupported_reason_invalid"
    )
    assert (
        _first_error_type(
            ExtractionResult,
            {
                "outcome": ExtractionOutcome.INSUFFICIENT_INFORMATION,
                "reason_code": ExtractionReasonCode.INSUFFICIENT_INFORMATION,
                "recovery_suggestions": ("请补充名称。",),
            },
        )
        == "insufficient_fields_required"
    )
    assert (
        _first_error_type(
            ExtractionResult,
            {
                "outcome": ExtractionOutcome.INSUFFICIENT_INFORMATION,
                "reason_code": ExtractionReasonCode.INSUFFICIENT_INFORMATION,
                "missing_fields": (CandidateField.TITLE,),
            },
        )
        == "recovery_suggestions_required"
    )


def test_candidate_count_has_a_hard_upper_bound_without_merging() -> None:
    candidates = tuple(
        _full_place(title=f"深圳地点 {index}") for index in range(MAX_EXTRACTION_CANDIDATES + 1)
    )

    with pytest.raises(ValidationError, match="too_long"):
        ExtractionResult.with_candidates(candidates)

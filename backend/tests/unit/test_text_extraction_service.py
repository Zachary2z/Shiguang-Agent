"""Offline M0-2B extraction orchestration, repair, boundary, and safety tests."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

import app.application.text_extraction as text_extraction_module
from app.application.extraction_output import (
    EXTRACTION_SEMANTIC_RULES,
    _normalize_model_extraction_output,
    build_repair_messages,
    extraction_result_schema,
    parse_extraction_response,
)
from app.application.text_extraction import (
    MAX_MODEL_OUTPUT_CHARS,
    MAX_TEXT_INPUT_CHARS,
    TextExtractionService,
)
from app.domain.collections import (
    CandidateField,
    EventCandidate,
    ExtractionOutcome,
    ExtractionReasonCode,
    ExtractionResult,
    PlaceCandidate,
    UnsupportedReason,
)
from nanobot_core.providers import (
    Message,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    StructuredOutput,
    StructuredOutputMode,
    ToolCall,
    ToolDefinition,
)
from tests.core.fakes import FakeProvider, fake_response

START = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def _full_place(
    *,
    title: str = "深圳当代艺术与城市规划馆",
    city_hint: str | None = "深圳",
) -> PlaceCandidate:
    missing = () if city_hint is not None else (CandidateField.CITY_HINT,)
    return PlaceCandidate(
        title=title,
        city_hint=city_hint,
        district="福田区",
        address="福中路184号",
        business_district="市民中心",
        landmark="深圳市民中心",
        metro_station="市民中心站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("室内", "博物馆"),
        missing_fields=missing,
    )


def _only_name_place(*, title: str = "M Stand") -> PlaceCandidate:
    return PlaceCandidate(
        title=title,
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


def _full_event(
    *,
    title: str = "深圳设计周主题展",
    city_hint: str = "深圳",
) -> EventCandidate:
    return EventCandidate(
        title=title,
        city_hint=city_hint,
        district="南山区",
        address="海上世界文化艺术中心",
        business_district="海上世界",
        landmark="海上世界文化艺术中心",
        metro_station="海上世界站",
        price_amount=Decimal("68.00"),
        price_currency="CNY",
        tags=("展览", "室内"),
        event_start_at=START,
        event_end_at=START + timedelta(hours=3),
        event_start_clue="7月25日14:00",
        event_end_clue="7月25日17:00",
        missing_fields=(
            CandidateField.EVENT_START_DATE,
            CandidateField.EVENT_END_DATE,
        ),
    )


def _event_without_time() -> EventCandidate:
    return EventCandidate(
        title="深圳周末艺术市集",
        city_hint="深圳",
        district="南山区",
        address="海上世界",
        business_district="海上世界",
        landmark="明华轮",
        metro_station="海上世界站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("市集", "周末"),
        event_start_clue="周六下午",
        missing_fields=(
            CandidateField.EVENT_START_DATE,
            CandidateField.EVENT_END_DATE,
            CandidateField.EVENT_START_AT,
            CandidateField.EVENT_END_AT,
        ),
    )


def _date_only_event() -> EventCandidate:
    return EventCandidate(
        title="夏季展览",
        city_hint="深圳",
        district="南山区",
        address="海上世界文化艺术中心",
        business_district="海上世界",
        landmark="海上世界文化艺术中心",
        metro_station="海上世界站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("展览",),
        event_start_date=date(2026, 6, 13),
        event_end_date=date(2026, 7, 31),
        missing_fields=(
            CandidateField.EVENT_START_AT,
            CandidateField.EVENT_END_AT,
        ),
    )


def _result_response(result: ExtractionResult) -> ModelResponse:
    return fake_response(content=result.model_dump_json())


@pytest.mark.asyncio
async def test_date_only_text_extraction_preserves_calendar_dates_without_midnight() -> None:
    response = _result_response(ExtractionResult.with_candidates((_date_only_event(),)))
    provider = FakeProvider(
        [
            response,
            _result_response(ExtractionResult.with_candidates((_date_only_event(),))),
        ]
    )
    service = TextExtractionService(provider)

    first = await service.extract("展期：2026.6.13–7.31")
    second = await service.extract("展期：2026.6.13–7.31")

    assert first == second
    candidate = first.candidates[0]
    assert isinstance(candidate, EventCandidate)
    assert candidate.event_start_date == date(2026, 6, 13)
    assert candidate.event_end_date == date(2026, 7, 31)
    assert candidate.event_start_at is None
    assert candidate.event_end_at is None
    assert "T00:00:00" not in first.model_dump_json()


class _EvidenceCheckingTextProvider(FakeProvider):
    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_format: StructuredOutput | None = None,
    ) -> ModelResponse:
        if self.calls:
            rendered = json.dumps(messages, ensure_ascii=False)
            assert "只修复深圳湾文化广场候选" in rendered
            assert "深圳湾文化广场" in rendered
            assert '"role": "assistant"' in rendered
        return await super().chat(
            messages=messages,
            tools=tools,
            response_format=response_format,
        )


def _recognized_price_without_currency_response(amount: Decimal) -> ModelResponse:
    payload = json.loads(
        ExtractionResult.with_candidates((_full_place(),)).model_dump_json()
    )
    payload["candidates"][0]["price_amount"] = str(amount)
    payload["candidates"][0].pop("price_currency")
    return fake_response(content=json.dumps(payload, ensure_ascii=False))


@pytest.mark.parametrize("amount", [Decimal("50"), Decimal("0")])
@pytest.mark.asyncio
async def test_recognized_local_price_without_currency_defaults_to_cny(
    amount: Decimal,
) -> None:
    response = _recognized_price_without_currency_response(amount)
    provider = FakeProvider([response, response])
    service = TextExtractionService(provider)

    first = await service.extract("人均 50" if amount else "明确免费")
    repeated = await service.extract("人均 50" if amount else "明确免费")

    assert first == repeated
    assert first.candidates[0].price_amount == amount
    assert first.candidates[0].price_currency == "CNY"
    system_prompt = provider.calls[0].messages[0]["content"]
    assert "renminbi only" in system_prompt
    assert 'price_currency "CNY"' in system_prompt
    assert "unrelated numbers" in system_prompt


@pytest.mark.asyncio
async def test_unrelated_number_is_not_inferred_as_price() -> None:
    provider = FakeProvider(
        [_result_response(ExtractionResult.with_candidates((_only_name_place(),)))]
    )

    result = await TextExtractionService(provider).extract("14 号线旁边的 M Stand")

    assert result.candidates[0].price_amount is None
    assert result.candidates[0].price_currency is None
    assert CandidateField.PRICE in result.candidates[0].missing_fields


@pytest.mark.asyncio
async def test_explicit_shenzhen_place_uses_one_provider_call() -> None:
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates((_full_place(),)))])

    result = await TextExtractionService(provider).extract(
        "想去深圳当代艺术与城市规划馆，福田区，免费"
    )

    assert result.outcome is ExtractionOutcome.CANDIDATES
    assert result.candidates == (_full_place(),)
    assert len(provider.calls) == 1
    assert provider.calls[0].tools is None


@pytest.mark.asyncio
async def test_only_store_name_keeps_candidate_with_missing_city_hint() -> None:
    provider = FakeProvider(
        [_result_response(ExtractionResult.with_candidates((_only_name_place(),)))]
    )

    result = await TextExtractionService(provider).extract("M Stand")

    candidate = result.candidates[0]
    assert isinstance(candidate, PlaceCandidate)
    assert candidate.city_hint is None
    assert CandidateField.CITY_HINT in candidate.missing_fields
    assert CandidateField.DISTRICT in candidate.missing_fields
    assert CandidateField.ADDRESS in candidate.missing_fields
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_clear_save_intent_preserves_named_place_for_details_flow() -> None:
    candidate = _only_name_place(title="虾一跳")
    provider = FakeProvider(
        [_result_response(ExtractionResult.with_candidates((candidate,)))]
    )

    result = await TextExtractionService(provider).extract("收藏一下虾一跳")

    assert result.outcome is ExtractionOutcome.CANDIDATES
    assert result.candidates == (candidate,)
    assert CandidateField.TITLE not in result.missing_fields
    system_prompt = provider.calls[0].messages[0]["content"]
    assert "clear named destination" in system_prompt


@pytest.mark.asyncio
async def test_weekend_visit_preference_cannot_turn_a_place_into_event() -> None:
    modeled_as_event = EventCandidate(
        **_candidate_fields_for_temporal_test(title="深圳天文台"),
        event_start_clue="周末",
        missing_fields=(
            CandidateField.EVENT_START_DATE,
            CandidateField.EVENT_END_DATE,
            CandidateField.EVENT_START_AT,
            CandidateField.EVENT_END_AT,
        ),
    )
    provider = FakeProvider(
        [_result_response(ExtractionResult.with_candidates((modeled_as_event,)))]
    )

    result = await TextExtractionService(provider).extract("周末想去深圳天文台")

    candidate = result.candidates[0]
    assert isinstance(candidate, PlaceCandidate)
    assert candidate.title == "深圳天文台"
    assert all(not field.value.startswith("event_") for field in candidate.missing_fields)
    system_prompt = provider.calls[0].messages[0]["content"]
    assert "visit preference" in system_prompt
    assert "visit preference alone is not an Event fact" in system_prompt


def _candidate_fields_for_temporal_test(*, title: str) -> dict[str, object]:
    return {
        "title": title,
        "city_hint": "深圳",
        "district": "南山区",
        "address": "海上世界",
        "business_district": "海上世界",
        "landmark": "文化艺术中心",
        "metro_station": "海上世界站",
        "price_amount": Decimal("0.00"),
        "price_currency": "CNY",
        "tags": ("展览",),
    }


@pytest.mark.asyncio
async def test_month_day_without_year_cannot_preserve_model_fabricated_year() -> None:
    fabricated = EventCandidate(
        **_candidate_fields_for_temporal_test(title="夏季展览"),
        event_start_date=date(2026, 8, 2),
        event_end_date=date(2026, 8, 2),
        event_start_at=datetime(2026, 8, 2, 10, 0, tzinfo=UTC),
        event_end_at=datetime(2026, 8, 2, 18, 0, tzinfo=UTC),
    )
    provider = FakeProvider(
        [_result_response(ExtractionResult.with_candidates((fabricated,)))]
    )

    result = await TextExtractionService(provider).extract("夏季展览在 8 月 2 日")

    candidate = result.candidates[0]
    assert isinstance(candidate, EventCandidate)
    assert candidate.event_start_date is None
    assert candidate.event_end_date is None
    assert candidate.event_start_at is None
    assert candidate.event_end_at is None
    assert candidate.event_start_clue == "8 月 2 日"
    assert {item.field for item in candidate.uncertainties} >= {
        CandidateField.EVENT_START_DATE,
        CandidateField.EVENT_END_DATE,
    }


@pytest.mark.asyncio
async def test_explicit_year_keeps_date_but_no_time_evidence_clears_exact_timestamp() -> None:
    modeled = EventCandidate(
        **_candidate_fields_for_temporal_test(title="夏季展览"),
        event_start_date=date(2026, 8, 2),
        event_end_date=date(2026, 8, 2),
        event_start_at=datetime(2026, 8, 2, 10, 0, tzinfo=UTC),
        event_end_at=datetime(2026, 8, 2, 18, 0, tzinfo=UTC),
    )
    provider = FakeProvider(
        [_result_response(ExtractionResult.with_candidates((modeled,)))]
    )

    result = await TextExtractionService(provider).extract("夏季展览在 2026 年 8 月 2 日")

    candidate = result.candidates[0]
    assert isinstance(candidate, EventCandidate)
    assert candidate.event_start_date == date(2026, 8, 2)
    assert candidate.event_end_date == date(2026, 8, 2)
    assert candidate.event_start_at is None
    assert candidate.event_end_at is None
    assert CandidateField.EVENT_START_AT in candidate.missing_fields
    assert CandidateField.EVENT_END_AT in candidate.missing_fields


@pytest.mark.asyncio
async def test_overly_generic_name_is_insufficient_without_provider_call() -> None:
    provider = FakeProvider([])

    result = await TextExtractionService(provider).extract("  咖啡店  ")

    assert result.outcome is ExtractionOutcome.INSUFFICIENT_INFORMATION
    assert result.reason_code is ExtractionReasonCode.INSUFFICIENT_INFORMATION
    assert CandidateField.TITLE in result.missing_fields
    assert result.candidates == ()
    assert provider.calls == []


@pytest.mark.parametrize(
    ("text", "candidate"),
    [
        (
            "周末想去广州塔看夜景",
            _full_place(title="广州塔", city_hint="广州"),
        ),
        (
            "这个展览在广州举办",
            _full_event(title="广州展览", city_hint="广州"),
        ),
    ],
)
@pytest.mark.asyncio
async def test_explicit_other_city_content_enters_provider_and_is_collectable(
    text: str,
    candidate: PlaceCandidate | EventCandidate,
) -> None:
    provider = FakeProvider(
        [_result_response(ExtractionResult.with_candidates((candidate,)))]
    )

    result = await TextExtractionService(provider).extract(text)

    assert result.outcome is ExtractionOutcome.CANDIDATES
    assert type(result.candidates[0]) is type(candidate)
    assert result.candidates[0].title == candidate.title
    assert result.candidates[0].city_hint == "广州"
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("想收藏深圳菜谱文化主题展", "深圳菜谱文化主题展"),
        ("想收藏深圳产品参数设计展", "深圳产品参数设计展"),
        ("想收藏深圳徒步路线文化展", "深圳徒步路线文化展"),
    ],
)
@pytest.mark.asyncio
async def test_event_title_keywords_do_not_trigger_unsupported_preflight(
    text: str,
    title: str,
) -> None:
    event = _full_event(title=title)
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates((event,)))])

    result = await TextExtractionService(provider).extract(text)

    assert isinstance(result.candidates[0], EventCandidate)
    assert result.candidates[0].title == event.title
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_shenzhen_day_trip_source_can_extract_multiple_requested_places() -> None:
    candidates = (
        _full_place(title="深圳博物馆"),
        _full_place(title="莲花山公园"),
    )
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates(candidates))])
    text = "深圳一日游里提到深圳博物馆和莲花山公园，请收藏这两个地点"

    result = await TextExtractionService(provider).extract(text)

    assert result.candidates == candidates
    assert len(result.candidates) == 2
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_one_source_can_return_separate_candidates_from_different_cities() -> None:
    candidates = (
        _full_place(title="广州塔", city_hint="广州"),
        _full_place(title="上海外滩", city_hint="上海"),
    )
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates(candidates))])

    result = await TextExtractionService(provider).extract("收藏广州塔和位于上海的外滩")

    assert result.candidates == candidates
    assert [candidate.city_hint for candidate in result.candidates] == ["广州", "上海"]
    assert len(provider.calls) == 1
    system_prompt = provider.calls[0].messages[0]["content"]
    assert "any city" in system_prompt
    assert "OUT_OF_SCOPE_CITY" not in system_prompt
    assert "search_scope_city" not in system_prompt


@pytest.mark.parametrize("title", ["上海宾馆", "北京饭店", "广州酒家"])
@pytest.mark.asyncio
async def test_place_name_city_substring_does_not_confirm_or_reject_city(title: str) -> None:
    provider = FakeProvider(
        [_result_response(ExtractionResult.with_candidates((_only_name_place(title=title),)))]
    )

    result = await TextExtractionService(provider).extract(title)

    candidate = result.candidates[0]
    assert isinstance(candidate, PlaceCandidate)
    assert candidate.title == title
    assert candidate.city_hint is None
    assert CandidateField.CITY_HINT in candidate.missing_fields
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_shenzhen_event_without_year_does_not_preserve_complete_times() -> None:
    event = _full_event()
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates((event,)))])

    result = await TextExtractionService(provider).extract("深圳设计周主题展，7月25日14:00到17:00")

    candidate = result.candidates[0]
    assert isinstance(candidate, EventCandidate)
    assert candidate.event_start_date is None
    assert candidate.event_end_date is None
    assert candidate.event_start_at is None
    assert candidate.event_end_at is None
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_event_missing_time_stays_candidate_and_does_not_invent_time() -> None:
    event = _event_without_time()
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates((event,)))])

    result = await TextExtractionService(provider).extract("深圳周末艺术市集，周六下午")

    candidate = result.candidates[0]
    assert isinstance(candidate, EventCandidate)
    assert candidate.event_start_at is None
    assert candidate.event_end_at is None
    assert CandidateField.EVENT_START_AT in candidate.missing_fields
    assert CandidateField.EVENT_END_AT in candidate.missing_fields


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("这款商品的型号参数和购买链接是什么", UnsupportedReason.PRODUCT),
        ("番茄炒蛋怎么做，给我食谱", UnsupportedReason.RECIPE),
        ("安排深圳到广州三日游", UnsupportedReason.MULTI_CITY_TRAVEL),
        ("给我梧桐山复杂徒步路线和 GPX", UnsupportedReason.COMPLEX_OUTDOOR_ROUTE),
    ],
)
@pytest.mark.asyncio
async def test_known_unsupported_content_has_stable_reason_without_model_call(
    text: str,
    reason: UnsupportedReason,
) -> None:
    provider = FakeProvider([])

    result = await TextExtractionService(provider).extract(text)

    assert result.outcome is ExtractionOutcome.UNSUPPORTED
    assert result.reason_code is ExtractionReasonCode.INPUT_UNSUPPORTED
    assert result.unsupported_reason is reason
    assert result.candidates == ()
    assert provider.calls == []


@pytest.mark.parametrize("text", ["", " ", "\n\t"])
@pytest.mark.asyncio
async def test_empty_input_never_calls_provider(text: str) -> None:
    provider = FakeProvider([])

    result = await TextExtractionService(provider).extract(text)

    assert result.reason_code is ExtractionReasonCode.INPUT_EMPTY
    assert provider.calls == []


@pytest.mark.asyncio
async def test_overlong_input_is_rejected_before_provider_call() -> None:
    provider = FakeProvider([])

    result = await TextExtractionService(provider).extract("深圳地点" + "x" * MAX_TEXT_INPUT_CHARS)

    assert result.reason_code is ExtractionReasonCode.INPUT_UNSUPPORTED
    assert result.unsupported_reason is UnsupportedReason.CONTENT_TOO_LONG
    assert provider.calls == []


@pytest.mark.asyncio
async def test_one_input_can_return_multiple_distinct_candidates() -> None:
    candidates = (
        _full_place(title="深圳地点 A"),
        _full_place(title="深圳地点 B"),
    )
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates(candidates))])

    result = await TextExtractionService(provider).extract("深圳地点 A 和深圳地点 B")

    assert result.candidates == candidates
    assert len(result.candidates) == 2


@pytest.mark.asyncio
async def test_place_and_event_candidates_can_coexist_without_merging() -> None:
    candidates = (_full_place(), _full_event())
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates(candidates))])

    result = await TextExtractionService(provider).extract("深圳的场馆和主题展")

    assert isinstance(result.candidates[0], PlaceCandidate)
    assert isinstance(result.candidates[1], EventCandidate)
    assert len(result.candidates) == 2


@pytest.mark.asyncio
async def test_valid_business_unsupported_result_does_not_trigger_repair() -> None:
    unsupported = ExtractionResult.unsupported(
        reason_code=ExtractionReasonCode.INPUT_UNSUPPORTED,
        unsupported_reason=UnsupportedReason.OTHER,
        recovery_suggestions=("model supplied text is replaced",),
    )
    provider = FakeProvider([_result_response(unsupported)])

    result = await TextExtractionService(provider).extract(
        "这是一段当前范围无法形成地点或活动候选的内容"
    )

    assert result.unsupported_reason is UnsupportedReason.OTHER
    assert len(provider.calls) == 1
    assert "model supplied text is replaced" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_first_valid_output_uses_exactly_one_provider_call() -> None:
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates((_full_place(),)))])

    await TextExtractionService(provider).extract("深圳博物馆")

    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_first_invalid_output_can_be_repaired_once() -> None:
    valid = ExtractionResult.with_candidates((_full_place(),))
    provider = FakeProvider([fake_response(content="not-json"), _result_response(valid)])

    result = await TextExtractionService(provider).extract("深圳博物馆")

    assert result == valid
    assert len(provider.calls) == 2
    repair_request = provider.calls[1].messages[-1]["content"]
    assert "json_invalid" in repair_request
    assert "Rebuild the object to match the schema and outcome rules." in repair_request
    assert "audit every candidate for field closure" not in repair_request
    assert "Rebuild one complete JSON object from the supplied evidence." not in repair_request
    assert provider.calls[1].tools is None


def _raw_candidate_result(candidate: dict[str, object]) -> dict[str, object]:
    return {"outcome": "candidates", "candidates": [candidate]}


def _parse_raw_result(
    payload: dict[str, object],
) -> tuple[ExtractionResult | None, tuple[dict[str, str], ...]]:
    return parse_extraction_response(
        fake_response(content=json.dumps(payload, ensure_ascii=False))
    )


def test_place_empty_fields_are_recorded_missing_in_candidate_field_order() -> None:
    raw_candidate: dict[str, object] = {
        "kind": "place",
        "title": "保守归一化地点",
        "missing_fields": [],
        "uncertainties": [],
    }

    result, issues = _parse_raw_result(_raw_candidate_result(raw_candidate))

    assert issues == ()
    assert result is not None
    candidate = result.candidates[0]
    assert isinstance(candidate, PlaceCandidate)
    assert candidate.title == "保守归一化地点"
    assert candidate.missing_fields == (
        CandidateField.CITY_HINT,
        CandidateField.DISTRICT,
        CandidateField.ADDRESS,
        CandidateField.BUSINESS_DISTRICT,
        CandidateField.LANDMARK,
        CandidateField.METRO_STATION,
        CandidateField.PRICE,
        CandidateField.TAGS,
    )
    assert CandidateField.EVENT_START_AT not in candidate.missing_fields
    assert CandidateField.EVENT_END_AT not in candidate.missing_fields


def test_event_adds_time_fields_without_changing_explicit_uncertainty() -> None:
    reason = "原文只有大致区域"
    raw_candidate: dict[str, object] = {
        "kind": "event",
        "title": "保守归一化活动",
        "city_hint": "深圳",
        "district": None,
        "uncertainties": [{"field": "district", "reason": reason}],
        "missing_fields": ["address"],
    }

    result, issues = _parse_raw_result(_raw_candidate_result(raw_candidate))

    assert issues == ()
    assert result is not None
    candidate = result.candidates[0]
    assert isinstance(candidate, EventCandidate)
    assert candidate.city_hint == "深圳"
    assert candidate.uncertainties[0].field is CandidateField.DISTRICT
    assert candidate.uncertainties[0].reason == reason
    assert CandidateField.DISTRICT not in candidate.missing_fields
    assert candidate.missing_fields == (
        CandidateField.ADDRESS,
        CandidateField.BUSINESS_DISTRICT,
        CandidateField.LANDMARK,
        CandidateField.METRO_STATION,
        CandidateField.EVENT_START_DATE,
        CandidateField.EVENT_END_DATE,
        CandidateField.EVENT_START_AT,
        CandidateField.EVENT_END_AT,
        CandidateField.PRICE,
        CandidateField.TAGS,
    )


def test_nonempty_model_facts_are_preserved_and_not_marked_missing() -> None:
    raw_candidate: dict[str, object] = {
        "kind": "place",
        "title": "事实保持地点",
        "city_hint": "深圳",
        "district": "福田区",
        "address": "福中路 184 号",
        "business_district": "市民中心",
        "landmark": "市民中心",
        "metro_station": "市民中心站",
        "price_amount": "0.00",
        "price_currency": "CNY",
        "tags": ["室内", "博物馆"],
        "missing_fields": [],
        "uncertainties": [],
    }

    result, issues = _parse_raw_result(_raw_candidate_result(raw_candidate))

    assert issues == ()
    assert result is not None
    candidate = result.candidates[0]
    assert candidate.title == raw_candidate["title"]
    assert candidate.city_hint == raw_candidate["city_hint"]
    assert candidate.district == raw_candidate["district"]
    assert candidate.address == raw_candidate["address"]
    assert candidate.business_district == raw_candidate["business_district"]
    assert candidate.landmark == raw_candidate["landmark"]
    assert candidate.metro_station == raw_candidate["metro_station"]
    assert candidate.price_amount == Decimal("0.00")
    assert candidate.price_currency == "CNY"
    assert candidate.tags == ("室内", "博物馆")
    assert candidate.missing_fields == ()


@pytest.mark.parametrize(
    ("candidate_update", "error_type"),
    [
        ({"city_hint": "深圳", "missing_fields": ["city_hint"]}, "present_field_marked_missing"),
        (
            {
                "missing_fields": ["city_hint"],
                "uncertainties": [{"field": "city_hint", "reason": "待确认"}],
            },
            "missing_and_uncertain_conflict",
        ),
        (
            {"missing_fields": ["city_hint", "city_hint"]},
            "duplicate_missing_field",
        ),
        (
            {
                "uncertainties": [
                    {"field": "city_hint", "reason": "待确认"},
                    {"field": "city_hint", "reason": "仍待确认"},
                ]
            },
            "duplicate_uncertainty_field",
        ),
        ({"missing_fields": "city_hint"}, "tuple_type"),
        ({"uncertainties": "city_hint"}, "tuple_type"),
        ({"uncertainties": [{"field": "city_hint"}]}, "missing"),
        ({"missing_fields": ["unknown_field"]}, "enum"),
        ({"kind": "unknown"}, "union_tag_invalid"),
        ({"district": 123}, "string_type"),
        ({"tags": None}, "tuple_type"),
    ],
)
def test_normalization_does_not_repair_invalid_model_classification(
    candidate_update: dict[str, object],
    error_type: str,
) -> None:
    candidate: dict[str, object] = {
        "kind": "place",
        "title": "非法状态候选",
        "missing_fields": [],
        "uncertainties": [],
    }
    candidate.update(candidate_update)

    result, issues = _parse_raw_result(_raw_candidate_result(candidate))

    assert result is None
    assert any(error_type in issue["type"] for issue in issues)


def test_price_pair_and_event_time_order_rules_remain_strict() -> None:
    place = {
        "kind": "place",
        "title": "币种孤立候选",
        "price_currency": "CNY",
        "missing_fields": [
            "city_hint",
            "district",
            "address",
            "business_district",
            "landmark",
            "metro_station",
            "price",
            "tags",
        ],
        "uncertainties": [],
    }
    event = {
        "kind": "event",
        "title": "时间倒序活动",
        "event_start_at": "2026-07-25T14:00:00+08:00",
        "event_end_at": "2026-07-25T13:00:00+08:00",
        "missing_fields": [
            "city_hint",
            "district",
            "address",
            "business_district",
            "landmark",
            "metro_station",
            "price",
            "tags",
        ],
        "uncertainties": [],
    }

    place_result, place_issues = _parse_raw_result(_raw_candidate_result(place))
    event_result, event_issues = _parse_raw_result(_raw_candidate_result(event))

    assert place_result is None
    assert place_issues[0]["type"] == "price_pair_incomplete"
    assert event_result is None
    assert event_issues[0]["type"] == "event_time_order_invalid"


def test_non_candidate_outcome_with_candidates_still_fails() -> None:
    payload = {
        "outcome": "unsupported",
        "reason_code": "INPUT_EMPTY",
        "candidates": [{"kind": "place", "title": "不应携带的候选"}],
    }

    result, issues = _parse_raw_result(payload)

    assert result is None
    assert issues[0]["type"] == "candidates_forbidden_for_outcome"


def test_normalization_is_immutable_repeatable_and_keeps_candidate_order() -> None:
    payload = {
        "outcome": "candidates",
        "candidates": [
            {
                "kind": "place",
                "title": "候选 A",
                "missing_fields": [],
                "uncertainties": [],
            },
            {
                "kind": "event",
                "title": "候选 B",
                "missing_fields": [],
                "uncertainties": [],
            },
        ],
    }
    original = deepcopy(payload)

    first = _normalize_model_extraction_output(payload)
    second = _normalize_model_extraction_output(payload)

    assert payload == original
    assert first == second
    assert first is not payload
    assert isinstance(first, dict)
    assert [candidate["title"] for candidate in first["candidates"]] == [
        "候选 A",
        "候选 B",
    ]


@pytest.mark.parametrize(
    "candidate",
    [
        {"kind": "place", "title": "固定 repair 地点一"},
        {"kind": "place", "title": "固定 repair 地点二", "city_hint": "深圳"},
        {
            "kind": "event",
            "title": "固定 repair 活动",
            "event_start_clue": "周六下午",
        },
    ],
)
def test_fixed_repair_response_with_only_missing_classification_omitted_passes_parser(
    candidate: dict[str, object],
) -> None:
    original = deepcopy(candidate)

    result, issues = _parse_raw_result(_raw_candidate_result(candidate))

    assert issues == ()
    assert result is not None
    parsed_candidate = result.candidates[0]
    assert parsed_candidate.title == original["title"]
    assert parsed_candidate.city_hint == original.get("city_hint")
    if isinstance(parsed_candidate, EventCandidate):
        assert parsed_candidate.event_start_clue == original["event_start_clue"]


@pytest.mark.asyncio
async def test_repair_preserves_text_evidence_and_specific_safe_guidance() -> None:
    secret = "private-source-and-response-value"
    invalid = json.loads(_invalid_event_time_json())
    invalid["candidates"][0]["title"] = secret
    invalid_json = json.dumps(invalid, ensure_ascii=False)
    valid = ExtractionResult.with_candidates((_full_place(),))
    provider = FakeProvider([fake_response(content=invalid_json), _result_response(valid)])

    result = await TextExtractionService(provider).extract(secret)

    repair_messages = provider.calls[1].messages
    repair_prompt = str(repair_messages[-1]["content"])
    assert result == valid
    assert "event_time_order_invalid" in repair_prompt
    assert "Ensure an exact Event end is after its exact start." in repair_prompt
    assert repair_messages[1] == {"role": "user", "content": secret}
    assert repair_messages[2] == {"role": "assistant", "content": invalid_json}
    assert [message["role"] for message in repair_messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]


@pytest.mark.asyncio
async def test_repair_result_depends_on_original_text_and_prior_candidate_evidence() -> None:
    source = "只修复深圳湾文化广场候选"
    invalid = json.loads(
        ExtractionResult.with_candidates(
            (_only_name_place(title="深圳湾文化广场"),)
        ).model_dump_json()
    )
    invalid["candidates"][0]["missing_fields"].append("city_hint")
    invalid_json = json.dumps(invalid, ensure_ascii=False)
    expected = ExtractionResult.with_candidates(
        (_only_name_place(title="深圳湾文化广场"),)
    )
    provider = _EvidenceCheckingTextProvider(
        [fake_response(content=invalid_json), _result_response(expected)]
    )

    result = await TextExtractionService(provider).extract(source)

    assert result == expected
    assert len(provider.calls) == 2


def test_safe_validation_issues_contain_only_path_and_stable_type() -> None:
    secret = "private-invalid-title"
    invalid = json.loads(_invalid_event_time_json())
    invalid["candidates"][0]["title"] = secret

    result, issues = parse_extraction_response(
        fake_response(content=json.dumps(invalid, ensure_ascii=False))
    )

    assert result is None
    assert issues == (
        {"path": "candidates.0.event", "type": "event_time_order_invalid"},
    )
    assert secret not in json.dumps(issues)
    assert all(set(issue) == {"path", "type"} for issue in issues)


def test_repair_messages_are_deep_copy_isolated_from_inputs() -> None:
    initial_messages: list[Message] = [
        {"role": "system", "content": {"rules": ["schema"]}},
        {"role": "user", "content": {"parts": ["深圳湾文化广场"]}},
    ]
    original_messages = json.loads(json.dumps(initial_messages, ensure_ascii=False))
    invalid_response = fake_response(content='{"outcome":"candidates"}')

    repaired = build_repair_messages(
        initial_messages,
        invalid_response=invalid_response,
        issues=({"path": "candidates", "type": "missing"},),
    )

    assert repaired is not None
    repaired[0]["content"]["rules"].append("changed")
    repaired[1]["content"]["parts"].append("changed")
    assert initial_messages == original_messages
    assert invalid_response.content == '{"outcome":"candidates"}'


def test_model_invalid_outcome_is_reserved_for_the_application() -> None:
    result, issues = parse_extraction_response(
        _result_response(ExtractionResult.model_invalid())
    )

    assert result is None
    assert issues == (
        {"path": "outcome", "type": "model_invalid_self_declared"},
    )


def test_generated_schema_and_shared_semantic_rules_stay_on_the_domain_contract() -> None:
    schema = extraction_result_schema()

    assert schema == ExtractionResult.model_json_schema()
    assert schema is not ExtractionResult.model_json_schema()
    assert schema["properties"]["outcome"]["description"].startswith("Selects exactly one")
    for rule in (
        "insufficient_information",
        "unsupported",
        "missing_fields",
        "Place candidates",
        "Event start/end",
        "CNY",
    ):
        assert rule in EXTRACTION_SEMANTIC_RULES
    assert "audit every candidate for field closure" not in EXTRACTION_SEMANTIC_RULES


@pytest.mark.asyncio
async def test_extraction_structured_output_is_explicit_and_isolated_for_both_calls() -> None:
    valid = ExtractionResult.with_candidates((_full_place(),))
    provider = FakeProvider([fake_response(content="not-json"), _result_response(valid)])

    result = await TextExtractionService(
        provider,
        structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
    ).extract("深圳博物馆")

    assert result == valid
    assert len(provider.calls) == 2
    first_format = provider.calls[0].response_format
    second_format = provider.calls[1].response_format
    assert first_format is not None
    assert second_format is not None
    assert first_format is not second_format
    assert first_format.json_schema == ExtractionResult.model_json_schema()
    assert second_format.json_schema == ExtractionResult.model_json_schema()


@pytest.mark.asyncio
async def test_two_invalid_outputs_stop_at_two_calls_with_stable_result() -> None:
    provider = FakeProvider(
        [fake_response(content="not-json"), fake_response(content="still-not-json")]
    )

    result = await TextExtractionService(provider).extract("深圳博物馆")

    assert result.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT
    assert result.reason_code is ExtractionReasonCode.MODEL_INVALID_OUTPUT
    assert result.candidates == ()
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_repair_normalizes_only_unclassified_absent_field_without_third_call() -> None:
    invalid_repair = json.loads(
        ExtractionResult.with_candidates((_only_name_place(),)).model_dump_json()
    )
    invalid_repair["candidates"][0]["missing_fields"].remove("address")
    original_repair = deepcopy(invalid_repair)
    provider = FakeProvider(
        [
            fake_response(content="{fixed-local-invalid-json"),
            fake_response(content=json.dumps(invalid_repair, ensure_ascii=False)),
        ]
    )

    result = await TextExtractionService(provider).extract("M Stand")

    candidate = result.candidates[0]
    assert candidate.title == "M Stand"
    assert set(candidate.missing_fields) == set(_only_name_place().missing_fields)
    assert candidate.missing_fields[-1] is CandidateField.ADDRESS
    assert invalid_repair == original_repair
    assert len(provider.calls) == 2


def _invalid_event_time_json() -> str:
    event = _full_event()
    payload = json.loads(ExtractionResult.with_candidates((event,)).model_dump_json())
    payload["candidates"][0]["event_end_at"] = payload["candidates"][0]["event_start_at"]
    return json.dumps(payload, ensure_ascii=False)


@pytest.mark.parametrize(
    "invalid_output",
    [
        "{not-json",
        "[]",
        '{"outcome":"candidates"}',
        ('{"outcome":"unsupported","reason_code":"obsolete_city_code","extra":"forbidden"}'),
        '{"outcome":"wrong-enum"}',
        _invalid_event_time_json(),
    ],
)
@pytest.mark.asyncio
async def test_json_root_fields_extra_enum_and_time_errors_each_get_one_repair(
    invalid_output: str,
) -> None:
    valid = ExtractionResult.with_candidates((_full_place(),))
    provider = FakeProvider([fake_response(content=invalid_output), _result_response(valid)])

    result = await TextExtractionService(provider).extract("深圳博物馆")

    assert result == valid
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_unexpected_tool_call_is_structural_error_and_repairs_once() -> None:
    valid = ExtractionResult.with_candidates((_full_place(),))
    provider = FakeProvider(
        [
            fake_response(tool_calls=[ToolCall("call-1", "unexpected", {})]),
            _result_response(valid),
        ]
    )

    result = await TextExtractionService(provider).extract("深圳博物馆")

    assert result == valid
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_missing_model_response_is_structural_error_and_repairs_once() -> None:
    valid = ExtractionResult.with_candidates((_full_place(),))
    provider = FakeProvider([None, _result_response(valid)])

    result = await TextExtractionService(provider).extract("深圳博物馆")

    assert result == valid
    assert "missing_model_response" in provider.calls[1].messages[-1]["content"]
    assert len(provider.calls) == 2


@pytest.mark.parametrize("code", list(ProviderErrorCode))
@pytest.mark.asyncio
async def test_provider_error_propagates_without_repair_or_automatic_retry(
    code: ProviderErrorCode,
) -> None:
    error = ProviderError(code=code)
    provider = FakeProvider([error])

    with pytest.raises(ProviderError) as caught:
        await TextExtractionService(provider).extract("深圳博物馆")

    assert caught.value is error
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_provider_error_during_repair_propagates_without_a_third_call() -> None:
    error = ProviderError(code=ProviderErrorCode.TIMEOUT)
    provider = FakeProvider([fake_response(content="bad"), error])

    with pytest.raises(ProviderError) as caught:
        await TextExtractionService(provider).extract("深圳博物馆")

    assert caught.value is error
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_cancelled_error_is_propagated_unchanged() -> None:
    cancellation = asyncio.CancelledError()
    provider = FakeProvider([cancellation])

    with pytest.raises(asyncio.CancelledError) as caught:
        await TextExtractionService(provider).extract("深圳博物馆")

    assert caught.value is cancellation
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_input_and_provider_message_snapshots_are_not_mutated() -> None:
    source_text = "  想收藏深圳菜谱文化主题展，保留原始空格  "
    event = _full_event(title="深圳菜谱文化主题展")
    provider = FakeProvider([_result_response(ExtractionResult.with_candidates((event,)))])

    await TextExtractionService(provider).extract(source_text)

    assert source_text == "  想收藏深圳菜谱文化主题展，保留原始空格  "
    assert provider.calls[0].messages[-1] == {"role": "user", "content": source_text}


@pytest.mark.asyncio
async def test_repeated_ambiguous_name_calls_do_not_share_city_gaps() -> None:
    responses = [
        _result_response(
            ExtractionResult.with_candidates((_only_name_place(title="上海宾馆"),))
        )
        for _ in range(2)
    ]
    provider = FakeProvider(responses)
    service = TextExtractionService(provider)

    first = await service.extract("上海宾馆")
    second = await service.extract("上海宾馆")

    assert first == second
    assert first is not second
    assert first.candidates[0] is not second.candidates[0]
    assert first.candidates[0].city_hint is None
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_repeated_calls_do_not_share_candidates_or_errors() -> None:
    first = ExtractionResult.with_candidates((_full_place(title="深圳地点 A"),))
    second = ExtractionResult.with_candidates((_full_place(title="深圳地点 B"),))
    provider = FakeProvider([_result_response(first), _result_response(second)])
    service = TextExtractionService(provider)

    result_a = await service.extract("深圳地点 A")
    result_b = await service.extract("深圳地点 B")

    assert result_a == first
    assert result_b == second
    assert result_a.candidates != result_b.candidates
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_concurrent_calls_do_not_share_result_state() -> None:
    titles = ("深圳菜谱文化主题展", "深圳产品参数设计展", "上海宾馆", "北京饭店")
    responses = [
        fake_response(
            content=json.dumps(
                _raw_candidate_result({"kind": "place", "title": title}),
                ensure_ascii=False,
            )
        )
        for title in titles
    ]
    provider = FakeProvider(responses)
    service = TextExtractionService(provider)

    results = await asyncio.gather(*(service.extract(title) for title in titles))

    result_titles = {result.candidates[0].title for result in results}
    assert result_titles == set(titles)
    assert all(
        result.candidates[0].missing_fields == _only_name_place().missing_fields
        for result in results
    )
    assert len({id(result) for result in results}) == 4
    assert len(provider.calls) == 4


@pytest.mark.asyncio
async def test_invalid_output_does_not_leak_source_prompt_response_or_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_text = "private full source pseudo-secret Authorization Cookie"
    raw_response = "raw provider response Bearer pseudo-secret Authorization Cookie " + "x" * 40
    provider = FakeProvider(
        [fake_response(content=raw_response), fake_response(content=raw_response)]
    )

    result = await TextExtractionService(provider).extract(source_text)
    public = result.model_dump_json()
    visible = " ".join((repr(result), str(result), public, caplog.text))

    assert result.reason_code is ExtractionReasonCode.MODEL_INVALID_OUTPUT
    for forbidden in (
        source_text,
        raw_response,
        "pseudo-secret",
        "Authorization",
        "Cookie",
        "Bearer",
        "JSON Schema",
    ):
        assert forbidden not in visible
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_oversized_invalid_response_is_not_copied_into_repair_messages() -> None:
    oversized = "x" * (MAX_MODEL_OUTPUT_CHARS + 1)
    valid = ExtractionResult.with_candidates((_full_place(),))
    provider = FakeProvider([fake_response(content=oversized), _result_response(valid)])

    result = await TextExtractionService(provider).extract("深圳博物馆")

    assert result == valid
    assert oversized not in json.dumps(provider.calls[1].messages)
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_validation_issue_summary_excludes_invalid_values() -> None:
    invalid_value = "Authorization Bearer pseudo-secret Cookie full-response"
    invalid = json.dumps(
        {
            "outcome": "unsupported",
            "reason_code": "obsolete_city_code",
            "unexpected": invalid_value,
        }
    )
    valid = ExtractionResult.with_candidates((_full_place(),))
    provider = FakeProvider([fake_response(content=invalid), _result_response(valid)])

    result = await TextExtractionService(provider).extract("深圳博物馆")

    repair_summary = provider.calls[1].messages[-1]["content"]
    assert result == valid
    assert invalid_value not in repair_summary
    assert "pseudo-secret" not in repair_summary
    assert "extra_forbidden" in repair_summary


def test_extraction_service_has_no_infrastructure_sdk_or_side_effect_imports() -> None:
    tree = ast.parse(inspect.getsource(text_extraction_module))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    forbidden_prefixes = (
        "app.infrastructure",
        "app.providers",
        "nanobot_core.agent",
        "nanobot_core.tools",
        "sqlalchemy",
        "openai",
        "httpx",
        "pathlib",
        "socket",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imported_modules)
    assert "CollectionItem" not in inspect.getsource(text_extraction_module)

"""Offline-testable application service for M0-2B plain-text extraction."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from datetime import date, datetime
from typing import Final
from zoneinfo import ZoneInfo

from app.application.extraction_output import (
    EXTRACTION_SEMANTIC_RULES,
    MAX_MODEL_OUTPUT_CHARS,
    build_repair_messages,
    canonicalize_extraction_result,
    extraction_response_format,
    extraction_result_schema_json,
    parse_extraction_response,
    unsupported_extraction_result,
)
from app.domain.collections import (
    CandidateField,
    EventCandidate,
    ExtractionOutcome,
    ExtractionReasonCode,
    ExtractionResult,
    PlaceCandidate,
    Uncertainty,
    UnsupportedReason,
)
from nanobot_core.providers import (
    Message,
    ModelProvider,
    ModelResponse,
    StructuredOutputMode,
)

MAX_TEXT_INPUT_CHARS: Final = 20_000
_PRODUCT_TIMEZONE: Final = ZoneInfo("Asia/Shanghai")
_GENERIC_INPUTS = frozenset(
    {
        "一个地方",
        "去哪玩",
        "咖啡店",
        "地点",
        "展览",
        "活动",
        "餐厅",
    }
)
_RECIPE_FORMAT = re.compile(r"菜谱|食谱|做法|烹饪步骤|配料表|食材清单")
_RECIPE_PROCEDURE_REQUEST = re.compile(
    r"怎么做|如何做|教我做|怎么烹饪|烹饪步骤|制作步骤|"
    r"(?:需要|准备)(?:哪些|什么)?(?:配料|食材)|给我(?:一份|一个)?(?:菜谱|食谱)"
)
_PRODUCT_REFERENCE = re.compile(
    r"(?:这|那|该)(?:一)?款.{0,8}(?:商品|产品)|"
    r"(?:商品|产品).{0,8}(?:型号|参数|价格|购买)|型号参数|产品参数|规格参数"
)
_PRODUCT_REQUEST = re.compile(
    r"购买链接|怎么买|哪里买|值得买吗|下单|选购攻略|商品比价|"
    r"(?:型号|产品|规格)?参数.{0,8}(?:是什么|多少|怎么样)|"
    r"(?:是什么|查询|介绍).{0,8}(?:型号|参数)"
)
_MULTI_DAY_TRAVEL = re.compile(
    r"(?:[2-9]\d*|[二两三四五六七八九十百]+)(?:日游|天(?:[一二两三四五六七八九十\d]+夜)?)|"
    r"多日(?:旅行|旅游|行程)"
)
_TRAVEL_PLAN_REQUEST = re.compile(r"安排|规划|制定|帮我做|给我做|旅行攻略|旅游行程")
_COMPLEX_ROUTE_KIND = re.compile(
    r"复杂户外路线|徒步路线|穿越路线|登山路线|越野路线",
    re.IGNORECASE,
)
_COMPLEX_ROUTE_EVIDENCE = re.compile(
    r"复杂|GPX|轨迹文件|轨迹下载|导航轨迹|穿越|越野",
    re.IGNORECASE,
)
_ROUTE_REQUEST = re.compile(r"给我|帮我|规划|制定|生成|导航|下载|怎么走")
_MONTH_DAY_CLUE = re.compile(r"(?<!\d)\d{1,2}\s*月\s*\d{1,2}\s*日")

_SYSTEM_PROMPT = (
    "You extract structured collection candidates for Shiguang.\n"
    "Return exactly one JSON object matching this JSON Schema, without Markdown or "
    f"commentary:\n{extraction_result_schema_json()}\n\n"
    "Rules:\n"
    f"{EXTRACTION_SEMANTIC_RULES}"
    "- Produce one candidate object per distinct Place or user-supplied Event; never "
    "merge objects.\n"
    "- Places and user-supplied Events from any city can be collected. Products, "
    "recipes, multi-city multi-day "
    "travel, and complex outdoor routes are unsupported.\n"
    "- city_hint is only a source-text clue, not a confirmed city code or planning "
    "eligibility decision. A city word inside a title or brand name alone is not a "
    "formal city statement. Never emit provider-specific or formal planning-city fields.\n"
    "- If city_hint is absent, leave it null. Do not invent it.\n"
    "- Keep distinct objects, including objects from different cities, as separate "
    "candidates. Multi-city multi-day planning requests remain unsupported.\n"
    "- Never invent an address, district, price, tag, Event date, or Event time. A clear "
    "date-only exhibition or activity range belongs in event_start_date/event_end_date, "
    "not event_start_at/event_end_at. Leave unavailable facts empty; use uncertainty "
    "only when the source itself is ambiguous.\n"
    "- Do not include source text, prompts, provider fields, credentials, headers, "
    "cookies, or raw responses.\n"
)
class TextExtractionService:
    """Extract candidates with one initial model call and at most one repair call."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        structured_output_mode: StructuredOutputMode | None = None,
        response_observer: Callable[[ModelResponse], None] | None = None,
    ) -> None:
        self._provider = provider
        self._response_format = extraction_response_format(structured_output_mode)
        self._response_observer = response_observer

    async def extract(self, text: str) -> ExtractionResult:
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        preflight = _preflight_result(text)
        if preflight is not None:
            return preflight

        initial_messages: list[Message] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        first_response = await self._provider.chat(
            messages=deepcopy(initial_messages),
            tools=None,
            response_format=self._response_format,
        )
        self._observe(first_response)
        first_result, issues = parse_extraction_response(first_response)
        if first_result is not None:
            return _enforce_text_semantic_evidence(
                canonicalize_extraction_result(
                first_result,
                insufficient_recovery_suggestions=(
                    "请补充具体店名、活动名、区域、商圈或地标。",
                ),
                ),
                text,
            )

        repair_messages = build_repair_messages(
            initial_messages,
            invalid_response=first_response,
            issues=issues,
        )
        assert repair_messages is not None
        repaired_response = await self._provider.chat(
            messages=repair_messages,
            tools=None,
            response_format=self._response_format,
        )
        self._observe(repaired_response)
        repaired_result, _repaired_issues = parse_extraction_response(repaired_response)
        if repaired_result is not None:
            return _enforce_text_semantic_evidence(
                canonicalize_extraction_result(
                repaired_result,
                insufficient_recovery_suggestions=(
                    "请补充具体店名、活动名、区域、商圈或地标。",
                ),
                ),
                text,
            )
        return ExtractionResult.model_invalid()

    def _observe(self, response: ModelResponse | None) -> None:
        if isinstance(response, ModelResponse) and self._response_observer is not None:
            self._response_observer(response)


def _preflight_result(text: str) -> ExtractionResult | None:
    if not text.strip():
        return ExtractionResult.unsupported(
            reason_code=ExtractionReasonCode.INPUT_EMPTY,
            recovery_suggestions=("请输入具体的地点或活动文字。",),
        )
    if len(text) > MAX_TEXT_INPUT_CHARS:
        return unsupported_extraction_result(
            reason=UnsupportedReason.CONTENT_TOO_LONG,
        )

    unsupported_reason = _explicit_unsupported_reason(text)
    if unsupported_reason is not None:
        return unsupported_extraction_result(reason=unsupported_reason)

    generic_key = re.sub(r"[\s，。！？,.!?]+", "", text).casefold()
    if generic_key in _GENERIC_INPUTS:
        return ExtractionResult.insufficient(
            missing_fields=(
                CandidateField.TITLE,
                CandidateField.CITY_HINT,
                CandidateField.DISTRICT,
                CandidateField.ADDRESS,
            ),
            recovery_suggestions=("请补充具体店名、活动名、区域、商圈或地标。",),
        )
    return None


def _explicit_unsupported_reason(text: str) -> UnsupportedReason | None:
    """Return only high-confidence unsupported intents; ambiguous text reaches the model."""
    if _RECIPE_FORMAT.search(text) and _RECIPE_PROCEDURE_REQUEST.search(text):
        return UnsupportedReason.RECIPE
    if _PRODUCT_REFERENCE.search(text) and _PRODUCT_REQUEST.search(text):
        return UnsupportedReason.PRODUCT
    if (
        _MULTI_DAY_TRAVEL.search(text)
        and _TRAVEL_PLAN_REQUEST.search(text)
        and re.search(r"\S{1,12}\s*(?:到|至|去往|前往)\s*\S{1,12}", text)
    ):
        return UnsupportedReason.MULTI_CITY_TRAVEL
    if (
        _COMPLEX_ROUTE_KIND.search(text)
        and _COMPLEX_ROUTE_EVIDENCE.search(text)
        and _ROUTE_REQUEST.search(text)
    ):
        return UnsupportedReason.COMPLEX_OUTDOOR_ROUTE
    return None


def _enforce_text_semantic_evidence(
    result: ExtractionResult,
    source_text: str,
) -> ExtractionResult:
    """Keep each Event's temporal facts behind evidence bound to that candidate."""

    if result.outcome is not ExtractionOutcome.CANDIDATES:
        return result
    normalized: list[PlaceCandidate | EventCandidate] = []
    for candidate in result.candidates:
        if not isinstance(candidate, EventCandidate):
            normalized.append(candidate)
            continue
        evidence = _candidate_evidence_scope(
            source_text,
            candidate=candidate,
            candidates=result.candidates,
        )
        payload = candidate.model_dump(mode="python")
        start_date_supported = _date_is_evidenced(evidence, candidate.event_start_date)
        end_date_supported = _date_is_evidenced(evidence, candidate.event_end_date)
        start_at_supported = _datetime_is_evidenced(
            evidence, candidate.event_start_at
        )
        end_at_supported = _datetime_is_evidenced(evidence, candidate.event_end_at)
        removed_dates = (
            candidate.event_start_date is not None and not start_date_supported
        ) or (candidate.event_end_date is not None and not end_date_supported)
        removed_times = (
            candidate.event_start_at is not None and not start_at_supported
        ) or (candidate.event_end_at is not None and not end_at_supported)
        if not removed_dates and not removed_times:
            normalized.append(candidate)
            continue
        if not start_date_supported:
            payload["event_start_date"] = None
        if not end_date_supported:
            payload["event_end_date"] = None
        if not start_at_supported:
            payload["event_start_at"] = None
        if not end_at_supported:
            payload["event_end_at"] = None
        clue_match = _MONTH_DAY_CLUE.search(evidence)
        clue = None if clue_match is None else clue_match.group(0)
        if clue is not None and payload.get("event_start_clue") is None:
            payload["event_start_clue"] = clue
        missing = [
            field
            for field in candidate.missing_fields
            if field
            not in {
                CandidateField.EVENT_START_DATE,
                CandidateField.EVENT_END_DATE,
                CandidateField.EVENT_START_AT,
                CandidateField.EVENT_END_AT,
            }
        ]
        uncertainties = [
            item
            for item in candidate.uncertainties
            if item.field
            not in {
                CandidateField.EVENT_START_DATE,
                CandidateField.EVENT_END_DATE,
                CandidateField.EVENT_START_AT,
                CandidateField.EVENT_END_AT,
            }
        ]
        date_fields = (
            (CandidateField.EVENT_START_DATE, payload["event_start_date"]),
            (CandidateField.EVENT_END_DATE, payload["event_end_date"]),
        )
        for field, value in date_fields:
            if value is None:
                if clue is None:
                    missing.append(field)
                else:
                    uncertainties.append(
                        Uncertainty(
                            field=field,
                            reason="原文提供了日期线索，但没有提供可确认的年份。",
                        )
                    )
        time_fields = (
            (CandidateField.EVENT_START_AT, payload["event_start_at"]),
            (CandidateField.EVENT_END_AT, payload["event_end_at"]),
        )
        missing.extend(field for field, value in time_fields if value is None)
        payload["missing_fields"] = tuple(missing)
        payload["uncertainties"] = tuple(uncertainties)
        normalized.append(EventCandidate.model_validate(payload))
    return ExtractionResult.with_candidates(tuple(normalized))


def _candidate_evidence_scope(
    source_text: str,
    *,
    candidate: EventCandidate,
    candidates: tuple[PlaceCandidate | EventCandidate, ...],
) -> str:
    """Bind evidence by the model candidate's title without interpreting its meaning."""

    if len(candidates) == 1:
        return source_text
    title_start = source_text.find(candidate.title)
    if title_start < 0:
        return ""
    next_starts = tuple(
        position
        for other in candidates
        if other is not candidate
        and (position := source_text.find(other.title, title_start + len(candidate.title))) >= 0
    )
    title_end = min(next_starts, default=len(source_text))
    return source_text[title_start:title_end]


def _date_is_evidenced(source: str, value: date | None) -> bool:
    if value is None:
        return True
    year = value.year
    month = value.month
    day = value.day
    compact = re.sub(r"\s+", "", source)
    year_evidence = re.search(rf"(?<!\d){year}(?:年|[-/.])", compact) is not None
    month_day_evidence = any(
        clue in compact
        for clue in (
            f"{month}月{day}日",
            f"{month:02d}月{day:02d}日",
            f"{month}.{day}",
            f"{month:02d}.{day:02d}",
            f"{month}/{day}",
            f"{month:02d}/{day:02d}",
            f"{month}-{day}",
            f"{month:02d}-{day:02d}",
        )
    )
    return year_evidence and month_day_evidence


def _time_is_evidenced(source: str, value: datetime | None) -> bool:
    if value is None:
        return True
    compact = re.sub(r"\s+", "", source)
    representations = (value, value.astimezone(_PRODUCT_TIMEZONE))
    return any(
        clue in compact
        for represented in representations
        for clue in (
            f"{represented.hour}:{represented.minute:02d}",
            f"{represented.hour:02d}:{represented.minute:02d}",
            f"{represented.hour}点{represented.minute:02d}",
            f"{represented.hour}时{represented.minute:02d}",
            f"{represented.hour}点" if represented.minute == 0 else "",
            f"{represented.hour}时" if represented.minute == 0 else "",
        )
        if clue
    )


def _datetime_is_evidenced(source: str, value: datetime | None) -> bool:
    if value is None:
        return True
    local_value = value.astimezone(_PRODUCT_TIMEZONE)
    return (
        _date_is_evidenced(source, value.date())
        or _date_is_evidenced(source, local_value.date())
    ) and _time_is_evidenced(source, value)


__all__ = [
    "MAX_MODEL_OUTPUT_CHARS",
    "MAX_TEXT_INPUT_CHARS",
    "TextExtractionService",
]

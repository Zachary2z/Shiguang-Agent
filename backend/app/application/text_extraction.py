"""Offline-testable application service for M0-2B plain-text extraction."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Final

from pydantic import ValidationError

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
from nanobot_core.providers import Message, ModelProvider, ModelResponse

MAX_TEXT_INPUT_CHARS: Final = 20_000
MAX_MODEL_OUTPUT_CHARS: Final = 50_000

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
_SHENZHEN_EVIDENCE = re.compile(
    r"深圳|福田区|罗湖区|南山区|盐田区|宝安区|龙岗区|龙华区|坪山区|光明区|大鹏新区"
)
_CITY_NAMES = (
    "深圳",
    "北京",
    "上海",
    "广州",
    "东莞",
    "佛山",
    "珠海",
    "惠州",
    "香港",
    "澳门",
    "成都",
    "重庆",
    "杭州",
    "武汉",
    "南京",
    "苏州",
    "西安",
    "长沙",
    "厦门",
    "青岛",
    "三亚",
    "海口",
)
_OUT_OF_SCOPE_CITY_ALTERNATION = "|".join(_CITY_NAMES[1:])
_EXPLICIT_OUT_OF_SCOPE_CITY_STATEMENT = re.compile(
    rf"(?:城市|所在城市|举办城市|目的地)\s*(?:是|为|在|：|:)\s*"
    rf"(?:{_OUT_OF_SCOPE_CITY_ALTERNATION})(?:市)?(?=$|[\s，。！？,!?；;])|"
    rf"(?:位于|地点在|地址在|举办于|举行于|发生于|展出于)\s*"
    rf"(?:{_OUT_OF_SCOPE_CITY_ALTERNATION})(?:市)?(?=$|[\s，。！？,!?；;])|"
    rf"(?:在|去|前往)\s*(?:{_OUT_OF_SCOPE_CITY_ALTERNATION})(?:市)?"
    r"(?:举办|举行|展出|发生|旅游|出差|游玩|看展|看演出)"
)
_EXPLICIT_OUT_OF_SCOPE_ENGLISH_CITY = re.compile(
    r"(?:city\s*(?:is|:)|located\s+in|destination\s*(?:is|:)|event\s+in)\s*"
    r"(?:beijing|shanghai|guangzhou|hong\s*kong|macao|macau|chengdu|hangzhou)\b",
    re.IGNORECASE,
)
_OUT_OF_SCOPE_DESTINATION_LANDMARK = re.compile(
    r"(?:想去|要去|计划去|准备去|前往|周末去).{0,6}(?:"
    r"广州塔(?=$|[，。！？,!?；;]|看|逛|游|拍|观景|打卡)|"
    r"上海外滩(?=$|[，。！？,!?；;]|看|逛|游|拍|观景|打卡)|"
    r"北京故宫(?=$|[，。！？,!?；;]|看|逛|游|拍|参观|打卡)"
    r")"
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
_CITY_ALTERNATION = "|".join(_CITY_NAMES)
_CROSS_CITY_ROUTE = re.compile(
    rf"(?:从\s*)?({_CITY_ALTERNATION})(?:市)?\s*(?:到|至|去往|前往)\s*"
    rf"({_CITY_ALTERNATION})(?:市)?"
    r"(?=$|[\s，。！？,!?；;]|[二两三四五六七八九十\d])"
)
_COMPLEX_ROUTE_KIND = re.compile(
    r"复杂户外路线|徒步路线|穿越路线|登山路线|越野路线",
    re.IGNORECASE,
)
_COMPLEX_ROUTE_EVIDENCE = re.compile(
    r"复杂|GPX|轨迹文件|轨迹下载|导航轨迹|穿越|越野",
    re.IGNORECASE,
)
_ROUTE_REQUEST = re.compile(r"给我|帮我|规划|制定|生成|导航|下载|怎么走")

_RESULT_SCHEMA = json.dumps(
    ExtractionResult.model_json_schema(),
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)
_SYSTEM_PROMPT = (
    "You extract structured candidates for the Shenzhen-only Shiguang MVP.\n"
    "Return exactly one JSON object matching this JSON Schema, without Markdown or "
    f"commentary:\n{_RESULT_SCHEMA}\n\n"
    "Rules:\n"
    "- Produce one candidate object per distinct Place or user-supplied Event; never "
    "merge objects.\n"
    "- Only Place and Event are supported. Products, recipes, multi-city multi-day "
    "travel, and complex outdoor routes are unsupported.\n"
    "- A candidate city may be 'shenzhen' only when the input explicitly supports "
    "Shenzhen. Otherwise use null; search_scope_city remains 'shenzhen' and city "
    "must be marked missing or uncertain.\n"
    "- Never invent an address, district, price, tag, or Event time. Every absent "
    "core field must be listed as missing or uncertain.\n"
    "- Event times use timezone-aware ISO 8601 values. Preserve incomplete time "
    "wording only in event_start_clue/event_end_clue and mark the exact field "
    "missing or uncertain.\n"
    "- Explicit non-Shenzhen content returns OUT_OF_SCOPE_CITY with no candidates.\n"
    "- Do not include source text, prompts, provider fields, credentials, headers, "
    "cookies, or raw responses.\n"
)
_REPAIR_PROMPT = (
    "The previous response did not match the required JSON structure.\n"
    "Return one corrected JSON object only. Do not quote the source, previous "
    "response, prompt, or validation values.\n"
    "Validation issues (paths and types only): {issues}\n"
)

_CITY_UNCONFIRMED = Uncertainty(
    field=CandidateField.CITY,
    reason="输入未明确城市；深圳仅作为搜索范围，城市仍待确认。",
)


class TextExtractionService:
    """Extract candidates with one initial model call and at most one repair call."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

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
        )
        first_result, issues = _parse_and_canonicalize(first_response, text=text)
        if first_result is not None:
            return first_result

        repair_messages = deepcopy(initial_messages)
        invalid_content = (
            first_response.content if isinstance(first_response, ModelResponse) else None
        )
        if isinstance(invalid_content, str) and len(invalid_content) <= MAX_MODEL_OUTPUT_CHARS:
            repair_messages.append({"role": "assistant", "content": invalid_content})
        repair_messages.append(
            {
                "role": "user",
                "content": _REPAIR_PROMPT.format(
                    issues=json.dumps(
                        issues,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                ),
            }
        )
        repaired_response = await self._provider.chat(
            messages=repair_messages,
            tools=None,
        )
        repaired_result, _repaired_issues = _parse_and_canonicalize(
            repaired_response,
            text=text,
        )
        if repaired_result is not None:
            return repaired_result
        return ExtractionResult.model_invalid()


def _preflight_result(text: str) -> ExtractionResult | None:
    if not text.strip():
        return ExtractionResult.unsupported(
            reason_code=ExtractionReasonCode.INPUT_EMPTY,
            recovery_suggestions=("请输入具体的深圳地点或活动文字。",),
        )
    if len(text) > MAX_TEXT_INPUT_CHARS:
        return _unsupported_result(
            reason=UnsupportedReason.CONTENT_TOO_LONG,
        )

    unsupported_reason = _explicit_unsupported_reason(text)
    if unsupported_reason is not None:
        return _unsupported_result(reason=unsupported_reason)

    if not _has_shenzhen_evidence(text) and _has_explicit_out_of_scope_city(text):
        return ExtractionResult.unsupported(
            reason_code=ExtractionReasonCode.OUT_OF_SCOPE_CITY,
            recovery_suggestions=("当前 MVP 只接受深圳地点和活动。",),
        )

    generic_key = re.sub(r"[\s，。！？,.!?]+", "", text).casefold()
    if generic_key in _GENERIC_INPUTS:
        return ExtractionResult.insufficient(
            missing_fields=(
                CandidateField.TITLE,
                CandidateField.CITY,
                CandidateField.DISTRICT,
                CandidateField.ADDRESS,
            ),
            recovery_suggestions=("请补充具体店名、活动名、区域、商圈或地标。",),
        )
    return None


def _unsupported_result(*, reason: UnsupportedReason) -> ExtractionResult:
    suggestions = {
        UnsupportedReason.PRODUCT: "商品暂不属于可规划收藏；请改发深圳地点或活动。",
        UnsupportedReason.RECIPE: "菜谱暂不属于可规划收藏；请改发深圳地点或活动。",
        UnsupportedReason.MULTI_CITY_TRAVEL: "跨城多日旅行暂不支持；请改发单个深圳地点或活动。",
        UnsupportedReason.COMPLEX_OUTDOOR_ROUTE: ("复杂户外路线暂不支持；请改发单个深圳地点。"),
        UnsupportedReason.CONTENT_TOO_LONG: "文字过长；请只保留地点或活动的关键信息。",
        UnsupportedReason.OTHER: "当前只支持深圳地点和用户主动提供的活动。",
    }
    return ExtractionResult.unsupported(
        reason_code=ExtractionReasonCode.INPUT_UNSUPPORTED,
        unsupported_reason=reason,
        recovery_suggestions=(suggestions[reason],),
    )


def _explicit_unsupported_reason(text: str) -> UnsupportedReason | None:
    """Return only high-confidence unsupported intents; ambiguous text reaches the model."""
    if _RECIPE_FORMAT.search(text) and _RECIPE_PROCEDURE_REQUEST.search(text):
        return UnsupportedReason.RECIPE
    if _PRODUCT_REFERENCE.search(text) and _PRODUCT_REQUEST.search(text):
        return UnsupportedReason.PRODUCT
    if (
        _MULTI_DAY_TRAVEL.search(text)
        and _TRAVEL_PLAN_REQUEST.search(text)
        and _has_explicit_cross_city_route(text)
    ):
        return UnsupportedReason.MULTI_CITY_TRAVEL
    if (
        _COMPLEX_ROUTE_KIND.search(text)
        and _COMPLEX_ROUTE_EVIDENCE.search(text)
        and _ROUTE_REQUEST.search(text)
    ):
        return UnsupportedReason.COMPLEX_OUTDOOR_ROUTE
    return None


def _parse_and_canonicalize(
    response: ModelResponse | None,
    *,
    text: str,
) -> tuple[ExtractionResult | None, tuple[dict[str, str], ...]]:
    if not isinstance(response, ModelResponse):
        return None, ({"path": "$", "type": "missing_model_response"},)
    if response.tool_calls:
        return None, ({"path": "$", "type": "unexpected_tool_calls"},)
    content = response.content
    if not isinstance(content, str) or not content.strip():
        return None, ({"path": "$", "type": "missing_json_content"},)
    if len(content) > MAX_MODEL_OUTPUT_CHARS:
        return None, ({"path": "$", "type": "output_too_long"},)

    try:
        parsed = ExtractionResult.model_validate_json(content)
    except ValidationError as exc:
        return None, _safe_validation_issues(exc)

    if parsed.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT:
        return None, ({"path": "outcome", "type": "self_declared_model_invalid"},)
    return _canonicalize_result(parsed, text=text), ()


def _canonicalize_result(result: ExtractionResult, *, text: str) -> ExtractionResult:
    if result.outcome is ExtractionOutcome.CANDIDATES:
        candidates = tuple(
            _normalize_city_confirmation(candidate, text=text) for candidate in result.candidates
        )
        return ExtractionResult.with_candidates(candidates)
    if result.outcome is ExtractionOutcome.INSUFFICIENT_INFORMATION:
        return ExtractionResult.insufficient(
            missing_fields=result.missing_fields,
            uncertainties=result.uncertainties,
            recovery_suggestions=("请补充具体店名、活动名、区域、商圈或地标。",),
        )
    if result.outcome is ExtractionOutcome.UNSUPPORTED:
        if result.reason_code is ExtractionReasonCode.INPUT_UNSUPPORTED:
            assert result.unsupported_reason is not None
            return _unsupported_result(reason=result.unsupported_reason)
        if result.reason_code is ExtractionReasonCode.OUT_OF_SCOPE_CITY:
            return ExtractionResult.unsupported(
                reason_code=ExtractionReasonCode.OUT_OF_SCOPE_CITY,
                recovery_suggestions=("当前 MVP 只接受深圳地点和活动。",),
            )
        return ExtractionResult.unsupported(
            reason_code=ExtractionReasonCode.INPUT_EMPTY,
            recovery_suggestions=("请输入具体的深圳地点或活动文字。",),
        )
    raise AssertionError("model-invalid results are handled before canonicalization")


def _normalize_city_confirmation(
    candidate: PlaceCandidate | EventCandidate,
    *,
    text: str,
) -> PlaceCandidate | EventCandidate:
    if candidate.city is None or _has_shenzhen_evidence(text):
        return candidate

    payload = candidate.model_dump()
    payload["city"] = None
    missing_fields = list(candidate.missing_fields)
    uncertainties = list(candidate.uncertainties)
    accounted = CandidateField.CITY in missing_fields or any(
        item.field is CandidateField.CITY for item in uncertainties
    )
    if not accounted:
        uncertainties.append(_CITY_UNCONFIRMED)
    payload["missing_fields"] = tuple(missing_fields)
    payload["uncertainties"] = tuple(uncertainties)
    return type(candidate).model_validate(payload)


def _safe_validation_issues(exc: ValidationError) -> tuple[dict[str, str], ...]:
    issues: list[dict[str, str]] = []
    for error in exc.errors(
        include_context=False,
        include_input=False,
        include_url=False,
    )[:8]:
        path = ".".join(str(part) for part in error["loc"]) or "$"
        issues.append({"path": path[:160], "type": str(error["type"])[:80]})
    return tuple(issues) or ({"path": "$", "type": "invalid_output"},)


def _has_shenzhen_evidence(text: str) -> bool:
    return _SHENZHEN_EVIDENCE.search(text) is not None


def _has_explicit_cross_city_route(text: str) -> bool:
    match = _CROSS_CITY_ROUTE.search(text)
    return match is not None and match.group(1) != match.group(2)


def _has_explicit_out_of_scope_city(text: str) -> bool:
    return bool(
        _EXPLICIT_OUT_OF_SCOPE_CITY_STATEMENT.search(text)
        or _EXPLICIT_OUT_OF_SCOPE_ENGLISH_CITY.search(text)
        or _OUT_OF_SCOPE_DESTINATION_LANDMARK.search(text)
    )


__all__ = [
    "MAX_MODEL_OUTPUT_CHARS",
    "MAX_TEXT_INPUT_CHARS",
    "TextExtractionService",
]

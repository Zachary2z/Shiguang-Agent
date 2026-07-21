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
_OUT_OF_SCOPE_CITY_NAMES = (
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
_OUT_OF_SCOPE_ENGLISH_CITY = re.compile(
    r"\b(?:beijing|shanghai|guangzhou|hong\s*kong|macao|macau|chengdu|hangzhou)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_PATTERNS: tuple[tuple[UnsupportedReason, re.Pattern[str]], ...] = (
    (
        UnsupportedReason.RECIPE,
        re.compile(r"菜谱|食谱|怎么做|做法|烹饪步骤|配料表|食材清单"),
    ),
    (
        UnsupportedReason.MULTI_CITY_TRAVEL,
        re.compile(
            r"跨城|多日旅行|旅行攻略|旅游行程|[一二两三四五六七八九十\d]+日游|"
            r"[一二两三四五六七八九十\d]+天[一二两三四五六七八九十\d]*夜|"
            r"深圳.{0,20}(?:广州|东莞|惠州|珠海|香港|澳门)|"
            r"(?:广州|东莞|惠州|珠海|香港|澳门).{0,20}深圳"
        ),
    ),
    (
        UnsupportedReason.COMPLEX_OUTDOOR_ROUTE,
        re.compile(r"复杂户外|徒步路线|穿越路线|登山路线|越野路线|轨迹文件|GPX", re.I),
    ),
    (
        UnsupportedReason.PRODUCT,
        re.compile(r"商品|开箱|型号参数|产品参数|选购攻略|商品比价"),
    ),
)

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

    for reason, pattern in _UNSUPPORTED_PATTERNS:
        if pattern.search(text) is not None:
            return _unsupported_result(reason=reason)

    if not _has_shenzhen_evidence(text) and _has_out_of_scope_city(text):
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


def _has_out_of_scope_city(text: str) -> bool:
    return any(city in text for city in _OUT_OF_SCOPE_CITY_NAMES) or bool(
        _OUT_OF_SCOPE_ENGLISH_CITY.search(text)
    )


__all__ = [
    "MAX_MODEL_OUTPUT_CHARS",
    "MAX_TEXT_INPUT_CHARS",
    "TextExtractionService",
]

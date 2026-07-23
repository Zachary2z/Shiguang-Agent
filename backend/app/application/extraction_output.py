"""Shared validation and repair helpers for every extraction input modality."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Final

from pydantic import ValidationError

from app.domain.collections import (
    ExtractionOutcome,
    ExtractionReasonCode,
    ExtractionResult,
    UnsupportedReason,
    default_cny_for_known_price,
)
from nanobot_core.providers import Message, ModelResponse

MAX_MODEL_OUTPUT_CHARS: Final = 50_000
PRICE_EXTRACTION_PROMPT_RULES: Final = (
    "- Shiguang currently uses renminbi only; users do not choose a currency.\n"
    "- When a local price is clear but no currency is written, emit price_amount and "
    'price_currency "CNY" together. This includes an explicit free price as amount 0.\n'
    "- Never treat unrelated numbers as prices. If a price cannot be identified, leave "
    "both price_amount and price_currency null and mark PRICE missing or uncertain.\n"
    "- Foreign currencies and exchange-rate conversion are unsupported.\n"
)

_REPAIR_PROMPT = (
    "The previous response did not match the required JSON structure.\n"
    "Return one corrected JSON object only. Do not quote the source, previous "
    "response, prompt, or validation values.\n"
    "Validation issues (paths and types only): {issues}\n"
)


def parse_extraction_response(
    response: ModelResponse | None,
) -> tuple[ExtractionResult | None, tuple[dict[str, str], ...]]:
    """Validate one model response without retaining inputs or validation values."""

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
        raw_result = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None, ({"path": "$", "type": "json_invalid"},)

    try:
        normalized_json = json.dumps(
            _default_candidate_price_currencies(raw_result),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        parsed = ExtractionResult.model_validate_json(normalized_json)
    except ValidationError as exc:
        return None, _safe_validation_issues(exc)

    if parsed.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT:
        return None, ({"path": "outcome", "type": "self_declared_model_invalid"},)
    return parsed, ()


def _default_candidate_price_currencies(raw_result: object) -> object:
    if not isinstance(raw_result, dict):
        return raw_result
    normalized = dict(raw_result)
    candidates = normalized.get("candidates")
    if not isinstance(candidates, list):
        return normalized
    normalized["candidates"] = [
        default_cny_for_known_price(candidate)
        if isinstance(candidate, dict)
        else candidate
        for candidate in candidates
    ]
    return normalized


def build_repair_messages(
    initial_messages: list[Message],
    *,
    invalid_response: ModelResponse | None,
    issues: tuple[dict[str, str], ...],
) -> list[Message]:
    """Create the sole structural-repair request while preserving caller isolation."""

    repair_messages = deepcopy(initial_messages)
    invalid_content = (
        invalid_response.content
        if isinstance(invalid_response, ModelResponse)
        else None
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
    return repair_messages


def canonicalize_extraction_result(
    result: ExtractionResult,
    *,
    insufficient_recovery_suggestions: tuple[str, ...],
) -> ExtractionResult:
    """Rebuild model output through the single trusted result constructors."""

    if result.outcome is ExtractionOutcome.CANDIDATES:
        return ExtractionResult.with_candidates(result.candidates)
    if result.outcome is ExtractionOutcome.INSUFFICIENT_INFORMATION:
        return ExtractionResult.insufficient(
            missing_fields=result.missing_fields,
            uncertainties=result.uncertainties,
            recovery_suggestions=insufficient_recovery_suggestions,
        )
    if result.outcome is ExtractionOutcome.UNSUPPORTED:
        if result.reason_code is ExtractionReasonCode.INPUT_UNSUPPORTED:
            assert result.unsupported_reason is not None
            return unsupported_extraction_result(reason=result.unsupported_reason)
        return ExtractionResult.unsupported(
            reason_code=ExtractionReasonCode.INPUT_EMPTY,
            recovery_suggestions=("请输入具体的地点或活动文字。",),
        )
    raise AssertionError("model-invalid results are handled before canonicalization")


def unsupported_extraction_result(*, reason: UnsupportedReason) -> ExtractionResult:
    """Return the shared stable unsupported-content result."""

    suggestions = {
        UnsupportedReason.PRODUCT: "商品暂不属于可规划收藏；请改发地点或活动。",
        UnsupportedReason.RECIPE: "菜谱暂不属于可规划收藏；请改发地点或活动。",
        UnsupportedReason.MULTI_CITY_TRAVEL: "跨城多日旅行暂不支持；请改发单个地点或活动。",
        UnsupportedReason.COMPLEX_OUTDOOR_ROUTE: "复杂户外路线暂不支持；请改发单个地点。",
        UnsupportedReason.CONTENT_TOO_LONG: "文字过长；请只保留地点或活动的关键信息。",
        UnsupportedReason.OTHER: "当前只支持地点和用户主动提供的活动。",
    }
    return ExtractionResult.unsupported(
        reason_code=ExtractionReasonCode.INPUT_UNSUPPORTED,
        unsupported_reason=reason,
        recovery_suggestions=(suggestions[reason],),
    )


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


__all__ = [
    "MAX_MODEL_OUTPUT_CHARS",
    "PRICE_EXTRACTION_PROMPT_RULES",
    "build_repair_messages",
    "canonicalize_extraction_result",
    "parse_extraction_response",
    "unsupported_extraction_result",
]

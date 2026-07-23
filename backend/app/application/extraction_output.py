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
from nanobot_core.providers import (
    Message,
    ModelResponse,
    StructuredOutput,
    StructuredOutputMode,
)

MAX_MODEL_OUTPUT_CHARS: Final = 50_000
_EXTRACTION_SCHEMA_NAME: Final = "shiguang_extraction_result"
_EXTRACTION_RESULT_SCHEMA: Final = ExtractionResult.model_json_schema()
EXTRACTION_SEMANTIC_RULES: Final = (
    "- Select exactly one outcome shape:\n"
    "  * candidates: one or more candidates; reason_code, unsupported_reason, "
    "result-level missing_fields, uncertainties, and recovery_suggestions must be empty.\n"
    "  * insufficient_information: no candidates; reason_code must be "
    "INSUFFICIENT_INFORMATION; identify at least one result-level missing or uncertain "
    "field; include a recovery suggestion; unsupported_reason must be null.\n"
    "  * unsupported: no candidates or field gaps; reason_code is INPUT_EMPTY or "
    "INPUT_UNSUPPORTED. unsupported_reason is required only for INPUT_UNSUPPORTED.\n"
    "  * Never emit model_invalid_output; that outcome is reserved for the application.\n"
    "- For every candidate, missing_fields must be unique and uncertainties may contain "
    "at most one item per field. The two sets must not overlap.\n"
    "- Every absent candidate city_hint, district, address, business_district, landmark, "
    "metro_station, price, or tags field must be classified as missing or uncertain. A "
    "present field cannot be marked missing.\n"
    "- Place candidates must not classify Event start/end fields and must not carry Event "
    "time semantics.\n"
    "- Event start/end values use timezone-aware ISO 8601. A missing exact time must be "
    "classified missing or uncertain; a present time cannot be missing. If both exact "
    "times exist, end must be after start. Incomplete wording belongs only in the matching "
    "time clue.\n"
    "- Shiguang currently uses renminbi only; users do not choose a currency.\n"
    "- When a local price is clear but no currency is written, emit price_amount and "
    'price_currency "CNY" together. This includes an explicit free price as amount 0.\n'
    "- Never treat unrelated numbers as prices. If a price cannot be identified, leave "
    "both price_amount and price_currency null and mark PRICE missing or uncertain.\n"
    "- Foreign currencies and exchange-rate conversion are unsupported.\n"
)

_REPAIR_PROMPT = (
    "The prior attempt violated the required extraction contract.\n"
    "Create one new corrected JSON object only. Do not quote or reproduce the source, "
    "prior response, prompt, or validation values.\n"
    "Validation issues (paths and types only): {issues}\n"
    "Safe correction guidance: {guidance}\n"
)
_UNKNOWN_REPAIR_GUIDANCE: Final = "Rebuild the object to match the schema and outcome rules."
_REPAIR_GUIDANCE_BY_TYPE: Final = {
    "price_pair_incomplete": "Provide amount and CNY together, or set both price fields null.",
    "price_currency_unsupported": "Use CNY for a known local amount; do not convert currency.",
    "missing_and_uncertain_conflict": "Classify a field as missing or uncertain, never both.",
    "present_field_marked_missing": "Remove present fields from missing_fields.",
    "absent_field_not_classified": "Classify each absent candidate field missing or uncertain.",
    "duplicate_missing_field": "List every missing field at most once.",
    "duplicate_uncertainty_field": "Give at most one uncertainty for each field.",
    "place_has_event_metadata": "Remove Event start/end classifications from Place candidates.",
    "event_time_order_invalid": "Ensure an exact Event end is after its exact start.",
    "event_time_absent_not_classified": (
        "Classify each absent exact Event time missing or uncertain."
    ),
    "candidates_required": "For candidates outcome, include at least one candidate.",
    "candidates_forbidden_for_outcome": "Remove candidates from every non-candidate outcome.",
    "candidate_outcome_has_error_metadata": (
        "For candidates outcome, clear result-level error metadata."
    ),
    "reason_code_invalid_for_outcome": "Use only the reason code required by the selected outcome.",
    "unsupported_reason_invalid": (
        "Use unsupported_reason only with INPUT_UNSUPPORTED, where it is required."
    ),
    "insufficient_fields_required": "Identify a missing or uncertain result-level field.",
    "recovery_suggestions_required": (
        "Include a safe recovery suggestion for insufficient information."
    ),
    "unsupported_fields_forbidden": "Remove candidate field gaps from unsupported outcomes.",
    "model_invalid_details_forbidden": "Remove model-derived details from model-invalid output.",
    "model_invalid_self_declared": "Choose candidates, insufficient_information, or unsupported.",
}


def extraction_result_schema() -> dict[str, object]:
    """Return the one generated ExtractionResult schema as an isolated snapshot."""

    return deepcopy(_EXTRACTION_RESULT_SCHEMA)


def extraction_result_schema_json() -> str:
    """Serialize the same generated schema used by optional structured output."""

    return json.dumps(
        extraction_result_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def extraction_response_format(
    mode: StructuredOutputMode | None,
) -> StructuredOutput | None:
    """Build the explicit extraction request for a verified provider capability."""

    if mode is None:
        return None
    if mode is StructuredOutputMode.JSON_OBJECT:
        return StructuredOutput(mode=mode)
    return StructuredOutput(
        mode=mode,
        schema_name=_EXTRACTION_SCHEMA_NAME,
        json_schema=extraction_result_schema(),
        strict=True,
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
        return None, ({"path": "outcome", "type": "model_invalid_self_declared"},)
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

    repair_messages = deepcopy(
        [message for message in initial_messages if message.get("role") == "system"]
    )
    del invalid_response
    guidance = tuple(
        _REPAIR_GUIDANCE_BY_TYPE.get(issue["type"], _UNKNOWN_REPAIR_GUIDANCE)
        for issue in issues
    )
    repair_messages.append(
        {
            "role": "user",
            "content": _REPAIR_PROMPT.format(
                issues=json.dumps(
                    issues,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                guidance=json.dumps(
                    guidance,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
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
    "EXTRACTION_SEMANTIC_RULES",
    "build_repair_messages",
    "canonicalize_extraction_result",
    "extraction_response_format",
    "extraction_result_schema",
    "extraction_result_schema_json",
    "parse_extraction_response",
    "unsupported_extraction_result",
]

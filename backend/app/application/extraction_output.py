"""Shared validation and repair helpers for every extraction input modality."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Final, TypeVar
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.domain.collections import (
    CandidateField,
    CollectionKind,
    EventCandidate,
    ExtractionOutcome,
    ExtractionReasonCode,
    ExtractionResult,
    PlaceCandidate,
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
_EVENT_TEMPORAL_FIELDS: Final = (
    CandidateField.EVENT_START_DATE,
    CandidateField.EVENT_END_DATE,
    CandidateField.EVENT_START_AT,
    CandidateField.EVENT_END_AT,
)
_EVENT_TEMPORAL_FIELD_VALUES: Final = frozenset(
    field.value for field in _EVENT_TEMPORAL_FIELDS
)
_SOURCE_EVIDENCE_PROPERTY: Final = "source_evidence"
_SOURCE_EVIDENCE_SCHEMA: Final[dict[str, object]] = {
    "type": "array",
    "maxItems": 32,
    "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidate_index": {"type": "integer", "minimum": 0},
            "field": {
                "type": "string",
                "enum": [field.value for field in _EVENT_TEMPORAL_FIELDS],
            },
            "value": {"type": "string", "minLength": 1, "maxLength": 80},
            "quote": {"type": "string", "minLength": 1, "maxLength": 200},
        },
        "required": ["candidate_index", "field", "value", "quote"],
    },
}
_CANDIDATE_FIELD_VALUES: Final = frozenset(field.value for field in CandidateField)
_CANDIDATE_MODELS_BY_KIND: Final[
    dict[str, type[PlaceCandidate] | type[EventCandidate]]
] = {
    CollectionKind.PLACE.value: PlaceCandidate,
    CollectionKind.EVENT.value: EventCandidate,
}
_CANDIDATE_FIELDS_BY_KIND: Final[dict[str, tuple[CandidateField, ...]]] = {
    kind: tuple(
        field
        for field in CandidateField
        if field is not CandidateField.TITLE
        and (field is CandidateField.PRICE or field.value in model.model_fields)
    )
    for kind, model in _CANDIDATE_MODELS_BY_KIND.items()
}
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
    "- Leave unavailable candidate facts empty. The application records conservative "
    "missing state after the model response; explicit uncertainty must remain explicit.\n"
    "- Place candidates must not carry or classify Event date, exact-time, or time-clue "
    "semantics.\n"
    "- A destination the user wants to visit is a Place even when the user mentions a "
    "preferred day such as a weekend. Create an Event only when the source describes an "
    "actual exhibition, performance, market, lecture, activity, or scheduled session; "
    "a visit preference alone is not an Event fact.\n"
    "- A clear named destination is sufficient for a Place candidate. Keep the destination "
    "title even when location details are missing; do not mistake surrounding save-intent "
    "wording for a missing title.\n"
    "- Event start/end effective dates and exact session times are different facts. Use "
    "event_start_date/event_end_date as ISO calendar dates only when the source states "
    "natural-day validity; the end date is inclusive and may equal the start date. Never "
    "convert a date-only fact to midnight, infer a timezone, or invent daily opening or "
    "closing hours. A compact source range may inherit its explicitly stated year within "
    "that same range only; never infer a year from system time or metadata.\n"
    "- Use event_start_at/event_end_at only when the source states a specific clock time. "
    "They must be timezone-aware ISO 8601 values, and an exact end must be after its exact "
    "start. Keep absent exact times null. Use event_start_clue/event_end_clue only for "
    "time expressions that cannot be reliably structured, and classify the corresponding "
    "fact uncertain.\n"
    "- For text input only, source_evidence is transient provenance, not candidate data. "
    "For every non-null Event date or exact-time field, emit one evidence item with the "
    "candidate's zero-based index, that exact field name, the exact JSON field value, and "
    "one contiguous verbatim source quote that fully supports the value. The same quote "
    "may support multiple fields of one candidate, but evidence must never be shared or "
    "swapped across candidates. Do not infer evidence from a title or paraphrase it.\n"
    "- Shiguang currently uses renminbi only; users do not choose a currency.\n"
    "- When a local price is clear but no currency is written, emit price_amount and "
    'price_currency "CNY" together. This includes an explicit free price as amount 0.\n'
    "- Never treat unrelated numbers as prices. If a price cannot be identified, leave "
    "both price_amount and price_currency null; use uncertainty only for ambiguous price "
    "evidence.\n"
    "- Foreign currencies and exchange-rate conversion are unsupported.\n"
)

_REPAIR_PROMPT = (
    "The prior attempt violated the required extraction contract.\n"
    "Create one new corrected JSON object only. Do not quote the prompt or validation "
    "values in the result.\n"
    "Validation issues (paths and types only): {issues}\n"
    "Safe correction guidance: {guidance}\n"
    "{evidence_constraint}"
)
_TEXT_REPAIR_EVIDENCE_CONSTRAINT: Final = (
    "Correct the same extraction using the original user input and prior assistant "
    "output above. Do not replace them with unrelated candidates or facts."
)
_IMAGE_REPAIR_EVIDENCE_CONSTRAINT: Final = (
    "The screenshot is intentionally not attached again. Correct only the candidate "
    "structure and facts already present in the prior assistant output above. Do not "
    "invent any place, activity, or fact that was absent from that output."
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
    "place_has_event_metadata": (
        "Remove Event date and exact-time classifications from Place candidates."
    ),
    "event_date_order_invalid": (
        "Ensure the inclusive Event end date is on or after its start date."
    ),
    "event_date_absent_not_classified": (
        "Classify each absent Event effective date missing or uncertain."
    ),
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
_IMAGE_PRIVATE_EVIDENCE = re.compile(
    r"(?:data:image/|;base64,|file://|/(?:users|private|var/folders)/|"
    r"[a-z]:\\|[\w .-]+\.(?:png|jpe?g|webp)\b|[A-Za-z0-9+/]{256,}={0,2})",
    re.IGNORECASE,
)
_SOURCE_CLAUSE = re.compile(r"[^；;。！？!?\n]+")
_EXPLICIT_DATE = re.compile(
    r"(?<!\d)"
    r"(?P<year>\d{4})\s*(?:年|[-./])\s*"
    r"(?P<month>\d{1,2})\s*(?:月|[-./])\s*"
    r"(?P<day>\d{1,2})\s*日?"
)
_INHERITED_RANGE_END_DATE = re.compile(
    r"(?:至|到|[-–—~～])\s*"
    r"(?P<month>\d{1,2})\s*(?:月|[./])\s*"
    r"(?P<day>\d{1,2})\s*日?"
)
_EXPLICIT_CLOCK = re.compile(
    r"(?P<period>凌晨|早上|上午|中午|下午|晚上)?\s*"
    r"(?P<hour>\d{1,2})"
    r"(?::(?P<colon_minute>\d{2})|点(?:(?P<minute>\d{1,2})分?)?)"
)
_SHANGHAI: Final = ZoneInfo("Asia/Shanghai")
_TemporalValue = TypeVar("_TemporalValue", date, time)


@dataclass(frozen=True)
class _TemporalFacts:
    """Deterministically parsed temporal facts from one exact source span."""

    dates: tuple[date, ...]
    clocks: tuple[time, ...]


def extraction_result_schema(
    *,
    include_source_evidence: bool = False,
) -> dict[str, object]:
    """Return the one generated ExtractionResult schema as an isolated snapshot."""

    schema = deepcopy(_EXTRACTION_RESULT_SCHEMA)
    if not include_source_evidence:
        return schema
    properties = schema.get("properties")
    required = schema.get("required")
    assert isinstance(properties, dict)
    assert isinstance(required, list)
    properties[_SOURCE_EVIDENCE_PROPERTY] = deepcopy(_SOURCE_EVIDENCE_SCHEMA)
    required.append(_SOURCE_EVIDENCE_PROPERTY)
    return schema


def extraction_result_schema_json(
    *,
    include_source_evidence: bool = False,
) -> str:
    """Serialize the same generated schema used by optional structured output."""

    return json.dumps(
        extraction_result_schema(include_source_evidence=include_source_evidence),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def extraction_response_format(
    mode: StructuredOutputMode | None,
    *,
    include_source_evidence: bool = False,
) -> StructuredOutput | None:
    """Build the explicit extraction request for a verified provider capability."""

    return structured_response_format(
        mode,
        schema_name=_EXTRACTION_SCHEMA_NAME,
        json_schema=extraction_result_schema(
            include_source_evidence=include_source_evidence
        ),
    )


def structured_response_format(
    mode: StructuredOutputMode | None,
    *,
    schema_name: str,
    json_schema: dict[str, object],
) -> StructuredOutput | None:
    """Build one configured structured-output request without capability probing."""

    if mode is None:
        return None
    if mode is StructuredOutputMode.JSON_OBJECT:
        return StructuredOutput(mode=mode)
    return StructuredOutput(
        mode=mode,
        schema_name=schema_name,
        json_schema=deepcopy(json_schema),
        strict=True,
    )


def parse_extraction_response(
    response: ModelResponse | None,
    *,
    source_text: str | None = None,
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
        if source_text is not None:
            structural_result = deepcopy(raw_result)
            if isinstance(structural_result, dict):
                structural_result.pop(_SOURCE_EVIDENCE_PROPERTY, None)
            ExtractionResult.model_validate_json(
                json.dumps(
                    _normalize_model_extraction_output(structural_result),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            raw_result = _apply_text_source_evidence(
                raw_result,
                source_text=source_text,
            )
        normalized_json = json.dumps(
            _normalize_model_extraction_output(raw_result),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        parsed = ExtractionResult.model_validate_json(normalized_json)
    except ValidationError as exc:
        return None, _safe_validation_issues(exc)

    if parsed.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT:
        return None, ({"path": "outcome", "type": "model_invalid_self_declared"},)
    return parsed, ()


def _apply_text_source_evidence(raw_result: object, *, source_text: str) -> object:
    """Consume candidate-field provenance before the strict domain DTO boundary."""

    normalized = deepcopy(raw_result)
    if not isinstance(normalized, dict):
        return normalized
    raw_evidence = normalized.pop(_SOURCE_EVIDENCE_PROPERTY, None)
    candidates = normalized.get("candidates")
    if not isinstance(candidates, list):
        return normalized
    supported = _supported_temporal_fields(
        candidates=candidates,
        raw_evidence=raw_evidence,
        source_text=source_text,
    )
    for index, candidate in enumerate(candidates):
        if isinstance(candidate, dict) and candidate.get("kind") == CollectionKind.EVENT:
            _clear_unsupported_temporal_fields(
                candidate,
                candidate_index=index,
                supported=supported,
            )
    return normalized


def _supported_temporal_fields(
    *,
    candidates: list[object],
    raw_evidence: object,
    source_text: str,
) -> set[tuple[int, str]]:
    if not isinstance(raw_evidence, list):
        return set()
    candidate_scopes = _candidate_source_scopes(
        candidates=candidates,
        source_text=source_text,
    )
    supported: set[tuple[int, str]] = set()
    for evidence in raw_evidence[:32]:
        if not isinstance(evidence, dict) or set(evidence) != {
            "candidate_index",
            "field",
            "value",
            "quote",
        }:
            continue
        index = evidence.get("candidate_index")
        field = evidence.get("field")
        value = evidence.get("value")
        quote = evidence.get("quote")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < len(candidates)
            or not isinstance(field, str)
            or field not in _EVENT_TEMPORAL_FIELD_VALUES
            or not isinstance(value, str)
            or not isinstance(quote, str)
            or not 0 < len(quote) <= 200
        ):
            continue
        candidate = candidates[index]
        if (
            not isinstance(candidate, dict)
            or candidate.get("kind") != CollectionKind.EVENT
            or candidate.get(field) != value
        ):
            continue
        candidate_scope = candidate_scopes.get(index)
        if candidate_scope is None:
            continue
        clause_start, clause_end, clause = candidate_scope
        if not any(
            clause_start <= start and start + len(quote) <= clause_end
            for start in _substring_occurrences(source_text, quote)
        ):
            continue
        if _temporal_quote_supports_field(
            field=field,
            value=value,
            quote=quote,
            candidate_clause=clause,
        ):
            supported.add((index, field))
    return supported


def _candidate_source_scopes(
    *,
    candidates: list[object],
    source_text: str,
) -> dict[int, tuple[int, int, str]]:
    """Bind only exact, unique candidate titles to one unambiguous source clause."""

    title_owners: dict[str, list[int]] = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or candidate.get("kind") != CollectionKind.EVENT:
            continue
        title = candidate.get("title")
        if isinstance(title, str) and title:
            title_owners.setdefault(title, []).append(index)

    scopes: dict[int, tuple[int, int, str]] = {}
    clauses = tuple(
        (match.start(), match.end(), match.group())
        for match in _SOURCE_CLAUSE.finditer(source_text)
    )
    for title, owners in title_owners.items():
        title_occurrences = _substring_occurrences(source_text, title)
        if len(owners) != 1 or len(title_occurrences) != 1:
            continue
        title_start = title_occurrences[0]
        matching_clauses = [
            clause
            for clause in clauses
            if clause[0] <= title_start and title_start + len(title) <= clause[1]
        ]
        if len(matching_clauses) != 1:
            continue
        clause = matching_clauses[0]
        if any(
            other_title != title
            and any(
                clause[0] <= start and start + len(other_title) <= clause[1]
                for start in _substring_occurrences(source_text, other_title)
            )
            for other_title in title_owners
        ):
            continue
        scopes[owners[0]] = clause
    return scopes


def _substring_occurrences(source_text: str, value: str) -> tuple[int, ...]:
    occurrences: list[int] = []
    offset = 0
    while (position := source_text.find(value, offset)) >= 0:
        occurrences.append(position)
        offset = position + 1
    return tuple(occurrences)


def _temporal_quote_supports_field(
    *,
    field: str,
    value: str,
    quote: str,
    candidate_clause: str,
) -> bool:
    """Verify model-located text against one centralized temporal grammar."""

    quote_facts = _parse_temporal_facts(quote)
    if field in {
        CandidateField.EVENT_START_DATE.value,
        CandidateField.EVENT_END_DATE.value,
    }:
        try:
            expected_date = date.fromisoformat(value)
        except ValueError:
            return False
        return expected_date == _field_temporal_value(
            quote_facts.dates,
            is_end=field == CandidateField.EVENT_END_DATE.value,
        )

    try:
        expected_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if expected_datetime.tzinfo is None:
        return False
    local_expected = expected_datetime.astimezone(_SHANGHAI)
    is_end = field == CandidateField.EVENT_END_AT.value
    expected_clock = _field_temporal_value(quote_facts.clocks, is_end=is_end)
    if local_expected.timetz().replace(tzinfo=None) != expected_clock:
        return False

    date_facts = quote_facts.dates
    if not date_facts:
        date_facts = _parse_temporal_facts(candidate_clause).dates
    return local_expected.date() == _field_temporal_value(date_facts, is_end=is_end)


def _field_temporal_value(
    values: tuple[_TemporalValue, ...],
    *,
    is_end: bool,
) -> _TemporalValue | None:
    if not values:
        return None
    return values[-1] if is_end else values[0]


def _parse_temporal_facts(value: str) -> _TemporalFacts:
    """Parse the one accepted source-date/clock grammar without model assistance."""

    dated_spans: list[tuple[int, date]] = []
    for match in _EXPLICIT_DATE.finditer(value):
        parsed = _safe_date(
            year=int(match.group("year")),
            month=int(match.group("month")),
            day=int(match.group("day")),
        )
        if parsed is None:
            continue
        dated_spans.append((match.start(), parsed))
        range_match = _INHERITED_RANGE_END_DATE.match(value, match.end())
        if range_match is None:
            continue
        range_end = _safe_date(
            year=parsed.year,
            month=int(range_match.group("month")),
            day=int(range_match.group("day")),
        )
        if range_end is not None:
            dated_spans.append((range_match.start(), range_end))

    clock_spans: list[tuple[int, time]] = []
    for match in _EXPLICIT_CLOCK.finditer(value):
        parsed_clock = _safe_clock(
            period=match.group("period"),
            hour=int(match.group("hour")),
            minute=int(match.group("colon_minute") or match.group("minute") or 0),
        )
        if parsed_clock is not None:
            clock_spans.append((match.start(), parsed_clock))
    return _TemporalFacts(
        dates=_ordered_unique(item for _, item in sorted(dated_spans)),
        clocks=_ordered_unique(item for _, item in sorted(clock_spans)),
    )


def _safe_date(*, year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _safe_clock(*, period: str | None, hour: int, minute: int) -> time | None:
    if not 0 <= minute <= 59:
        return None
    if period is None:
        if not 0 <= hour <= 23:
            return None
    elif period in {"凌晨", "早上", "上午"}:
        if not 1 <= hour <= 12:
            return None
        if hour == 12:
            hour = 0
    else:
        if not 1 <= hour <= 12:
            return None
        if hour < 12:
            hour += 12
    return time(hour, minute)


def _ordered_unique(
    values: Iterable[_TemporalValue],
) -> tuple[_TemporalValue, ...]:
    result: list[_TemporalValue] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def _clear_unsupported_temporal_fields(
    candidate: dict[str, object],
    *,
    candidate_index: int,
    supported: set[tuple[int, str]],
) -> None:
    cleared: list[CandidateField] = []
    for field in _EVENT_TEMPORAL_FIELDS:
        if (
            candidate.get(field.value) is not None
            and (candidate_index, field.value) not in supported
        ):
            candidate[field.value] = None
            cleared.append(field)
    if not cleared:
        return

    raw_missing = candidate.get("missing_fields")
    raw_uncertainties = candidate.get("uncertainties")
    missing = list(raw_missing) if isinstance(raw_missing, list) else []
    uncertainties = list(raw_uncertainties) if isinstance(raw_uncertainties, list) else []
    cleared_values = {field.value for field in cleared}
    missing = [field for field in missing if field not in cleared_values]
    uncertainties = [
        item
        for item in uncertainties
        if not isinstance(item, dict) or item.get("field") not in cleared_values
    ]
    uncertainties.extend(
        {
            "field": field.value,
            "reason": "时间事实缺少可绑定的原文证据。",
        }
        for field in cleared
    )
    candidate["missing_fields"] = missing
    candidate["uncertainties"] = uncertainties


def _normalize_model_extraction_output(raw_result: object) -> object:
    """Copy and normalize only application-derived state at the model JSON boundary."""

    normalized = deepcopy(raw_result)
    if not isinstance(normalized, dict):
        return normalized
    candidates = normalized.get("candidates")
    if not isinstance(candidates, list):
        return normalized
    normalized["candidates"] = [
        _normalize_model_candidate(candidate) for candidate in candidates
    ]
    return normalized


def _normalize_model_candidate(candidate: object) -> object:
    if not isinstance(candidate, dict):
        return candidate

    normalized = default_cny_for_known_price(candidate)
    classification = _valid_candidate_classification(normalized)
    kind = normalized.get("kind")
    applicable_fields = (
        _CANDIDATE_FIELDS_BY_KIND.get(kind) if isinstance(kind, str) else None
    )
    if classification is None or applicable_fields is None:
        return normalized

    missing_fields, uncertain_fields = classification
    additions = [
        field.value
        for field in applicable_fields
        if field.value not in missing_fields
        and field.value not in uncertain_fields
        and _candidate_field_is_empty(normalized, field)
    ]
    if additions:
        normalized["missing_fields"] = [*missing_fields, *additions]
    return normalized


def _valid_candidate_classification(
    candidate: dict[str, object],
) -> tuple[list[str], set[str]] | None:
    raw_missing = candidate.get("missing_fields", [])
    raw_uncertainties = candidate.get("uncertainties", [])
    if not isinstance(raw_missing, list) or not isinstance(raw_uncertainties, list):
        return None
    if not all(isinstance(field, str) for field in raw_missing):
        return None

    missing_fields = list(raw_missing)
    if (
        any(field not in _CANDIDATE_FIELD_VALUES for field in missing_fields)
        or len(set(missing_fields)) != len(missing_fields)
    ):
        return None

    uncertain_fields: list[str] = []
    for uncertainty in raw_uncertainties:
        if (
            not isinstance(uncertainty, dict)
            or set(uncertainty) != {"field", "reason"}
            or not isinstance(uncertainty.get("field"), str)
            or not isinstance(uncertainty.get("reason"), str)
        ):
            return None
        uncertain_fields.append(uncertainty["field"])
    if (
        any(field not in _CANDIDATE_FIELD_VALUES for field in uncertain_fields)
        or len(set(uncertain_fields)) != len(uncertain_fields)
        or set(missing_fields).intersection(uncertain_fields)
    ):
        return None
    return missing_fields, set(uncertain_fields)


def _candidate_field_is_empty(
    candidate: dict[str, object],
    field: CandidateField,
) -> bool:
    if field is CandidateField.PRICE:
        return (
            candidate.get("price_amount") is None
            and candidate.get("price_currency") is None
        )
    if field is CandidateField.TAGS:
        return candidate.get(field.value, []) == []
    return candidate.get(field.value) is None


def build_repair_messages(
    initial_messages: list[Message],
    *,
    invalid_response: ModelResponse | None,
    issues: tuple[dict[str, str], ...],
) -> list[Message] | None:
    """Create the sole structural-repair request while preserving caller isolation."""

    image_request = any(_message_contains_image(message) for message in initial_messages)
    prior_output = _safe_prior_output(invalid_response)
    if image_request:
        if prior_output is None or not _has_image_candidate_evidence(prior_output):
            return None
        repair_messages = deepcopy(
            [message for message in initial_messages if message.get("role") == "system"]
        )
        evidence_constraint = _IMAGE_REPAIR_EVIDENCE_CONSTRAINT
    else:
        repair_messages = deepcopy(initial_messages)
        evidence_constraint = _TEXT_REPAIR_EVIDENCE_CONSTRAINT

    if prior_output is not None:
        repair_messages.append({"role": "assistant", "content": prior_output})
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
                evidence_constraint=evidence_constraint,
            ),
        }
    )
    return repair_messages


def _message_contains_image(message: Message) -> bool:
    content = message.get("content")
    return isinstance(content, list) and any(
        isinstance(part, dict) and part.get("type") == "image_url" for part in content
    )


def _safe_prior_output(response: ModelResponse | None) -> str | None:
    if (
        not isinstance(response, ModelResponse)
        or response.tool_calls
        or not isinstance(response.content, str)
        or not response.content.strip()
        or len(response.content) > MAX_MODEL_OUTPUT_CHARS
    ):
        return None
    return response.content


def _has_image_candidate_evidence(content: str) -> bool:
    if _IMAGE_PRIVATE_EVIDENCE.search(content) is not None:
        return False
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(value, dict) or not isinstance(value.get("candidates"), list):
        return False
    return any(
        isinstance(candidate, dict)
        and candidate.get("kind") in {"place", "event"}
        and isinstance(candidate.get("title"), str)
        and 0 < len(candidate["title"].strip()) <= 200
        for candidate in value["candidates"]
    )


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
    "structured_response_format",
    "extraction_result_schema",
    "extraction_result_schema_json",
    "parse_extraction_response",
    "unsupported_extraction_result",
]

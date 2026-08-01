"""Pure, deterministic, and provider-neutral place matching rules."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from enum import StrEnum
from math import isfinite
from typing import Self
from unicodedata import category, normalize

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.domain.collections.extraction import EventCandidate, PlaceCandidate
from app.domain.places.contracts import CityScope, Coordinate, Poi, PoiProvider, PoiType

MAX_PLACE_MATCH_CANDIDATES = 3


class PlaceMatchingContract(BaseModel):
    """Immutable strict base that hides invalid inputs from validation errors."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class MatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    NEEDS_CONTEXT = "needs_context"
    NOT_FOUND = "not_found"


class MatchConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceField(StrEnum):
    NAME = "name"
    BRANCH_NAME = "branch_name"
    CITY = "city"
    DISTRICT = "district"
    BUSINESS_AREA = "business_area"
    ADDRESS = "address"
    LANDMARK = "landmark"
    METRO_STATION = "metro_station"
    PHONE = "phone"
    POI_TYPE = "poi_type"
    SOURCE_CONTEXT = "source_context"


class EvidenceOutcome(StrEnum):
    MATCH = "match"
    PARTIAL_MATCH = "partial_match"
    CONFLICT = "conflict"
    MISSING = "missing"


class EvidenceReason(StrEnum):
    EXACT = "exact"
    PARTIAL = "partial"
    CONFLICT = "conflict"
    SOURCE_MISSING = "source_missing"
    PROVIDER_MISSING = "provider_missing"
    WITHIN_SEARCH_SCOPE = "within_search_scope"
    OUTSIDE_SEARCH_SCOPE = "outside_search_scope"
    CITY_HINT_CONFLICT = "city_hint_conflict"
    CITY_HINT_UNRESOLVED = "city_hint_unresolved"
    BRANCH_CORROBORATED = "branch_corroborated"
    BRANCH_CONFLICT = "branch_conflict"
    PHONE_CORROBORATED = "phone_corroborated"
    PHONE_CONFLICT = "phone_conflict"
    TYPE_CORROBORATED = "type_corroborated"
    TYPE_CONFLICT = "type_conflict"
    CONTEXT_CORROBORATES = "context_corroborates"
    CONTEXT_NOT_DECISIVE = "context_not_decisive"


class MatchEvidence(PlaceMatchingContract):
    """One structured explanation without copied source or provider payloads."""

    field: EvidenceField
    outcome: EvidenceOutcome
    reason: EvidenceReason
    score_delta: float = Field(ge=-100, le=100)
    hard_conflict: bool = False

    @field_validator("score_delta")
    @classmethod
    def require_finite_score_delta(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("score delta must be finite")
        return round(value, 3)

    @model_validator(mode="after")
    def validate_conflict_semantics(self) -> Self:
        if self.hard_conflict and self.outcome is not EvidenceOutcome.CONFLICT:
            raise ValueError("hard conflicts require conflict evidence")
        if self.outcome is EvidenceOutcome.CONFLICT and self.score_delta > 0:
            raise ValueError("conflict evidence cannot increase a score")
        if self.outcome in {EvidenceOutcome.MATCH, EvidenceOutcome.PARTIAL_MATCH} and (
            self.score_delta < 0
        ):
            raise ValueError("matching evidence cannot decrease a score")
        if self.outcome is EvidenceOutcome.MISSING and self.score_delta != 0:
            raise ValueError("missing evidence must have zero score delta")
        return self


class EvidenceWeights(PlaceMatchingContract):
    """The single ordered weight set used by the scoring function."""

    name: float = Field(default=35.0, gt=0, le=100)
    branch_name: float = Field(default=5.0, gt=0, le=100)
    district: float = Field(default=15.0, gt=0, le=100)
    business_area: float = Field(default=2.0, gt=0, le=100)
    address: float = Field(default=25.0, gt=0, le=100)
    landmark: float = Field(default=2.0, gt=0, le=100)
    metro_station: float = Field(default=2.0, gt=0, le=100)
    phone: float = Field(default=3.0, gt=0, le=100)
    poi_type: float = Field(default=3.0, gt=0, le=100)
    source_context: float = Field(default=2.0, gt=0, le=100)

    @model_validator(mode="after")
    def validate_total_weight(self) -> Self:
        total = sum(
            (
                self.name,
                self.branch_name,
                self.district,
                self.business_area,
                self.address,
                self.landmark,
                self.metro_station,
                self.phone,
                self.poi_type,
                self.source_context,
            )
        )
        if not isfinite(total) or total > 100:
            raise ValueError("place matching weights must have a finite total at most 100")
        return self


class PlaceMatchingPolicy(PlaceMatchingContract):
    """Validated thresholds and weights injected into every matching call."""

    unique_match_score: float = Field(gt=0, le=100)
    minimum_score_gap: float = Field(gt=0, le=100)
    candidate_score: float = Field(gt=0, le=100)
    partial_match_factor: float = Field(default=0.75, gt=0, lt=1)
    weights: EvidenceWeights = Field(default_factory=EvidenceWeights)

    @field_validator(
        "unique_match_score",
        "minimum_score_gap",
        "candidate_score",
        "partial_match_factor",
        mode="before",
    )
    @classmethod
    def reject_boolean_or_non_finite_threshold(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("place matching thresholds must be finite numbers")
        if isinstance(value, int | float) and not isfinite(value):
            raise ValueError("place matching thresholds must be finite numbers")
        return value

    @model_validator(mode="after")
    def validate_threshold_order(self) -> Self:
        if self.candidate_score > self.unique_match_score:
            raise ValueError("candidate score cannot exceed unique match score")
        return self


class PlaceMatchRequest(PlaceMatchingContract):
    """One request-local search scope plus source data that remains private."""

    candidate: PlaceCandidate | EventCandidate = Field(repr=False)
    city: CityScope
    search_district: str | None = Field(default=None, max_length=100, repr=False)
    search_location: Coordinate | None = Field(default=None, repr=False)
    source_context: SecretStr | None = Field(default=None, repr=False)

    @field_validator("source_context", mode="before")
    @classmethod
    def validate_source_context(cls, value: object) -> object:
        if value is None:
            return value
        if isinstance(value, SecretStr):
            raw = value.get_secret_value()
        elif isinstance(value, str):
            raw = value
            value = SecretStr(value)
        else:
            return value
        if len(raw) > 20_000:
            raise ValueError("source context is too long")
        return value


class PlaceMatchCandidate(PlaceMatchingContract):
    """One safe normalized POI candidate with a deterministic rank and score."""

    provider: PoiProvider
    poi_id: str = Field(min_length=1, max_length=128)
    city_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    coordinate: Coordinate = Field(repr=False)
    name: str = Field(min_length=1, max_length=200)
    branch_name: str | None = Field(default=None, max_length=160)
    district: str | None = Field(default=None, max_length=100)
    business_area: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=500)
    poi_type: PoiType
    opening_hours_summary: str | None = Field(default=None, max_length=240)
    provider_rank: int = Field(ge=1)
    rank: int = Field(ge=1, le=MAX_PLACE_MATCH_CANDIDATES)
    score: float = Field(ge=0, le=100)
    confidence: MatchConfidence
    evidence: tuple[MatchEvidence, ...]

    @field_validator("score")
    @classmethod
    def require_finite_score(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("score must be finite")
        return round(value, 3)

    @field_validator("evidence")
    @classmethod
    def normalize_evidence(
        cls,
        value: tuple[MatchEvidence, ...],
    ) -> tuple[MatchEvidence, ...]:
        fields = tuple(item.field for item in value)
        if len(set(fields)) != len(fields):
            raise ValueError("candidate evidence fields must be unique")
        if not {EvidenceField.NAME, EvidenceField.CITY}.issubset(fields):
            raise ValueError("candidate evidence must retain core identity fields")
        order = {field: index for index, field in enumerate(EvidenceField)}
        return tuple(sorted(value, key=lambda item: order[item.field]))

    @property
    def identity(self) -> tuple[PoiProvider, str]:
        return (self.provider, self.poi_id)

    @property
    def has_hard_conflict(self) -> bool:
        return any(item.hard_conflict for item in self.evidence)


class PlaceMatchResult(PlaceMatchingContract):
    """A complete match decision containing at most three normalized candidates."""

    status: MatchStatus
    candidates: tuple[PlaceMatchCandidate, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PLACE_MATCH_CANDIDATES,
    )

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        identities = tuple(candidate.identity for candidate in self.candidates)
        if len(set(identities)) != len(identities):
            raise ValueError("match candidates must have unique provider and POI identities")
        if tuple(candidate.rank for candidate in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("candidate ranks must be consecutive and ordered")
        if self.status is MatchStatus.NOT_FOUND and self.candidates:
            raise ValueError("not-found results cannot carry candidates")
        if self.status in {MatchStatus.MATCHED, MatchStatus.AMBIGUOUS} and not self.candidates:
            raise ValueError("matched and ambiguous outcomes require candidates")
        if any(candidate.has_hard_conflict for candidate in self.candidates):
            raise ValueError("public match candidates cannot carry hard conflicts")
        return self


def poi_from_match_candidate(candidate: PlaceMatchCandidate) -> Poi:
    """Project a normalized match candidate into the existing internal POI DTO."""

    return Poi(
        provider=candidate.provider,
        poi_id=candidate.poi_id,
        name=candidate.name,
        branch_name=candidate.branch_name,
        city_code=candidate.city_code,
        district=candidate.district,
        business_area=candidate.business_area,
        address=candidate.address,
        coordinate=candidate.coordinate.model_copy(deep=True),
        poi_type=candidate.poi_type,
        opening_hours_summary=candidate.opening_hours_summary,
    )


class PlaceSelectionKind(StrEnum):
    CANDIDATE = "candidate"
    ANY_BRANCH = "any_branch"
    NONE_OF_ABOVE = "none_of_above"


class PlaceSelection(PlaceMatchingContract):
    """An explicit user choice; it carries no persistence behavior."""

    kind: PlaceSelectionKind
    provider: PoiProvider | None = None
    poi_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_choice_shape(self) -> Self:
        has_identity = self.provider is not None and self.poi_id is not None
        if self.kind is PlaceSelectionKind.CANDIDATE and not has_identity:
            raise ValueError("candidate selections require one provider and POI identity")
        if self.kind is not PlaceSelectionKind.CANDIDATE and (
            self.provider is not None or self.poi_id is not None
        ):
            raise ValueError("non-candidate selections cannot carry a POI identity")
        return self


def validate_place_selection(
    result: PlaceMatchResult,
    selection: PlaceSelection,
) -> PlaceSelection:
    """Validate one explicit choice against the exact current candidate snapshot."""

    if not result.candidates:
        raise ValueError("selection is not available without current candidates")
    if selection.kind is PlaceSelectionKind.CANDIDATE:
        identity = (selection.provider, selection.poi_id)
        if sum(candidate.identity == identity for candidate in result.candidates) != 1:
            raise ValueError("selected POI is not a unique member of current candidates")
    return selection.model_copy(deep=True)


_PUNCTUATION_OR_SPACE = re.compile(r"[\W_]+", flags=re.UNICODE)
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?(\d(?:[- ]?\d){6,14})(?!\d)")
_BRANCH = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]{2,18}(?:分店|店)")

_GENERIC_PLACE_SUFFIXES: tuple[str, ...] = (
    "咖啡店",
    "咖啡馆",
    "书店",
    "餐厅",
    "餐馆",
    "饭店",
    "酒家",
    "茶饮店",
    "奶茶店",
    "甜品店",
    "面包店",
    "蛋糕店",
    "便利店",
    "火锅店",
)

_CITY_HINT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("shenzhen", ("shenzhen", "深圳", "深圳市")),
    ("guangzhou", ("guangzhou", "canton", "广州", "广州市")),
)

_TYPE_ALIASES: tuple[tuple[PoiType, tuple[str, ...]], ...] = (
    (PoiType.MUSEUM, ("museum", "博物馆", "美术馆", "艺术馆", "展馆")),
    (PoiType.CAFE, ("cafe", "coffee", "咖啡")),
    (PoiType.RESTAURANT, ("restaurant", "餐厅", "餐馆", "饭店", "酒家", "火锅")),
    (PoiType.PARK, ("park", "公园")),
    (PoiType.ATTRACTION, ("attraction", "景点", "景区")),
    (PoiType.SHOPPING, ("shopping", "商场", "购物中心", "商城")),
    (PoiType.TRANSIT, ("transit", "地铁站", "火车站", "汽车站")),
)


def _compact(value: str | None) -> str:
    if not value:
        return ""
    normalized = normalize("NFKC", value).casefold()
    return _PUNCTUATION_OR_SPACE.sub("", normalized)


def resolve_city_hint(value: str | None) -> tuple[bool, str | None]:
    """Resolve supported hints through the single future CityCatalog integration point."""

    if value is None:
        return (False, None)
    normalized = _compact(value)
    for city_code, aliases in _CITY_HINT_ALIASES:
        if normalized in {_compact(alias) for alias in aliases}:
            return (True, city_code)
    # A supplied but unsupported hint is deliberately distinct from no hint. U1 can
    # replace this resolver with the shared CityCatalog without changing scoring.
    return (True, None)


def _require_safe_policy(policy: PlaceMatchingPolicy) -> None:
    thresholds = (
        policy.unique_match_score,
        policy.minimum_score_gap,
        policy.candidate_score,
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value <= 0
        or value > 100
        for value in thresholds
    ) or policy.candidate_score > policy.unique_match_score:
        raise ValueError("place matching policy thresholds are invalid")


def _relation(left: str | None, right: str | None) -> EvidenceOutcome:
    left_text = _compact(left)
    right_text = _compact(right)
    if not left_text:
        return EvidenceOutcome.MISSING
    if not right_text:
        return EvidenceOutcome.MISSING
    if left_text == right_text:
        return EvidenceOutcome.MATCH
    shorter, longer = sorted((left_text, right_text), key=len)
    if len(shorter) >= 2 and shorter in longer:
        return EvidenceOutcome.PARTIAL_MATCH
    if SequenceMatcher(a=left_text, b=right_text, autojunk=False).ratio() >= 0.72:
        return EvidenceOutcome.PARTIAL_MATCH
    return EvidenceOutcome.CONFLICT


def _reason_for_relation(outcome: EvidenceOutcome) -> EvidenceReason:
    return {
        EvidenceOutcome.MATCH: EvidenceReason.EXACT,
        EvidenceOutcome.PARTIAL_MATCH: EvidenceReason.PARTIAL,
        EvidenceOutcome.CONFLICT: EvidenceReason.CONFLICT,
        EvidenceOutcome.MISSING: EvidenceReason.SOURCE_MISSING,
    }[outcome]


def _weighted_evidence(
    *,
    field: EvidenceField,
    source: str | None,
    provider: str | None,
    weight: float,
    partial_factor: float,
    hard_conflict: bool = False,
) -> MatchEvidence:
    if not source:
        return MatchEvidence(
            field=field,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.SOURCE_MISSING,
            score_delta=0.0,
        )
    if not provider:
        return MatchEvidence(
            field=field,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.PROVIDER_MISSING,
            score_delta=0.0,
        )
    outcome = _relation(source, provider)
    delta = {
        EvidenceOutcome.MATCH: weight,
        EvidenceOutcome.PARTIAL_MATCH: weight * partial_factor,
        EvidenceOutcome.CONFLICT: -weight,
        EvidenceOutcome.MISSING: 0.0,
    }[outcome]
    return MatchEvidence(
        field=field,
        outcome=outcome,
        reason=_reason_for_relation(outcome),
        score_delta=delta,
        hard_conflict=hard_conflict and outcome is EvidenceOutcome.CONFLICT,
    )


def _source_context(request: PlaceMatchRequest) -> str:
    if request.source_context is None:
        return ""
    value = request.source_context.get_secret_value()
    return "".join(character for character in value if not category(character).startswith("C"))


def _name_without_branch(poi: Poi) -> str:
    name = _compact(poi.name)
    branch = _compact(poi.branch_name)
    if branch and branch in name:
        return name.replace(branch, "", 1)
    return name


def _name_source(candidate_title: str, provider_name: str) -> str:
    """Ignore a generic business suffix only when it merely extends the POI name."""

    source = _compact(candidate_title)
    provider = _compact(provider_name)
    suffixes = ("店", *_GENERIC_PLACE_SUFFIXES)
    if source in {f"{provider}{_compact(suffix)}" for suffix in suffixes}:
        return provider_name
    return candidate_title


def _specific_branch_clues(corpus: str) -> tuple[str, ...]:
    clues: list[str] = []
    for item in _BRANCH.findall(normalize("NFKC", corpus)):
        compact = _compact(item)
        if item == "这家店" or compact in {"店", "分店"}:
            continue
        if any(compact.endswith(_compact(suffix)) for suffix in _GENERIC_PLACE_SUFFIXES):
            continue
        if item not in clues:
            clues.append(item)
    return tuple(clues)


def _branch_evidence(
    *,
    candidate: PlaceCandidate,
    poi: Poi,
    context: str,
    weight: float,
) -> MatchEvidence:
    if poi.branch_name is None:
        return MatchEvidence(
            field=EvidenceField.BRANCH_NAME,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.PROVIDER_MISSING,
            score_delta=0.0,
        )
    corpus = f"{candidate.title} {context}"
    branch = _compact(poi.branch_name)
    if branch and branch in _compact(corpus):
        return MatchEvidence(
            field=EvidenceField.BRANCH_NAME,
            outcome=EvidenceOutcome.MATCH,
            reason=EvidenceReason.BRANCH_CORROBORATED,
            score_delta=weight,
        )
    explicit_branches = _specific_branch_clues(corpus)
    if explicit_branches:
        return MatchEvidence(
            field=EvidenceField.BRANCH_NAME,
            outcome=EvidenceOutcome.CONFLICT,
            reason=EvidenceReason.BRANCH_CONFLICT,
            score_delta=-weight,
        )
    return MatchEvidence(
        field=EvidenceField.BRANCH_NAME,
        outcome=EvidenceOutcome.MISSING,
        reason=EvidenceReason.SOURCE_MISSING,
        score_delta=0.0,
    )


def _phone_evidence(*, poi: Poi, context: str, weight: float) -> MatchEvidence:
    source_phones = tuple(
        re.sub(r"\D", "", match.group(1)) for match in _PHONE.finditer(context)
    )
    if not source_phones:
        return MatchEvidence(
            field=EvidenceField.PHONE,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.SOURCE_MISSING,
            score_delta=0.0,
        )
    provider_phones = tuple(
        re.sub(r"\D", "", match.group(1)) for match in _PHONE.finditer(poi.phone or "")
    )
    if not provider_phones:
        return MatchEvidence(
            field=EvidenceField.PHONE,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.PROVIDER_MISSING,
            score_delta=0.0,
        )
    matches = any(
        source.endswith(provider) or provider.endswith(source)
        for source in source_phones
        for provider in provider_phones
    )
    return MatchEvidence(
        field=EvidenceField.PHONE,
        outcome=EvidenceOutcome.MATCH if matches else EvidenceOutcome.CONFLICT,
        reason=(
            EvidenceReason.PHONE_CORROBORATED if matches else EvidenceReason.PHONE_CONFLICT
        ),
        score_delta=weight if matches else -weight,
    )


def _type_evidence(
    *,
    candidate: PlaceCandidate,
    poi: Poi,
    context: str,
    weight: float,
) -> MatchEvidence:
    corpus = _compact(" ".join((candidate.title, *candidate.tags, context)))
    source_types = tuple(
        poi_type
        for poi_type, aliases in _TYPE_ALIASES
        if any(_compact(alias) in corpus for alias in aliases)
    )
    if not source_types:
        return MatchEvidence(
            field=EvidenceField.POI_TYPE,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.SOURCE_MISSING,
            score_delta=0.0,
        )
    matches = poi.poi_type in source_types
    return MatchEvidence(
        field=EvidenceField.POI_TYPE,
        outcome=EvidenceOutcome.MATCH if matches else EvidenceOutcome.CONFLICT,
        reason=(
            EvidenceReason.TYPE_CORROBORATED if matches else EvidenceReason.TYPE_CONFLICT
        ),
        score_delta=weight if matches else -weight,
    )


def _context_evidence(*, poi: Poi, context: str, weight: float) -> MatchEvidence:
    compact_context = _compact(context)
    if not compact_context:
        return MatchEvidence(
            field=EvidenceField.SOURCE_CONTEXT,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.SOURCE_MISSING,
            score_delta=0.0,
        )
    corroborates = any(
        len(value) >= 2 and value in compact_context
        for value in (
            _compact(poi.name),
            _compact(poi.branch_name),
            _compact(poi.district),
            _compact(poi.business_area),
            _compact(poi.address),
        )
    )
    return MatchEvidence(
        field=EvidenceField.SOURCE_CONTEXT,
        outcome=EvidenceOutcome.MATCH if corroborates else EvidenceOutcome.MISSING,
        reason=(
            EvidenceReason.CONTEXT_CORROBORATES
            if corroborates
            else EvidenceReason.CONTEXT_NOT_DECISIVE
        ),
        score_delta=weight if corroborates else 0.0,
    )


def score_place_candidate(
    *,
    request: PlaceMatchRequest,
    poi: Poi,
    provider_rank: int,
    policy: PlaceMatchingPolicy,
) -> PlaceMatchCandidate:
    """Score one POI without mutation, I/O, shared state, or retained source text."""

    if not isinstance(request.candidate, PlaceCandidate):
        raise TypeError("Event candidates cannot enter POI matching")
    if provider_rank < 1:
        raise ValueError("provider rank must be positive")
    _require_safe_policy(policy)

    candidate = request.candidate
    context = _source_context(request)
    weights = policy.weights
    poi_haystack = " ".join(
        value
        for value in (
            poi.name,
            poi.branch_name,
            poi.district,
            poi.business_area,
            poi.address,
        )
        if value
    )
    has_city_hint, hinted_city = resolve_city_hint(candidate.city_hint)
    unresolved_city_hint = has_city_hint and hinted_city is None
    within_search_scope = poi.city_code == request.city.city_code
    city_hint_conflicts = (
        hinted_city is not None and hinted_city != request.city.city_code
    )
    city_matches = (
        within_search_scope and not unresolved_city_hint and not city_hint_conflicts
    )
    provider_name = _name_without_branch(poi)
    evidence = (
        _weighted_evidence(
            field=EvidenceField.NAME,
            source=_name_source(candidate.title, provider_name),
            provider=provider_name,
            weight=weights.name,
            partial_factor=policy.partial_match_factor,
            hard_conflict=True,
        ),
        _branch_evidence(
            candidate=candidate,
            poi=poi,
            context=context,
            weight=weights.branch_name,
        ),
        MatchEvidence(
            field=EvidenceField.CITY,
            outcome=EvidenceOutcome.MATCH if city_matches else EvidenceOutcome.CONFLICT,
            reason=(
                EvidenceReason.WITHIN_SEARCH_SCOPE
                if city_matches
                else (
                    EvidenceReason.CITY_HINT_UNRESOLVED
                    if unresolved_city_hint
                    else (
                        EvidenceReason.CITY_HINT_CONFLICT
                        if city_hint_conflicts
                        else EvidenceReason.OUTSIDE_SEARCH_SCOPE
                    )
                )
            ),
            # Search scope is a hard boundary, never positive proof of confirmed city.
            score_delta=0.0,
            hard_conflict=not city_matches,
        ),
        _weighted_evidence(
            field=EvidenceField.DISTRICT,
            source=candidate.district,
            provider=poi.district,
            weight=weights.district,
            partial_factor=policy.partial_match_factor,
        ),
        _weighted_evidence(
            field=EvidenceField.BUSINESS_AREA,
            source=candidate.business_district,
            provider=poi.business_area,
            weight=weights.business_area,
            partial_factor=policy.partial_match_factor,
        ),
        _weighted_evidence(
            field=EvidenceField.ADDRESS,
            source=candidate.address,
            provider=poi.address,
            weight=weights.address,
            partial_factor=policy.partial_match_factor,
        ),
        _weighted_evidence(
            field=EvidenceField.LANDMARK,
            source=candidate.landmark,
            provider=poi_haystack,
            weight=weights.landmark,
            partial_factor=policy.partial_match_factor,
        ),
        _weighted_evidence(
            field=EvidenceField.METRO_STATION,
            source=candidate.metro_station,
            provider=poi_haystack,
            weight=weights.metro_station,
            partial_factor=policy.partial_match_factor,
        ),
        _phone_evidence(poi=poi, context=context, weight=weights.phone),
        _type_evidence(candidate=candidate, poi=poi, context=context, weight=weights.poi_type),
        _context_evidence(poi=poi, context=context, weight=weights.source_context),
    )
    score = round(max(0.0, min(100.0, sum(item.score_delta for item in evidence))), 3)
    hard_conflict = any(item.hard_conflict for item in evidence)
    confidence = (
        MatchConfidence.LOW
        if hard_conflict or score < policy.candidate_score
        else (
            MatchConfidence.HIGH
            if score >= policy.unique_match_score
            else MatchConfidence.MEDIUM
        )
    )
    return PlaceMatchCandidate(
        provider=poi.provider,
        poi_id=poi.poi_id,
        city_code=poi.city_code,
        coordinate=poi.coordinate.model_copy(deep=True),
        name=poi.name,
        branch_name=poi.branch_name,
        district=poi.district,
        business_area=poi.business_area,
        address=poi.address,
        poi_type=poi.poi_type,
        opening_hours_summary=poi.opening_hours_summary,
        provider_rank=provider_rank,
        rank=1,
        score=score,
        confidence=confidence,
        evidence=evidence,
    )


def classify_place_matches(
    scored_candidates: tuple[PlaceMatchCandidate, ...],
    *,
    policy: PlaceMatchingPolicy,
) -> PlaceMatchResult:
    """Sort and classify scored candidates using only deterministic rules."""

    _require_safe_policy(policy)
    identities = tuple(candidate.identity for candidate in scored_candidates)
    if len(set(identities)) != len(identities):
        raise ValueError("scored candidates contain duplicate provider and POI identities")
    ordered = sorted(
        scored_candidates,
        key=lambda candidate: (
            -candidate.score,
            candidate.provider_rank,
            candidate.provider.value,
            candidate.poi_id,
        ),
    )
    reasonable = tuple(
        candidate
        for candidate in ordered
        if not candidate.has_hard_conflict
    )
    selected = tuple(
        candidate.model_copy(update={"rank": index}, deep=True)
        for index, candidate in enumerate(reasonable[:MAX_PLACE_MATCH_CANDIDATES], start=1)
    )
    if not ordered:
        return PlaceMatchResult(status=MatchStatus.NOT_FOUND)
    if not selected:
        return PlaceMatchResult(status=MatchStatus.NEEDS_CONTEXT)

    top = selected[0]
    competitor_scores = tuple(
        candidate.score for candidate in reasonable if candidate.identity != top.identity
    )
    gap = top.score - max(competitor_scores) if competitor_scores else 100.0
    if (
        top.score >= policy.unique_match_score
        and gap >= policy.minimum_score_gap
        and gap > 0
        and not top.has_hard_conflict
    ):
        return PlaceMatchResult(status=MatchStatus.MATCHED, candidates=selected)

    status = MatchStatus.AMBIGUOUS if len(selected) >= 2 else MatchStatus.NEEDS_CONTEXT
    return PlaceMatchResult(status=status, candidates=selected)

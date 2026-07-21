"""Strict provider-neutral contracts for M0-2B text extraction."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.collections.entities import CollectionKind
from app.domain.time import require_aware_utc

MAX_EXTRACTION_CANDIDATES = 10

_SENSITIVE_TEXT = re.compile(
    r"(?:authorization\s*[:=]|set-cookie\s*:|cookie\s*[:=]|bearer\s+\S+|"
    r"api[-_ ]?key\s*[:=]|\bsk-[a-z0-9]{8,})",
    re.IGNORECASE,
)


class ExtractionOutcome(StrEnum):
    """Mutually exclusive outcomes of one text extraction attempt."""

    CANDIDATES = "candidates"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    UNSUPPORTED = "unsupported"
    MODEL_INVALID_OUTPUT = "model_invalid_output"


class ExtractionReasonCode(StrEnum):
    """Stable application reason codes exposed without provider details."""

    INPUT_EMPTY = "INPUT_EMPTY"
    INPUT_UNSUPPORTED = "INPUT_UNSUPPORTED"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    MODEL_INVALID_OUTPUT = "MODEL_INVALID_OUTPUT"


class UnsupportedReason(StrEnum):
    """Stable detail for content classified as ``INPUT_UNSUPPORTED``."""

    PRODUCT = "product"
    RECIPE = "recipe"
    MULTI_CITY_TRAVEL = "multi_city_travel"
    COMPLEX_OUTDOOR_ROUTE = "complex_outdoor_route"
    CONTENT_TOO_LONG = "content_too_long"
    OTHER = "other"


class CandidateField(StrEnum):
    """Provider-neutral fields that can be missing or uncertain."""

    TITLE = "title"
    CITY_HINT = "city_hint"
    DISTRICT = "district"
    ADDRESS = "address"
    BUSINESS_DISTRICT = "business_district"
    LANDMARK = "landmark"
    METRO_STATION = "metro_station"
    EVENT_START_AT = "event_start_at"
    EVENT_END_AT = "event_end_at"
    PRICE = "price"
    TAGS = "tags"


class ExtractionDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")
    if _SENSITIVE_TEXT.search(normalized) is not None:
        raise ValueError(f"{field_name} contains disallowed sensitive text")
    return normalized


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_required_text(value, field_name=field_name)


class Uncertainty(ExtractionDomainModel):
    """A field whose value or interpretation still needs confirmation."""

    field: CandidateField
    reason: str = Field(min_length=1, max_length=240, repr=False)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="uncertainty reason")


class _CandidateBase(ExtractionDomainModel):
    title: str = Field(min_length=1, max_length=200, repr=False)
    city_hint: str | None = Field(default=None, max_length=100, repr=False)
    district: str | None = Field(default=None, max_length=100, repr=False)
    address: str | None = Field(default=None, max_length=500, repr=False)
    business_district: str | None = Field(default=None, max_length=100, repr=False)
    landmark: str | None = Field(default=None, max_length=160, repr=False)
    metro_station: str | None = Field(default=None, max_length=100, repr=False)
    price_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        repr=False,
    )
    price_currency: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{3}$",
        repr=False,
    )
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=20, repr=False)
    missing_fields: tuple[CandidateField, ...] = Field(
        default_factory=tuple,
        max_length=len(CandidateField),
        repr=False,
    )
    uncertainties: tuple[Uncertainty, ...] = Field(
        default_factory=tuple,
        max_length=len(CandidateField),
        repr=False,
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="title")

    @field_validator(
        "district",
        "address",
        "business_district",
        "landmark",
        "metro_station",
    )
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="candidate text")

    @field_validator("city_hint", mode="before")
    @classmethod
    def normalize_city_hint(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        return _normalize_required_text(value, field_name="city_hint")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for tag in value:
            clean = _normalize_required_text(tag, field_name="tag")
            if len(clean) > 64:
                raise ValueError("tags must be at most 64 characters")
            key = clean.casefold()
            if key in seen:
                raise ValueError("tags must be unique")
            seen.add(key)
            normalized.append(clean)
        return tuple(normalized)

    @model_validator(mode="after")
    def validate_common_semantics(self) -> Self:
        if (self.price_amount is None) is not (self.price_currency is None):
            raise ValueError("price amount and currency must be provided together")

        missing = set(self.missing_fields)
        if len(missing) != len(self.missing_fields):
            raise ValueError("missing_fields must be unique")
        uncertain_fields = [item.field for item in self.uncertainties]
        if len(set(uncertain_fields)) != len(uncertain_fields):
            raise ValueError("uncertainties must contain at most one reason per field")
        if missing.intersection(uncertain_fields):
            raise ValueError("a field cannot be both missing and uncertain")

        present_fields = {
            CandidateField.CITY_HINT: self.city_hint is not None,
            CandidateField.DISTRICT: self.district is not None,
            CandidateField.ADDRESS: self.address is not None,
            CandidateField.BUSINESS_DISTRICT: self.business_district is not None,
            CandidateField.LANDMARK: self.landmark is not None,
            CandidateField.METRO_STATION: self.metro_station is not None,
            CandidateField.PRICE: self.price_amount is not None,
            CandidateField.TAGS: bool(self.tags),
        }
        for field, is_present in present_fields.items():
            if is_present and field in missing:
                raise ValueError(f"{field.value} cannot be both present and missing")
            if not is_present and field not in missing and field not in uncertain_fields:
                raise ValueError(f"absent {field.value} must be marked missing or uncertain")
        return self


class PlaceCandidate(_CandidateBase):
    """An any-city place candidate without Event-only schedule fields."""

    kind: Literal[CollectionKind.PLACE] = CollectionKind.PLACE

    @model_validator(mode="after")
    def reject_event_only_metadata(self) -> Self:
        fields = set(self.missing_fields).union(item.field for item in self.uncertainties)
        if fields.intersection({CandidateField.EVENT_START_AT, CandidateField.EVENT_END_AT}):
            raise ValueError("Place candidates cannot carry Event schedule metadata")
        return self


class EventCandidate(_CandidateBase):
    """A user-supplied Event candidate with exact times or explicit gaps."""

    kind: Literal[CollectionKind.EVENT] = CollectionKind.EVENT
    event_start_at: datetime | None = Field(default=None, repr=False)
    event_end_at: datetime | None = Field(default=None, repr=False)
    event_start_clue: str | None = Field(default=None, max_length=120, repr=False)
    event_end_clue: str | None = Field(default=None, max_length=120, repr=False)

    @field_validator("event_start_at", "event_end_at")
    @classmethod
    def normalize_event_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_aware_utc(value)

    @field_validator("event_start_clue", "event_end_clue")
    @classmethod
    def validate_time_clue(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="event time clue")

    @model_validator(mode="after")
    def validate_event_schedule(self) -> Self:
        if self.event_start_at is not None and self.event_end_at is not None:
            if self.event_end_at <= self.event_start_at:
                raise ValueError("event_end_at must be after event_start_at")

        missing = set(self.missing_fields)
        uncertain = {item.field for item in self.uncertainties}
        for field, value in (
            (CandidateField.EVENT_START_AT, self.event_start_at),
            (CandidateField.EVENT_END_AT, self.event_end_at),
        ):
            if value is not None and field in missing:
                raise ValueError(f"{field.value} cannot be both present and missing")
            if value is None and field not in missing and field not in uncertain:
                raise ValueError(f"absent {field.value} must be marked missing or uncertain")
        return self


ExtractionCandidate = Annotated[
    PlaceCandidate | EventCandidate,
    Field(discriminator="kind"),
]


class ExtractionResult(ExtractionDomainModel):
    """One safe result that never represents failures as empty successes."""

    outcome: ExtractionOutcome
    candidates: tuple[ExtractionCandidate, ...] = Field(
        default_factory=tuple,
        max_length=MAX_EXTRACTION_CANDIDATES,
        repr=False,
    )
    reason_code: ExtractionReasonCode | None = None
    unsupported_reason: UnsupportedReason | None = None
    missing_fields: tuple[CandidateField, ...] = Field(
        default_factory=tuple,
        max_length=len(CandidateField),
        repr=False,
    )
    uncertainties: tuple[Uncertainty, ...] = Field(
        default_factory=tuple,
        max_length=len(CandidateField),
        repr=False,
    )
    recovery_suggestions: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=4,
        repr=False,
    )

    @field_validator("missing_fields")
    @classmethod
    def validate_missing_fields(
        cls,
        value: tuple[CandidateField, ...],
    ) -> tuple[CandidateField, ...]:
        if len(set(value)) != len(value):
            raise ValueError("missing_fields must be unique")
        return value

    @field_validator("uncertainties")
    @classmethod
    def validate_uncertainties(
        cls,
        value: tuple[Uncertainty, ...],
    ) -> tuple[Uncertainty, ...]:
        fields = [item.field for item in value]
        if len(set(fields)) != len(fields):
            raise ValueError("uncertainties must contain at most one reason per field")
        return value

    @field_validator("recovery_suggestions")
    @classmethod
    def validate_recovery_suggestions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for suggestion in value:
            clean = _normalize_required_text(suggestion, field_name="recovery suggestion")
            if len(clean) > 240:
                raise ValueError("recovery suggestions must be at most 240 characters")
            if clean in seen:
                raise ValueError("recovery suggestions must be unique")
            seen.add(clean)
            normalized.append(clean)
        return tuple(normalized)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if set(self.missing_fields).intersection(item.field for item in self.uncertainties):
            raise ValueError("a field cannot be both missing and uncertain")

        if self.outcome is ExtractionOutcome.CANDIDATES:
            if not self.candidates:
                raise ValueError("candidate outcomes require at least one candidate")
            if (
                self.reason_code is not None
                or self.unsupported_reason is not None
                or self.missing_fields
                or self.uncertainties
                or self.recovery_suggestions
            ):
                raise ValueError("candidate outcomes cannot carry result-level errors")
            return self

        if self.candidates:
            raise ValueError("non-candidate outcomes cannot carry candidates")

        if self.outcome is ExtractionOutcome.INSUFFICIENT_INFORMATION:
            if self.reason_code is not ExtractionReasonCode.INSUFFICIENT_INFORMATION:
                raise ValueError("insufficient outcomes require their stable reason code")
            if self.unsupported_reason is not None:
                raise ValueError("insufficient outcomes cannot carry unsupported_reason")
            if not (self.missing_fields or self.uncertainties):
                raise ValueError("insufficient outcomes must identify an information gap")
            if not self.recovery_suggestions:
                raise ValueError("insufficient outcomes require a recovery suggestion")
            return self

        if self.outcome is ExtractionOutcome.UNSUPPORTED:
            allowed = {
                ExtractionReasonCode.INPUT_EMPTY,
                ExtractionReasonCode.INPUT_UNSUPPORTED,
            }
            if self.reason_code not in allowed:
                raise ValueError("unsupported outcomes require a stable unsupported code")
            if (self.reason_code is ExtractionReasonCode.INPUT_UNSUPPORTED) is not (
                self.unsupported_reason is not None
            ):
                raise ValueError("unsupported_reason is required only for INPUT_UNSUPPORTED")
            if self.missing_fields or self.uncertainties:
                raise ValueError("unsupported outcomes cannot carry candidate field gaps")
            return self

        if self.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT:
            if self.reason_code is not ExtractionReasonCode.MODEL_INVALID_OUTPUT:
                raise ValueError("model-invalid outcomes require MODEL_INVALID_OUTPUT")
            if self.unsupported_reason is not None or self.missing_fields or self.uncertainties:
                raise ValueError("model-invalid outcomes cannot carry model-derived details")
            return self

        raise ValueError("unknown extraction outcome")

    @classmethod
    def with_candidates(
        cls,
        candidates: tuple[PlaceCandidate | EventCandidate, ...],
    ) -> ExtractionResult:
        return cls(outcome=ExtractionOutcome.CANDIDATES, candidates=candidates)

    @classmethod
    def insufficient(
        cls,
        *,
        missing_fields: tuple[CandidateField, ...],
        uncertainties: tuple[Uncertainty, ...] = (),
        recovery_suggestions: tuple[str, ...],
    ) -> ExtractionResult:
        return cls(
            outcome=ExtractionOutcome.INSUFFICIENT_INFORMATION,
            reason_code=ExtractionReasonCode.INSUFFICIENT_INFORMATION,
            missing_fields=missing_fields,
            uncertainties=uncertainties,
            recovery_suggestions=recovery_suggestions,
        )

    @classmethod
    def unsupported(
        cls,
        *,
        reason_code: ExtractionReasonCode,
        unsupported_reason: UnsupportedReason | None = None,
        recovery_suggestions: tuple[str, ...] = (),
    ) -> ExtractionResult:
        return cls(
            outcome=ExtractionOutcome.UNSUPPORTED,
            reason_code=reason_code,
            unsupported_reason=unsupported_reason,
            recovery_suggestions=recovery_suggestions,
        )

    @classmethod
    def model_invalid(cls) -> ExtractionResult:
        return cls(
            outcome=ExtractionOutcome.MODEL_INVALID_OUTPUT,
            reason_code=ExtractionReasonCode.MODEL_INVALID_OUTPUT,
            recovery_suggestions=("请稍后重试结构化抽取。",),
        )

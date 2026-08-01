"""Strict provider-neutral contracts for M0-2B text extraction."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.domain.collections.candidate_metadata import (
    CandidateField,
    Uncertainty,
    normalize_optional_candidate_text,
    normalize_required_candidate_text,
    validate_cny_price_pair,
    validate_event_date_range,
)
from app.domain.collections.types import CollectionKind
from app.domain.time import require_aware_utc

MAX_EXTRACTION_CANDIDATES = 10


def _semantic_error(error_type: str) -> PydanticCustomError:
    return PydanticCustomError(
        error_type,
        "Extraction semantic contract violation.",
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


class ExtractionDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _normalize_required_text(value: str, *, field_name: str) -> str:
    return normalize_required_candidate_text(value, field_name=field_name)


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    return normalize_optional_candidate_text(value, field_name=field_name)


class _CandidateBase(ExtractionDomainModel):
    """Shared candidate fields with explicit missing/uncertain classification."""

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
        validate_cny_price_pair(self.price_amount, self.price_currency)

        missing = set(self.missing_fields)
        if len(missing) != len(self.missing_fields):
            raise _semantic_error("duplicate_missing_field")
        uncertain_fields = [item.field for item in self.uncertainties]
        if len(set(uncertain_fields)) != len(uncertain_fields):
            raise _semantic_error("duplicate_uncertainty_field")
        if missing.intersection(uncertain_fields):
            raise _semantic_error("missing_and_uncertain_conflict")

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
                raise _semantic_error("present_field_marked_missing")
        return self


class PlaceCandidate(_CandidateBase):
    """An any-city Place; Event schedule fields cannot be missing or uncertain metadata."""

    kind: Literal[CollectionKind.PLACE] = CollectionKind.PLACE

    @model_validator(mode="after")
    def reject_event_only_metadata(self) -> Self:
        fields = set(self.missing_fields).union(item.field for item in self.uncertainties)
        if fields.intersection(
            {
                CandidateField.EVENT_START_DATE,
                CandidateField.EVENT_END_DATE,
                CandidateField.EVENT_START_AT,
                CandidateField.EVENT_END_AT,
            }
        ):
            raise _semantic_error("place_has_event_metadata")
        return self


class EventCandidate(_CandidateBase):
    """A user-supplied Event with distinct calendar dates and exact-time facts."""

    kind: Literal[CollectionKind.EVENT] = CollectionKind.EVENT
    event_start_date: date | None = Field(default=None, repr=False)
    event_end_date: date | None = Field(default=None, repr=False)
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
        validate_event_date_range(self.event_start_date, self.event_end_date)
        if self.event_start_at is not None and self.event_end_at is not None:
            if self.event_end_at <= self.event_start_at:
                raise _semantic_error("event_time_order_invalid")

        missing = set(self.missing_fields)
        uncertain = {item.field for item in self.uncertainties}
        for field, value in (
            (CandidateField.EVENT_START_DATE, self.event_start_date),
            (CandidateField.EVENT_END_DATE, self.event_end_date),
        ):
            if value is not None and field in missing:
                raise _semantic_error("present_field_marked_missing")
            if value is None and field not in missing and field not in uncertain:
                raise _semantic_error("event_date_absent_not_classified")
        for field, value in (
            (CandidateField.EVENT_START_AT, self.event_start_at),
            (CandidateField.EVENT_END_AT, self.event_end_at),
        ):
            if value is not None and field in missing:
                raise _semantic_error("present_field_marked_missing")
            if value is None and field not in missing and field not in uncertain:
                raise _semantic_error("event_time_absent_not_classified")
        return self


ExtractionCandidate = Annotated[
    PlaceCandidate | EventCandidate,
    Field(discriminator="kind"),
]


class ExtractionResult(ExtractionDomainModel):
    """One exclusive outcome: candidates, insufficient information, unsupported, or invalid."""

    outcome: ExtractionOutcome = Field(
        description=(
            "Selects exactly one result shape. candidates requires candidates; every other "
            "outcome forbids candidates."
        )
    )
    candidates: tuple[ExtractionCandidate, ...] = Field(
        default_factory=tuple,
        max_length=MAX_EXTRACTION_CANDIDATES,
        description=(
            "Non-empty only for the candidates outcome. Each candidate is a discriminated "
            "Place or Event with absent fields classified as missing or uncertain."
        ),
        repr=False,
    )
    reason_code: ExtractionReasonCode | None = Field(
        default=None,
        description="Required stable reason only for non-candidate outcomes.",
    )
    unsupported_reason: UnsupportedReason | None = Field(
        default=None,
        description="Present only with unsupported plus INPUT_UNSUPPORTED.",
    )
    missing_fields: tuple[CandidateField, ...] = Field(
        default_factory=tuple,
        max_length=len(CandidateField),
        description=(
            "Result-level information gaps for insufficient_information only; unique and "
            "disjoint from uncertainties."
        ),
        repr=False,
    )
    uncertainties: tuple[Uncertainty, ...] = Field(
        default_factory=tuple,
        max_length=len(CandidateField),
        description=(
            "Result-level uncertain fields for insufficient_information only; unique by "
            "field and disjoint from missing_fields."
        ),
        repr=False,
    )
    recovery_suggestions: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=4,
        description="Required for insufficient_information and safe recovery only.",
        repr=False,
    )

    @field_validator("missing_fields")
    @classmethod
    def validate_missing_fields(
        cls,
        value: tuple[CandidateField, ...],
    ) -> tuple[CandidateField, ...]:
        if len(set(value)) != len(value):
            raise _semantic_error("duplicate_missing_field")
        return value

    @field_validator("uncertainties")
    @classmethod
    def validate_uncertainties(
        cls,
        value: tuple[Uncertainty, ...],
    ) -> tuple[Uncertainty, ...]:
        fields = [item.field for item in value]
        if len(set(fields)) != len(fields):
            raise _semantic_error("duplicate_uncertainty_field")
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
            raise _semantic_error("missing_and_uncertain_conflict")

        if self.outcome is ExtractionOutcome.CANDIDATES:
            if not self.candidates:
                raise _semantic_error("candidates_required")
            if (
                self.reason_code is not None
                or self.unsupported_reason is not None
                or self.missing_fields
                or self.uncertainties
                or self.recovery_suggestions
            ):
                raise _semantic_error("candidate_outcome_has_error_metadata")
            return self

        if self.candidates:
            raise _semantic_error("candidates_forbidden_for_outcome")

        if self.outcome is ExtractionOutcome.INSUFFICIENT_INFORMATION:
            if self.reason_code is not ExtractionReasonCode.INSUFFICIENT_INFORMATION:
                raise _semantic_error("reason_code_invalid_for_outcome")
            if self.unsupported_reason is not None:
                raise _semantic_error("unsupported_reason_invalid")
            if not (self.missing_fields or self.uncertainties):
                raise _semantic_error("insufficient_fields_required")
            if not self.recovery_suggestions:
                raise _semantic_error("recovery_suggestions_required")
            return self

        if self.outcome is ExtractionOutcome.UNSUPPORTED:
            allowed = {
                ExtractionReasonCode.INPUT_EMPTY,
                ExtractionReasonCode.INPUT_UNSUPPORTED,
            }
            if self.reason_code not in allowed:
                raise _semantic_error("reason_code_invalid_for_outcome")
            if (self.reason_code is ExtractionReasonCode.INPUT_UNSUPPORTED) is not (
                self.unsupported_reason is not None
            ):
                raise _semantic_error("unsupported_reason_invalid")
            if self.missing_fields or self.uncertainties:
                raise _semantic_error("unsupported_fields_forbidden")
            return self

        if self.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT:
            if self.reason_code is not ExtractionReasonCode.MODEL_INVALID_OUTPUT:
                raise _semantic_error("reason_code_invalid_for_outcome")
            if self.unsupported_reason is not None or self.missing_fields or self.uncertainties:
                raise _semantic_error("model_invalid_details_forbidden")
            return self

        raise _semantic_error("outcome_invalid")

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

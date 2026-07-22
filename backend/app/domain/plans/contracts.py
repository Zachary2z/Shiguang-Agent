"""Deterministic, provider-neutral contracts for one Shenzhen plan request."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self, cast
from unicodedata import category

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import ErrorDetails, InitErrorDetails

from app.domain.collections import PlanCity
from app.domain.places import CityScope, Coordinate, TransportMode
from app.domain.time import require_aware_utc

_MAX_PLAN_DURATION = timedelta(hours=24)
_MAX_BUDGET = Decimal("1000000.00")
_MAX_AREA_VALUES = 8
_MAX_REQUIREMENTS = 16
_SENSITIVE_ERROR_LOCATIONS = frozenset({"area", "origin", "include", "exclude"})
_PUBLIC_ERROR_LOCATIONS = frozenset(
    {
        "budget",
        "city_code",
        "collection_only",
        "coordinate_system",
        "created_at",
        "districts",
        "end_at",
        "expires_at",
        "field",
        "labels",
        "latitude",
        "longitude",
        "pace",
        "start_at",
        "transport_modes",
    }
)
_SAFE_CUSTOM_VALIDATION_MESSAGES = frozenset(
    {
        "application timestamps must be timezone-aware",
        "end_at must be later than start_at",
        "plan duration must not exceed 24 hours",
        "expires_at must be later than created_at",
        "activity area requires a district or label",
        "transport_modes must be unique",
        "include and exclude must not conflict",
        *(
            f"{field_name} {suffix}"
            for field_name in ("districts", "area labels", "include", "exclude")
            for suffix in (
                "must not be blank",
                "is too long",
                "contains unsupported characters",
                "contains too many values",
                "values must be unique",
            )
        ),
    }
)
_SAFE_MESSAGE_REPLACEMENTS = {
    "activity area or origin is required": "activity range is required",
}


def _safe_validation_message(error: ErrorDetails) -> str:
    message = error["msg"]
    prefix = "Value error, "
    if not message.startswith(prefix):
        return "plan constraint value is invalid"
    detail = message.removeprefix(prefix)
    if detail in _SAFE_MESSAGE_REPLACEMENTS:
        return _SAFE_MESSAGE_REPLACEMENTS[detail]
    if detail in _SAFE_CUSTOM_VALIDATION_MESSAGES:
        return detail
    return "plan constraint value is invalid"


def _safe_validation_location(error: ErrorDetails) -> tuple[str | int, ...]:
    location = tuple(error["loc"])
    if any(part in _SENSITIVE_ERROR_LOCATIONS for part in location):
        return ("sensitive_constraint",)
    return tuple(
        part
        for part in location
        if isinstance(part, int) or part in _PUBLIC_ERROR_LOCATIONS
    ) or ("plan_constraints",)


def _sanitize_validation_error(error: ValidationError) -> ValidationError:
    """Rebuild a Pydantic error without any caller-provided values or exception chain."""

    line_errors = [
        InitErrorDetails(
            type="value_error",
            loc=_safe_validation_location(item),
            input=None,
            ctx={"error": ValueError(_safe_validation_message(item))},
        )
        for item in error.errors(include_url=False)
    ]
    return ValidationError.from_exception_data(
        error.title,
        line_errors,
        hide_input=True,
    )


class _RedactingSchemaValidator:
    """Delegate to one compiled Pydantic validator and sanitize every failure."""

    def __init__(self, validator: Any) -> None:
        self._validator = validator

    def __getattr__(self, name: str) -> Any:
        return getattr(self._validator, name)

    def _validate(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        safe_error: ValidationError | None = None
        try:
            method = getattr(self._validator, method_name)
            return method(*args, **kwargs)
        except ValidationError as error:
            safe_error = _sanitize_validation_error(error)
        if safe_error is not None:
            raise safe_error from None
        raise AssertionError("schema validation boundary did not return or raise")

    def validate_python(self, *args: Any, **kwargs: Any) -> Any:
        return self._validate("validate_python", *args, **kwargs)

    def validate_json(self, *args: Any, **kwargs: Any) -> Any:
        return self._validate("validate_json", *args, **kwargs)

    def validate_strings(self, *args: Any, **kwargs: Any) -> Any:
        return self._validate("validate_strings", *args, **kwargs)

    def validate_assignment(self, *args: Any, **kwargs: Any) -> Any:
        return self._validate("validate_assignment", *args, **kwargs)


class PlanContract(BaseModel):
    """Shared safety configuration for public planning contracts."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )

    @classmethod
    def __pydantic_on_complete__(cls) -> None:
        """Install one safety boundary around the compiled core validator."""

        super().__pydantic_on_complete__()
        validator = cls.__pydantic_validator__
        if not isinstance(validator, _RedactingSchemaValidator):
            cls.__pydantic_validator__ = cast(
                Any,
                _RedactingSchemaValidator(validator),
            )


class PlanPace(StrEnum):
    """User-facing density preference; it never becomes a required question."""

    RELAXED = "relaxed"
    BALANCED = "balanced"
    PACKED = "packed"


class MissingPlanConstraint(StrEnum):
    """Stable orderable identifiers for the only required planning questions."""

    TIME_WINDOW = "time_window"
    ACTIVITY_RANGE = "activity_range"


class MissingPlanConstraintInfo(PlanContract):
    """One missing item, with no optional or sensitive values attached."""

    field: MissingPlanConstraint


def _normalize_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} is too long")
    if any(category(character).startswith("C") for character in normalized):
        raise ValueError(f"{field_name} contains unsupported characters")
    return normalized


def _normalize_unique_values(
    values: tuple[str, ...],
    *,
    field_name: str,
    max_count: int,
    max_length: int,
) -> tuple[str, ...]:
    if len(values) > max_count:
        raise ValueError(f"{field_name} contains too many values")
    normalized = tuple(
        _normalize_text(value, field_name=field_name, max_length=max_length)
        for value in values
    )
    identities = tuple(value.casefold() for value in normalized)
    if len(set(identities)) != len(identities):
        raise ValueError(f"{field_name} values must be unique")
    return normalized


def _normalize_time(value: datetime) -> datetime:
    return require_aware_utc(value)


def _validate_time_window(start_at: datetime, end_at: datetime) -> None:
    if end_at <= start_at:
        raise ValueError("end_at must be later than start_at")
    if end_at - start_at > _MAX_PLAN_DURATION:
        raise ValueError("plan duration must not exceed 24 hours")


def _validate_temporary_lifetime(created_at: datetime, expires_at: datetime) -> None:
    if expires_at <= created_at:
        raise ValueError("expires_at must be later than created_at")


class ActivityArea(PlanContract):
    """A bounded coarse activity area; exact locations belong in ``origin``."""

    districts: tuple[str, ...] = Field(default_factory=tuple)
    labels: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("districts")
    @classmethod
    def normalize_districts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_unique_values(
            value,
            field_name="districts",
            max_count=_MAX_AREA_VALUES,
            max_length=80,
        )

    @field_validator("labels")
    @classmethod
    def normalize_labels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_unique_values(
            value,
            field_name="area labels",
            max_count=_MAX_AREA_VALUES,
            max_length=80,
        )

    @model_validator(mode="after")
    def require_area_value(self) -> Self:
        if not self.districts and not self.labels:
            raise ValueError("activity area requires a district or label")
        return self


class _PlanConstraintValues(PlanContract):
    """Common optional preferences and explicit temporary lifetime."""

    city_code: PlanCity
    area: ActivityArea | None = Field(default=None, repr=False)
    origin: Coordinate | None = Field(default=None, repr=False, exclude=True)
    budget: Decimal | None = Field(
        default=None,
        ge=0,
        le=_MAX_BUDGET,
        max_digits=10,
        decimal_places=2,
    )
    pace: PlanPace = PlanPace.BALANCED
    transport_modes: tuple[TransportMode, ...] = Field(default_factory=tuple, max_length=4)
    include: tuple[str, ...] = Field(default_factory=tuple, repr=False)
    exclude: tuple[str, ...] = Field(default_factory=tuple, repr=False)
    collection_only: bool = False
    created_at: datetime
    expires_at: datetime

    @field_validator("transport_modes")
    @classmethod
    def require_unique_transport_modes(
        cls, value: tuple[TransportMode, ...]
    ) -> tuple[TransportMode, ...]:
        if len(set(value)) != len(value):
            raise ValueError("transport_modes must be unique")
        return value

    @field_validator("include", "exclude")
    @classmethod
    def normalize_requirements(cls, value: tuple[str, ...], info: object) -> tuple[str, ...]:
        field_name = getattr(info, "field_name", "requirements")
        return _normalize_unique_values(
            value,
            field_name=str(field_name),
            max_count=_MAX_REQUIREMENTS,
            max_length=80,
        )

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_lifetime(cls, value: datetime) -> datetime:
        return _normalize_time(value)

    @model_validator(mode="after")
    def validate_common_constraints(self) -> Self:
        _validate_temporary_lifetime(self.created_at, self.expires_at)
        include = {value.casefold() for value in self.include}
        exclude = {value.casefold() for value in self.exclude}
        if include & exclude:
            raise ValueError("include and exclude must not conflict")
        return self

    @property
    def city_scope(self) -> CityScope:
        """Adapt the single plan city to the existing provider boundary."""

        return CityScope(city_code=self.city_code.value)

    def is_active(self, at: datetime) -> bool:
        """Temporary constraints are active on ``[created_at, expires_at)``."""

        normalized = require_aware_utc(at)
        return self.created_at <= normalized < self.expires_at


class PlanConstraintInput(_PlanConstraintValues):
    """Partial deterministic input accepted before required questions are complete."""

    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_optional_plan_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _normalize_time(value)

    @model_validator(mode="after")
    def validate_complete_time_window(self) -> Self:
        if self.start_at is not None and self.end_at is not None:
            _validate_time_window(self.start_at, self.end_at)
        return self


class PlanConstraints(_PlanConstraintValues):
    """The one complete, immutable hard boundary for a Shenzhen plan."""

    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_plan_time(cls, value: datetime) -> datetime:
        return _normalize_time(value)

    @model_validator(mode="after")
    def validate_required_constraints(self) -> Self:
        _validate_time_window(self.start_at, self.end_at)
        if self.area is None and self.origin is None:
            raise ValueError("activity area or origin is required")
        return self

    @property
    def duration(self) -> timedelta:
        return self.end_at - self.start_at


PlanConstraintResolution = PlanConstraints | MissingPlanConstraintInfo


def resolve_plan_constraints(
    value: PlanConstraintInput,
    *,
    now: datetime,
) -> PlanConstraintResolution:
    """Return a complete contract or exactly one stable next missing item.

    An inactive temporary input is treated as unavailable. This prevents expired
    time, location, or user requirements from being silently reused.
    """

    if not value.is_active(now) or value.start_at is None or value.end_at is None:
        return MissingPlanConstraintInfo(field=MissingPlanConstraint.TIME_WINDOW)
    if value.area is None and value.origin is None:
        return MissingPlanConstraintInfo(field=MissingPlanConstraint.ACTIVITY_RANGE)
    return PlanConstraints(
        city_code=value.city_code,
        start_at=value.start_at,
        end_at=value.end_at,
        area=value.area,
        origin=value.origin,
        budget=value.budget,
        pace=value.pace,
        transport_modes=value.transport_modes,
        include=value.include,
        exclude=value.exclude,
        collection_only=value.collection_only,
        created_at=value.created_at,
        expires_at=value.expires_at,
    )

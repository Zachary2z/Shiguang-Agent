"""Deterministic, provider-neutral contracts for one Shenzhen plan request."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar, Literal, Self, TypeVar
from unicodedata import category

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.domain.collections import PlanCity
from app.domain.identifiers import validate_collection_item_id
from app.domain.places import CityScope, Coordinate, TransportMode
from app.domain.time import require_aware_utc

_MAX_PLAN_DURATION = timedelta(hours=24)
_MAX_BUDGET = Decimal("1000000.00")
_MAX_AREA_VALUES = 8
_MAX_REQUIREMENTS = 16
_MAX_SELECTED_COLLECTION_ITEMS = 20
_MIN_CONSTRAINT_LIFETIME = timedelta(hours=1)


class PlanContract(BaseModel):
    """Shared strict configuration for native planning contracts."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class PlanConstraintParseError(ValueError):
    """Fixed public failure for untrusted plan-constraint parsing."""

    __slots__ = ()
    code: ClassVar[str] = "INVALID_PLAN_CONSTRAINTS"
    summary: ClassVar[str] = "Plan constraints are invalid."

    def __init__(self) -> None:
        super().__init__(self.summary)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("PlanConstraintParseError is frozen")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "summary": self.summary}


class PlanPace(StrEnum):
    """User-facing density preference; it never becomes a required question."""

    RELAXED = "relaxed"
    BALANCED = "balanced"
    PACKED = "packed"


class PlanPaceSource(StrEnum):
    """Why the effective pace has its current value."""

    USER_REQUEST = "user_request"
    SYSTEM_DEFAULT = "system_default"
    MEMORY_DEFAULT = "memory_default"


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


def plan_constraint_expires_at(
    *,
    now: datetime,
    start_at: datetime | None,
    end_at: datetime | None,
) -> datetime:
    """Return the single minimum lifetime for partial or complete plan constraints."""

    created = require_aware_utc(now)
    if start_at is None or end_at is None:
        return created + _MIN_CONSTRAINT_LIFETIME
    require_aware_utc(start_at)
    return max(
        created + _MIN_CONSTRAINT_LIFETIME,
        require_aware_utc(end_at) + _MIN_CONSTRAINT_LIFETIME,
    )


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

    def as_memory_value(self) -> str:
        """Serialize one explicitly classified coarse area for long-term storage."""

        if len(self.districts) + len(self.labels) != 1:
            raise ValueError("a usual area requires exactly one district or area label")
        name = (self.districts or self.labels)[0]
        if len(name) > 40:
            raise ValueError("a usual area name is too long")
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_memory_value(cls, value: str) -> ActivityArea:
        area = cls.model_validate_json(value)
        if area.as_memory_value() != value:
            raise ValueError("usual area value is not canonical")
        return area

    @property
    def display_name(self) -> str:
        if len(self.districts) + len(self.labels) != 1:
            raise ValueError("a usual area requires exactly one district or area label")
        return (self.districts or self.labels)[0]


class _PlanConstraintValues(PlanContract):
    """Common optional preferences and explicit temporary lifetime."""

    city_code: PlanCity
    area: ActivityArea | None = Field(default=None, repr=False)
    origin: Coordinate | None = Field(default=None, repr=False, exclude=True)
    original_request: str | None = Field(default=None, repr=False, exclude=True)
    budget: Decimal | None = Field(
        default=None,
        ge=0,
        le=_MAX_BUDGET,
        max_digits=10,
        decimal_places=2,
    )
    pace: PlanPace = PlanPace.BALANCED
    pace_source: PlanPaceSource = PlanPaceSource.USER_REQUEST
    transport_modes: tuple[TransportMode, ...] = Field(default_factory=tuple, max_length=4)
    include: tuple[str, ...] = Field(default_factory=tuple, repr=False)
    exclude: tuple[str, ...] = Field(default_factory=tuple, repr=False)
    collection_only: bool = False
    selected_collection_item_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=_MAX_SELECTED_COLLECTION_ITEMS,
        repr=False,
    )
    required_collection_item_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=_MAX_SELECTED_COLLECTION_ITEMS,
        repr=False,
    )
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

    @field_validator("original_request")
    @classmethod
    def normalize_original_request(cls, value: str | None) -> str | None:
        return (
            None
            if value is None
            else _normalize_text(value, field_name="original_request", max_length=4000)
        )

    @field_validator(
        "selected_collection_item_ids",
        "required_collection_item_ids",
        mode="before",
    )
    @classmethod
    def normalize_selected_collection_items(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (tuple, list)):
            raise ValueError("selected collection item IDs must be a list or tuple")
        return tuple(dict.fromkeys(validate_collection_item_id(item) for item in value))

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
        if not set(self.required_collection_item_ids).issubset(
            self.selected_collection_item_ids
        ):
            raise ValueError("required collection items must also be selected")
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


def plan_constraints_internal_dump(
    constraints: PlanConstraints,
    *,
    mode: Literal["json", "python"],
) -> dict[str, Any]:
    """Project complete constraints for private persistence and internal identity."""

    values = constraints.model_dump(mode=mode)
    if constraints.origin is not None:
        values["origin"] = constraints.origin.model_dump(mode=mode)
    if constraints.original_request is not None:
        values["original_request"] = constraints.original_request
    return values


_PlanContractT = TypeVar("_PlanContractT", bound=PlanContract)


def _parse_untrusted_plan_contract(
    parser: Callable[[], _PlanContractT],
) -> _PlanContractT:
    """Map native Pydantic failures to the sole public safe parse error."""

    invalid = False
    try:
        return parser()
    except (ValidationError, TypeError):
        invalid = True
    if invalid:
        raise PlanConstraintParseError() from None
    raise AssertionError("plan constraint parser did not return or fail")


def parse_plan_constraint_input(value: object) -> PlanConstraintInput:
    """Parse untrusted Python input without exposing native validation errors."""

    return _parse_untrusted_plan_contract(lambda: PlanConstraintInput.model_validate(value))


def parse_plan_constraint_input_json(
    value: str | bytes | bytearray,
) -> PlanConstraintInput:
    """Parse untrusted JSON input without exposing native validation errors."""

    return _parse_untrusted_plan_contract(
        lambda: PlanConstraintInput.model_validate_json(value)
    )


def parse_plan_constraints(value: object) -> PlanConstraints:
    """Parse complete untrusted Python constraints through the safe boundary."""

    return _parse_untrusted_plan_contract(lambda: PlanConstraints.model_validate(value))


def parse_plan_constraints_json(value: str | bytes | bytearray) -> PlanConstraints:
    """Parse complete untrusted JSON constraints through the safe boundary."""

    return _parse_untrusted_plan_contract(lambda: PlanConstraints.model_validate_json(value))


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
        original_request=value.original_request,
        budget=value.budget,
        pace=value.pace,
        pace_source=value.pace_source,
        transport_modes=value.transport_modes,
        include=value.include,
        exclude=value.exclude,
        collection_only=value.collection_only,
        selected_collection_item_ids=value.selected_collection_item_ids,
        required_collection_item_ids=value.required_collection_item_ids,
        created_at=value.created_at,
        expires_at=value.expires_at,
    )

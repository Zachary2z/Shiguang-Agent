"""Strict internal DTOs shared by every map-provider implementation."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PlaceContract(BaseModel):
    """Immutable, extra-forbid base for provider-neutral place data."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


def _required_text(value: str, *, field_name: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


class CoordinateSystem(StrEnum):
    """Stable coordinate reference systems understood by the application."""

    GCJ_02 = "gcj_02"
    WGS_84 = "wgs_84"


class PoiType(StrEnum):
    """Coarse application categories; provider taxonomies are mapped into these."""

    ATTRACTION = "attraction"
    CAFE = "cafe"
    MUSEUM = "museum"
    PARK = "park"
    RESTAURANT = "restaurant"
    SHOPPING = "shopping"
    TRANSIT = "transit"
    OTHER = "other"


class TransportMode(StrEnum):
    """Route modes with provider-independent meaning."""

    WALKING = "walking"
    CYCLING = "cycling"
    TRANSIT = "transit"
    DRIVING = "driving"


class CityScope(PlaceContract):
    """An explicit stable city boundary carried by every map operation."""

    city_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")

    @field_validator("city_code")
    @classmethod
    def normalize_city_code(cls, value: str) -> str:
        return _required_text(value, field_name="city_code")


class Coordinate(PlaceContract):
    """A validated point whose coordinate system can never be implicit."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    coordinate_system: CoordinateSystem


class Poi(PlaceContract):
    """One internal POI without a retained provider response."""

    poi_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    branch_name: str | None = Field(default=None, max_length=160)
    city_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    district: str | None = Field(default=None, max_length=100)
    business_area: str | None = Field(default=None, max_length=100)
    address: str = Field(min_length=1, max_length=500)
    coordinate: Coordinate
    poi_type: PoiType
    phone: str | None = Field(default=None, max_length=64, repr=False)
    opening_hours_summary: str | None = Field(default=None, max_length=240)

    @field_validator("poi_id", "name", "city_code", "address")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _required_text(value, field_name="POI text")

    @field_validator(
        "branch_name",
        "district",
        "business_area",
        "phone",
        "opening_hours_summary",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _optional_text(value, field_name="POI text")


class SearchPoiRequest(PlaceContract):
    """Search POIs only inside the caller-provided city scope."""

    query: str = Field(min_length=1, max_length=200, repr=False)
    city: CityScope
    district: str | None = Field(default=None, max_length=100, repr=False)
    location: Coordinate | None = Field(default=None, repr=False)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return _required_text(value, field_name="query")

    @field_validator("district")
    @classmethod
    def normalize_district(cls, value: str | None) -> str | None:
        return _optional_text(value, field_name="district")


class PoiSearchResult(PlaceContract):
    """An ordered search result; an empty tuple is the explicit no-result case."""

    city_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    pois: tuple[Poi, ...] = Field(default_factory=tuple, repr=False)

    @model_validator(mode="after")
    def require_one_city(self) -> Self:
        if any(poi.city_code != self.city_code for poi in self.pois):
            raise ValueError("all search results must belong to the declared city")
        if len({poi.poi_id for poi in self.pois}) != len(self.pois):
            raise ValueError("search results must contain unique POI identifiers")
        return self


class GetPoiRequest(PlaceContract):
    """Fetch one POI by identifier within an explicit city scope."""

    poi_id: str = Field(min_length=1, max_length=128)
    city: CityScope

    @field_validator("poi_id")
    @classmethod
    def normalize_poi_id(cls, value: str) -> str:
        return _required_text(value, field_name="poi_id")


class GetPoiResult(PlaceContract):
    """Successful POI detail lookup."""

    poi: Poi


class RouteRequest(PlaceContract):
    """Route between two coordinates within one explicit city scope."""

    city: CityScope
    origin: Coordinate = Field(repr=False)
    destination: Coordinate = Field(repr=False)
    mode: TransportMode

    @model_validator(mode="after")
    def require_one_coordinate_system(self) -> Self:
        if self.origin.coordinate_system is not self.destination.coordinate_system:
            raise ValueError("route endpoints must use the same coordinate system")
        return self


class RouteResult(PlaceContract):
    """Normalized route totals; zero is valid for identical endpoints."""

    city_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    origin: Coordinate = Field(repr=False)
    destination: Coordinate = Field(repr=False)
    mode: TransportMode
    distance_meters: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)

    @model_validator(mode="after")
    def require_one_coordinate_system(self) -> Self:
        if self.origin.coordinate_system is not self.destination.coordinate_system:
            raise ValueError("route endpoints must use the same coordinate system")
        return self


class WeatherRequest(PlaceContract):
    """Weather query scoped to one city and one optional calendar date."""

    city: CityScope
    on_date: date | None = None


class WeatherResult(PlaceContract):
    """A dated, bounded temperature summary without a raw forecast payload."""

    city_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    on_date: date
    condition: str = Field(min_length=1, max_length=80)
    temperature_celsius: float = Field(ge=-100, le=100)
    low_temperature_celsius: float | None = Field(default=None, ge=-100, le=100)
    high_temperature_celsius: float | None = Field(default=None, ge=-100, le=100)
    summary: str | None = Field(default=None, max_length=240)

    @field_validator("condition")
    @classmethod
    def normalize_condition(cls, value: str) -> str:
        return _required_text(value, field_name="condition")

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        return _optional_text(value, field_name="weather summary")

    @model_validator(mode="after")
    def validate_temperature_range(self) -> Self:
        if (
            self.low_temperature_celsius is not None
            and self.high_temperature_celsius is not None
            and self.low_temperature_celsius > self.high_temperature_celsius
        ):
            raise ValueError("low temperature cannot exceed high temperature")
        return self


class NavigationRequest(PlaceContract):
    """Build a navigation URI for a POI in an explicit city scope."""

    city: CityScope
    poi_id: str = Field(min_length=1, max_length=128)
    coordinate: Coordinate = Field(repr=False)

    @field_validator("poi_id")
    @classmethod
    def normalize_navigation_poi_id(cls, value: str) -> str:
        return _required_text(value, field_name="poi_id")


class NavigationUri(PlaceContract):
    """A safe public navigation URI using an explicit supported scheme."""

    uri: str = Field(min_length=1, max_length=2048)

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, value: str) -> str:
        normalized = _required_text(value, field_name="uri")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"geo", "https"}:
            raise ValueError("navigation URI must use the geo or https scheme")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("navigation URI must not contain credentials")
        return normalized

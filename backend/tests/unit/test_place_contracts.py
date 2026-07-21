"""Boundary validation for provider-neutral place DTOs."""

from __future__ import annotations

from datetime import date
from math import inf, nan

import pytest
from pydantic import ValidationError

from app.domain.places import (
    CityScope,
    Coordinate,
    CoordinateSystem,
    NavigationUri,
    Poi,
    PoiSearchResult,
    RouteRequest,
    RouteResult,
    TransportMode,
    WeatherRequest,
    WeatherResult,
)
from tests.fixtures.maps import SHENZHEN_MUSEUM, SHENZHEN_MUSEUM_COORDINATE


def test_poi_contract_is_strict_immutable_and_rejects_unknown_fields() -> None:
    poi = SHENZHEN_MUSEUM

    assert poi.city_code == "shenzhen"
    assert poi.coordinate.coordinate_system is CoordinateSystem.GCJ_02
    with pytest.raises(ValidationError):
        Poi(**poi.model_dump(), adcode="440300")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        poi.name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("city_code", ["", " ", "Shenzhen", "shenzhen city", "a"])
def test_city_scope_rejects_blank_or_unstable_codes(city_code: str) -> None:
    with pytest.raises(ValidationError):
        CityScope(city_code=city_code)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (-90.1, 0.0),
        (90.1, 0.0),
        (0.0, -180.1),
        (0.0, 180.1),
        (nan, 0.0),
        (0.0, inf),
    ],
)
def test_coordinate_rejects_out_of_range_or_non_finite_values(
    latitude: float,
    longitude: float,
) -> None:
    with pytest.raises(ValidationError):
        Coordinate(
            latitude=latitude,
            longitude=longitude,
            coordinate_system=CoordinateSystem.GCJ_02,
        )


def test_coordinate_accepts_inclusive_world_boundaries() -> None:
    coordinate = Coordinate(
        latitude=90.0,
        longitude=-180.0,
        coordinate_system=CoordinateSystem.WGS_84,
    )

    assert coordinate.latitude == 90.0
    assert coordinate.longitude == -180.0


@pytest.mark.parametrize(
    ("distance", "duration"),
    [(-1, 0), (0, -1), (True, 0), (0, False)],
)
def test_route_rejects_negative_or_boolean_totals(
    distance: object,
    duration: object,
) -> None:
    with pytest.raises(ValidationError):
        RouteResult(
            city_code="shenzhen",
            origin=SHENZHEN_MUSEUM_COORDINATE,
            destination=SHENZHEN_MUSEUM_COORDINATE,
            mode=TransportMode.WALKING,
            distance_meters=distance,
            duration_seconds=duration,
        )


def test_route_rejects_mixed_coordinate_systems() -> None:
    other_system = SHENZHEN_MUSEUM_COORDINATE.model_copy(
        update={"coordinate_system": CoordinateSystem.WGS_84}
    )

    with pytest.raises(ValidationError):
        RouteRequest(
            city=CityScope(city_code="shenzhen"),
            origin=SHENZHEN_MUSEUM_COORDINATE,
            destination=other_system,
            mode=TransportMode.WALKING,
        )


def test_weather_date_and_temperature_contracts_are_strict() -> None:
    with pytest.raises(ValidationError):
        WeatherRequest(
            city=CityScope(city_code="shenzhen"),
            on_date="2026-07-22",  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        WeatherResult(
            city_code="shenzhen",
            on_date=date(2026, 7, 22),
            condition="sunny",
            temperature_celsius=20.0,
            low_temperature_celsius=30.0,
            high_temperature_celsius=20.0,
        )
    with pytest.raises(ValidationError):
        WeatherResult(
            city_code="shenzhen",
            on_date=date(2026, 7, 22),
            condition="sunny",
            temperature_celsius=101.0,
        )


@pytest.mark.parametrize(
    "uri",
    [
        "http://maps.example.invalid/navigation",
        "https://user:password@maps.example.invalid/navigation",
        "not-a-uri",
    ],
)
def test_navigation_uri_rejects_unsafe_or_invalid_schemes(uri: str) -> None:
    with pytest.raises(ValidationError):
        NavigationUri(uri=uri)


def test_search_results_reject_mixed_cities_and_duplicate_identifiers() -> None:
    guangzhou_copy = SHENZHEN_MUSEUM.model_copy(update={"city_code": "guangzhou"})
    with pytest.raises(ValidationError):
        PoiSearchResult(city_code="shenzhen", pois=(guangzhou_copy,))
    with pytest.raises(ValidationError):
        PoiSearchResult(
            city_code="shenzhen",
            pois=(SHENZHEN_MUSEUM, SHENZHEN_MUSEUM),
        )


def test_public_dtos_have_no_provider_raw_field_names() -> None:
    public_fields = set(Poi.model_fields) | set(Coordinate.model_fields)

    assert public_fields.isdisjoint(
        {"adcode", "pname", "cityname", "raw_response", "api_key", "headers"}
    )

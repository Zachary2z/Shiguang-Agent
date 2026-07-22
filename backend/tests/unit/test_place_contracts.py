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
    PoiProvider,
    PoiSearchResult,
    RouteRequest,
    RouteResult,
    TransportMode,
    WeatherRequest,
    WeatherResult,
)
from tests.fixtures.maps import SHENZHEN_MUSEUM, SHENZHEN_MUSEUM_COORDINATE

FAKE_URI_SECRET = "fake-navigation-secret-must-not-leak"


def test_poi_contract_is_strict_immutable_and_rejects_unknown_fields() -> None:
    poi = SHENZHEN_MUSEUM

    assert poi.provider is PoiProvider.AMAP
    assert poi.city_code == "shenzhen"
    assert poi.coordinate.coordinate_system is CoordinateSystem.GCJ_02
    with pytest.raises(ValidationError):
        Poi(**poi.model_dump(), adcode="440300")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        poi.name = "changed"  # type: ignore[misc]


def test_poi_provider_is_required_strict_and_stable_with_poi_id() -> None:
    payload = SHENZHEN_MUSEUM.model_dump()
    payload.pop("provider")
    with pytest.raises(ValidationError):
        Poi(**payload)
    payload["provider"] = "amap"
    with pytest.raises(ValidationError):
        Poi(**payload)

    assert (SHENZHEN_MUSEUM.provider, SHENZHEN_MUSEUM.poi_id) == (
        PoiProvider.AMAP,
        "poi_sz_moca_up",
    )


@pytest.mark.parametrize("city_code", ["", " ", "Shenzhen", "shenzhen city", "a"])
def test_city_scope_rejects_blank_or_unstable_codes(city_code: str) -> None:
    with pytest.raises(ValidationError):
        CityScope(city_code=city_code)


def test_all_city_code_fields_share_one_rule_without_whitespace_normalization() -> None:
    city_models = (CityScope, Poi, PoiSearchResult, RouteResult, WeatherResult)

    patterns = {
        model.model_json_schema()["properties"]["city_code"]["pattern"]
        for model in city_models
    }

    assert patterns == {r"^[a-z][a-z0-9_]{1,31}$"}
    assert CityScope(city_code="shenzhen").city_code == "shenzhen"
    with pytest.raises(ValidationError):
        CityScope(city_code=" shenzhen ")


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
        "",
        "   ",
        "geo:",
        "geo:?q=",
        "geo:91,0",
        "geo:-91,0",
        "geo:0,181",
        "geo:0,-181",
        "geo:nan,0",
        "geo:0,NaN",
        "geo:inf,0",
        "geo:0,-inf",
        "geo:not-a-latitude,114",
        "geo:22.5",
        "geo:22.5,114,10",
        "geo:22.5,114#fragment",
        "http://maps.example.invalid/navigation",
        "https://",
        "https:///missing-host",
        "https://user:password@maps.example.invalid/navigation",
        "https://maps.example.invalid:not-a-port/navigation",
        "https://maps.example.invalid:70000/navigation",
        "https://-invalid-host.example/navigation",
        "https://maps.example.invalid/navigation%ZZ",
        "https://maps.example.invalid/nav\nigation",
        "https://maps.example.invalid/navigation\x00",
        "https://maps.example.invalid/navigation\u0091",
        "https://maps.example.invalid\\navigation",
        "not-a-uri",
    ],
)
def test_navigation_uri_rejects_unsafe_or_incomplete_values(uri: str) -> None:
    with pytest.raises(ValidationError):
        NavigationUri(uri=uri)


@pytest.mark.parametrize(
    "uri",
    [
        "geo:22.541174,114.057701?q=22.541174,114.057701%28poi_sz_moca_up%29",
        "geo:23.117242,113.321242?q=23.117242,113.321242%28poi_gz_museum%29",
        "geo:-90,-180",
        "geo:90,180",
        "geo:0,0;u=25",
        "https://maps.example.invalid/navigation?poi_id=poi_sz_moca_up",
        "https://127.0.0.1:443/navigation",
        "https://[::1]/navigation",
    ],
)
def test_navigation_uri_accepts_complete_geo_and_https_values(uri: str) -> None:
    original = uri

    first = NavigationUri(uri=uri)
    second = NavigationUri(uri=uri)

    assert uri == original
    assert first == second
    assert first is not second
    assert first.uri == original


def test_navigation_uri_validation_error_and_public_details_hide_sensitive_input(
    caplog: pytest.LogCaptureFixture,
) -> None:
    unsafe_uri = (
        "https://maps.example.invalid/navigation?authorization="
        f"{FAKE_URI_SECRET}%ZZ"
    )

    with caplog.at_level("INFO"), pytest.raises(ValidationError) as captured:
        NavigationUri(uri=unsafe_uri)

    error = captured.value
    public_details = error.errors(
        include_input=False,
        include_context=False,
        include_url=False,
    )
    exposed = str(error) + repr(error) + repr(public_details) + caplog.text
    assert FAKE_URI_SECRET not in exposed
    assert "authorization=" not in exposed.casefold()
    assert "raw-provider-response" not in exposed


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

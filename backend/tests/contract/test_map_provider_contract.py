"""Contract behavior shared by every MapProvider implementation."""

from __future__ import annotations

import inspect

import pytest

from app.domain.places import (
    GetPoiRequest,
    NavigationRequest,
    PoiProvider,
    RouteRequest,
    SearchPoiRequest,
    WeatherRequest,
)
from app.providers import MapProvider, MapProviderError, MapProviderErrorCode
from tests.fixtures.maps import (
    CHAIN_SEARCH,
    GZ_GET_POI,
    GZ_NAVIGATION,
    GZ_ROUTE,
    GZ_UNIQUE_SEARCH,
    GZ_WEATHER,
    MISSING_GET_POI,
    NO_RESULT_SEARCH,
    SZ_GET_POI,
    SZ_NAVIGATION,
    SZ_ROUTE,
    SZ_UNIQUE_SEARCH,
    SZ_WEATHER,
    TIMEOUT_SEARCH,
    make_stub_map_provider,
)


def test_map_provider_has_exactly_five_explicit_request_contracts() -> None:
    expected = {
        "search_poi": SearchPoiRequest,
        "get_poi": GetPoiRequest,
        "route": RouteRequest,
        "weather": WeatherRequest,
        "build_navigation_uri": NavigationRequest,
    }

    assert set(MapProvider.__abstractmethods__) == set(expected)
    for name, request_type in expected.items():
        parameter = inspect.signature(getattr(MapProvider, name)).parameters["request"]
        assert parameter.annotation == request_type.__name__
        assert "city" in request_type.model_fields


@pytest.mark.asyncio
async def test_search_covers_unique_multiple_empty_and_timeout_results() -> None:
    provider = make_stub_map_provider()

    sz_poi = (await provider.search_poi(SZ_UNIQUE_SEARCH)).pois[0]
    assert (sz_poi.provider, sz_poi.poi_id) == (PoiProvider.AMAP, "poi_sz_moca_up")
    assert (await provider.search_poi(GZ_UNIQUE_SEARCH)).pois[0].city_code == "guangzhou"
    assert len((await provider.search_poi(CHAIN_SEARCH)).pois) == 2
    assert (await provider.search_poi(NO_RESULT_SEARCH)).pois == ()
    with pytest.raises(MapProviderError) as error:
        await provider.search_poi(TIMEOUT_SEARCH)
    assert error.value.code is MapProviderErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_get_poi_success_and_safe_not_found() -> None:
    provider = make_stub_map_provider()

    sz_poi = (await provider.get_poi(SZ_GET_POI)).poi
    assert (sz_poi.provider, sz_poi.poi_id, sz_poi.city_code) == (
        PoiProvider.AMAP,
        "poi_sz_moca_up",
        "shenzhen",
    )
    assert (await provider.get_poi(GZ_GET_POI)).poi.city_code == "guangzhou"
    with pytest.raises(MapProviderError) as error:
        await provider.get_poi(MISSING_GET_POI)
    assert error.value.to_public_dict() == {
        "code": "MAP_POI_NOT_FOUND",
        "summary": "The requested POI was not found.",
        "retryable": False,
    }


@pytest.mark.asyncio
async def test_route_weather_and_navigation_cover_both_city_scopes() -> None:
    provider = make_stub_map_provider()

    sz_route, gz_route = await provider.route(SZ_ROUTE), await provider.route(GZ_ROUTE)
    sz_weather, gz_weather = (
        await provider.weather(SZ_WEATHER),
        await provider.weather(GZ_WEATHER),
    )
    sz_uri, gz_uri = (
        await provider.build_navigation_uri(SZ_NAVIGATION),
        await provider.build_navigation_uri(GZ_NAVIGATION),
    )

    assert (sz_route.city_code, gz_route.city_code) == ("shenzhen", "guangzhou")
    assert sz_route.distance_meters == 850
    assert (sz_weather.city_code, gz_weather.city_code) == ("shenzhen", "guangzhou")
    assert sz_weather.on_date == SZ_WEATHER.on_date
    assert sz_uri.uri.startswith("geo:22.541174,114.057701")
    assert gz_uri.uri.startswith("geo:23.117242,113.321242")

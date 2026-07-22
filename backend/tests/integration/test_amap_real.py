"""Explicitly gated, read-only real Amap Web Service acceptance entry."""

from __future__ import annotations

import os

import pytest

from app.config import DEFAULT_ENV_FILE, AmapConfigurationError, Settings
from app.domain.places import (
    CityScope,
    Coordinate,
    CoordinateSystem,
    GetPoiRequest,
    NavigationRequest,
    PoiProvider,
    RouteRequest,
    SearchPoiRequest,
    TransportMode,
    WeatherRequest,
)
from app.providers import AmapMapProvider


def _real_amap_settings() -> Settings:
    if os.environ.get("RUN_REAL_MAP_TESTS") != "1":
        pytest.skip(
            "real map test not run: set RUN_REAL_MAP_TESTS=1 only after explicit authorization; "
            "no network request was made"
        )

    settings = Settings(_env_file=DEFAULT_ENV_FILE)  # type: ignore[call-arg]
    try:
        settings.require_amap_provider()
    except AmapConfigurationError as exc:
        pytest.skip(f"real map test not run: {exc}; no network request was made")
    return settings


@pytest.mark.real_map_provider
@pytest.mark.asyncio
async def test_real_amap_read_only_shenzhen_guangzhou_acceptance() -> None:
    """Perform five logical reads (at most ten HTTP attempts) plus one local URI build."""

    shenzhen = CityScope(city_code="shenzhen")
    guangzhou = CityScope(city_code="guangzhou")
    provider = AmapMapProvider.from_settings(_real_amap_settings())
    try:
        shenzhen_search = await provider.search_poi(
            SearchPoiRequest(query="深圳当代艺术与城市规划馆", city=shenzhen)
        )
        guangzhou_search = await provider.search_poi(
            SearchPoiRequest(query="广东省博物馆", city=guangzhou)
        )
        assert shenzhen_search.pois
        assert guangzhou_search.pois

        selected = shenzhen_search.pois[0]
        detail = await provider.get_poi(
            GetPoiRequest(poi_id=selected.poi_id, city=shenzhen)
        )
        route = await provider.route(
            RouteRequest(
                city=shenzhen,
                origin=Coordinate(
                    latitude=22.540325,
                    longitude=114.059322,
                    coordinate_system=CoordinateSystem.GCJ_02,
                ),
                destination=detail.poi.coordinate,
                mode=TransportMode.WALKING,
            )
        )
        weather = await provider.weather(WeatherRequest(city=shenzhen))
        navigation = await provider.build_navigation_uri(
            NavigationRequest(
                city=shenzhen,
                poi_id=detail.poi.poi_id,
                coordinate=detail.poi.coordinate,
            )
        )
    finally:
        await provider.close()

    assert (detail.poi.provider, detail.poi.poi_id, detail.poi.city_code) == (
        PoiProvider.AMAP,
        selected.poi_id,
        "shenzhen",
    )
    assert all(poi.provider is PoiProvider.AMAP for poi in shenzhen_search.pois)
    assert all(poi.provider is PoiProvider.AMAP for poi in guangzhou_search.pois)
    assert route.city_code == "shenzhen"
    assert weather.city_code == "shenzhen"
    assert navigation.uri.startswith("https://uri.amap.com/marker?")
    assert "key=" not in navigation.uri.casefold()

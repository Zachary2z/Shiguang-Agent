"""One reusable M0-3A map fixture set for contract and integration tests."""

from __future__ import annotations

from datetime import date

from app.domain.places import (
    CityScope,
    Coordinate,
    CoordinateSystem,
    GetPoiRequest,
    GetPoiResult,
    NavigationRequest,
    NavigationUri,
    Poi,
    PoiSearchResult,
    PoiType,
    RouteRequest,
    RouteResult,
    SearchPoiRequest,
    TransportMode,
    WeatherRequest,
    WeatherResult,
)
from app.providers import StubMapProvider

SHENZHEN = CityScope(city_code="shenzhen")
GUANGZHOU = CityScope(city_code="guangzhou")

SHENZHEN_MUSEUM_COORDINATE = Coordinate(
    latitude=22.541174,
    longitude=114.057701,
    coordinate_system=CoordinateSystem.GCJ_02,
)
SHENZHEN_CAFE_COORDINATE = Coordinate(
    latitude=22.540325,
    longitude=114.059322,
    coordinate_system=CoordinateSystem.GCJ_02,
)
GUANGZHOU_MUSEUM_COORDINATE = Coordinate(
    latitude=23.117242,
    longitude=113.321242,
    coordinate_system=CoordinateSystem.GCJ_02,
)

SHENZHEN_MUSEUM = Poi(
    poi_id="poi_sz_moca_up",
    name="深圳当代艺术与城市规划馆",
    city_code="shenzhen",
    district="福田区",
    business_area="市民中心",
    address="福中路184号",
    coordinate=SHENZHEN_MUSEUM_COORDINATE,
    poi_type=PoiType.MUSEUM,
    phone="0755-00000000",
    opening_hours_summary="周二至周日开放",
)
SHENZHEN_CHAIN_CAFE_ONE = Poi(
    poi_id="poi_sz_chain_cafe_one",
    name="未名咖啡",
    branch_name="市民中心店",
    city_code="shenzhen",
    district="福田区",
    business_area="市民中心",
    address="福中一路1号",
    coordinate=SHENZHEN_CAFE_COORDINATE,
    poi_type=PoiType.CAFE,
)
SHENZHEN_CHAIN_CAFE_TWO = Poi(
    poi_id="poi_sz_chain_cafe_two",
    name="未名咖啡",
    branch_name="中心书城店",
    city_code="shenzhen",
    district="福田区",
    business_area="中心区",
    address="福中一路2014号",
    coordinate=Coordinate(
        latitude=22.543100,
        longitude=114.057900,
        coordinate_system=CoordinateSystem.GCJ_02,
    ),
    poi_type=PoiType.CAFE,
)
GUANGZHOU_MUSEUM = Poi(
    poi_id="poi_gz_museum",
    name="广东省博物馆",
    city_code="guangzhou",
    district="天河区",
    business_area="珠江新城",
    address="珠江东路2号",
    coordinate=GUANGZHOU_MUSEUM_COORDINATE,
    poi_type=PoiType.MUSEUM,
    opening_hours_summary="周二至周日开放",
)

SZ_UNIQUE_SEARCH = SearchPoiRequest(query="深圳当代艺术与城市规划馆", city=SHENZHEN)
GZ_UNIQUE_SEARCH = SearchPoiRequest(query="广东省博物馆", city=GUANGZHOU)
CHAIN_SEARCH = SearchPoiRequest(query="未名咖啡", city=SHENZHEN)
NO_RESULT_SEARCH = SearchPoiRequest(query="不存在的地点", city=SHENZHEN)
TIMEOUT_SEARCH = SearchPoiRequest(query="超时地点", city=SHENZHEN)

SZ_GET_POI = GetPoiRequest(poi_id=SHENZHEN_MUSEUM.poi_id, city=SHENZHEN)
GZ_GET_POI = GetPoiRequest(poi_id=GUANGZHOU_MUSEUM.poi_id, city=GUANGZHOU)
MISSING_GET_POI = GetPoiRequest(poi_id="poi_missing", city=SHENZHEN)

SZ_ROUTE = RouteRequest(
    city=SHENZHEN,
    origin=SHENZHEN_CAFE_COORDINATE,
    destination=SHENZHEN_MUSEUM_COORDINATE,
    mode=TransportMode.WALKING,
)
GZ_ROUTE = RouteRequest(
    city=GUANGZHOU,
    origin=GUANGZHOU_MUSEUM_COORDINATE,
    destination=Coordinate(
        latitude=23.116700,
        longitude=113.324800,
        coordinate_system=CoordinateSystem.GCJ_02,
    ),
    mode=TransportMode.WALKING,
)

FIXTURE_DATE = date(2026, 7, 22)
SZ_WEATHER = WeatherRequest(city=SHENZHEN, on_date=FIXTURE_DATE)
GZ_WEATHER = WeatherRequest(city=GUANGZHOU, on_date=FIXTURE_DATE)

SZ_NAVIGATION = NavigationRequest(
    city=SHENZHEN,
    poi_id=SHENZHEN_MUSEUM.poi_id,
    coordinate=SHENZHEN_MUSEUM_COORDINATE,
)
GZ_NAVIGATION = NavigationRequest(
    city=GUANGZHOU,
    poi_id=GUANGZHOU_MUSEUM.poi_id,
    coordinate=GUANGZHOU_MUSEUM_COORDINATE,
)


def make_stub_map_provider() -> StubMapProvider:
    """Build a fresh stateless provider over the shared immutable fixture values."""

    return StubMapProvider(
        search_results={
            SZ_UNIQUE_SEARCH: PoiSearchResult(
                city_code="shenzhen",
                pois=(SHENZHEN_MUSEUM,),
            ),
            GZ_UNIQUE_SEARCH: PoiSearchResult(
                city_code="guangzhou",
                pois=(GUANGZHOU_MUSEUM,),
            ),
            CHAIN_SEARCH: PoiSearchResult(
                city_code="shenzhen",
                pois=(SHENZHEN_CHAIN_CAFE_ONE, SHENZHEN_CHAIN_CAFE_TWO),
            ),
            NO_RESULT_SEARCH: PoiSearchResult(city_code="shenzhen"),
        },
        poi_results={
            SZ_GET_POI: GetPoiResult(poi=SHENZHEN_MUSEUM),
            GZ_GET_POI: GetPoiResult(poi=GUANGZHOU_MUSEUM),
        },
        route_results={
            SZ_ROUTE: RouteResult(
                city_code="shenzhen",
                origin=SZ_ROUTE.origin,
                destination=SZ_ROUTE.destination,
                mode=SZ_ROUTE.mode,
                distance_meters=850,
                duration_seconds=720,
            ),
            GZ_ROUTE: RouteResult(
                city_code="guangzhou",
                origin=GZ_ROUTE.origin,
                destination=GZ_ROUTE.destination,
                mode=GZ_ROUTE.mode,
                distance_meters=420,
                duration_seconds=360,
            ),
        },
        weather_results={
            SZ_WEATHER: WeatherResult(
                city_code="shenzhen",
                on_date=FIXTURE_DATE,
                condition="阵雨",
                temperature_celsius=29.0,
                low_temperature_celsius=27.0,
                high_temperature_celsius=32.0,
                summary="午后可能有阵雨",
            ),
            GZ_WEATHER: WeatherResult(
                city_code="guangzhou",
                on_date=FIXTURE_DATE,
                condition="多云",
                temperature_celsius=30.0,
                low_temperature_celsius=27.0,
                high_temperature_celsius=34.0,
            ),
        },
        navigation_results={
            SZ_NAVIGATION: NavigationUri(
                uri="geo:22.541174,114.057701?q=22.541174,114.057701%28poi_sz_moca_up%29"
            ),
            GZ_NAVIGATION: NavigationUri(
                uri="geo:23.117242,113.321242?q=23.117242,113.321242%28poi_gz_museum%29"
            ),
        },
        timeout_requests=(TIMEOUT_SEARCH,),
    )

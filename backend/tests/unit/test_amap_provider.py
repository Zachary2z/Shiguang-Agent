"""Offline Amap adapter tests using only httpx MockTransport responses."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import date
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from app.config import AmapConfigurationError, AmapProviderSettings, Settings
from app.domain.places import (
    CityScope,
    Coordinate,
    CoordinateSystem,
    GetPoiRequest,
    NavigationRequest,
    PoiProvider,
    PoiType,
    RouteRequest,
    SearchPoiRequest,
    TransportMode,
    WeatherRequest,
)
from app.providers import AmapMapProvider, MapProviderError, MapProviderErrorCode

FAKE_KEY = "fake-amap-key-must-not-leak"
FAKE_RAW_RESPONSE = "fake-amap-raw-response-must-not-leak"
SHENZHEN = CityScope(city_code="shenzhen")
GUANGZHOU = CityScope(city_code="guangzhou")
SZ_ORIGIN = Coordinate(
    latitude=22.540325,
    longitude=114.059322,
    coordinate_system=CoordinateSystem.GCJ_02,
)
SZ_DESTINATION = Coordinate(
    latitude=22.541174,
    longitude=114.057701,
    coordinate_system=CoordinateSystem.GCJ_02,
)


def amap_config(
    *,
    max_retries: int = 1,
    retry_after_max_seconds: float = 1.0,
) -> AmapProviderSettings:
    return AmapProviderSettings(
        api_key=SecretStr(FAKE_KEY),
        base_url="https://restapi.amap.com",
        timeout_seconds=1,
        max_retries=max_retries,
        retry_after_max_seconds=retry_after_max_seconds,
    )


def envelope(**values: object) -> dict[str, object]:
    return {"status": "1", "info": "OK", "infocode": "10000", **values}


def raw_poi(
    *,
    poi_id: str = "B0SZ000001",
    name: str = "深圳当代艺术与城市规划馆",
    city_code: str = "shenzhen",
    typecode: str = "140100",
) -> dict[str, object]:
    if city_code == "shenzhen":
        return {
            "id": poi_id,
            "name": name,
            "typecode": typecode,
            "address": "福中路184号",
            "location": "114.057701,22.541174",
            "pname": "广东省",
            "cityname": "深圳市",
            "adname": "福田区",
            "adcode": "440304",
            "citycode": "0755",
            "business_area": "市民中心",
            "tel": "0755-12345678",
        }
    return {
        "id": poi_id,
        "name": name,
        "typecode": typecode,
        "address": "珠江东路2号",
        "location": "113.321242,23.117242",
        "pname": "广东省",
        "cityname": "广州市",
        "adname": "天河区",
        "adcode": "440106",
        "citycode": "020",
        "business_area": "珠江新城",
        "tel": "020-12345678",
    }


def route_payload(
    *,
    distance: str = "850",
    duration: str = "720",
    transit: bool = False,
) -> dict[str, object]:
    choice = {
        "distance": distance,
        "cost": {"duration": duration},
        "steps": [{"unsafe": "ignored"}],
    }
    return envelope(route={"transits" if transit else "paths": [choice]})


def weather_payload(
    *,
    daytemp: object = "32",
    nighttemp: object = "27",
    include_casts: bool = True,
) -> dict[str, object]:
    forecast: dict[str, object] = {
        "province": "广东省",
        "city": "深圳市",
        "adcode": "440300",
    }
    if include_casts:
        forecast["casts"] = [
            {
                "date": "2026-07-22",
                "dayweather": "阵雨",
                "nightweather": "多云",
                "daytemp": daytemp,
                "nighttemp": nighttemp,
            },
            {
                "date": "2026-07-23",
                "dayweather": "晴",
                "nightweather": "晴",
                "daytemp": "33",
                "nighttemp": "28",
            },
        ]
    return envelope(forecasts=[forecast])


def mock_transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def safe_params(request: httpx.Request) -> dict[str, str]:
    params = dict(request.url.params)
    assert params.pop("key", None) == FAKE_KEY
    return params


def exception_graph_text(error: BaseException) -> str:
    """Traverse every public exception link and attribute for leak assertions."""

    pending = [error]
    seen: set[int] = set()
    rendered: list[str] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        rendered.extend(
            (
                str(current),
                repr(current),
                repr(current.args),
                repr(vars(current)),
            )
        )
        for linked in (current.__context__, current.__cause__):
            if linked is not None:
                pending.append(linked)
        pending.extend(
            value for value in vars(current).values() if isinstance(value, BaseException)
        )
    return "\n".join(rendered)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://example.com",
        "https://restapi.amap.com.evil.example",
        "https://user:password@restapi.amap.com",
        "http://restapi.amap.com",
        "https://restapi.amap.com:443",
        "https://restapi.amap.com/v3/place/text",
        "https://restapi.amap.com?key=fake-url-secret",
        "https://restapi.amap.com?",
        "https://restapi.amap.com#fragment",
        "https://restapi.amap.com#",
        "https://restapi.amap.com\n.evil.example",
        "https://[broken",
    ],
)
def test_non_official_base_url_cannot_construct_provider_or_make_http_request(
    base_url: str,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json=envelope(pois=[]))

    with pytest.raises(AmapConfigurationError) as exc_info:
        AmapMapProvider(
            config=AmapProviderSettings(
                api_key=SecretStr(FAKE_KEY),
                base_url=base_url,
                timeout_seconds=1,
                max_retries=0,
                retry_after_max_seconds=0,
            ),
            transport=mock_transport(handler),
        )

    exposed = str(exc_info.value) + repr(exc_info.value) + repr(vars(exc_info.value))
    assert attempts == 0
    assert base_url not in exposed
    assert FAKE_KEY not in exposed


def test_direct_provider_config_normalizes_safe_trailing_slash() -> None:
    config = AmapProviderSettings(
        api_key=SecretStr(FAKE_KEY),
        base_url="https://restapi.amap.com/",
        timeout_seconds=1,
        max_retries=0,
        retry_after_max_seconds=0,
    )

    assert config.base_url == "https://restapi.amap.com"


@pytest.mark.asyncio
async def test_search_uses_request_local_city_citylimit_and_gcj_longitude_first() -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = safe_params(request)
        seen.append((request.url.path, params))
        city = "shenzhen" if params["city"] == "440300" else "guangzhou"
        poi = raw_poi(
            poi_id="B0SZ000001" if city == "shenzhen" else "B0GZ000001",
            name="深圳地点" if city == "shenzhen" else "广州地点",
            city_code=city,
        )
        return httpx.Response(200, json=envelope(pois=[poi]))

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))
    sz_request = SearchPoiRequest(
        query="地点",
        city=SHENZHEN,
        district="福田区",
        location=SZ_ORIGIN,
    )
    gz_request = SearchPoiRequest(query="地点", city=GUANGZHOU)
    before = (sz_request.model_dump(), gz_request.model_dump())

    sz_result = await provider.search_poi(sz_request)
    gz_result = await provider.search_poi(gz_request)

    assert (sz_result.city_code, gz_result.city_code) == ("shenzhen", "guangzhou")
    assert sz_result.pois[0].provider is PoiProvider.AMAP
    assert sz_result.pois[0].coordinate == Coordinate(
        latitude=22.541174,
        longitude=114.057701,
        coordinate_system=CoordinateSystem.GCJ_02,
    )
    assert seen[0] == (
        "/v3/place/text",
        {
            "keywords": "地点 福田区",
            "city": "440300",
            "citylimit": "true",
            "extensions": "all",
            "offset": "20",
            "page": "1",
            "output": "JSON",
            "location": "114.059322,22.540325",
        },
    )
    assert seen[1][1]["city"] == "440100"
    assert (sz_request.model_dump(), gz_request.model_dump()) == before
    await provider.close()


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [
        ("140101", PoiType.MUSEUM),
        ("050501", PoiType.CAFE),
        ("050118", PoiType.RESTAURANT),
        ("060101", PoiType.SHOPPING),
        ("110101", PoiType.PARK),
        ("110201", PoiType.ATTRACTION),
        ("150500", PoiType.TRANSIT),
        ("999999", PoiType.OTHER),
    ],
)
@pytest.mark.asyncio
async def test_poi_type_has_one_mapping_and_unknown_is_other(
    raw_type: str,
    expected: PoiType,
) -> None:
    transport = mock_transport(
        lambda request: httpx.Response(200, json=envelope(pois=[raw_poi(typecode=raw_type)]))
    )
    provider = AmapMapProvider(config=amap_config(), transport=transport)

    result = await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert result.pois[0].poi_type is expected
    await provider.close()


@pytest.mark.parametrize("pois", [[], [raw_poi()], [raw_poi(), raw_poi(poi_id="B0SZ000002")]])
@pytest.mark.asyncio
async def test_search_preserves_empty_unique_and_multiple_results(
    pois: list[dict[str, object]],
) -> None:
    provider = AmapMapProvider(
        config=amap_config(),
        transport=mock_transport(lambda request: httpx.Response(200, json=envelope(pois=pois))),
    )

    result = await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert len(result.pois) == len(pois)
    await provider.close()


@pytest.mark.parametrize(
    "pois",
    [
        [raw_poi(), raw_poi()],
        [raw_poi(), raw_poi(poi_id="B0GZ000001", city_code="guangzhou")],
    ],
)
@pytest.mark.asyncio
async def test_search_rejects_duplicate_or_mixed_city_results(
    pois: list[dict[str, object]],
) -> None:
    provider = AmapMapProvider(
        config=amap_config(max_retries=0),
        transport=mock_transport(lambda request: httpx.Response(200, json=envelope(pois=pois))),
    )

    with pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert exc_info.value.code is MapProviderErrorCode.INVALID_RESPONSE
    await provider.close()


@pytest.mark.asyncio
async def test_get_poi_success_not_found_and_city_conflict() -> None:
    responses = iter(
        [
            envelope(pois=[raw_poi()]),
            envelope(pois=[]),
            envelope(pois=[raw_poi(city_code="guangzhou")]),
        ]
    )
    provider = AmapMapProvider(
        config=amap_config(max_retries=0),
        transport=mock_transport(lambda request: httpx.Response(200, json=next(responses))),
    )
    request = GetPoiRequest(poi_id="B0SZ000001", city=SHENZHEN)

    detail = (await provider.get_poi(request)).poi
    assert (detail.provider, detail.poi_id, detail.city_code) == (
        PoiProvider.AMAP,
        "B0SZ000001",
        "shenzhen",
    )
    with pytest.raises(MapProviderError) as missing:
        await provider.get_poi(request)
    with pytest.raises(MapProviderError) as conflict:
        await provider.get_poi(request)

    assert missing.value.code is MapProviderErrorCode.POI_NOT_FOUND
    assert conflict.value.code is MapProviderErrorCode.INVALID_RESPONSE
    await provider.close()


@pytest.mark.parametrize(
    ("mode", "expected_path"),
    [
        (TransportMode.WALKING, "/v5/direction/walking"),
        (TransportMode.CYCLING, "/v5/direction/bicycling"),
        (TransportMode.TRANSIT, "/v5/direction/transit/integrated"),
        (TransportMode.DRIVING, "/v5/direction/driving"),
    ],
)
@pytest.mark.asyncio
async def test_route_maps_all_modes_and_returns_only_normalized_totals(
    mode: TransportMode,
    expected_path: str,
) -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, safe_params(request)))
        return httpx.Response(200, json=route_payload(transit=mode is TransportMode.TRANSIT))

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))
    request = RouteRequest(city=SHENZHEN, origin=SZ_ORIGIN, destination=SZ_DESTINATION, mode=mode)

    result = await provider.route(request)

    assert seen[0][0] == expected_path
    assert seen[0][1]["origin"] == "114.059322,22.540325"
    assert seen[0][1]["destination"] == "114.057701,22.541174"
    assert seen[0][1]["show_fields"] == "cost"
    if mode is TransportMode.TRANSIT:
        assert (seen[0][1]["city1"], seen[0][1]["city2"]) == ("0755", "0755")
    assert result.distance_meters == 850
    assert result.duration_seconds == 720
    assert result.origin is request.origin
    assert result.destination is request.destination
    assert set(result.model_dump()) == {
        "city_code",
        "origin",
        "destination",
        "mode",
        "distance_meters",
        "duration_seconds",
    }
    await provider.close()


@pytest.mark.parametrize(("distance", "duration"), [("0", "0"), ("850", "720")])
@pytest.mark.asyncio
async def test_route_accepts_zero_and_normal_totals(distance: str, duration: str) -> None:
    provider = AmapMapProvider(
        config=amap_config(),
        transport=mock_transport(
            lambda request: httpx.Response(
                200,
                json=route_payload(distance=distance, duration=duration),
            )
        ),
    )

    result = await provider.route(
        RouteRequest(
            city=SHENZHEN,
            origin=SZ_ORIGIN,
            destination=SZ_DESTINATION,
            mode=TransportMode.WALKING,
        )
    )

    assert (result.distance_meters, result.duration_seconds) == (int(distance), int(duration))
    await provider.close()


@pytest.mark.parametrize(
    ("distance", "duration"),
    [("-1", "10"), ("10", "-1"), ("1.5", "2"), ("1", "NaN")],
)
@pytest.mark.asyncio
async def test_route_rejects_invalid_totals(distance: str, duration: str) -> None:
    provider = AmapMapProvider(
        config=amap_config(max_retries=0),
        transport=mock_transport(
            lambda request: httpx.Response(
                200,
                json=route_payload(distance=distance, duration=duration),
            )
        ),
    )

    with pytest.raises(MapProviderError) as exc_info:
        await provider.route(
            RouteRequest(
                city=SHENZHEN,
                origin=SZ_ORIGIN,
                destination=SZ_DESTINATION,
                mode=TransportMode.WALKING,
            )
        )

    assert exc_info.value.code is MapProviderErrorCode.INVALID_RESPONSE
    await provider.close()


@pytest.mark.asyncio
async def test_weather_uses_city_adcode_and_maps_requested_forecast_date() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(safe_params(request))
        return httpx.Response(200, json=weather_payload())

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))

    result = await provider.weather(WeatherRequest(city=SHENZHEN, on_date=date(2026, 7, 23)))

    assert seen == [{"city": "440300", "extensions": "all", "output": "JSON"}]
    assert result.on_date == date(2026, 7, 23)
    assert result.condition == "晴"
    assert result.temperature_celsius == 33
    assert result.low_temperature_celsius == 28
    assert result.high_temperature_celsius == 33
    assert result.summary == "白天晴，夜间晴"
    await provider.close()


@pytest.mark.parametrize(
    "payload",
    [
        weather_payload(include_casts=False),
        weather_payload(daytemp="not-a-temperature"),
        weather_payload(daytemp="NaN"),
        weather_payload(daytemp="101"),
    ],
)
@pytest.mark.asyncio
async def test_weather_rejects_missing_or_invalid_temperature(payload: dict[str, object]) -> None:
    provider = AmapMapProvider(
        config=amap_config(max_retries=0),
        transport=mock_transport(lambda request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(MapProviderError) as exc_info:
        await provider.weather(WeatherRequest(city=SHENZHEN))

    assert exc_info.value.code is MapProviderErrorCode.INVALID_RESPONSE
    await provider.close()


@pytest.mark.asyncio
async def test_navigation_uri_is_local_key_free_and_does_not_touch_http() -> None:
    attempts = 0

    def fail_if_called(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise AssertionError("navigation URI must not perform HTTP")

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(fail_if_called))

    result = await provider.build_navigation_uri(
        NavigationRequest(city=SHENZHEN, poi_id="B0SZ000001", coordinate=SZ_DESTINATION)
    )

    parsed = urlsplit(result.uri)
    query = parse_qs(parsed.query)
    assert attempts == 0
    assert (parsed.scheme, parsed.netloc, parsed.path) == ("https", "uri.amap.com", "/marker")
    assert query["position"] == ["114.057701,22.541174"]
    assert query["coordinate"] == ["gaode"]
    assert "key" not in query
    assert FAKE_KEY not in result.uri
    await provider.close()


@pytest.mark.parametrize("operation", ["search", "route", "navigation"])
@pytest.mark.asyncio
async def test_non_gcj_coordinates_are_rejected_without_http(operation: str) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500)

    wgs = Coordinate(
        latitude=22.54,
        longitude=114.05,
        coordinate_system=CoordinateSystem.WGS_84,
    )
    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))

    with pytest.raises(MapProviderError) as exc_info:
        if operation == "search":
            await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN, location=wgs))
        elif operation == "route":
            await provider.route(
                RouteRequest(
                    city=SHENZHEN,
                    origin=wgs,
                    destination=wgs,
                    mode=TransportMode.WALKING,
                )
            )
        else:
            await provider.build_navigation_uri(
                NavigationRequest(city=SHENZHEN, poi_id="B0SZ000001", coordinate=wgs)
            )

    assert exc_info.value.code is MapProviderErrorCode.INVALID_REQUEST
    assert attempts == 0
    await provider.close()


@pytest.mark.asyncio
async def test_unsupported_city_is_rejected_without_falling_back_to_shenzhen() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500)

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))

    with pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(
            SearchPoiRequest(query="地点", city=CityScope(city_code="shanghai"))
        )

    assert exc_info.value.code is MapProviderErrorCode.INVALID_REQUEST
    assert attempts == 0
    await provider.close()


@pytest.mark.parametrize("failure", ["timeout", "connection", "500"])
@pytest.mark.asyncio
async def test_recoverable_transport_and_http_errors_retry_once(failure: str) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("safe timeout", request=request)
            if failure == "connection":
                raise httpx.ConnectError("safe connection failure", request=request)
            return httpx.Response(500, text=FAKE_RAW_RESPONSE)
        return httpx.Response(200, json=envelope(pois=[]))

    waits: list[float] = []

    async def wait(seconds: float) -> None:
        waits.append(seconds)

    provider = AmapMapProvider(
        config=amap_config(),
        transport=mock_transport(handler),
        wait=wait,
    )

    result = await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert result.pois == ()
    assert attempts == 2
    assert waits == ([0.0] if failure == "500" else [])
    await provider.close()


@pytest.mark.asyncio
async def test_429_retry_after_is_capped_without_real_sleep_and_attempts_are_bounded() -> None:
    attempts = 0
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "99"}, text=FAKE_RAW_RESPONSE)

    async def wait(seconds: float) -> None:
        waits.append(seconds)

    provider = AmapMapProvider(
        config=amap_config(retry_after_max_seconds=1),
        transport=mock_transport(handler),
        wait=wait,
    )

    with pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert exc_info.value.code is MapProviderErrorCode.RATE_LIMITED
    assert exc_info.value.retry_after_seconds == 1
    assert attempts == 2
    assert waits == [1]
    await provider.close()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, MapProviderErrorCode.AUTHENTICATION_FAILED),
        (403, MapProviderErrorCode.AUTHENTICATION_FAILED),
        (400, MapProviderErrorCode.INVALID_REQUEST),
        (404, MapProviderErrorCode.INVALID_REQUEST),
        (501, MapProviderErrorCode.UNAVAILABLE),
    ],
)
@pytest.mark.asyncio
async def test_non_retryable_http_errors_attempt_once(
    status: int,
    expected: MapProviderErrorCode,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, text=FAKE_RAW_RESPONSE)

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))

    with pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert exc_info.value.code is expected
    assert attempts == 1
    await provider.close()


@pytest.mark.parametrize(
    ("infocode", "expected", "attempts"),
    [
        ("10001", MapProviderErrorCode.AUTHENTICATION_FAILED, 1),
        ("10012", MapProviderErrorCode.AUTHENTICATION_FAILED, 1),
        ("10013", MapProviderErrorCode.AUTHENTICATION_FAILED, 1),
        ("10004", MapProviderErrorCode.RATE_LIMITED, 2),
        ("10014", MapProviderErrorCode.RATE_LIMITED, 2),
        ("10015", MapProviderErrorCode.RATE_LIMITED, 2),
        ("10019", MapProviderErrorCode.RATE_LIMITED, 2),
        ("10016", MapProviderErrorCode.UNAVAILABLE, 2),
        ("10017", MapProviderErrorCode.UNAVAILABLE, 2),
        ("10011", MapProviderErrorCode.INVALID_REQUEST, 1),
        ("20000", MapProviderErrorCode.INVALID_REQUEST, 1),
        ("30001", MapProviderErrorCode.UNAVAILABLE, 2),
        ("99999", MapProviderErrorCode.INVALID_RESPONSE, 1),
    ],
)
@pytest.mark.asyncio
async def test_amap_status_zero_infocodes_are_safely_classified(
    infocode: str,
    expected: MapProviderErrorCode,
    attempts: int,
) -> None:
    actual_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal actual_attempts
        actual_attempts += 1
        return httpx.Response(
            200,
            json={
                "status": "0",
                "info": FAKE_RAW_RESPONSE,
                "infocode": infocode,
            },
        )

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))

    with pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert exc_info.value.code is expected
    assert exc_info.value.retryable is (attempts == 2)
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None
    assert actual_attempts == attempts
    await provider.close()


@pytest.mark.parametrize(
    "infocode",
    ["10014", "10015", "10019", "10016", "10017", "30001"],
)
@pytest.mark.asyncio
async def test_retryable_infocode_first_failure_then_success_attempts_twice(
    infocode: str,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                200,
                json={"status": "0", "info": FAKE_RAW_RESPONSE, "infocode": infocode},
            )
        return httpx.Response(200, json=envelope(pois=[]))

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))

    result = await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert result.pois == ()
    assert attempts == 2
    await provider.close()


@pytest.mark.parametrize("infocode", ["10012", "10013"])
@pytest.mark.asyncio
async def test_permission_infocode_never_attempts_a_second_success(
    infocode: str,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                200,
                json={"status": "0", "info": FAKE_RAW_RESPONSE, "infocode": infocode},
            )
        return httpx.Response(200, json=envelope(pois=[]))

    provider = AmapMapProvider(config=amap_config(), transport=mock_transport(handler))

    with pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert exc_info.value.code is MapProviderErrorCode.AUTHENTICATION_FAILED
    assert exc_info.value.retryable is False
    assert attempts == 1
    await provider.close()


@pytest.mark.parametrize(
    "response_factory",
    [
        lambda: httpx.Response(200, text="not-json"),
        lambda: httpx.Response(200, json={}),
        lambda: httpx.Response(200, json=[]),
        lambda: httpx.Response(200, json={"status": 1, "info": "OK", "infocode": "10000"}),
        lambda: httpx.Response(200, json=envelope(pois="not-a-list")),
    ],
)
@pytest.mark.asyncio
async def test_non_json_empty_json_and_wrong_field_types_are_invalid(
    response_factory: Callable[[], httpx.Response],
) -> None:
    provider = AmapMapProvider(
        config=amap_config(max_retries=0),
        transport=mock_transport(lambda request: response_factory()),
    )

    with pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert exc_info.value.code is MapProviderErrorCode.INVALID_RESPONSE
    await provider.close()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda poi: poi.pop("id"),
        lambda poi: poi.update(name=[]),
        lambda poi: poi.update(address=""),
        lambda poi: poi.update(location="22.54,114.05,extra"),
        lambda poi: poi.update(location="NaN,22.54"),
        lambda poi: poi.update(location="181,22.54"),
        lambda poi: poi.update(adcode="440106"),
        lambda poi: poi.update(pname="not-guangdong"),
        lambda poi: poi.update(cityname="广州市"),
        lambda poi: poi.update(citycode="020"),
        lambda poi: poi.update(typecode="damaged"),
    ],
)
@pytest.mark.asyncio
async def test_poi_required_fields_coordinates_and_city_membership_are_strict(
    mutation: Callable[[dict[str, object]], object],
) -> None:
    poi = raw_poi()
    mutation(poi)
    provider = AmapMapProvider(
        config=amap_config(max_retries=0),
        transport=mock_transport(lambda request: httpx.Response(200, json=envelope(pois=[poi]))),
    )

    with pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    assert exc_info.value.code is MapProviderErrorCode.INVALID_RESPONSE
    await provider.close()


@pytest.mark.asyncio
async def test_cancelled_error_propagates_unchanged() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    provider = AmapMapProvider(
        config=amap_config(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(asyncio.CancelledError):
        await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))

    await provider.close()


@pytest.mark.asyncio
async def test_repeated_and_concurrent_city_calls_do_not_share_city_state() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        params = safe_params(request)
        await asyncio.sleep(0)
        if params["city"] == "440300":
            return httpx.Response(200, json=envelope(pois=[raw_poi()]))
        return httpx.Response(
            200,
            json=envelope(
                pois=[raw_poi(poi_id="B0GZ000001", name="广州地点", city_code="guangzhou")]
            ),
        )

    provider = AmapMapProvider(config=amap_config(), transport=httpx.MockTransport(handler))
    requests = (
        SearchPoiRequest(query="地点", city=SHENZHEN),
        SearchPoiRequest(query="地点", city=GUANGZHOU),
    ) * 20
    before = [request.model_dump() for request in requests]

    results = await asyncio.gather(*(provider.search_poi(request) for request in requests))

    assert [result.city_code for result in results] == [
        city for _ in range(20) for city in ("shenzhen", "guangzhou")
    ]
    assert all(poi.city_code == result.city_code for result in results for poi in result.pois)
    assert [request.model_dump() for request in requests] == before
    await provider.close()


@pytest.mark.asyncio
async def test_errors_repr_public_dict_and_logs_never_expose_secret_url_or_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = AmapMapProvider(
        config=amap_config(max_retries=0),
        transport=mock_transport(
            lambda request: httpx.Response(500, text=f"{FAKE_RAW_RESPONSE} {FAKE_KEY}")
        ),
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query="sensitive query", city=SHENZHEN))

    public_text = repr(provider) + repr(exc_info.value) + str(exc_info.value.to_public_dict())
    for sensitive in (FAKE_KEY, FAKE_RAW_RESPONSE, "sensitive query", "Authorization", "?key="):
        assert sensitive not in public_text
        assert sensitive not in caplog.text
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None
    await provider.close()


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("timeout", MapProviderErrorCode.TIMEOUT),
        ("connect", MapProviderErrorCode.UNAVAILABLE),
        ("non_json", MapProviderErrorCode.INVALID_RESPONSE),
        ("poi_validation", MapProviderErrorCode.INVALID_RESPONSE),
    ],
)
@pytest.mark.asyncio
async def test_public_error_chain_fully_detaches_sensitive_provider_objects(
    failure: str,
    expected_code: MapProviderErrorCode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    nested_secret = "fake-nested-provider-secret-must-not-leak"
    query = "sensitive query for detached exception"

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout(nested_secret, request=request)
        if failure == "connect":
            raise httpx.ConnectError(nested_secret, request=request)
        if failure == "non_json":
            return httpx.Response(200, text=f"not-json {nested_secret} {FAKE_RAW_RESPONSE}")
        poi = raw_poi(name=(nested_secret + "-") * 12)
        return httpx.Response(200, json=envelope(pois=[poi]))

    provider = AmapMapProvider(
        config=amap_config(max_retries=0),
        transport=mock_transport(handler),
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(MapProviderError) as exc_info:
        await provider.search_poi(SearchPoiRequest(query=query, city=SHENZHEN))

    error = exc_info.value
    exposed = "\n".join(
        (
            exception_graph_text(error),
            repr(provider),
            str(error.to_public_dict()),
            caplog.text,
        )
    )
    assert error.code is expected_code
    assert error.__context__ is None
    assert error.__cause__ is None
    for sensitive in (
        FAKE_KEY,
        nested_secret,
        FAKE_RAW_RESPONSE,
        query,
        "https://restapi.amap.com/v3/place/text",
        "?key=",
    ):
        assert sensitive not in exposed

    await provider.close()


@pytest.mark.asyncio
async def test_from_settings_injects_mock_transport_and_connection_pool_closes() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        amap_api_key=FAKE_KEY,
    )
    provider = AmapMapProvider.from_settings(
        settings,
        transport=mock_transport(lambda request: httpx.Response(200, json=envelope(pois=[]))),
    )

    assert (await provider.search_poi(SearchPoiRequest(query="地点", city=SHENZHEN))).pois == ()
    await provider.close()
    await provider.close()
    assert provider._client.is_closed  # noqa: SLF001 - lifecycle is the behavior under test


def test_map_errors_validate_retry_after_and_publish_only_stable_fields() -> None:
    error = MapProviderError(
        code=MapProviderErrorCode.RATE_LIMITED,
        retry_after_seconds=1.5,
    )

    assert error.to_public_dict() == {
        "code": "MAP_PROVIDER_RATE_LIMITED",
        "summary": "The map provider rate limit was reached.",
        "retryable": True,
        "retry_after_seconds": 1.5,
    }
    for invalid in (-1.0, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            MapProviderError(
                code=MapProviderErrorCode.RATE_LIMITED,
                retry_after_seconds=invalid,
            )
    with pytest.raises(ValueError):
        MapProviderError(code=MapProviderErrorCode.TIMEOUT, retry_after_seconds=1)


def test_test_fixtures_do_not_mutate_shared_payloads() -> None:
    payload = weather_payload()
    snapshot = deepcopy(payload)

    assert weather_payload() == snapshot
    assert payload == snapshot

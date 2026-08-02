"""Server-side Amap Web Service adapter with strict provider-neutral mapping."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date
from math import isfinite
from types import MappingProxyType
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError

from app.config import AmapProviderSettings, Settings
from app.domain.places import (
    Coordinate,
    CoordinateSystem,
    GetPoiRequest,
    GetPoiResult,
    NavigationRequest,
    NavigationUri,
    Poi,
    PoiProvider,
    PoiSearchResult,
    PoiType,
    RouteRequest,
    RouteResult,
    SearchPoiRequest,
    TransportMode,
    WeatherRequest,
    WeatherResult,
)
from app.providers.http_logging import enforce_safe_http_client_logging
from app.providers.map import MapProvider, MapProviderError, MapProviderErrorCode

WaitFunction = Callable[[float], Awaitable[None]]

_RECOVERABLE_HTTP_STATUSES = frozenset({500, 502, 503, 504})
_AUTHENTICATION_INFOCODES = frozenset(
    {
        "10001",
        "10002",
        "10005",
        "10006",
        "10007",
        "10008",
        "10009",
        "10012",
        "10013",
        "10026",
        "10041",
    }
)
_RATE_LIMIT_INFOCODES = frozenset(
    {
        "10003",
        "10004",
        "10010",
        "10014",
        "10015",
        "10019",
        "10020",
        "10021",
        "10029",
        "10044",
        "10045",
    }
)
_TEMPORARILY_UNAVAILABLE_INFOCODES = frozenset({"10016", "10017"})
_INVALID_REQUEST_INFOCODES = frozenset({"10011"})
_REQUEST_INFOCODE_PREFIXES = ("2",)
@dataclass(frozen=True, slots=True)
class _AmapCity:
    city_code: str
    adcode: str
    citycode: str
    province_names: tuple[str, ...]
    city_names: tuple[str, ...]

    def owns_adcode(self, value: str) -> bool:
        return len(value) == 6 and value.isdigit() and value[:4] == self.adcode[:4]


_AMAP_CITIES: Mapping[str, _AmapCity] = MappingProxyType(
    {
        "shenzhen": _AmapCity(
            city_code="shenzhen",
            adcode="440300",
            citycode="0755",
            province_names=("广东省", "广东"),
            city_names=("深圳市", "深圳"),
        ),
        "guangzhou": _AmapCity(
            city_code="guangzhou",
            adcode="440100",
            citycode="020",
            province_names=("广东省", "广东"),
            city_names=("广州市", "广州"),
        ),
    }
)
_AMAP_CITIES_BY_CITYCODE: Mapping[str, _AmapCity] = MappingProxyType(
    {city.citycode: city for city in _AMAP_CITIES.values()}
)

# Amap typecode prefixes are ordered from specific to broad and map exactly once here.
_POI_TYPE_PREFIXES: tuple[tuple[str, PoiType], ...] = (
    ("1401", PoiType.MUSEUM),
    ("0505", PoiType.CAFE),
    ("05", PoiType.RESTAURANT),
    ("06", PoiType.SHOPPING),
    ("1101", PoiType.PARK),
    ("11", PoiType.ATTRACTION),
    ("15", PoiType.TRANSIT),
)

_ROUTE_PATHS: Mapping[TransportMode, str] = MappingProxyType(
    {
        TransportMode.WALKING: "/v5/direction/walking",
        TransportMode.CYCLING: "/v5/direction/bicycling",
        TransportMode.TRANSIT: "/v5/direction/transit/integrated",
        TransportMode.DRIVING: "/v5/direction/driving",
    }
)


class _InvalidAmapResponse(ValueError):
    """Internal sentinel carrying no response data."""


class _UnsupportedAmapCity(ValueError):
    """Internal sentinel for a valid identity outside the supported city catalog."""


class _InvalidAmapRequest(ValueError):
    """Internal sentinel for a valid request unsupported by the current response."""


def create_amap_http_client(
    *,
    config: AmapProviderSettings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Construct the adapter's only HTTP client, with injectable offline transport."""

    return httpx.AsyncClient(
        base_url=config.base_url,
        timeout=httpx.Timeout(config.timeout_seconds),
        follow_redirects=False,
        transport=transport,
    )


class AmapMapProvider(MapProvider):
    """Implement the single MapProvider contract using Amap Web Service APIs."""

    def __init__(
        self,
        *,
        config: AmapProviderSettings,
        transport: httpx.AsyncBaseTransport | None = None,
        wait: WaitFunction = asyncio.sleep,
    ) -> None:
        enforce_safe_http_client_logging()
        self._client = create_amap_http_client(config=config, transport=transport)
        self._api_key = config.api_key.get_secret_value()
        self._max_retries = config.max_retries
        self._retry_after_max_seconds = config.retry_after_max_seconds
        self._wait = wait

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        wait: WaitFunction = asyncio.sleep,
    ) -> AmapMapProvider:
        """Construct the real adapter only after deferred configuration validation."""

        return cls(
            config=settings.require_amap_provider(),
            transport=transport,
            wait=wait,
        )

    async def __aenter__(self) -> AmapMapProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the owned connection pool; repeated closes are safe."""

        await self._client.aclose()

    async def search_poi(self, request: SearchPoiRequest) -> PoiSearchResult:
        city = _require_city(request.city.city_code)
        params: dict[str, str] = {
            "keywords": _search_keywords(request),
            "city": city.adcode,
            "citylimit": "true",
            "extensions": "all",
            "offset": "20",
            "page": "1",
            "output": "JSON",
        }
        if request.location is not None:
            _require_gcj_02(request.location)
            params["location"] = _coordinate_text(request.location)

        payload = await self._request_json("/v3/place/text", params=params)
        result: PoiSearchResult | None = None
        invalid_response = False
        try:
            raw_pois = _required_list(payload, "pois")
            mapped_pois: list[Poi] = []
            for item in raw_pois:
                try:
                    poi = _map_poi(item, city=city)
                except (_InvalidAmapResponse, ValidationError, TypeError, ValueError):
                    continue
                mapped_pois.append(poi)
            if raw_pois and not mapped_pois:
                raise _InvalidAmapResponse
            pois = _deduplicate_search_pois(mapped_pois)
            if raw_pois and not pois:
                raise _InvalidAmapResponse
            result = PoiSearchResult(city_code=city.city_code, pois=pois)
        except (_InvalidAmapResponse, ValidationError, TypeError, ValueError):
            invalid_response = True
        if invalid_response:
            raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
        assert result is not None
        return result

    async def get_poi(self, request: GetPoiRequest) -> GetPoiResult:
        asserted_city = (
            None if request.city is None else _require_city(request.city.city_code)
        )
        payload = await self._request_json(
            "/v3/place/detail",
            params={"id": request.poi_id, "extensions": "all", "output": "JSON"},
        )
        result: GetPoiResult | None = None
        error_code: MapProviderErrorCode | None = None
        try:
            raw_pois = _required_list(payload, "pois")
            if not raw_pois:
                error_code = MapProviderErrorCode.POI_NOT_FOUND
            elif len(raw_pois) != 1:
                raise _InvalidAmapResponse
            else:
                city = asserted_city or _city_from_poi(raw_pois[0])
                poi = _map_poi(raw_pois[0], city=city)
                if poi.poi_id != request.poi_id:
                    raise _InvalidAmapResponse
                result = GetPoiResult(poi=poi)
        except _UnsupportedAmapCity:
            error_code = MapProviderErrorCode.UNSUPPORTED_CITY
        except (_InvalidAmapResponse, ValidationError, TypeError, ValueError):
            error_code = MapProviderErrorCode.INVALID_RESPONSE
        if error_code is not None:
            raise MapProviderError(code=error_code)
        assert result is not None
        return result

    async def route(self, request: RouteRequest) -> RouteResult:
        city = _require_city(request.city.city_code)
        _require_gcj_02(request.origin)
        _require_gcj_02(request.destination)
        params = {
            "origin": _coordinate_text(request.origin),
            "destination": _coordinate_text(request.destination),
            "show_fields": "cost",
            "output": "JSON",
        }
        if request.mode is TransportMode.TRANSIT:
            params.update(
                {
                    "city1": city.citycode,
                    "city2": city.citycode,
                    "strategy": "0",
                    "AlternativeRoute": "1",
                }
            )
        elif request.mode is TransportMode.DRIVING:
            params.update({"strategy": "32", "alternative_route": "1"})
        else:
            params["alternative_route"] = "1"

        payload = await self._request_json(_ROUTE_PATHS[request.mode], params=params)
        result: RouteResult | None = None
        invalid_response = False
        try:
            route = _required_mapping(payload, "route")
            choices_key = "transits" if request.mode is TransportMode.TRANSIT else "paths"
            choices = _required_list(route, choices_key)
            if not choices:
                raise _InvalidAmapResponse
            choice = _mapping_value(choices[0])
            distance = _non_negative_integer(choice, "distance")
            cost = _required_mapping(choice, "cost")
            duration = _non_negative_integer(cost, "duration")
            result = RouteResult(
                city_code=city.city_code,
                origin=request.origin,
                destination=request.destination,
                mode=request.mode,
                distance_meters=distance,
                duration_seconds=duration,
            )
        except (_InvalidAmapResponse, ValidationError, TypeError, ValueError):
            invalid_response = True
        if invalid_response:
            raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
        assert result is not None
        return result

    async def weather(self, request: WeatherRequest) -> WeatherResult:
        city = _require_city(request.city.city_code)
        payload = await self._request_json(
            "/v3/weather/weatherInfo",
            params={"city": city.adcode, "extensions": "all", "output": "JSON"},
        )
        result: WeatherResult | None = None
        error_code: MapProviderErrorCode | None = None
        try:
            forecasts = _required_list(payload, "forecasts")
            if len(forecasts) != 1:
                raise _InvalidAmapResponse
            forecast = _mapping_value(forecasts[0])
            _validate_city(forecast, city=city, require_citycode=False)
            casts = _required_list(forecast, "casts")
            parsed_casts = tuple((_cast_date(item), _mapping_value(item)) for item in casts)
            if len({cast_date for cast_date, _ in parsed_casts}) != len(parsed_casts):
                raise _InvalidAmapResponse
            target_date = request.on_date or (parsed_casts[0][0] if parsed_casts else None)
            if target_date is None:
                raise _InvalidAmapResponse
            matching = [item for cast_date, item in parsed_casts if cast_date == target_date]
            if not matching:
                raise _InvalidAmapRequest
            cast = matching[0]
            day_condition = _required_text(cast, "dayweather")
            night_condition = _required_text(cast, "nightweather")
            day_temperature = _temperature(cast, "daytemp")
            night_temperature = _temperature(cast, "nighttemp")
            low = min(day_temperature, night_temperature)
            high = max(day_temperature, night_temperature)
            condition = (
                day_condition
                if day_condition == night_condition
                else f"{day_condition}转{night_condition}"
            )
            summary = f"白天{day_condition}，夜间{night_condition}"
            result = WeatherResult(
                city_code=city.city_code,
                on_date=target_date,
                condition=condition,
                temperature_celsius=day_temperature,
                low_temperature_celsius=low,
                high_temperature_celsius=high,
                summary=summary,
            )
        except _InvalidAmapRequest:
            error_code = MapProviderErrorCode.INVALID_REQUEST
        except (_InvalidAmapResponse, ValidationError, TypeError, ValueError):
            error_code = MapProviderErrorCode.INVALID_RESPONSE
        if error_code is not None:
            raise MapProviderError(code=error_code)
        assert result is not None
        return result

    async def build_navigation_uri(self, request: NavigationRequest) -> NavigationUri:
        _require_city(request.city.city_code)
        _require_gcj_02(request.coordinate)
        query = urlencode(
            {
                "position": _coordinate_text(request.coordinate),
                "name": request.poi_id,
                "src": "shiguang",
                "coordinate": "gaode",
                "callnative": "0",
            }
        )
        result: NavigationUri | None = None
        invalid_response = False
        try:
            result = NavigationUri(uri=f"https://uri.amap.com/marker?{query}")
        except (ValidationError, TypeError, ValueError):
            invalid_response = True
        if invalid_response:
            raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
        assert result is not None
        return result

    async def _request_json(self, path: str, *, params: Mapping[str, str]) -> Mapping[str, object]:
        safe_params = dict(params)
        safe_params["key"] = self._api_key
        for attempt in range(self._max_retries + 1):
            response: httpx.Response | None = None
            transport_error_code: MapProviderErrorCode | None = None
            try:
                response = await self._client.get(path, params=safe_params)
            except asyncio.CancelledError:
                raise
            except httpx.TimeoutException:
                transport_error_code = MapProviderErrorCode.TIMEOUT
            except httpx.TransportError:
                transport_error_code = MapProviderErrorCode.UNAVAILABLE
            if transport_error_code is not None:
                if attempt < self._max_retries:
                    continue
                raise MapProviderError(code=transport_error_code)
            assert response is not None

            http_error = _http_error(response, retry_after_cap=self._retry_after_max_seconds)
            if http_error is not None:
                if attempt < self._max_retries and (
                    response.status_code in _RECOVERABLE_HTTP_STATUSES
                    or response.status_code == 429
                ):
                    await self._wait_for_retry(http_error.retry_after_seconds or 0.0)
                    continue
                raise http_error

            decoded: object = None
            decode_failed = False
            try:
                decoded = response.json()
            except ValueError:
                decode_failed = True
            if decode_failed:
                raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
            if not isinstance(decoded, dict) or not decoded:
                raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
            payload: Mapping[str, object] = decoded
            vendor_error = _validate_envelope(payload)
            if vendor_error is None:
                return payload
            if attempt < self._max_retries and vendor_error.code in {
                MapProviderErrorCode.RATE_LIMITED,
                MapProviderErrorCode.UNAVAILABLE,
            }:
                await self._wait_for_retry(vendor_error.retry_after_seconds or 0.0)
                continue
            raise vendor_error
        raise AssertionError("bounded Amap request loop exhausted")

    async def _wait_for_retry(self, seconds: float) -> None:
        wait_failed = False
        try:
            await self._wait(seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            wait_failed = True
        if wait_failed:
            raise MapProviderError(code=MapProviderErrorCode.UNAVAILABLE)


def _require_city(city_code: str) -> _AmapCity:
    city = _AMAP_CITIES.get(city_code)
    if city is None:
        raise MapProviderError(code=MapProviderErrorCode.INVALID_REQUEST)
    return city


def _city_from_poi(value: object) -> _AmapCity:
    item = _mapping_value(value)
    city = _AMAP_CITIES_BY_CITYCODE.get(_required_text(item, "citycode"))
    if city is None:
        raise _UnsupportedAmapCity
    _validate_city(item, city=city)
    return city


def _require_gcj_02(coordinate: Coordinate) -> None:
    if coordinate.coordinate_system is not CoordinateSystem.GCJ_02:
        raise MapProviderError(code=MapProviderErrorCode.INVALID_REQUEST)


def _coordinate_text(coordinate: Coordinate) -> str:
    return f"{coordinate.longitude:.6f},{coordinate.latitude:.6f}"


def _search_keywords(request: SearchPoiRequest) -> str:
    keywords = request.query if request.district is None else f"{request.query} {request.district}"
    if len(keywords) > 80:
        raise MapProviderError(code=MapProviderErrorCode.INVALID_REQUEST)
    return keywords


def _http_error(
    response: httpx.Response,
    *,
    retry_after_cap: float,
) -> MapProviderError | None:
    status = response.status_code
    if 200 <= status < 300:
        return None
    if status in {401, 403}:
        return MapProviderError(code=MapProviderErrorCode.AUTHENTICATION_FAILED)
    if status == 429:
        return MapProviderError(
            code=MapProviderErrorCode.RATE_LIMITED,
            retry_after_seconds=_retry_after(response, cap=retry_after_cap),
        )
    if 400 <= status < 500:
        return MapProviderError(code=MapProviderErrorCode.INVALID_REQUEST)
    return MapProviderError(code=MapProviderErrorCode.UNAVAILABLE)


def _retry_after(response: httpx.Response, *, cap: float) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    if not isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, cap)


def _validate_envelope(payload: Mapping[str, object]) -> MapProviderError | None:
    status = payload.get("status")
    info = payload.get("info")
    infocode = payload.get("infocode")
    if not all(isinstance(value, str) for value in (status, info, infocode)):
        return MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
    assert isinstance(status, str)
    assert isinstance(info, str)
    assert isinstance(infocode, str)
    if status == "1":
        if info.casefold() == "ok" and infocode == "10000":
            return None
        return MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
    if status != "0" or not infocode:
        return MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
    if infocode in _AUTHENTICATION_INFOCODES:
        return MapProviderError(code=MapProviderErrorCode.AUTHENTICATION_FAILED)
    if infocode in _RATE_LIMIT_INFOCODES:
        return MapProviderError(code=MapProviderErrorCode.RATE_LIMITED)
    if infocode in _TEMPORARILY_UNAVAILABLE_INFOCODES:
        return MapProviderError(code=MapProviderErrorCode.UNAVAILABLE)
    if infocode in _INVALID_REQUEST_INFOCODES or infocode.startswith(
        _REQUEST_INFOCODE_PREFIXES
    ):
        return MapProviderError(code=MapProviderErrorCode.INVALID_REQUEST)
    if infocode.startswith("3"):
        return MapProviderError(code=MapProviderErrorCode.UNAVAILABLE)
    return MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)


def _required_list(container: Mapping[str, object], key: str) -> list[object]:
    value = container.get(key)
    if not isinstance(value, list):
        raise _InvalidAmapResponse
    return value


def _required_mapping(container: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _mapping_value(container.get(key))


def _mapping_value(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise _InvalidAmapResponse
    return value


def _required_text(container: Mapping[str, object], key: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _InvalidAmapResponse
    return " ".join(value.split())


def _optional_text(container: Mapping[str, object], key: str) -> str | None:
    if key not in container:
        return None
    value = container[key]
    if isinstance(value, list) and not value:
        return None
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _validate_city(
    item: Mapping[str, object],
    *,
    city: _AmapCity,
    require_citycode: bool = True,
) -> None:
    adcode = _required_text(item, "adcode")
    province = _required_text(item, "pname" if "pname" in item else "province")
    city_name = _required_text(item, "cityname" if "cityname" in item else "city")
    if (
        not city.owns_adcode(adcode)
        or province not in city.province_names
        or city_name not in city.city_names
    ):
        raise _InvalidAmapResponse
    if require_citycode and _required_text(item, "citycode") != city.citycode:
        raise _InvalidAmapResponse


def _map_poi(value: object, *, city: _AmapCity) -> Poi:
    item = _mapping_value(value)
    _validate_city(item, city=city)
    location = _required_text(item, "location")
    components = location.split(",")
    if len(components) != 2:
        raise _InvalidAmapResponse
    longitude: float | None = None
    latitude: float | None = None
    invalid_coordinate = False
    try:
        longitude, latitude = (float(component) for component in components)
    except ValueError:
        invalid_coordinate = True
    if invalid_coordinate:
        raise _InvalidAmapResponse
    assert longitude is not None
    assert latitude is not None
    if not isfinite(longitude) or not isfinite(latitude):
        raise _InvalidAmapResponse
    typecode = _optional_text(item, "typecode")
    return Poi(
        provider=PoiProvider.AMAP,
        poi_id=_required_text(item, "id"),
        name=_required_text(item, "name"),
        branch_name=None,
        city_code=city.city_code,
        district=_optional_text(item, "adname"),
        business_area=_optional_text(item, "business_area"),
        address=_optional_text(item, "address"),
        coordinate=Coordinate(
            latitude=latitude,
            longitude=longitude,
            coordinate_system=CoordinateSystem.GCJ_02,
        ),
        poi_type=_map_poi_type(typecode),
        phone=_optional_text(item, "tel"),
        opening_hours_summary=None,
    )


def _map_poi_type(typecode: str | None) -> PoiType:
    if (
        typecode is None
        or len(typecode) != 6
        or not typecode.isascii()
        or not typecode.isdigit()
    ):
        return PoiType.OTHER
    for prefix, poi_type in _POI_TYPE_PREFIXES:
        if typecode.startswith(prefix):
            return poi_type
    return PoiType.OTHER


def _deduplicate_search_pois(pois: list[Poi]) -> tuple[Poi, ...]:
    """Keep identical identities once and isolate identities with conflicting core facts."""

    grouped: dict[tuple[PoiProvider, str], list[Poi]] = {}
    for poi in pois:
        grouped.setdefault((poi.provider, poi.poi_id), []).append(poi)

    accepted: list[Poi] = []
    for identity_pois in grouped.values():
        first = identity_pois[0]
        first_core = _poi_core_facts(first)
        if all(_poi_core_facts(item) == first_core for item in identity_pois[1:]):
            accepted.append(first)
    return tuple(accepted)


def _poi_core_facts(poi: Poi) -> tuple[object, ...]:
    return (
        poi.provider,
        poi.poi_id,
        poi.name,
        poi.city_code,
        poi.coordinate,
    )


def _non_negative_integer(container: Mapping[str, object], key: str) -> int:
    value = _required_text(container, key)
    if not value.isascii() or not value.isdigit():
        raise _InvalidAmapResponse
    parsed = int(value)
    if parsed < 0:
        raise _InvalidAmapResponse
    return parsed


def _cast_date(value: object) -> date:
    item = _mapping_value(value)
    parsed: date | None = None
    invalid_date = False
    try:
        parsed = date.fromisoformat(_required_text(item, "date"))
    except ValueError:
        invalid_date = True
    if invalid_date:
        raise _InvalidAmapResponse
    assert parsed is not None
    return parsed


def _temperature(container: Mapping[str, object], key: str) -> float:
    value: float | None = None
    invalid_temperature = False
    try:
        value = float(_required_text(container, key))
    except ValueError:
        invalid_temperature = True
    if invalid_temperature:
        raise _InvalidAmapResponse
    assert value is not None
    if not isfinite(value) or value < -100 or value > 100:
        raise _InvalidAmapResponse
    return value

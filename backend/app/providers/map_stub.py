"""Deterministic, injectable, and completely offline MapProvider stub."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection, Mapping
from types import MappingProxyType
from typing import TypeVar
from urllib.parse import quote

from pydantic import BaseModel

from app.domain.places import (
    GetPoiRequest,
    GetPoiResult,
    NavigationRequest,
    NavigationUri,
    PoiSearchResult,
    RouteRequest,
    RouteResult,
    SearchPoiRequest,
    WeatherRequest,
    WeatherResult,
)
from app.providers.map import MapProvider, MapProviderError, MapProviderErrorCode

MapRequest = (
    SearchPoiRequest | GetPoiRequest | RouteRequest | WeatherRequest | NavigationRequest
)
MapCallHook = Callable[[MapRequest], Awaitable[None]]
_RequestT = TypeVar("_RequestT", bound=BaseModel)
_ResultT = TypeVar("_ResultT", bound=BaseModel)


class StubMapProvider(MapProvider):
    """Serve immutable fixture mappings without queues, caches, retries, or I/O."""

    def __init__(
        self,
        *,
        search_results: Mapping[SearchPoiRequest, PoiSearchResult] | None = None,
        poi_results: Mapping[GetPoiRequest, GetPoiResult] | None = None,
        route_results: Mapping[RouteRequest, RouteResult] | None = None,
        weather_results: Mapping[WeatherRequest, WeatherResult] | None = None,
        navigation_results: Mapping[NavigationRequest, NavigationUri] | None = None,
        timeout_requests: Collection[MapRequest] = (),
        call_hook: MapCallHook | None = None,
    ) -> None:
        self._search_results = self._snapshot(search_results)
        self._poi_results = self._snapshot(poi_results)
        self._route_results = self._snapshot(route_results)
        self._weather_results = self._snapshot(weather_results)
        self._navigation_results = self._snapshot(navigation_results)
        self._timeout_requests = frozenset(
            request.model_copy(deep=True) for request in timeout_requests
        )
        self._call_hook = call_hook
        self._validate_fixtures()

    @staticmethod
    def _snapshot(
        values: Mapping[_RequestT, _ResultT] | None,
    ) -> Mapping[_RequestT, _ResultT]:
        if values is None:
            return MappingProxyType({})
        return MappingProxyType(
            {
                request.model_copy(deep=True): result.model_copy(deep=True)
                for request, result in values.items()
            }
        )

    def _validate_fixtures(self) -> None:
        for search_request, search_result in self._search_results.items():
            if search_result.city_code != search_request.city.city_code:
                raise ValueError("search fixture city must match its request city")
        for poi_request, poi_result in self._poi_results.items():
            if poi_result.poi.city_code != poi_request.city.city_code:
                raise ValueError("POI fixture city must match its request city")
            if poi_result.poi.poi_id != poi_request.poi_id:
                raise ValueError("POI fixture identifier must match its request")
        for route_request, route_result in self._route_results.items():
            if (
                route_result.city_code != route_request.city.city_code
                or route_result.origin != route_request.origin
                or route_result.destination != route_request.destination
                or route_result.mode is not route_request.mode
            ):
                raise ValueError("route fixture must match its request")
        for weather_request, weather_result in self._weather_results.items():
            if weather_result.city_code != weather_request.city.city_code:
                raise ValueError("weather fixture city must match its request city")
            if (
                weather_request.on_date is not None
                and weather_result.on_date != weather_request.on_date
            ):
                raise ValueError("weather fixture date must match its request date")

    async def _before_call(self, request: MapRequest) -> None:
        if self._call_hook is not None:
            hook_failed = False
            try:
                await self._call_hook(request.model_copy(deep=True))
            except asyncio.CancelledError:
                raise
            except Exception:
                hook_failed = True
            if hook_failed:
                # Raise outside the handler so the unsafe test exception is not retained as
                # ``__context__`` on the public-safe provider failure.
                raise MapProviderError(code=MapProviderErrorCode.UNAVAILABLE)
        if request in self._timeout_requests:
            raise MapProviderError(code=MapProviderErrorCode.TIMEOUT)

    async def search_poi(self, request: SearchPoiRequest) -> PoiSearchResult:
        await self._before_call(request)
        result = self._search_results.get(request)
        if result is None:
            return PoiSearchResult(city_code=request.city.city_code)
        return result.model_copy(deep=True)

    async def get_poi(self, request: GetPoiRequest) -> GetPoiResult:
        await self._before_call(request)
        result = self._poi_results.get(request)
        if result is None:
            raise MapProviderError(code=MapProviderErrorCode.POI_NOT_FOUND)
        return result.model_copy(deep=True)

    async def route(self, request: RouteRequest) -> RouteResult:
        await self._before_call(request)
        result = self._route_results.get(request)
        if result is None:
            raise MapProviderError(code=MapProviderErrorCode.UNAVAILABLE)
        return result.model_copy(deep=True)

    async def weather(self, request: WeatherRequest) -> WeatherResult:
        await self._before_call(request)
        result = self._weather_results.get(request)
        if result is None:
            raise MapProviderError(code=MapProviderErrorCode.UNAVAILABLE)
        return result.model_copy(deep=True)

    async def build_navigation_uri(self, request: NavigationRequest) -> NavigationUri:
        await self._before_call(request)
        result = self._navigation_results.get(request)
        if result is not None:
            return result.model_copy(deep=True)
        latitude = f"{request.coordinate.latitude:.6f}"
        longitude = f"{request.coordinate.longitude:.6f}"
        label = quote(request.poi_id, safe="")
        return NavigationUri(
            uri=f"geo:{latitude},{longitude}?q={latitude},{longitude}%28{label}%29"
        )

"""The single provider-neutral map capability boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

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


class MapProviderErrorCode(StrEnum):
    """Stable error codes that never expose an SDK or provider response."""

    TIMEOUT = "MAP_PROVIDER_TIMEOUT"
    POI_NOT_FOUND = "MAP_POI_NOT_FOUND"
    UNAVAILABLE = "MAP_PROVIDER_UNAVAILABLE"


_ERROR_SUMMARIES = {
    MapProviderErrorCode.TIMEOUT: "The map provider request timed out.",
    MapProviderErrorCode.POI_NOT_FOUND: "The requested POI was not found.",
    MapProviderErrorCode.UNAVAILABLE: "The map provider request is unavailable.",
}


class MapProviderError(Exception):
    """A fixed, public-safe map failure with no retained provider payload."""

    def __init__(self, *, code: MapProviderErrorCode) -> None:
        if not isinstance(code, MapProviderErrorCode):
            raise TypeError("code must be a MapProviderErrorCode")
        summary = _ERROR_SUMMARIES[code]
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.retryable = code in {
            MapProviderErrorCode.TIMEOUT,
            MapProviderErrorCode.UNAVAILABLE,
        }

    def to_public_dict(self) -> dict[str, object]:
        """Return only stable fields safe for API responses and logs."""

        return {
            "code": self.code.value,
            "summary": self.summary,
            "retryable": self.retryable,
        }


class MapProvider(ABC):
    """All map operations require request-local city scope."""

    @abstractmethod
    async def search_poi(self, request: SearchPoiRequest) -> PoiSearchResult:
        """Return ordered POIs or an explicit empty result."""

    @abstractmethod
    async def get_poi(self, request: GetPoiRequest) -> GetPoiResult:
        """Return one POI or raise a safe not-found error."""

    @abstractmethod
    async def route(self, request: RouteRequest) -> RouteResult:
        """Return normalized distance and duration totals."""

    @abstractmethod
    async def weather(self, request: WeatherRequest) -> WeatherResult:
        """Return a dated city weather summary."""

    @abstractmethod
    async def build_navigation_uri(self, request: NavigationRequest) -> NavigationUri:
        """Return a URI without performing a network request."""

"""The single provider-neutral map capability boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from math import isfinite

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
    AUTHENTICATION_FAILED = "MAP_PROVIDER_AUTHENTICATION_FAILED"
    RATE_LIMITED = "MAP_PROVIDER_RATE_LIMITED"
    INVALID_REQUEST = "MAP_PROVIDER_INVALID_REQUEST"
    INVALID_RESPONSE = "MAP_PROVIDER_INVALID_RESPONSE"


_ERROR_SUMMARIES = {
    MapProviderErrorCode.TIMEOUT: "The map provider request timed out.",
    MapProviderErrorCode.POI_NOT_FOUND: "The requested POI was not found.",
    MapProviderErrorCode.UNAVAILABLE: "The map provider request is unavailable.",
    MapProviderErrorCode.AUTHENTICATION_FAILED: "The map provider authentication failed.",
    MapProviderErrorCode.RATE_LIMITED: "The map provider rate limit was reached.",
    MapProviderErrorCode.INVALID_REQUEST: "The map provider request was rejected.",
    MapProviderErrorCode.INVALID_RESPONSE: "The map provider returned an invalid response.",
}


class MapProviderError(Exception):
    """A fixed, public-safe map failure with no retained provider payload."""

    def __init__(
        self,
        *,
        code: MapProviderErrorCode,
        retry_after_seconds: float | None = None,
    ) -> None:
        if not isinstance(code, MapProviderErrorCode):
            raise TypeError("code must be a MapProviderErrorCode")
        summary = _ERROR_SUMMARIES[code]
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.retryable = code in {
            MapProviderErrorCode.TIMEOUT,
            MapProviderErrorCode.UNAVAILABLE,
            MapProviderErrorCode.RATE_LIMITED,
        }
        if retry_after_seconds is not None and code is not MapProviderErrorCode.RATE_LIMITED:
            raise ValueError("retry-after is only valid for rate-limit errors")
        if retry_after_seconds is not None and (
            isinstance(retry_after_seconds, bool)
            or not isfinite(retry_after_seconds)
            or retry_after_seconds < 0
        ):
            raise ValueError("retry-after must be a finite non-negative number")
        self.retry_after_seconds = retry_after_seconds

    def to_public_dict(self) -> dict[str, object]:
        """Return only stable fields safe for API responses and logs."""

        public: dict[str, object] = {
            "code": self.code.value,
            "summary": self.summary,
            "retryable": self.retryable,
        }
        if self.retry_after_seconds is not None:
            public["retry_after_seconds"] = self.retry_after_seconds
        return public


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

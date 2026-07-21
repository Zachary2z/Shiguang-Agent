"""Application-layer adapters for external providers."""

from app.providers.amap import AmapMapProvider, create_amap_http_client
from app.providers.map import MapProvider, MapProviderError, MapProviderErrorCode
from app.providers.map_stub import StubMapProvider
from app.providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "AmapMapProvider",
    "MapProvider",
    "MapProviderError",
    "MapProviderErrorCode",
    "OpenAICompatibleProvider",
    "StubMapProvider",
    "create_amap_http_client",
]

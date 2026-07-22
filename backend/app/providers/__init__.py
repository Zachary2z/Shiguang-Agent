"""Application-layer adapters for external providers."""

from app.providers.amap import AmapMapProvider, create_amap_http_client
from app.providers.map import MapProvider, MapProviderError, MapProviderErrorCode
from app.providers.map_stub import StubMapProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.storage import (
    PrivateAccessMethod,
    PrivateFileAccess,
    PrivateFileDeleteResult,
    PrivateFileMetadata,
    RetentionPolicy,
    StorageProvider,
    StorageProviderError,
    StorageProviderErrorCode,
)

__all__ = [
    "AmapMapProvider",
    "MapProvider",
    "MapProviderError",
    "MapProviderErrorCode",
    "OpenAICompatibleProvider",
    "PrivateAccessMethod",
    "PrivateFileAccess",
    "PrivateFileDeleteResult",
    "PrivateFileMetadata",
    "RetentionPolicy",
    "StorageProvider",
    "StorageProviderError",
    "StorageProviderErrorCode",
    "StubMapProvider",
    "create_amap_http_client",
]

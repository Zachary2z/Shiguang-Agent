"""Application-layer adapters for external providers."""

from app.providers.amap import AmapMapProvider, create_amap_http_client
from app.providers.jobs import JobQueue
from app.providers.map import MapProvider, MapProviderError, MapProviderErrorCode
from app.providers.map_stub import StubMapProvider
from app.providers.openai_compatible import (
    OpenAICompatibleProvider,
    configured_model_provider,
)
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
from app.providers.web import (
    HttpxWebContentProvider,
    SystemHostResolver,
    WebContentProvider,
    WebFetchConfig,
    create_web_http_client,
)

__all__ = [
    "AmapMapProvider",
    "MapProvider",
    "JobQueue",
    "MapProviderError",
    "MapProviderErrorCode",
    "OpenAICompatibleProvider",
    "configured_model_provider",
    "PrivateAccessMethod",
    "PrivateFileAccess",
    "PrivateFileDeleteResult",
    "PrivateFileMetadata",
    "RetentionPolicy",
    "StorageProvider",
    "StorageProviderError",
    "StorageProviderErrorCode",
    "StubMapProvider",
    "SystemHostResolver",
    "WebContentProvider",
    "WebFetchConfig",
    "HttpxWebContentProvider",
    "create_amap_http_client",
    "create_web_http_client",
]

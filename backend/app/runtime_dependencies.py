"""Shared construction of process-level runtime providers.

API and Worker use this one entry for private storage so Compose cannot start
with different provider availability in the two processes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.providers.storage import StorageProvider


@dataclass(frozen=True, slots=True)
class RuntimeStorageProviders:
    real: StorageProvider
    demo: StorageProvider | None


def build_runtime_storage_providers(
    settings: Settings,
    *,
    real: StorageProvider | None = None,
    demo: StorageProvider | None = None,
) -> RuntimeStorageProviders:
    """Resolve the one configured storage adapter for both runtime processes."""

    return RuntimeStorageProviders(
        real=real
        if real is not None
        else LocalPrivateStorageProvider(config=settings.storage_provider_settings()),
        demo=(
            demo
            if demo is not None
            else (
                None
                if settings.resolved_demo_database_url() is None
                else LocalPrivateStorageProvider(
                    config=settings.demo_storage_provider_settings()
                )
            )
        ),
    )


__all__ = ["RuntimeStorageProviders", "build_runtime_storage_providers"]

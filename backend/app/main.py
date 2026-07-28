"""FastAPI application factory and Uvicorn entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.api.errors import install_error_handlers
from app.application.text_collection_workflow import IdempotencyLockRegistry
from app.config import Settings, load_settings
from app.infrastructure.db import Database
from app.observability import RequestContextMiddleware, configure_logging
from app.providers.map import MapProvider
from app.providers.openai_compatible import configured_model_provider
from app.providers.storage import StorageProvider
from app.providers.web import WebContentProvider
from nanobot_core.providers import ModelProvider


def create_app(
    settings: Settings | None = None,
    *,
    text_provider: ModelProvider | None = None,
    web_provider: WebContentProvider | None = None,
    storage_provider: StorageProvider | None = None,
    demo_storage_provider: StorageProvider | None = None,
    map_provider: MapProvider | None = None,
) -> FastAPI:
    """Create a configured FastAPI application without running migrations."""

    resolved_settings = settings or load_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved_settings.database_url)
        demo_url = resolved_settings.resolved_demo_database_url()
        demo_database = None if demo_url is None else Database(demo_url)
        api.state.database = database
        api.state.demo_database = demo_database
        try:
            await database.connect()
            if demo_database is not None:
                await demo_database.connect()
            yield
        finally:
            if demo_database is not None:
                await demo_database.close()
            await database.close()

    api = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    api.state.settings = resolved_settings
    api.state.database = None
    api.state.demo_database = None
    api.state.text_provider = (
        text_provider
        if text_provider is not None
        else configured_model_provider(resolved_settings)
    )
    api.state.web_provider = web_provider
    api.state.storage_provider = storage_provider
    api.state.demo_storage_provider = demo_storage_provider
    api.state.map_provider = map_provider
    api.state.idempotency_locks = IdempotencyLockRegistry()
    api.add_middleware(RequestContextMiddleware)
    install_error_handlers(api)
    api.include_router(api_router)

    @api.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return api


app = create_app()

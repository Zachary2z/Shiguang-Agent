"""FastAPI application factory and Uvicorn entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, load_settings
from app.infrastructure.db import Database
from app.observability import RequestContextMiddleware, configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a configured FastAPI application without running migrations."""

    resolved_settings = settings or load_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved_settings.database_url)
        api.state.database = database
        try:
            await database.connect()
            yield
        finally:
            await database.close()

    api = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    api.state.settings = resolved_settings
    api.add_middleware(RequestContextMiddleware)

    @api.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return api


app = create_app()

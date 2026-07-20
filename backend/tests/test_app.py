"""FastAPI application and request observability tests."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import app.main as main_module
from app.config import Settings
from app.main import app as module_app
from app.main import create_app
from app.observability import REQUEST_ID_HEADER


@asynccontextmanager
async def client_for(api: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with api.router.lifespan_context(api):
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_healthz_returns_stable_payload_and_generated_request_id(
    test_settings: Settings,
) -> None:
    async with client_for(create_app(test_settings)) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_valid_client_request_id_is_returned(test_settings: Settings) -> None:
    async with client_for(create_app(test_settings)) as client:
        response = await client.get("/healthz", headers={REQUEST_ID_HEADER: "client-request-123"})

    assert response.headers[REQUEST_ID_HEADER] == "client-request-123"


@pytest.mark.asyncio
async def test_invalid_client_request_id_is_replaced(test_settings: Settings) -> None:
    async with client_for(create_app(test_settings)) as client:
        response = await client.get(
            "/healthz", headers={REQUEST_ID_HEADER: "invalid id with spaces"}
        )

    assert response.headers[REQUEST_ID_HEADER] != "invalid id with spaces"
    assert response.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_request_log_contains_metadata_without_query_or_sensitive_config(
    test_settings: Settings,
    caplog: logging.LogCaptureFixture,
) -> None:
    secret_marker = "do-not-log-this-secret"
    caplog.set_level(logging.INFO, logger="shiguang.request")

    async with client_for(create_app(test_settings)) as client:
        response = await client.get(
            f"/healthz?token={secret_marker}",
            headers={REQUEST_ID_HEADER: "safe-id"},
        )

    request_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_id=safe-id" in request_logs
    assert "method=GET" in request_logs
    assert "path=/healthz" in request_logs
    assert "status=200" in request_logs
    assert secret_marker not in request_logs
    assert secret_marker not in response.text
    assert test_settings.database_url not in request_logs
    assert test_settings.database_url not in response.text
    assert logging.getLogger("uvicorn.access").disabled


def test_factory_does_not_connect_before_lifespan(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "not-created-at-import.db"
    settings = test_settings.model_copy(
        update={"database_url": f"sqlite+aiosqlite:///{database_path}"}
    )

    created_app = create_app(settings)

    assert created_app.title == settings.app_name
    assert not database_path.exists()
    assert module_app.title == "Shiguang API"


@pytest.mark.asyncio
async def test_database_is_closed_when_startup_connection_fails(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle_events: list[str] = []

    class FailingDatabase:
        def __init__(self, database_url: str) -> None:
            assert database_url == test_settings.database_url

        async def connect(self) -> None:
            lifecycle_events.append("connect")
            raise RuntimeError("database unavailable")

        async def close(self) -> None:
            lifecycle_events.append("close")

    monkeypatch.setattr(main_module, "Database", FailingDatabase)
    api = create_app(test_settings)

    with pytest.raises(RuntimeError, match="database unavailable"):
        async with api.router.lifespan_context(api):
            pass

    assert lifecycle_events == ["connect", "close"]

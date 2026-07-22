"""Offline contract coverage for the one M0-4D input pipeline."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import text

from app.application.collection_writes import CollectionWriteService
from app.application.demo_sessions import DEMO_USER_ID
from app.application.input_contracts import ImageInput, TextInput, UrlInput
from app.config import Settings
from app.domain.collections import CandidateField, ExtractionResult, PlaceCandidate
from app.domain.web import (
    WebFetchDiagnostics,
    WebFetchFailure,
    WebFetchFailureCode,
    WebPageContent,
)
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.main import create_app
from app.providers.web import WebContentProvider
from nanobot_core.providers import ModelProvider
from tests.core.fakes import FakeProvider, fake_response
from tests.fixtures.images import PNG_SCREENSHOT

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, tzinfo=UTC)


class StubWebProvider(WebContentProvider):
    def __init__(self, result: WebPageContent | WebFetchFailure) -> None:
        self.result = result
        self.calls: list[str] = []

    async def fetch(self, url: str) -> WebPageContent | WebFetchFailure:
        self.calls.append(url)
        return self.result


class BlockingWebProvider(WebContentProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, url: str) -> WebPageContent | WebFetchFailure:
        del url
        self.calls += 1
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _place(title: str = "深圳当代艺术与城市规划馆") -> PlaceCandidate:
    return PlaceCandidate(
        title=title,
        city_hint="深圳",
        district="福田区",
        address="福中路184号",
        business_district="市民中心",
        landmark="市民中心",
        metro_station="市民中心站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("室内",),
    )


def _response(title: str = "深圳当代艺术与城市规划馆"):
    return fake_response(
        content=ExtractionResult.with_candidates((_place(title),)).model_dump_json()
    )


def _web_success() -> WebPageContent:
    return WebPageContent(
        normalized_url="https://example.com/article?a=1&b=2",
        final_url="https://example.com/final",
        title="A page",
        text="深圳当代艺术与城市规划馆，福田区，免费 RAW_WEB_PRIVATE_MARKER",
        content_type="text/html",
        fetched_at=NOW,
        diagnostics=WebFetchDiagnostics(
            http_status=200,
            redirect_count=1,
            decoded_byte_size=88,
        ),
    )


def _migrate(settings: Settings) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@asynccontextmanager
async def _client(
    settings: Settings,
    provider: ModelProvider,
    *,
    web: WebContentProvider | None = None,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, LocalPrivateStorageProvider]]:
    database_path = Path(settings.database_url.removeprefix("sqlite+aiosqlite:///"))
    active_settings = settings.model_copy(
        update={"storage_private_root": database_path.parent / "private"}
    )
    await asyncio.to_thread(_migrate, active_settings)
    storage = LocalPrivateStorageProvider.from_settings(active_settings)
    api = create_app(
        active_settings,
        text_provider=provider,
        web_provider=web,
        storage_provider=storage,
    )
    async with api.router.lifespan_context(api):
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield api, client, storage


async def _demo(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/v1/demo/sessions")
    assert response.status_code == 201
    return str(response.json()["session_id"])


@pytest.mark.asyncio
async def test_text_url_and_image_share_one_result_and_collection_mapping(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("Text"), _response("URL"), _response("Image")])
    web = StubWebProvider(_web_success())
    async with _client(test_settings, provider, web=web) as (api, client, _storage):
        session_id = await _demo(client)
        text_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"type": "text", "idempotency_key": "text", "text": "具体地点"},
        )
        url_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "url",
                "url": "https://example.com/article?a=1&b=2",
            },
        )
        image_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "image"},
        )
        runs = [
            await client.get(f"/api/v1/agent-runs/{result.json()['trace_id']}")
            for result in (text_result, url_result, image_result)
        ]
        async with api.state.database.session() as session:
            sources = await SqlAlchemyCollectionRepository(session).list_sources(
                user_id=DEMO_USER_ID
            )

    assert all(result.status_code == 200 for result in (text_result, url_result, image_result))
    assert [result.json()["input_type"] for result in (text_result, url_result, image_result)] == [
        "text",
        "url",
        "image",
    ]
    assert {result.json()["collections"][0]["status"] for result in (
        text_result,
        url_result,
        image_result,
    )} == {"pending_details"}
    assert [len(run.json()["tool_runs"]) for run in runs] == [0, 1, 1]
    assert runs[1].json()["tool_runs"][0]["tool_name"] == "web_content_fetch"
    assert runs[2].json()["tool_runs"][0]["tool_name"] == "image_recognition"
    assert len(sources) == 3
    assert sources[1].url == "https://example.com/article?a=1&b=2"
    assert sources[1].metadata.final_url == "https://example.com/final"
    assert sources[2].file_key is not None
    assert sources[2].metadata.content_sha256 is not None
    assert sources[2].file_key not in image_result.text
    database_path = Path(
        test_settings.database_url.removeprefix("sqlite+aiosqlite:///")
    )
    database_dump = await asyncio.to_thread(database_path.read_bytes)
    assert b"RAW_WEB_PRIVATE_MARKER" not in database_dump
    assert PNG_SCREENSHOT not in database_dump


@pytest.mark.asyncio
async def test_url_failure_is_recoverable_and_never_calls_model(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([])
    web = StubWebProvider(WebFetchFailure.for_code(WebFetchFailureCode.TARGET_BLOCKED))
    async with _client(test_settings, provider, web=web) as (api, client, _storage):
        session_id = await _demo(client)
        response = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "blocked",
                "url": "http://127.0.0.1/private?secret=hidden",
            },
        )
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "blocked",
                "url": "http://127.0.0.1/private?secret=hidden",
            },
        )
        run = await client.get(f"/api/v1/agent-runs/{response.json()['trace_id']}")
        async with api.state.database.session() as session:
            sources = await SqlAlchemyCollectionRepository(session).list_sources(
                user_id=DEMO_USER_ID
            )

    assert response.status_code == replay.status_code == 200
    assert response.json()["run_status"] == "partially_succeeded"
    assert response.json()["error_code"] == "WEB_TARGET_BLOCKED"
    assert response.json()["collections"] == []
    assert set(response.json()["recovery_actions"]) == {"supply_text", "send_screenshot"}
    assert replay.json()["replayed"] is True
    assert len(web.calls) == 1 and provider.calls == []
    assert run.json()["status"] == "partially_succeeded"
    assert run.json()["tool_runs"][0]["status"] == "failed"
    assert len(sources) == 1 and sources[0].parse_status.value == "failed"
    assert sources[0].metadata.failure_code == "WEB_TARGET_BLOCKED"
    assert "hidden" not in run.text


@pytest.mark.asyncio
async def test_normalized_url_replay_and_different_content_conflict(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response()])
    web = StubWebProvider(_web_success())
    async with _client(test_settings, provider, web=web) as (_api, client, _storage):
        session_id = await _demo(client)
        first = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "normalized",
                "url": "HTTPS://EXAMPLE.COM:443/article?a=1&b=2",
            },
        )
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "normalized",
                "url": "https://example.com/article?a=1&b=2",
            },
        )
        conflict = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"type": "text", "idempotency_key": "normalized", "text": "different"},
        )

    assert first.status_code == replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert conflict.status_code == 409
    assert len(web.calls) == len(provider.calls) == 1


@pytest.mark.asyncio
async def test_same_key_is_isolated_between_sessions_and_image_replay_stores_once(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("First"), _response("Second"), _response("Image")])
    async with _client(test_settings, provider) as (_api, client, _storage):
        first_session, second_session = await _demo(client), await _demo(client)
        first, second = await asyncio.gather(
            client.post(
                f"/api/v1/sessions/{first_session}/messages",
                json={"idempotency_key": "shared", "content": "first"},
            ),
            client.post(
                f"/api/v1/sessions/{second_session}/messages",
                json={"idempotency_key": "shared", "content": "second"},
            ),
        )
        image = await client.post(
            f"/api/v1/sessions/{first_session}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "same-image"},
        )
        replay = await client.post(
            f"/api/v1/sessions/{first_session}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "same-image"},
        )

    assert first.status_code == second.status_code == image.status_code == replay.status_code == 200
    assert first.json()["trace_id"] != second.json()["trace_id"]
    assert first.json()["message_id"] != second.json()["message_id"]
    assert replay.json()["replayed"] is True
    assert replay.json()["source_id"] == image.json()["source_id"]
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_invalid_and_different_image_payloads_never_duplicate_or_leak_files(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("Image")])
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        invalid = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=b"not-an-image-private-marker",
            headers={"Content-Type": "image/png", "Idempotency-Key": "invalid-image"},
        )
        first = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "image-conflict"},
        )
        conflict = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT + b"different",
            headers={"Content-Type": "image/png", "Idempotency-Key": "image-conflict"},
        )
        invalid_run = await client.get(
            f"/api/v1/agent-runs/{invalid.json()['trace_id']}"
        )

    private_root = Path(
        test_settings.database_url.removeprefix("sqlite+aiosqlite:///")
    ).parent / "private"
    objects = list((private_root / "objects").iterdir())
    combined = invalid.text + invalid_run.text + repr(ImageInput.from_bytes(
        PNG_SCREENSHOT,
        content_type="image/png",
    ))
    assert invalid.status_code == 500
    assert invalid.json()["error_code"] == "IMAGE_CONTENT_SIGNATURE_MISMATCH"
    assert invalid.json()["recovery_actions"] == ["reupload_image", "supply_text"]
    assert invalid_run.json()["status"] == "failed"
    assert invalid_run.json()["tool_runs"][0]["error_code"] == (
        "IMAGE_CONTENT_SIGNATURE_MISMATCH"
    )
    assert first.status_code == 200 and conflict.status_code == 409
    assert len(provider.calls) == 1 and len(objects) == 1
    assert "not-an-image-private-marker" not in combined
    assert str(private_root) not in combined


@pytest.mark.asyncio
async def test_image_insufficient_information_keeps_private_source_unconfirmed(
    test_settings: Settings,
) -> None:
    insufficient = ExtractionResult.insufficient(
        missing_fields=(CandidateField.TITLE, CandidateField.ADDRESS),
        recovery_suggestions=("请补充店名或重新上传清晰截图。",),
    )
    provider = FakeProvider([fake_response(content=insufficient.model_dump_json())])
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        response = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "insufficient"},
        )
        async with api.state.database.session() as session:
            sources = await SqlAlchemyCollectionRepository(session).list_sources(
                user_id=DEMO_USER_ID
            )

    assert response.status_code == 200
    assert response.json()["extraction"]["outcome"] == "insufficient_information"
    assert response.json()["collections"] == []
    assert response.json()["source_parse_status"] == "failed"
    assert response.json()["recovery_actions"] == ["supply_text", "reupload_image"]
    assert len(sources) == 1 and sources[0].file_key is not None


@pytest.mark.asyncio
async def test_url_timeout_is_terminal_replayable_and_does_not_retry(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"agent_timeout_seconds": 0.01})
    provider = FakeProvider([])
    web = BlockingWebProvider()
    async with _client(settings, provider, web=web) as (_api, client, _storage):
        session_id = await _demo(client)
        payload = {
            "type": "url",
            "idempotency_key": "url-timeout",
            "url": "https://example.com/slow",
        }
        timed_out = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=payload,
        )
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=payload,
        )
        run = await client.get(f"/api/v1/agent-runs/{timed_out.json()['trace_id']}")

    assert timed_out.status_code == replay.status_code == 504
    assert timed_out.json()["error_code"] == replay.json()["error_code"] == "RUN_TIMEOUT"
    assert web.calls == 1 and provider.calls == []
    assert run.json()["status"] == "failed"
    assert run.json()["tool_runs"][0]["status"] == "cancelled"
    assert run.json()["tool_runs"][0]["error_code"] == "RUN_TIMEOUT"


@pytest.mark.asyncio
async def test_image_cancellation_finalizes_run_and_removes_new_file(
    test_settings: Settings,
) -> None:
    cancellation = asyncio.CancelledError()
    provider = FakeProvider([cancellation])
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        with pytest.raises(asyncio.CancelledError) as caught:
            await client.post(
                f"/api/v1/sessions/{session_id}/messages",
                content=PNG_SCREENSHOT,
                headers={"Content-Type": "image/png", "Idempotency-Key": "cancel-image"},
            )
        async with api.state.database.session() as session:
            trace_id = await session.scalar(
                text("SELECT trace_id FROM agent_runs ORDER BY created_at DESC LIMIT 1")
            )
        run = await client.get(f"/api/v1/agent-runs/{trace_id}")

    private_root = Path(
        test_settings.database_url.removeprefix("sqlite+aiosqlite:///")
    ).parent / "private"
    assert caught.value is cancellation
    assert run.json()["status"] == "cancelled"
    assert run.json()["error_code"] == "RUN_CANCELLED"
    assert run.json()["tool_runs"][0]["status"] == "cancelled"
    assert list((private_root / "objects").iterdir()) == []


@pytest.mark.asyncio
async def test_image_collection_write_failure_rolls_back_and_cleans_file(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider([_response("Image")])

    async def fail_write(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("private-database-failure-marker")

    monkeypatch.setattr(CollectionWriteService, "auto_save", fail_write)
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        with pytest.raises(RuntimeError, match="private-database-failure-marker"):
            await client.post(
                f"/api/v1/sessions/{session_id}/messages",
                content=PNG_SCREENSHOT,
                headers={"Content-Type": "image/png", "Idempotency-Key": "db-failure"},
            )
        async with api.state.database.session() as session:
            count_values: list[int] = []
            for table in ("sources", "collection_items", "collection_write_operations"):
                value = await session.scalar(text(f"SELECT COUNT(*) FROM {table}"))
                count_values.append(int(value or 0))
            counts = tuple(count_values)
            run_status = await session.scalar(
                text("SELECT status FROM agent_runs ORDER BY created_at DESC LIMIT 1")
            )

    private_root = Path(
        test_settings.database_url.removeprefix("sqlite+aiosqlite:///")
    ).parent / "private"
    assert counts == (0, 0, 0)
    assert run_status == "failed"
    assert list((private_root / "objects").iterdir()) == []


def test_input_contracts_are_frozen_and_hide_sensitive_payloads() -> None:
    text = TextInput(text="private text")
    url = UrlInput(url="https://example.com/?token=private")
    image = ImageInput.from_bytes(PNG_SCREENSHOT, content_type="image/png")

    for value in (text, url, image):
        with pytest.raises(ValidationError):
            value.type = "changed"  # type: ignore[misc]
    combined = repr(text) + repr(url) + repr(image)
    assert "private text" not in combined
    assert "token=private" not in combined
    assert "PNG" not in combined

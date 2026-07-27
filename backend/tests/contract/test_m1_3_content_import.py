"""M1-3 contract: 202 -> one JobWorker -> SSE -> authoritative result."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import select

from app.application.content_import_jobs import (
    CONTENT_IMPORT_JOB_TYPE,
    ContentImportJobHandler,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.config import Settings
from app.domain.collections import ExtractionResult, PlaceCandidate
from app.infrastructure.db.models import ScheduledJobModel, SourceModel
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.main import create_app
from app.worker.service import JobWorker
from tests.core.fakes import FakeProvider, fake_response
from tests.fixtures.images import PNG_SCREENSHOT

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _migrate(settings: Settings) -> None:
    previous = os.environ.get("DATABASE_URL")
    try:
        for url in (settings.database_url, settings.resolved_demo_database_url()):
            assert url is not None
            os.environ["DATABASE_URL"] = url
            command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _response(title: str = "深圳天文台"):
    extraction = ExtractionResult.with_candidates(
        (
            PlaceCandidate(
                title=title,
                city_hint="深圳",
                district="大鹏新区",
                address="南澳街道西涌社区",
                business_district="大鹏半岛",
                landmark="西涌",
                metro_station="大鹏接驳站",
                price_amount=Decimal("0.00"),
                price_currency="CNY",
                tags=("观星",),
            ),
        )
    )
    return fake_response(content=extraction.model_dump_json())


@asynccontextmanager
async def _runtime(
    settings: Settings,
    provider: FakeProvider,
) -> AsyncIterator[
    tuple[FastAPI, httpx.AsyncClient, JobWorker, LocalPrivateStorageProvider]
]:
    root = Path(settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent
    active = settings.model_copy(
        update={
            "storage_private_root": root / "private",
            "demo_storage_private_root": root / "demo-private",
        }
    )
    await asyncio.to_thread(_migrate, active)
    storage = LocalPrivateStorageProvider(
        config=active.demo_storage_provider_settings()
    )
    api = create_app(
        active,
        text_provider=provider,
        demo_storage_provider=storage,
    )
    async with api.router.lifespan_context(api):
        handler = ContentImportJobHandler(
            session_factory=api.state.demo_database.session_factory,
            provider=provider,
            pricing=ConfiguredPricingPolicy.from_settings(active),
            locks=api.state.idempotency_locks,
            timeout_seconds=active.agent_timeout_seconds,
            storage=storage,
            storage_config=active.demo_storage_provider_settings(),
            structured_output_mode=active.extraction_structured_output_mode(),
        )
        worker = JobWorker(
            queue=PostgresJobQueue(api.state.demo_database.session_factory),
            worker_id="worker_m1_3_contract",
            handlers={CONTENT_IMPORT_JOB_TYPE: handler},
            poll_seconds=0.01,
        )
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield api, client, worker, storage


async def _session(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post("/api/v1/demo/sessions")
    assert response.status_code == 201
    body = response.json()
    client.headers["X-CSRF-Token"] = body["csrf_token"]
    return body


@pytest.mark.asyncio
async def test_text_import_is_queued_streamed_and_read_from_authoritative_result(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response()])
    async with _runtime(test_settings, provider) as (_api, client, worker, _storage):
        session = await _session(client)
        accepted = await client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={
                "type": "text",
                "idempotency_key": "m1-text",
                "text": "<img src=x onerror=alert(1)> 深圳天文台",
            },
        )
        assert accepted.status_code == 202
        assert accepted.json()["run_status"] == "queued"
        queued_result = await client.get(accepted.json()["result_url"])
        assert queued_result.status_code == 200, queued_result.text
        assert queued_result.json()["collections"] == []

        completed = await worker.run_once()
        assert completed is not None and completed.status.value == "succeeded"
        events = await client.get(accepted.json()["events_url"])
        result = await client.get(accepted.json()["result_url"])

        assert events.status_code == 200
        assert "content_receiving" in events.text
        assert "place_recognition" in events.text
        assert "result_organizing" in events.text
        assert result.status_code == 200
        assert result.json()["run_status"] == "succeeded"
        assert result.json()["collections"][0]["title"] == "深圳天文台"
        assert "onerror" not in result.text


@pytest.mark.asyncio
async def test_same_key_reuses_message_job_source_and_collection(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("海上世界文化艺术中心")])
    async with _runtime(test_settings, provider) as (_api, client, worker, _storage):
        session = await _session(client)
        path = f"/api/v1/sessions/{session['session_id']}/messages"
        payload = {
            "type": "text",
            "idempotency_key": "m1-replay",
            "text": "海上世界文化艺术中心",
        }
        first, replay = await asyncio.gather(
            client.post(path, json=payload),
            client.post(path, json=payload),
        )
        assert first.status_code == replay.status_code == 202
        assert first.json()["message_id"] == replay.json()["message_id"]
        assert first.json()["trace_id"] == replay.json()["trace_id"]
        await worker.run_once()
        result = await client.get(first.json()["result_url"])
        second_replay = await client.post(path, json=payload)
        conflict = await client.post(
            path,
            json={**payload, "text": "不同正文"},
        )
        assert len(result.json()["collections"]) == 1
        assert second_replay.json()["trace_id"] == first.json()["trace_id"]
        assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_private_image_reference_and_real_delete_restore(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("深圳湾公园")])
    async with _runtime(test_settings, provider) as (_api, client, worker, storage):
        session = await _session(client)
        accepted = await client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            content=PNG_SCREENSHOT,
            headers={
                "Content-Type": "image/png",
                "Idempotency-Key": "m1-image",
            },
        )
        assert accepted.status_code == 202
        async with _api.state.demo_database.session() as database_session:
            job = await database_session.scalar(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.trace_id == accepted.json()["trace_id"]
                )
            )
            source = await database_session.scalar(select(SourceModel))
        assert job is not None and source is not None
        assert set(job.payload_json) == {
            "session_id",
            "message_id",
            "source_id",
            "input_type",
        }
        assert source.file_key not in str(job.payload_json)
        assert len(source.metadata_json["content_sha256"]) == 64
        completed = await worker.run_once()
        assert completed is not None
        result = await client.get(accepted.json()["result_url"])
        assert result.json()["run_status"] == "succeeded", result.text
        item = result.json()["collections"][0]
        deleted = await client.delete(
            f"/api/v1/collections/{item['id']}?expected_version={item['version']}"
        )
        restored = await client.post(
            f"/api/v1/collections/{item['id']}/restore"
        )
        repeated_restore = await client.post(
            f"/api/v1/collections/{item['id']}/restore"
        )
        assert deleted.json()["status"] == "deleted"
        assert restored.json()["status"] == item["status"]
        assert repeated_restore.json()["status"] == item["status"]
        metadata, stored = await storage.read_private(source.file_key)
        assert metadata.content_sha256 == source.metadata_json["content_sha256"]
        assert stored == PNG_SCREENSHOT


@pytest.mark.asyncio
async def test_session_auth_and_csrf_are_enforced(test_settings: Settings) -> None:
    provider = FakeProvider([_response()])
    async with _runtime(test_settings, provider) as (_api, client, _worker, _storage):
        session = await _session(client)
        path = f"/api/v1/sessions/{session['session_id']}/messages"
        client.cookies.clear()
        unauthorized = await client.post(
            path,
            json={"type": "text", "idempotency_key": "auth-a", "text": "地点"},
        )
        await _session(client)
        client.headers["X-CSRF-Token"] = "invalid-csrf"
        forbidden = await client.post(
            path,
            json={"type": "text", "idempotency_key": "auth-b", "text": "地点"},
        )
        assert unauthorized.status_code == 401
        assert forbidden.status_code == 403

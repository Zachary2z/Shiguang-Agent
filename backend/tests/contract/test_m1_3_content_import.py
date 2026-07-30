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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.content_import_jobs import (
    CONTENT_IMPORT_JOB_TYPE,
    ContentImportJobHandler,
)
from app.application.plan_adjustments import PlanAdjustmentParser
from app.application.plan_experience import (
    PLAN_GENERATION_JOB_TYPE,
    PlanGenerationJobHandler,
    PlanGenerationOutcome,
    PlanGenerationResult,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.config import Settings
from app.domain.collections import CandidateField, ExtractionResult, PlaceCandidate
from app.domain.jobs import JobCreate
from app.domain.plans.drafts import PlanItemSource
from app.infrastructure.db.models import (
    AgentRunModel,
    MessageModel,
    ScheduledJobModel,
    SourceModel,
)
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.main import create_app
from app.worker.service import JobWorker
from nanobot_core.providers import StructuredOutputMode
from tests.contract.test_m1_5_plans import _draft, _request
from tests.core.fakes import FakeProvider, fake_response
from tests.fixtures.images import PNG_SCREENSHOT
from tests.fixtures.maps import make_stub_map_provider

BACKEND_ROOT = Path(__file__).resolve().parents[2]
COUNTED_MODELS = (MessageModel, AgentRunModel, ScheduledJobModel, SourceModel)


async def _row_counts(session: AsyncSession) -> tuple[int, ...]:
    values: list[int] = []
    for model in COUNTED_MODELS:
        value = await session.scalar(select(func.count()).select_from(model))
        values.append(int(value or 0))
    return tuple(values)


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
    provider: FakeProvider | None,
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
async def test_response_loss_replay_reuses_message_run_job_source_and_model_call(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("海上世界文化艺术中心")])
    async with _runtime(test_settings, provider) as (_api, client, worker, _storage):
        session = await _session(client)
        path = f"/api/v1/sessions/{session['session_id']}/messages"
        async def submit(content: bytes = PNG_SCREENSHOT) -> httpx.Response:
            return await client.post(
                path,
                data={
                    "idempotency_key": "m1-replay",
                    "text": "海上世界文化艺术中心",
                },
                files={"image": ("screenshot.png", content, "image/png")},
            )

        first, replay = await asyncio.gather(
            submit(),
            submit(),
        )
        assert first.status_code == replay.status_code == 202
        assert first.json()["message_id"] == replay.json()["message_id"]
        assert first.json()["trace_id"] == replay.json()["trace_id"]
        async with _api.state.demo_database.session() as database_session:
            assert await _row_counts(database_session) == (1, 1, 1, 1)
        await worker.run_once()
        result = await client.get(first.json()["result_url"])
        second_replay = await submit()
        conflict = await submit(PNG_SCREENSHOT + b"different")
        assert len(result.json()["collections"]) == 1
        assert second_replay.json()["trace_id"] == first.json()["trace_id"]
        assert conflict.status_code == 409
        assert len(provider.calls) == 1
        async with _api.state.demo_database.session() as database_session:
            assert await _row_counts(database_session) == (1, 1, 1, 1)


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
async def test_multipart_image_and_text_stay_one_idempotent_unified_input(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("深圳湾公园")])
    async with _runtime(test_settings, provider) as (api, client, worker, storage):
        session = await _session(client)
        path = f"/api/v1/sessions/{session['session_id']}/messages"

        async def request() -> httpx.Response:
            return await client.post(
                path,
                data={
                    "idempotency_key": "m1-image-with-text",
                    "text": "截图补充：想去看日落",
                },
                files={"image": ("screenshot.png", PNG_SCREENSHOT, "image/png")},
            )

        first = await request()
        replay = await request()

        assert first.status_code == replay.status_code == 202
        assert replay.json()["message_id"] == first.json()["message_id"]
        assert replay.json()["trace_id"] == first.json()["trace_id"]
        async with api.state.demo_database.session() as database_session:
            assert await _row_counts(database_session) == (1, 1, 1, 1)
        storage_root = (
            Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent
            / "demo-private"
        )
        assert len(tuple((storage_root / "objects").iterdir())) == 1

        assert await worker.run_once() is not None
        rendered_call = str(provider.calls[0].messages)
        assert "截图补充：想去看日落" in rendered_call
        assert first.json()["input_type"] == "image"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("storage", "database", "cancel"))
async def test_image_prepare_failures_leave_no_records_or_private_files(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    provider = FakeProvider([_response()])
    async with _runtime(test_settings, provider) as (api, client, _worker, storage):
        session = await _session(client)
        path = f"/api/v1/sessions/{session['session_id']}/messages"

        if failure == "database":
            async def fail_add_source(
                repository: SqlAlchemyCollectionRepository,
                *,
                user_id: str,
                source: object,
            ) -> None:
                del repository, user_id, source
                raise RuntimeError("database write failed")

            monkeypatch.setattr(
                SqlAlchemyCollectionRepository,
                "add_source",
                fail_add_source,
            )
            expected_error: type[BaseException] = RuntimeError
        else:
            async def fail_put(*args: object, **kwargs: object) -> object:
                del args, kwargs
                if failure == "cancel":
                    raise asyncio.CancelledError
                raise RuntimeError("storage write failed")

            monkeypatch.setattr(storage, "put_private", fail_put)
            expected_error = asyncio.CancelledError if failure == "cancel" else RuntimeError

        with pytest.raises(expected_error):
            await client.post(
                path,
                content=PNG_SCREENSHOT,
                headers={
                    "Content-Type": "image/png",
                    "Idempotency-Key": f"m1-image-{failure}",
                },
            )

        async with api.state.demo_database.session() as database_session:
            assert await _row_counts(database_session) == (0, 0, 0, 0)
        object_root = (
            Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent
            / "demo-private"
            / "objects"
        )
        assert not object_root.exists() or list(object_root.iterdir()) == []


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


@pytest.mark.asyncio
async def test_missing_model_configuration_finishes_run_safely(
    test_settings: Settings,
) -> None:
    async with _runtime(test_settings, None) as (_api, client, worker, _storage):
        session = await _session(client)
        accepted = await client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={
                "type": "text",
                "idempotency_key": "missing-model",
                "text": "深圳天文台",
            },
        )
        assert accepted.status_code == 202
        completed = await worker.run_once()
        result = await client.get(accepted.json()["result_url"])
        assert completed is not None
        assert completed.status.value == "succeeded"
        assert completed.result_summary is not None
        assert completed.result_summary.outcome == "failed"
        assert result.json()["run_status"] == "failed"
        assert result.json()["error_code"] == "MODEL_PROVIDER_NOT_CONFIGURED"
        assert result.json()["recovery_actions"] == ["retry_later"]


@pytest.mark.asyncio
@pytest.mark.parametrize("image", (False, True))
async def test_queue_failure_compensates_and_same_key_retries_without_orphans(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    image: bool,
) -> None:
    original_create = PostgresJobQueue.create
    attempts = 0

    async def fail_once(
        queue: PostgresJobQueue,
        request: JobCreate,
    ):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("private queue outage")
        return await original_create(queue, request)

    monkeypatch.setattr(PostgresJobQueue, "create", fail_once)
    provider = FakeProvider([_response()])
    async with _runtime(test_settings, provider) as (api, client, worker, _storage):
        session = await _session(client)
        path = f"/api/v1/sessions/{session['session_id']}/messages"
        request = (
            {
                "content": PNG_SCREENSHOT,
                "headers": {
                    "Content-Type": "image/png",
                    "Idempotency-Key": "queue-retry",
                },
            }
            if image
            else {
                "json": {
                    "type": "text",
                    "idempotency_key": "queue-retry",
                    "text": "深圳天文台",
                }
            }
        )
        with pytest.raises(RuntimeError, match="private queue outage"):
            await client.post(path, **request)
        async with api.state.demo_database.session() as database_session:
            counts = await _row_counts(database_session)
        assert counts == (0, 0, 0, 0)
        storage_root = (
            Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent
            / "demo-private"
        )
        assert list((storage_root / "objects").iterdir()) == []

        accepted = await client.post(path, **request)
        assert accepted.status_code == 202
        assert await worker.run_once() is not None
        result = await client.get(accepted.json()["result_url"])
        assert result.json()["run_status"] == "succeeded"
        async with api.state.demo_database.session() as database_session:
            final_counts = await _row_counts(database_session)
        assert final_counts == (1, 1, 1, 1)


@pytest.mark.asyncio
async def test_offline_text_details_selection_plan_adjust_confirm_core_loop(
    test_settings: Settings,
) -> None:
    extracted = ExtractionResult.with_candidates(
        (
            PlaceCandidate(
                title="未名咖啡",
                city_hint="深圳",
                missing_fields=(
                    CandidateField.DISTRICT,
                    CandidateField.ADDRESS,
                    CandidateField.BUSINESS_DISTRICT,
                    CandidateField.LANDMARK,
                    CandidateField.METRO_STATION,
                    CandidateField.PRICE,
                    CandidateField.TAGS,
                ),
            ),
        )
    )
    provider = FakeProvider(
        [
            fake_response(content=extracted.model_dump_json()),
            fake_response(content='{"pace":"relaxed"}'),
        ]
    )

    async with _runtime(test_settings, provider) as (api, client, import_worker, _storage):
        api.state.map_provider = make_stub_map_provider()
        session = await _session(client)
        accepted = await client.post(
            f"/api/v1/sessions/{session['session_id']}/messages",
            json={
                "type": "text",
                "idempotency_key": "offline-core-import",
                "text": "收藏一下深圳的未名咖啡",
            },
        )
        assert accepted.status_code == 202
        assert await import_worker.run_once() is not None
        imported = await client.get(accepted.json()["result_url"])
        item = imported.json()["collections"][0]
        assert item["title"] == "未名咖啡"
        assert item["status"] == "pending_details"
        assert item["planning_eligible"] is False

        supplemented = await client.patch(
            f"/api/v1/collections/{item['id']}",
            json={
                "expected_version": item["version"],
                "changes": {"address": "福中一路"},
            },
        )
        assert supplemented.status_code == 200, supplemented.text
        pending = supplemented.json()
        assert pending["status"] == "pending_selection"
        assert "address" not in pending["missing_fields"]
        assert pending["planning_eligible"] is False

        candidates_response = await client.get(
            f"/api/v1/collections/{item['id']}/poi-candidates"
        )
        choices = candidates_response.json()
        assert len(choices["candidates"]) == 2
        chosen = choices["candidates"][0]
        selected = await client.post(
            f"/api/v1/collections/{item['id']}/poi-selection",
            json={
                "expected_version": choices["expected_version"],
                "snapshot_fingerprint": choices["snapshot_fingerprint"],
                "idempotency_key": "offline-core-select",
                "choice": "candidate",
                "provider": chosen["provider"],
                "poi_id": chosen["poi_id"],
            },
        )
        active = selected.json()["items"][0]
        assert active["status"] == "active"
        assert active["planning_eligible"] is True

        draft = _draft(title=active["title"])
        option = draft.options[0]
        plan_item = option.items[0]
        linked_item = plan_item.model_copy(
            update={
                "source": PlanItemSource(collection_item_ids=(active["id"],)),
                "inbound_route": plan_item.inbound_route.model_copy(
                    update={"to_collection_item_ids": (active["id"],)}
                ),
            }
        )
        linked_draft = draft.model_copy(
            update={
                "options": (
                    option.model_copy(update={"items": (linked_item,)}),
                )
            }
        )

        class DraftExecutor:
            async def execute(self, *, user_id, constraints, approval):
                del user_id, constraints, approval
                return PlanGenerationResult(
                    outcome=PlanGenerationOutcome.DRAFT,
                    draft=linked_draft,
                )

        plan_worker = JobWorker(
            queue=PostgresJobQueue(api.state.demo_database.session_factory),
            worker_id="worker_offline_core_plan",
            handlers={
                PLAN_GENERATION_JOB_TYPE: PlanGenerationJobHandler(
                    session_factory=api.state.demo_database.session_factory,
                    pricing=ConfiguredPricingPolicy.from_settings(test_settings),
                    executor_factory=lambda session: DraftExecutor(),
                    adjustment_parser=PlanAdjustmentParser(
                        provider,
                        structured_output_mode=StructuredOutputMode.JSON_OBJECT,
                    ),
                )
            },
            poll_seconds=0.01,
        )
        plan_request = _request("offline-core-plan")
        plan_request["start_at"] = "2026-08-02T10:00:00+08:00"
        plan_request["end_at"] = "2026-08-02T18:00:00+08:00"
        created = await client.post("/api/v1/plans", json=plan_request)
        assert created.status_code == 202, created.text
        assert await plan_worker.run_once() is not None

        adjusted = await client.post(
            f"/api/v1/plans/{created.json()['plan_id']}/adjustments",
            json={
                "idempotency_key": "offline-core-adjust",
                "instruction": "节奏轻松一点",
            },
        )
        assert adjusted.status_code == 202, adjusted.text
        assert await plan_worker.run_once() is not None
        listed = await client.get("/api/v1/plans")
        current = listed.json()["items"][0]
        assert current["version"] == 2
        assert current["constraints"]["pace"] == "relaxed"

        confirmed = await client.post(
            f"/api/v1/plans/{current['id']}/confirm",
            json={"idempotency_key": "offline-core-confirm"},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["plan"]["status"] == "confirmed"

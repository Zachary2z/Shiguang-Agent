from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import func, select

from app.application.agent_intents import AgentIntentError, AgentIntentParser
from app.application.content_import_jobs import (
    AGENT_MESSAGE_JOB_TYPE,
    CONTENT_IMPORT_JOB_TYPE,
    ContentImportJobHandler,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.config import Settings
from app.domain.collections import ExtractionResult, PlaceCandidate
from app.domain.time import utc_now
from app.infrastructure.db.models import (
    AgentRunModel,
    CollectionItemModel,
    MemoryModel,
    PlanModel,
    ScheduledJobModel,
)
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.main import create_app
from app.worker.service import JobWorker
from nanobot_core.providers import ModelResponse, ProviderError, ProviderErrorCode
from tests.core.fakes import FakeProvider, fake_response
from tests.fixtures.images import PNG_SCREENSHOT

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _route(intent: dict[str, object]) -> ModelResponse:
    return fake_response(content=json.dumps(intent, ensure_ascii=False, default=str))


def _collection_route(title: str = "深圳天文台") -> ModelResponse:
    extraction = ExtractionResult.with_candidates(
        (
            PlaceCandidate(
                title=title,
                city_hint="深圳",
                district="大鹏新区",
                address="南澳街道西涌社区",
                price_amount=Decimal("0"),
                price_currency="CNY",
            ),
        )
    )
    return _route(
        {
            "intent": "collect_content",
            "extraction": extraction.model_dump(mode="json"),
        }
    )


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


@asynccontextmanager
async def _runtime(
    settings: Settings,
    provider: FakeProvider,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, JobWorker]]:
    root = Path(settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent
    active = settings.model_copy(
        update={
            "storage_private_root": root / "private",
            "demo_storage_private_root": root / "demo-private",
        }
    )
    await asyncio.to_thread(_migrate, active)
    storage = LocalPrivateStorageProvider(config=active.demo_storage_provider_settings())
    api = create_app(active, text_provider=provider, demo_storage_provider=storage)
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
            worker_id="worker_agent_intent_contract",
            handlers={
                AGENT_MESSAGE_JOB_TYPE: handler,
                CONTENT_IMPORT_JOB_TYPE: handler,
            },
            poll_seconds=0.01,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://test",
        ) as client:
            session = await client.post("/api/v1/demo/sessions")
            assert session.status_code == 201
            client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
            client.headers["X-Test-Session"] = session.json()["session_id"]
            yield api, client, worker


async def _submit(client: httpx.AsyncClient, *, key: str, text: str) -> httpx.Response:
    return await client.post(
        f"/api/v1/sessions/{client.headers['X-Test-Session']}/messages",
        json={"type": "agent_text", "idempotency_key": key, "text": text},
    )


@pytest.mark.asyncio
async def test_collection_route_uses_one_model_call_and_existing_import(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_collection_route()])
    async with _runtime(test_settings, provider) as (_api, client, worker):
        accepted = await _submit(client, key="route-collection", text="收藏一下深圳天文台")
        assert accepted.status_code == 202
        await worker.run_once()
        result = (await client.get(accepted.json()["result_url"])).json()

        assert result["intent"] == "collect_content"
        assert result["collections"][0]["title"] == "深圳天文台"
        assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_plan_route_asks_once_then_continues_same_session(
    test_settings: Settings,
) -> None:
    now = utc_now()
    provider = FakeProvider(
        [
            _route(
                {
                    "intent": "plan",
                    "area": {"districts": ["南山区"], "labels": []},
                    "include": ["炸鸡", "商场"],
                }
            ),
            _route(
                {
                    "intent": "plan",
                    "start_at": (now + timedelta(days=1)).replace(hour=10).isoformat(),
                    "end_at": (now + timedelta(days=1)).replace(hour=14).isoformat(),
                    "area": {"districts": ["南山区"], "labels": []},
                    "include": ["炸鸡", "商场"],
                }
            ),
        ]
    )
    async with _runtime(test_settings, provider) as (api, client, worker):
        first = await _submit(client, key="route-plan-missing", text="帮我安排时间，在南山")
        await worker.run_once()
        first_result = (await client.get(first.json()["result_url"])).json()
        assert first_result["question"] == "你什么时候有一段连续空闲时间？"
        assert first_result["plan_id"] is None

        second = await _submit(client, key="route-plan-followup", text="明天上午十点到两点")
        await worker.run_once()
        second_result = (await client.get(second.json()["result_url"])).json()
        assert second_result["plan_id"].startswith("pln_")
        assert "pending_context" in provider.calls[1].messages[-1]["content"]

        async with api.state.demo_database.session() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 1
            assert await session.scalar(select(func.count()).select_from(CollectionItemModel)) == 0
            assert await session.scalar(select(func.count()).select_from(MemoryModel)) == 0


@pytest.mark.asyncio
async def test_memory_authorization_temporary_constraint_and_clarification(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [
            _route(
                {
                    "intent": "memory",
                    "authorization": "explicit",
                    "type": "negative_preference",
                    "content": "不吃日料",
                    "value": "日料",
                }
            ),
            _route(
                {
                    "intent": "memory",
                    "authorization": "needs_confirmation",
                    "type": "negative_preference",
                    "content": "不喜欢日料",
                    "value": "日料",
                }
            ),
            _route(
                {
                    "intent": "memory",
                    "authorization": "explicit",
                    "type": "negative_preference",
                    "content": "不吃日料",
                    "value": "日料",
                }
            ),
            _route(
                {
                    "intent": "plan",
                    "exclude": ["日料"],
                }
            ),
            _route({"intent": "clarify", "question": "你是想收藏地点，还是安排计划？"}),
        ]
    )
    async with _runtime(test_settings, provider) as (api, client, worker):
        explicit = await _submit(client, key="memory-explicit", text="记住我不吃日料")
        await worker.run_once()
        explicit_result = (await client.get(explicit.json()["result_url"])).json()
        assert explicit_result["memory_id"].startswith("mem_")
        assert "我的" in explicit_result["question"]

        replay = await _submit(client, key="memory-explicit", text="记住我不吃日料")
        assert replay.json()["trace_id"] == explicit.json()["trace_id"]

        confirmation = await _submit(
            client,
            key="memory-confirm",
            text="我不喜欢吃日料",
        )
        await worker.run_once()
        confirmation_result = (
            await client.get(confirmation.json()["result_url"])
        ).json()
        assert "记住" in confirmation_result["question"]
        async with api.state.demo_database.session() as session:
            assert await session.scalar(select(func.count()).select_from(MemoryModel)) == 1

        confirmed = await _submit(client, key="memory-confirmed", text="是，请记住")
        await worker.run_once()
        confirmed_result = (await client.get(confirmed.json()["result_url"])).json()
        assert confirmed_result["memory_id"].startswith("mem_")
        assert "pending_context" in provider.calls[2].messages[-1]["content"]

        temporary = await _submit(client, key="memory-temporary", text="这次不要日料")
        await worker.run_once()
        temporary_result = (await client.get(temporary.json()["result_url"])).json()
        assert temporary_result["intent"] == "plan"
        assert temporary_result["question"]

        for key, text in (("route-clarify", "帮我处理一下"),):
            accepted = await _submit(client, key=key, text=text)
            await worker.run_once()
            result = (await client.get(accepted.json()["result_url"])).json()
            assert result["question"]

        async with api.state.demo_database.session() as session:
            assert await session.scalar(select(func.count()).select_from(MemoryModel)) == 2
            jobs = (
                await session.scalars(
                    select(ScheduledJobModel).where(
                        ScheduledJobModel.job_type == AGENT_MESSAGE_JOB_TYPE
                    )
                )
            ).all()
            assert all(job.max_attempts == 1 for job in jobs)
        assert len(provider.calls) == 5


@pytest.mark.asyncio
async def test_pure_url_and_screenshot_keep_content_import_without_intent_call(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([])
    async with _runtime(test_settings, provider) as (api, client, _worker):
        accepted = await client.post(
            f"/api/v1/sessions/{client.headers['X-Test-Session']}/messages",
            json={
                "type": "url",
                "idempotency_key": "pure-url",
                "url": "https://example.com/place",
            },
        )
        assert accepted.status_code == 202
        image = await client.post(
            f"/api/v1/sessions/{client.headers['X-Test-Session']}/messages",
            content=PNG_SCREENSHOT,
            headers={
                "Content-Type": "image/png",
                "Idempotency-Key": "pure-image",
            },
        )
        assert image.status_code == 202
        async with api.state.demo_database.session() as session:
            jobs = (
                await session.scalars(
                    select(ScheduledJobModel).where(
                        ScheduledJobModel.trace_id.in_(
                            (accepted.json()["trace_id"], image.json()["trace_id"])
                        )
                    )
                )
            ).all()
            assert len(jobs) == 2
            assert all(job.job_type == CONTENT_IMPORT_JOB_TYPE for job in jobs)
        assert provider.calls == []


@pytest.mark.asyncio
async def test_parser_rejects_invalid_empty_provider_error_and_cancel_without_mutation() -> None:
    text = "输入保持不变"
    invalid = AgentIntentParser(
        FakeProvider([fake_response(content="{}")]),
        structured_output_mode=None,
    )
    with pytest.raises(AgentIntentError):
        await invalid.parse(text=text, now=utc_now())
    assert text == "输入保持不变"

    empty = AgentIntentParser(
        FakeProvider([fake_response(content=None)]),
        structured_output_mode=None,
    )
    with pytest.raises(AgentIntentError):
        await empty.parse(text=text, now=utc_now())

    for code in (ProviderErrorCode.TIMEOUT, ProviderErrorCode.PROVIDER_ERROR):
        parser = AgentIntentParser(
            FakeProvider([ProviderError(code=code)]),
            structured_output_mode=None,
        )
        with pytest.raises(ProviderError) as error:
            await parser.parse(text=text, now=utc_now())
        assert error.value.code is code

    class CancelProvider(FakeProvider):
        async def chat(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await AgentIntentParser(CancelProvider([]), structured_output_mode=None).parse(
            text=text,
            now=utc_now(),
        )


@pytest.mark.asyncio
async def test_invalid_route_fails_run_without_business_side_effects(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([fake_response(content="{}")])
    async with _runtime(test_settings, provider) as (api, client, worker):
        accepted = await _submit(client, key="invalid-route", text="帮我处理")
        failed = await worker.run_once()
        assert failed is not None
        assert failed.status.value == "failed"

        async with api.state.demo_database.session() as session:
            run = await session.scalar(
                select(AgentRunModel).where(
                    AgentRunModel.trace_id == accepted.json()["trace_id"]
                )
            )
            assert run is not None
            assert run.status == "failed"
            assert run.error_code == AgentIntentError.code
            assert await session.scalar(
                select(func.count()).select_from(CollectionItemModel)
            ) == 0
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 0
            assert await session.scalar(select(func.count()).select_from(MemoryModel)) == 0


@pytest.mark.asyncio
async def test_pending_context_does_not_cross_sessions(
    test_settings: Settings,
) -> None:
    question = "你是想收藏地点，还是安排计划？"
    provider = FakeProvider(
        [
            _route({"intent": "clarify", "question": question}),
            _route({"intent": "clarify", "question": "请再说明一下你的目标。"}),
        ]
    )
    async with _runtime(test_settings, provider) as (_api, client, worker):
        await _submit(client, key="session-one", text="帮我处理一下")
        await worker.run_once()

        client.cookies.clear()
        session = await client.post("/api/v1/demo/sessions")
        assert session.status_code == 201
        client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        client.headers["X-Test-Session"] = session.json()["session_id"]
        await _submit(client, key="session-two", text="继续")
        await worker.run_once()

        second_input = provider.calls[1].messages[-1]["content"]
        assert '"pending_context":null' in second_input
        assert question not in second_input

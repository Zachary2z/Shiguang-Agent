from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import func, select

from app.application.agent_intents import AgentIntentError, AgentIntentParser, PlanIntent
from app.application.content_import_jobs import (
    AGENT_MESSAGE_JOB_TYPE,
    CONTENT_IMPORT_JOB_TYPE,
    ContentImportJobHandler,
    _plan_origin_coordinate,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.config import Settings
from app.domain.collections import ExtractionResult, PlaceCandidate
from app.domain.places import (
    CityScope,
    Coordinate,
    CoordinateSystem,
    MatchStatus,
    PlaceMatchRequest,
    Poi,
    PoiProvider,
    PoiSearchResult,
    PoiType,
    SearchPoiRequest,
    classify_place_matches,
    score_place_candidate,
)
from app.domain.time import ASIA_SHANGHAI, utc_now
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
from app.providers import MapProvider, StubMapProvider
from app.worker.service import JobWorker
from nanobot_core.providers import (
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    StructuredOutputMode,
)
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
    map_provider: MapProvider | None = None,
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
            map_provider=map_provider,
            matching_policy=(
                None if map_provider is None else active.place_matching_policy()
            ),
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
async def test_plan_intent_context_and_output_use_shanghai_local_time() -> None:
    provider = FakeProvider(
        [
            _route(
                {
                    "intent": "plan",
                    "start_at": "2026-08-09T14:00:00+08:00",
                    "end_at": "2026-08-09T18:00:00+08:00",
                    "area": {"districts": ["福田区"], "labels": []},
                }
            )
        ]
    )

    intent = await AgentIntentParser(
        provider,
        structured_output_mode=StructuredOutputMode.JSON_OBJECT,
    ).parse(
        text="明天下午2点到6点，在福田区",
        now=datetime(2026, 8, 8, 4, tzinfo=UTC),
    )

    assert isinstance(intent, PlanIntent)
    constraints = intent.constraints(now=datetime(2026, 8, 8, 4, tzinfo=UTC))
    assert constraints.start_at == datetime(2026, 8, 9, 6, tzinfo=UTC)
    assert constraints.end_at == datetime(2026, 8, 9, 10, tzinfo=UTC)
    assert constraints.start_at.astimezone(ASIA_SHANGHAI).hour == 14
    request = provider.calls[0]
    assert "Asia/Shanghai" in request.messages[0]["content"]
    assert '"timezone":"Asia/Shanghai"' in request.messages[1]["content"]
    assert '"current_time":"2026-08-08T12:00:00+08:00"' in request.messages[1][
        "content"
    ]


def _origin_poi(
    *,
    poi_id: str,
    name: str = "少年宫地铁站",
    latitude: float = 22.555,
) -> Poi:
    return Poi(
        provider=PoiProvider.AMAP,
        poi_id=poi_id,
        name=name,
        city_code="shenzhen",
        district="福田区",
        address="红荔路",
        coordinate=Coordinate(
            latitude=latitude,
            longitude=114.055,
            coordinate_system=CoordinateSystem.GCJ_02,
        ),
        poi_type=PoiType.TRANSIT,
    )


def _origin_provider(
    pois: tuple[Poi, ...],
    calls: list[SearchPoiRequest],
    *,
    timeout: bool = False,
) -> StubMapProvider:
    request = SearchPoiRequest(
        query="少年宫地铁站",
        city=CityScope(city_code="shenzhen"),
        district="福田区",
    )

    async def record(call: object) -> None:
        if isinstance(call, SearchPoiRequest):
            calls.append(call)

    return StubMapProvider(
        search_results={
            request: PoiSearchResult(city_code="shenzhen", pois=pois),
        },
        timeout_requests=(request,) if timeout else (),
        call_hook=record,
    )


@pytest.mark.parametrize(
    "pois",
    [
        (_origin_poi(poi_id="origin"),),
        (
            _origin_poi(poi_id="station", name="少年宫(地铁站)"),
            _origin_poi(poi_id="exit-f1", name="少年宫地铁站F1口", latitude=22.556),
            _origin_poi(poi_id="exit-c2", name="少年宫地铁站C2口", latitude=22.557),
        ),
    ],
    ids=("single", "station-with-partial-name-exits"),
)
@pytest.mark.asyncio
async def test_unique_origin_is_searched_once_persisted_and_only_exposed_as_flag(
    test_settings: Settings,
    pois: tuple[Poi, ...],
) -> None:
    calls: list[SearchPoiRequest] = []
    provider = FakeProvider(
        [
            _route(
                {
                    "intent": "plan",
                    "start_at": "2026-08-09T14:00:00+08:00",
                    "end_at": "2026-08-09T18:00:00+08:00",
                    "area": {"districts": ["福田区"], "labels": []},
                    "origin_query": "少年宫地铁站",
                }
            )
        ]
    )
    map_provider = _origin_provider(pois, calls)

    async with _runtime(test_settings, provider, map_provider) as (api, client, worker):
        accepted = await _submit(
            client,
            key=f"route-plan-origin-{len(pois)}",
            text="明天下午2点到6点，在福田区，从少年宫地铁站出发",
        )
        await worker.run_once()
        result = (await client.get(accepted.json()["result_url"])).json()
        plan = await client.get(f"/api/v1/plans/{result['plan_id']}")

        assert len(calls) == 1
        assert plan.status_code == 200
        assert plan.json()["constraints"]["has_exact_origin"] is True
        assert "latitude" not in plan.text and "longitude" not in plan.text
        async with api.state.demo_database.session() as session:
            row = await session.get(PlanModel, result["plan_id"])
            assert row is not None
            assert row.constraints_json["origin"] == {
                "latitude": 22.555,
                "longitude": 114.055,
                "coordinate_system": "gcj_02",
            }


@pytest.mark.parametrize(
    "pois",
    [
        (_origin_poi(poi_id="one"), _origin_poi(poi_id="two", latitude=22.556)),
        (_origin_poi(poi_id="weak", name="少年宫"),),
        (_origin_poi(poi_id="wrong", name="深圳市民中心地铁站"),),
        (),
    ],
    ids=(
        "two-exact",
        "partial-name",
        "name-conflict",
        "not-found",
    ),
)
@pytest.mark.asyncio
async def test_uncertain_origin_never_uses_first_candidate_and_asks_for_detail(
    test_settings: Settings,
    pois: tuple[Poi, ...],
) -> None:
    calls: list[SearchPoiRequest] = []
    provider = FakeProvider(
        [
            _route(
                {
                    "intent": "plan",
                    "start_at": "2026-08-09T14:00:00+08:00",
                    "end_at": "2026-08-09T18:00:00+08:00",
                    "area": {"districts": ["福田区"], "labels": []},
                    "origin_query": "少年宫地铁站",
                }
            )
        ]
    )

    async with _runtime(
        test_settings,
        provider,
        _origin_provider(pois, calls),
    ) as (api, client, worker):
        accepted = await _submit(client, key=f"origin-{len(pois)}", text="安排计划")
        await worker.run_once()
        result = (await client.get(accepted.json()["result_url"])).json()

        assert len(calls) == 1
        assert "更准确的出发点" in result["question"]
        assert result["plan_id"] is None
        async with api.state.demo_database.session() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 0


def test_plan_origin_rejects_city_hard_conflict() -> None:
    settings = Settings(_env_file=None, app_env="test")  # type: ignore[call-arg]
    candidate = score_place_candidate(
        request=PlaceMatchRequest(
            candidate=PlaceCandidate(
                title="少年宫地铁站",
                city_hint="广州",
                district="福田区",
            ),
            city=CityScope(city_code="shenzhen"),
        ),
        poi=_origin_poi(poi_id="wrong-city"),
        provider_rank=1,
        policy=settings.place_matching_policy(),
    )
    result = classify_place_matches(
        (candidate,),
        policy=settings.place_matching_policy(),
    )

    assert candidate.has_hard_conflict is True
    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert result.candidates == ()
    assert _plan_origin_coordinate(result) is None


@pytest.mark.asyncio
async def test_origin_map_failure_creates_no_fake_origin_or_plan(
    test_settings: Settings,
) -> None:
    calls: list[SearchPoiRequest] = []
    provider = FakeProvider(
        [
            _route(
                {
                    "intent": "plan",
                    "start_at": "2026-08-09T14:00:00+08:00",
                    "end_at": "2026-08-09T18:00:00+08:00",
                    "area": {"districts": ["福田区"], "labels": []},
                    "origin_query": "少年宫地铁站",
                }
            )
        ]
    )

    async with _runtime(
        test_settings,
        provider,
        _origin_provider((), calls, timeout=True),
    ) as (api, client, worker):
        accepted = await _submit(client, key="origin-map-failure", text="安排计划")
        failed = await worker.run_once()

        assert failed is not None and failed.status.value == "failed"
        assert len(calls) == 1
        async with api.state.demo_database.session() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 0
            run = await session.scalar(
                select(AgentRunModel).where(
                    AgentRunModel.trace_id == accepted.json()["trace_id"]
                )
            )
            assert run is not None
            assert run.error_code == "MAP_PROVIDER_TIMEOUT"


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
    future_start = now + timedelta(days=5)
    future_end = future_start + timedelta(hours=4)
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
                    "start_at": future_start.isoformat(),
                    "end_at": future_end.isoformat(),
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
        async with api.state.demo_database.session() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 0

        second = await _submit(
            client,
            key="route-plan-followup",
            text="五天后这个时间开始，我有四小时",
        )
        await worker.run_once()
        second_result = (await client.get(second.json()["result_url"])).json()
        assert second_result["plan_id"].startswith("pln_")
        assert "pending_context" in provider.calls[1].messages[-1]["content"]
        assert len(provider.calls) == 2

        async with api.state.demo_database.session() as session:
            plan = await session.scalar(select(PlanModel))
            assert plan is not None
            end_at = datetime.fromisoformat(plan.constraints_json["end_at"])
            expires_at = datetime.fromisoformat(plan.constraints_json["expires_at"])
            assert expires_at == end_at + timedelta(hours=1)
            assert expires_at > datetime.fromisoformat(plan.constraints_json["start_at"])
            assert "origin" not in plan.constraints_json
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

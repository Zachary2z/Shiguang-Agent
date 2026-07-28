"""Offline FastAPI + real JobWorker server used by the browser M1-3 proof."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import select

from app.application.content_import_jobs import (
    CONTENT_IMPORT_JOB_TYPE,
    ContentImportJobHandler,
)
from app.application.map_plan_facts import MapPlanFactResolver
from app.application.plan_adjustments import PlanAdjustmentParser
from app.application.plan_experience import (
    PLAN_GENERATION_JOB_TYPE,
    ExistingPlanServicesExecutor,
    PlanGenerationJobHandler,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.config import Settings
from app.domain.collections import (
    CollectionItem,
    CollectionKind,
    CollectionStatus,
    ExtractionResult,
    PlaceCandidate,
)
from app.domain.identifiers import generate_collection_item_id
from app.domain.places import (
    CityScope,
    Coordinate,
    CoordinateSystem,
    EvidenceField,
    EvidenceOutcome,
    EvidenceReason,
    MatchConfidence,
    MatchEvidence,
    MatchStatus,
    PlaceConfirmationSource,
    PlaceScope,
    PlaceTarget,
    Poi,
    PoiProvider,
    PoiType,
    WeatherRequest,
    WeatherResult,
)
from app.infrastructure.db.models import UserModel
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.main import create_app
from app.providers import StubMapProvider
from app.worker.service import JobWorker
from tests.core.fakes import FakeProvider, fake_response

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _candidate_response():
    candidate = PlaceCandidate(
        title="深圳天文台",
        city_hint="深圳",
        district="大鹏新区",
        address="南澳街道西涌社区",
        business_district="大鹏半岛",
        landmark="西涌",
        metro_station="大鹏接驳站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("观星", "周末"),
    )
    return fake_response(
        content=ExtractionResult.with_candidates((candidate,)).model_dump_json()
    )


def _plan_place(user_id: str) -> CollectionItem:
    now = datetime.now(UTC)
    poi = Poi(
        provider=PoiProvider.AMAP,
        poi_id=f"e2e_seaworld_{user_id[-8:]}",
        name="海上世界散步公园",
        city_code="shenzhen",
        district="南山区",
        business_area="海上世界",
        address="南山区海上世界广场",
        coordinate=Coordinate(
            latitude=22.4794,
            longitude=113.9188,
            coordinate_system=CoordinateSystem.GCJ_02,
        ),
        poi_type=PoiType.PARK,
        opening_hours_summary="全天开放",
    )
    target = PlaceTarget(
        scope=PlaceScope.EXACT,
        poi=poi,
        match_status=MatchStatus.MATCHED,
        confidence=MatchConfidence.HIGH,
        confirmed_by=PlaceConfirmationSource.USER_SELECTION,
        confirmed_at=now,
        evidence_summary=(
            MatchEvidence(
                field=EvidenceField.NAME,
                outcome=EvidenceOutcome.MATCH,
                reason=EvidenceReason.EXACT,
                score_delta=30,
            ),
        ),
    )
    return CollectionItem(
        id=generate_collection_item_id(),
        user_id=user_id,
        kind=CollectionKind.PLACE,
        title=poi.name,
        city_hint="深圳",
        district=poi.district,
        address=poi.address,
        tags=("散步", "公园", "海上世界"),
        place_target=target,
        status=CollectionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _plan_map_provider() -> StubMapProvider:
    weather_results = {}
    for offset in range(-1, 15):
        on_date = date.today() + timedelta(days=offset)
        request = WeatherRequest(
            city=CityScope(city_code="shenzhen"),
            on_date=on_date,
        )
        weather_results[request] = WeatherResult(
            city_code="shenzhen",
            on_date=on_date,
            condition="晴",
            temperature_celsius=27,
        )
    return StubMapProvider(weather_results=weather_results)


async def _seed_plan_collections(application: FastAPI, stop: asyncio.Event) -> None:
    seeded: set[str] = set()
    while not stop.is_set():
        async with application.state.demo_database.session_factory() as session:
            user_ids = tuple((await session.scalars(select(UserModel.id))).all())
            repository = SqlAlchemyCollectionRepository(session)
            for user_id in user_ids:
                if user_id in seeded:
                    continue
                await repository.add_collection_item(
                    user_id=user_id,
                    item=_plan_place(user_id),
                )
                seeded.add(user_id)
            await session.commit()
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.02)
        except TimeoutError:
            pass


def _migrate(url: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = url
        command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def build_app() -> FastAPI:
    root = Path(tempfile.mkdtemp(prefix="shiguang-m1-3-e2e-"))
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{root / 'main.db'}",
        demo_database_url=f"sqlite+aiosqlite:///{root / 'demo.db'}",
        storage_private_root=root / "private",
        demo_storage_private_root=root / "demo-private",
        log_level="WARNING",
    )
    _migrate(settings.database_url)
    assert settings.demo_database_url is not None
    _migrate(settings.demo_database_url)
    provider = FakeProvider([_candidate_response() for _ in range(8)])
    adjustment_provider = FakeProvider(
        [
            fake_response(content='{"pace":"relaxed"}'),
            fake_response(content="{}"),
        ]
    )
    map_provider = _plan_map_provider()
    storage = LocalPrivateStorageProvider(
        config=settings.demo_storage_provider_settings()
    )
    api = create_app(
        settings,
        text_provider=adjustment_provider,
        map_provider=map_provider,
        demo_storage_provider=storage,
    )
    original_lifespan = api.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        async with original_lifespan(application):
            handler = ContentImportJobHandler(
                session_factory=application.state.demo_database.session_factory,
                provider=provider,
                pricing=ConfiguredPricingPolicy.from_settings(settings),
                locks=application.state.idempotency_locks,
                timeout_seconds=settings.agent_timeout_seconds,
                storage=storage,
                storage_config=settings.demo_storage_provider_settings(),
                structured_output_mode=settings.extraction_structured_output_mode(),
                map_provider=map_provider,
                matching_policy=settings.place_matching_policy(),
            )
            plan_handler = PlanGenerationJobHandler(
                session_factory=application.state.demo_database.session_factory,
                pricing=ConfiguredPricingPolicy.from_settings(settings),
                executor_factory=lambda session: ExistingPlanServicesExecutor(
                    session=session,
                    map_provider=map_provider,
                    matching_policy=settings.place_matching_policy(),
                    facts=MapPlanFactResolver(
                        session=session,
                        map_provider=map_provider,
                        matching_policy=settings.place_matching_policy(),
                    ),
                ),
                adjustment_parser=PlanAdjustmentParser(
                    adjustment_provider,
                    structured_output_mode=(
                        settings.extraction_structured_output_mode()
                    ),
                ),
            )
            stop = asyncio.Event()
            worker = JobWorker(
                queue=PostgresJobQueue(
                    application.state.demo_database.session_factory
                ),
                worker_id="worker_browser_e2e",
                handlers={
                    CONTENT_IMPORT_JOB_TYPE: handler,
                    PLAN_GENERATION_JOB_TYPE: plan_handler,
                },
                poll_seconds=0.02,
            )
            task = asyncio.create_task(worker.run_forever(stop))
            seed_task = asyncio.create_task(_seed_plan_collections(application, stop))
            try:
                yield
            finally:
                stop.set()
                await asyncio.gather(task, seed_task)

    api.router.lifespan_context = lifespan
    return api


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=8100, log_level="warning")

"""Offline FastAPI + real JobWorker server used by the browser M1-3 proof."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI

from app.application.content_import_jobs import (
    CONTENT_IMPORT_JOB_TYPE,
    ContentImportJobHandler,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.config import Settings
from app.domain.collections import ExtractionResult, PlaceCandidate
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.main import create_app
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
    storage = LocalPrivateStorageProvider(
        config=settings.demo_storage_provider_settings()
    )
    api = create_app(
        settings,
        text_provider=provider,
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
            )
            stop = asyncio.Event()
            worker = JobWorker(
                queue=PostgresJobQueue(
                    application.state.demo_database.session_factory
                ),
                worker_id="worker_browser_e2e",
                handlers={CONTENT_IMPORT_JOB_TYPE: handler},
                poll_seconds=0.02,
            )
            task = asyncio.create_task(worker.run_forever(stop))
            try:
                yield
            finally:
                stop.set()
                await task

    api.router.lifespan_context = lifespan
    return api


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=8100, log_level="warning")

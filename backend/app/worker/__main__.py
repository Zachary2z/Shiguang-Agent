"""Process entrypoint for the one Shiguang Worker."""

from __future__ import annotations

import asyncio
import secrets
import signal

from app.application.content_import_jobs import (
    CONTENT_IMPORT_JOB_TYPE,
    ContentImportJobHandler,
)
from app.application.map_plan_facts import MapPlanFactResolver
from app.application.plan_experience import (
    PLAN_GENERATION_JOB_TYPE,
    ExistingPlanServicesExecutor,
    PlanGenerationJobHandler,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.application.text_collection_workflow import IdempotencyLockRegistry
from app.config import load_settings
from app.infrastructure.db import Database
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.providers import (
    AmapMapProvider,
    HttpxWebContentProvider,
    SystemHostResolver,
    configured_model_provider,
    create_web_http_client,
)
from app.worker.service import JobHandler, JobWorker, deterministic_noop


async def _run() -> None:
    settings = load_settings()
    database = Database(settings.database_url)
    demo_url = settings.resolved_demo_database_url()
    demo_database = None if demo_url is None else Database(demo_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_number, stop.set)
    provider = configured_model_provider(settings)
    map_provider = (
        None
        if settings.amap_api_key is None
        else AmapMapProvider.from_settings(settings)
    )
    pricing = ConfiguredPricingPolicy.from_settings(settings)
    locks = IdempotencyLockRegistry()
    web_client = create_web_http_client()
    web_provider = HttpxWebContentProvider(
        http_client=web_client,
        resolver=SystemHostResolver(),
    )
    storage = LocalPrivateStorageProvider(config=settings.storage_provider_settings())
    handlers: dict[str, JobHandler] = {
        "deterministic.noop": deterministic_noop,
        CONTENT_IMPORT_JOB_TYPE: ContentImportJobHandler(
            session_factory=database.session_factory,
            provider=provider,
            pricing=pricing,
            locks=locks,
            timeout_seconds=settings.agent_timeout_seconds,
            web_provider=web_provider,
            storage=storage,
            storage_config=settings.storage_provider_settings(),
            structured_output_mode=settings.extraction_structured_output_mode(),
            map_provider=map_provider,
            matching_policy=settings.place_matching_policy(),
        ),
    }
    if map_provider is not None:
        handlers[PLAN_GENERATION_JOB_TYPE] = PlanGenerationJobHandler(
            session_factory=database.session_factory,
            pricing=pricing,
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
        )
    workers = [
        JobWorker(
            queue=PostgresJobQueue(database.session_factory),
            worker_id=f"worker_{secrets.token_hex(8)}",
            handlers=handlers,
            poll_seconds=settings.worker_poll_seconds,
        )
    ]
    if demo_database is not None:
        demo_storage = LocalPrivateStorageProvider(
            config=settings.demo_storage_provider_settings()
        )
        demo_handlers: dict[str, JobHandler] = {
            "deterministic.noop": deterministic_noop,
            CONTENT_IMPORT_JOB_TYPE: ContentImportJobHandler(
                session_factory=demo_database.session_factory,
                provider=provider,
                pricing=pricing,
                locks=locks,
                timeout_seconds=settings.agent_timeout_seconds,
                web_provider=web_provider,
                storage=demo_storage,
                storage_config=settings.demo_storage_provider_settings(),
                structured_output_mode=(
                    settings.extraction_structured_output_mode()
                ),
                map_provider=map_provider,
                matching_policy=settings.place_matching_policy(),
            ),
        }
        if map_provider is not None:
            demo_handlers[PLAN_GENERATION_JOB_TYPE] = PlanGenerationJobHandler(
                session_factory=demo_database.session_factory,
                pricing=pricing,
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
            )
        workers.append(
            JobWorker(
                queue=PostgresJobQueue(demo_database.session_factory),
                worker_id=f"worker_demo_{secrets.token_hex(8)}",
                handlers=demo_handlers,
                poll_seconds=settings.worker_poll_seconds,
            )
        )
    try:
        await database.connect()
        if demo_database is not None:
            await demo_database.connect()
        await asyncio.gather(*(worker.run_forever(stop) for worker in workers))
    finally:
        if map_provider is not None:
            await map_provider.close()
        await web_client.aclose()
        if demo_database is not None:
            await demo_database.close()
        await database.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

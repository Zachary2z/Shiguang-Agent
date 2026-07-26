"""Persistent RunEvent sequencing, isolation, safety, and SSE replay tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.api.dependencies import get_current_user_id
from app.application.demo_sessions import DEMO_USER_ID
from app.application.run_events import RunEventService
from app.config import Settings
from app.domain.runs.events import RunEventType
from app.domain.runs.inputs import AgentRunCreate
from app.infrastructure.db import Database
from app.infrastructure.repositories import AgentRunRepository
from app.main import create_app

OTHER_USER_ID = "usr_fedcba9876543210fedcba9876543210"
TRACE_ID = "trc_0123456789abcdef0123456789abcdef"
OTHER_TRACE_ID = "trc_fedcba9876543210fedcba9876543210"


@asynccontextmanager
async def _client_for(api: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with api.router.lifespan_context(api):
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield client


async def _create_run(
    database: Database,
    *,
    user_id: str,
    trace_id: str,
) -> None:
    async with database.session() as session:
        await AgentRunRepository(session).create_queued(
            AgentRunCreate(
                trace_id=trace_id,
                user_id=user_id,
                session_id=None,
                intent="infrastructure_probe",
                workflow="m1_0",
            ),
            now=datetime.now(UTC),
        )
        await session.commit()


@pytest.mark.postgresql
def test_concurrent_run_events_are_monotonic_and_trace_isolated(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        try:
            await _create_run(database, user_id=DEMO_USER_ID, trace_id=TRACE_ID)
            await _create_run(
                database,
                user_id=OTHER_USER_ID,
                trace_id=OTHER_TRACE_ID,
            )

            async def publish(index: int) -> None:
                async with database.session() as session:
                    await RunEventService(session).publish(
                        user_id=DEMO_USER_ID,
                        trace_id=TRACE_ID,
                        event_type=RunEventType.STAGE_CHANGED,
                        summary={"stage": f"fixture-{index}"},
                    )

            await asyncio.gather(*(publish(index) for index in range(20)))
            async with database.session() as session:
                service = RunEventService(session)
                events = await service.list_after(
                    user_id=DEMO_USER_ID,
                    trace_id=TRACE_ID,
                    after_sequence=0,
                )
                wrong_user = await service.list_after(
                    user_id=OTHER_USER_ID,
                    trace_id=TRACE_ID,
                    after_sequence=0,
                )
                other_trace = await service.list_after(
                    user_id=OTHER_USER_ID,
                    trace_id=OTHER_TRACE_ID,
                    after_sequence=0,
                )

            assert [event.sequence for event in events] == list(range(1, 21))
            assert len({event.sequence for event in events}) == 20
            assert wrong_user == []
            assert other_trace == []
            assert all(event.trace_id == TRACE_ID for event in events)
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.postgresql
def test_sse_last_event_id_replays_only_unconfirmed_sequences(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        try:
            await _create_run(database, user_id=DEMO_USER_ID, trace_id=TRACE_ID)
            async with database.session() as session:
                service = RunEventService(session)
                for event_type, summary in (
                    (RunEventType.RUN_STARTED, {"status": "running"}),
                    (RunEventType.STAGE_CHANGED, {"stage": "fixture"}),
                    (RunEventType.RESULT_UPDATED, {"status": "ready"}),
                    (RunEventType.RUN_COMPLETED, {"status": "succeeded"}),
                ):
                    await service.publish(
                        user_id=DEMO_USER_ID,
                        trace_id=TRACE_ID,
                        event_type=event_type,
                        summary=summary,
                    )
        finally:
            await database.close()

        settings = Settings(
            _env_file=None,
            app_env="test",
            database_url=postgresql_database_url,
            log_level="ERROR",
        )
        api = create_app(settings)
        async with _client_for(api) as client:
            replay = await client.get(
                f"/api/v1/agent-runs/{TRACE_ID}/events",
                headers={"Last-Event-ID": "2"},
            )
            all_events = await client.get(f"/api/v1/agent-runs/{TRACE_ID}/events")

            api.dependency_overrides[get_current_user_id] = lambda: OTHER_USER_ID
            isolated = await client.get(f"/api/v1/agent-runs/{TRACE_ID}/events")

        assert replay.status_code == 200
        assert replay.headers["content-type"].startswith("text/event-stream")
        assert [
            line for line in replay.text.splitlines() if line.startswith("id: ")
        ] == ["id: 3", "id: 4"]
        assert replay.text.count("id: 3") == 1
        assert replay.text.count("id: 4") == 1
        assert [
            line for line in all_events.text.splitlines() if line.startswith("id: ")
        ] == ["id: 1", "id: 2", "id: 3", "id: 4"]
        assert isolated.status_code == 404
        assert TRACE_ID not in isolated.text

    asyncio.run(scenario())


@pytest.mark.postgresql
def test_run_event_summary_rejects_sensitive_material(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        try:
            await _create_run(database, user_id=DEMO_USER_ID, trace_id=TRACE_ID)
            async with database.session() as session:
                with pytest.raises(ValueError, match="forbidden field"):
                    await RunEventService(session).publish(
                        user_id=DEMO_USER_ID,
                        trace_id=TRACE_ID,
                        event_type=RunEventType.RESULT_UPDATED,
                        summary={"prompt": "private"},
                    )
        finally:
            await database.close()

    asyncio.run(scenario())

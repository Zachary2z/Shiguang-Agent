"""APScheduler is limited to creating durable jobs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.jobs import JobCreate
from app.worker.scheduler import JobScheduler


class RecordingQueue:
    def __init__(self) -> None:
        self.requests: list[JobCreate] = []
        self.created = asyncio.Event()

    async def create(self, request: JobCreate) -> None:
        self.requests.append(request)
        self.created.set()


@pytest.mark.asyncio
async def test_scheduler_only_calls_the_job_queue_create_boundary() -> None:
    queue = RecordingQueue()
    scheduler = JobScheduler(queue=queue)  # type: ignore[arg-type]
    request = JobCreate(
        user_id="usr_0123456789abcdef0123456789abcdef",
        job_type="deterministic.noop",
        payload={"operation": "probe"},
        run_at=datetime.now(UTC),
        idempotency_key="scheduler-probe",
    )

    scheduler.start()
    try:
        scheduler.schedule_create(
            request,
            create_at=datetime.now(UTC) + timedelta(milliseconds=10),
        )
        await asyncio.wait_for(queue.created.wait(), timeout=1)
    finally:
        scheduler.shutdown()

    assert queue.requests == [request]

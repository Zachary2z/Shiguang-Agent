"""Worker uses the one JobQueue and explicit result summary contract."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.domain.jobs import (
    JobCreate,
    JobResultSummary,
    JobStatus,
    ScheduledJob,
)
from app.worker.service import JobWorker

USER_ID = "usr_0123456789abcdef0123456789abcdef"
NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _job() -> ScheduledJob:
    return ScheduledJob(
        id="job_0123456789abcdef0123456789abcdef",
        user_id=USER_ID,
        job_type="deterministic.noop",
        payload={"operation": "probe"},
        run_at=NOW,
        status=JobStatus.RUNNING,
        attempt=1,
        max_attempts=3,
        idempotency_key="worker-test",
        trace_id=None,
        worker_id="worker_test",
        lease_expires_at=NOW,
        last_error_code=None,
        result_summary=None,
        created_at=NOW,
        updated_at=NOW,
        started_at=NOW,
        finished_at=None,
    )


class RecordingQueue:
    def __init__(self, job: ScheduledJob) -> None:
        self.job: ScheduledJob | None = job
        self.summary: JobResultSummary | None = None
        self.failed = False

    async def create(self, request: JobCreate) -> ScheduledJob:
        del request
        if self.job is None:
            raise RuntimeError("fixture job is unavailable")
        return self.job

    async def claim(self, *, worker_id: str, now: datetime) -> ScheduledJob | None:
        del worker_id, now
        claimed, self.job = self.job, None
        return claimed

    async def complete(
        self,
        *,
        job_id: str,
        worker_id: str,
        summary: JobResultSummary,
        now: datetime,
    ) -> bool:
        del job_id, worker_id, now
        self.summary = summary
        return True

    async def fail(
        self,
        *,
        job_id: str,
        worker_id: str,
        error_code: str,
        now: datetime,
    ) -> ScheduledJob | None:
        del job_id, worker_id, error_code, now
        self.failed = True
        return None

    async def cancel(self, *, user_id: str, job_id: str, now: datetime) -> bool:
        del user_id, job_id, now
        return False

    async def recover_stale(self, *, now: datetime) -> int:
        del now
        return 0

    async def get(self, *, user_id: str, job_id: str) -> ScheduledJob | None:
        del user_id, job_id
        return _job()


@pytest.mark.asyncio
async def test_worker_persists_only_explicit_result_summary() -> None:
    queue = RecordingQueue(_job())
    expected = JobResultSummary(outcome="completed", content_sha256="a" * 64)

    async def handler(job: ScheduledJob) -> JobResultSummary:
        assert job.payload == {"operation": "probe"}
        return expected

    worker = JobWorker(
        queue=queue,
        worker_id="worker_test",
        handlers={"deterministic.noop": handler},
    )

    assert await worker.run_once() is not None
    assert queue.summary is expected
    assert queue.failed is False


@pytest.mark.asyncio
async def test_worker_maps_handler_failure_without_public_exception_data() -> None:
    queue = RecordingQueue(_job())

    async def handler(job: ScheduledJob) -> JobResultSummary:
        del job
        raise RuntimeError("private model response")

    worker = JobWorker(
        queue=queue,
        worker_id="worker_test",
        handlers={"deterministic.noop": handler},
    )

    assert await worker.run_once() is None
    assert queue.failed is True
    assert queue.summary is None


@pytest.mark.asyncio
async def test_worker_propagates_cancellation() -> None:
    queue = RecordingQueue(_job())
    cancellation = asyncio.CancelledError("worker cancelled")

    async def handler(job: ScheduledJob) -> JobResultSummary:
        del job
        raise cancellation

    worker = JobWorker(
        queue=queue,
        worker_id="worker_test",
        handlers={"deterministic.noop": handler},
    )

    with pytest.raises(asyncio.CancelledError) as caught:
        await worker.run_once()
    assert caught.value is cancellation
    assert queue.summary is None
    assert queue.failed is False

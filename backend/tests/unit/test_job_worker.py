"""Worker uses the one JobQueue and explicit result summary contract."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.domain.jobs import (
    JobCreate,
    JobResultSummary,
    JobStatus,
    ScheduledJob,
)
from app.providers import configured_model_provider
from app.worker.service import JobWorker

USER_ID = "usr_0123456789abcdef0123456789abcdef"
NOW = datetime(2026, 7, 26, tzinfo=UTC)


def test_worker_allows_model_provider_to_be_unconfigured(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(
        update={
            "model_api_base": None,
            "model_api_key": None,
            "model_name": None,
        }
    )
    assert configured_model_provider(settings) is None


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
        self.renewals = 0
        self.allow_renewal = True
        self.renew_error: Exception | None = None

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

    async def renew_lease(
        self,
        *,
        job_id: str,
        worker_id: str,
        now: datetime,
    ) -> bool:
        del job_id, worker_id, now
        self.renewals += 1
        if self.renew_error is not None:
            raise self.renew_error
        return self.allow_renewal

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


@pytest.mark.asyncio
async def test_worker_renews_lease_until_handler_completes_then_stops() -> None:
    queue = RecordingQueue(_job())
    release = asyncio.Event()

    async def handler(job: ScheduledJob) -> JobResultSummary:
        del job
        await release.wait()
        return JobResultSummary(outcome="completed")

    worker = JobWorker(
        queue=queue,
        worker_id="worker_test",
        handlers={"deterministic.noop": handler},
        heartbeat_seconds=0.01,
    )
    execution = asyncio.create_task(worker.run_once())
    await asyncio.sleep(0.025)
    assert queue.renewals >= 2
    release.set()
    assert await execution is not None
    renewals_at_completion = queue.renewals
    await asyncio.sleep(0.02)
    assert queue.renewals == renewals_at_completion


@pytest.mark.asyncio
async def test_worker_cancels_handler_when_lease_is_lost() -> None:
    queue = RecordingQueue(_job())
    queue.allow_renewal = False
    handler_cancelled = asyncio.Event()

    async def handler(job: ScheduledJob) -> JobResultSummary:
        del job
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            handler_cancelled.set()
            raise

    worker = JobWorker(
        queue=queue,
        worker_id="worker_test",
        handlers={"deterministic.noop": handler},
        heartbeat_seconds=0.01,
    )
    assert await worker.run_once() is None
    assert handler_cancelled.is_set()
    assert queue.failed is False


@pytest.mark.asyncio
async def test_worker_cancellation_stops_heartbeat() -> None:
    queue = RecordingQueue(_job())

    async def handler(job: ScheduledJob) -> JobResultSummary:
        del job
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    worker = JobWorker(
        queue=queue,
        worker_id="worker_test",
        handlers={"deterministic.noop": handler},
        heartbeat_seconds=0.01,
    )
    execution = asyncio.create_task(worker.run_once())
    await asyncio.sleep(0.025)
    execution.cancel()
    with pytest.raises(asyncio.CancelledError):
        await execution
    renewals_at_cancellation = queue.renewals
    await asyncio.sleep(0.02)
    assert queue.renewals == renewals_at_cancellation


@pytest.mark.asyncio
async def test_heartbeat_exception_cancels_handler_and_fails_owned_job() -> None:
    queue = RecordingQueue(_job())
    queue.renew_error = RuntimeError("database unavailable")
    handler_cancelled = asyncio.Event()

    async def handler(job: ScheduledJob) -> JobResultSummary:
        del job
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            handler_cancelled.set()
            raise

    worker = JobWorker(
        queue=queue,
        worker_id="worker_test",
        handlers={"deterministic.noop": handler},
        heartbeat_seconds=0.01,
    )
    assert await worker.run_once() is None
    assert handler_cancelled.is_set()
    assert queue.failed is True

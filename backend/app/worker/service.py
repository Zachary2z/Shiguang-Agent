"""The single Worker loop; business execution is reached only through JobQueue."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping

from app.domain.jobs import (
    JOB_HEARTBEAT_SECONDS,
    JobResultSummary,
    ScheduledJob,
    validate_safe_label,
)
from app.domain.time import utc_now
from app.providers.jobs import JobQueue

JobHandler = Callable[[ScheduledJob], Awaitable[JobResultSummary]]


class JobLeaseLostError(RuntimeError):
    """The durable lease no longer belongs to the executing worker."""


class JobWorker:
    def __init__(
        self,
        *,
        queue: JobQueue,
        worker_id: str,
        handlers: Mapping[str, JobHandler],
        poll_seconds: float = 1.0,
        heartbeat_seconds: float = JOB_HEARTBEAT_SECONDS,
    ) -> None:
        if poll_seconds <= 0 or poll_seconds > 60:
            raise ValueError("poll_seconds must be in (0, 60]")
        if heartbeat_seconds <= 0 or heartbeat_seconds > JOB_HEARTBEAT_SECONDS:
            raise ValueError(
                f"heartbeat_seconds must be in (0, {JOB_HEARTBEAT_SECONDS}]"
            )
        self._queue = queue
        self._worker_id = validate_safe_label(worker_id, name="worker_id")
        self._handlers = dict(handlers)
        self._poll_seconds = poll_seconds
        self._heartbeat_seconds = heartbeat_seconds

    async def run_once(self) -> ScheduledJob | None:
        now = utc_now()
        await self._queue.recover_stale(now=now)
        job = await self._queue.claim(worker_id=self._worker_id, now=now)
        if job is None:
            return None
        handler = self._handlers.get(job.job_type)
        if handler is None:
            return await self._queue.fail(
                job_id=job.id,
                worker_id=self._worker_id,
                error_code="JOB_TYPE_UNSUPPORTED",
                now=utc_now(),
            )
        try:
            summary = await self._execute_with_heartbeat(job, handler)
        except asyncio.CancelledError:
            raise
        except JobLeaseLostError:
            return None
        except Exception:
            return await self._queue.fail(
                job_id=job.id,
                worker_id=self._worker_id,
                error_code="JOB_HANDLER_FAILED",
                now=utc_now(),
            )
        completed = await self._queue.complete(
            job_id=job.id,
            worker_id=self._worker_id,
            summary=summary,
            now=utc_now(),
        )
        if completed:
            return await self._queue.get(user_id=job.user_id, job_id=job.id)
        return None

    async def _execute_with_heartbeat(
        self,
        job: ScheduledJob,
        handler: JobHandler,
    ) -> JobResultSummary:
        handler_task: asyncio.Future[JobResultSummary] = asyncio.ensure_future(
            handler(job)
        )
        heartbeat_task = asyncio.create_task(self._maintain_lease(job))
        try:
            done, _pending = await asyncio.wait(
                (handler_task, heartbeat_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                await heartbeat_task
                raise AssertionError("lease heartbeat returned without terminating")
            return await handler_task
        finally:
            for task in (handler_task, heartbeat_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(handler_task, heartbeat_task, return_exceptions=True)

    async def _maintain_lease(self, job: ScheduledJob) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            renewed = await self._queue.renew_lease(
                job_id=job.id,
                worker_id=self._worker_id,
                now=utc_now(),
            )
            if not renewed:
                raise JobLeaseLostError("job lease ownership was lost")

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            job = await self.run_once()
            if job is not None:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                continue


async def deterministic_noop(job: ScheduledJob) -> JobResultSummary:
    """Side-effect-free handler used only for local infrastructure verification."""

    del job
    return JobResultSummary(outcome="completed")


__all__ = [
    "JobHandler",
    "JobLeaseLostError",
    "JobWorker",
    "deterministic_noop",
]

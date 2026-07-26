"""The single Worker loop; business execution is reached only through JobQueue."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from app.domain.jobs import ScheduledJob, validate_safe_job_data, validate_safe_label
from app.domain.time import utc_now
from app.providers.jobs import JobQueue

JobHandler = Callable[[ScheduledJob], Awaitable[dict[str, Any]]]


class JobWorker:
    def __init__(
        self,
        *,
        queue: JobQueue,
        worker_id: str,
        handlers: Mapping[str, JobHandler],
        poll_seconds: float = 1.0,
    ) -> None:
        if poll_seconds <= 0 or poll_seconds > 60:
            raise ValueError("poll_seconds must be in (0, 60]")
        self._queue = queue
        self._worker_id = validate_safe_label(worker_id, name="worker_id")
        self._handlers = dict(handlers)
        self._poll_seconds = poll_seconds

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
            summary = validate_safe_job_data(await handler(job))
        except asyncio.CancelledError:
            raise
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

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            job = await self.run_once()
            if job is not None:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                continue


async def deterministic_noop(job: ScheduledJob) -> dict[str, Any]:
    """Side-effect-free handler used only for local infrastructure verification."""

    del job
    return {"outcome": "completed"}


__all__ = ["JobHandler", "JobWorker", "deterministic_noop"]

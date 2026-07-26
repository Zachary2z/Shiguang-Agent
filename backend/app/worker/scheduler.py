"""APScheduler adapter that only creates durable jobs."""

from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from app.domain.jobs import JobCreate
from app.providers.jobs import JobQueue


class JobScheduler:
    def __init__(
        self,
        *,
        queue: JobQueue,
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        self._queue = queue
        self._scheduler = scheduler or AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    def schedule_create(self, request: JobCreate, *, create_at: datetime) -> None:
        self._scheduler.add_job(
            self._create,
            trigger="date",
            run_date=create_at,
            args=(request,),
            id=f"schedule:{request.user_id}:{request.idempotency_key}",
            replace_existing=True,
        )

    async def _create(self, request: JobCreate) -> None:
        await self._queue.create(request)


__all__ = ["JobScheduler"]

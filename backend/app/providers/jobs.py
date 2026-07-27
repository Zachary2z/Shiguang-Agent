"""The single provider-neutral JobQueue contract."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.jobs import JobCreate, JobResultSummary, ScheduledJob


class JobQueue(Protocol):
    async def create(self, request: JobCreate) -> ScheduledJob: ...

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
    ) -> ScheduledJob | None: ...

    async def complete(
        self,
        *,
        job_id: str,
        worker_id: str,
        summary: JobResultSummary,
        now: datetime,
    ) -> bool: ...

    async def renew_lease(
        self,
        *,
        job_id: str,
        worker_id: str,
        now: datetime,
    ) -> bool: ...

    async def fail(
        self,
        *,
        job_id: str,
        worker_id: str,
        error_code: str,
        now: datetime,
    ) -> ScheduledJob | None: ...

    async def cancel(
        self,
        *,
        user_id: str,
        job_id: str,
        now: datetime,
    ) -> bool: ...

    async def recover_stale(self, *, now: datetime) -> int: ...

    async def get(self, *, user_id: str, job_id: str) -> ScheduledJob | None: ...

    async def get_by_trace(
        self, *, user_id: str, trace_id: str
    ) -> ScheduledJob | None: ...


__all__ = ["JobQueue"]

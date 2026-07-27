"""PostgreSQL row-lock implementation of the single JobQueue contract."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.identifiers import validate_user_id
from app.domain.jobs import (
    JOB_LEASE_SECONDS,
    JOB_RETRY_DELAYS_SECONDS,
    JobConflictError,
    JobCreate,
    JobResultSummary,
    JobStatus,
    ScheduledJob,
    validate_safe_label,
)
from app.domain.time import required_utc, utc_now
from app.infrastructure.db.dml import execute_dml_rowcount
from app.infrastructure.db.models import ScheduledJobModel


class PostgresJobQueue:
    """Claim due jobs with ``FOR UPDATE SKIP LOCKED`` and durable leases."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._now = now

    async def create(self, request: JobCreate) -> ScheduledJob:
        fingerprint = _request_fingerprint(request)
        timestamp = required_utc(self._now())
        row = ScheduledJobModel(
            id=f"job_{secrets.token_hex(16)}",
            user_id=request.user_id,
            job_type=request.job_type,
            payload_json=request.payload,
            run_at=request.run_at,
            status=JobStatus.QUEUED.value,
            attempt=0,
            max_attempts=request.max_attempts,
            idempotency_key=request.idempotency_key,
            request_fingerprint=fingerprint,
            trace_id=request.trace_id,
            worker_id=None,
            lease_expires_at=None,
            last_error_code=None,
            result_summary_json=None,
            created_at=timestamp,
            updated_at=timestamp,
            started_at=None,
            finished_at=None,
        )
        async with self._session_factory() as session:
            session.add(row)
            try:
                await session.commit()
                return _scheduled_job(row)
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(ScheduledJobModel).where(
                        ScheduledJobModel.user_id == request.user_id,
                        ScheduledJobModel.idempotency_key == request.idempotency_key,
                    )
                )
                if existing is None or existing.request_fingerprint != fingerprint:
                    raise JobConflictError(
                        "idempotency key conflicts with another job"
                    ) from None
                return _scheduled_job(existing, replayed=True)

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
    ) -> ScheduledJob | None:
        worker = validate_safe_label(worker_id, name="worker_id")
        timestamp = required_utc(now)
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(ScheduledJobModel)
                .where(
                    ScheduledJobModel.status == JobStatus.QUEUED.value,
                    ScheduledJobModel.run_at <= timestamp,
                    ScheduledJobModel.attempt < ScheduledJobModel.max_attempts,
                )
                .order_by(ScheduledJobModel.run_at, ScheduledJobModel.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return None
            row.status = JobStatus.RUNNING.value
            row.attempt += 1
            row.worker_id = worker
            row.lease_expires_at = timestamp + timedelta(seconds=JOB_LEASE_SECONDS)
            row.started_at = row.started_at or timestamp
            row.updated_at = timestamp
            await session.flush()
            result = _scheduled_job(row)
        return result

    async def complete(
        self,
        *,
        job_id: str,
        worker_id: str,
        summary: JobResultSummary,
        now: datetime,
    ) -> bool:
        validate_safe_label(job_id, name="job_id")
        worker = validate_safe_label(worker_id, name="worker_id")
        timestamp = required_utc(now)
        async with self._session_factory() as session, session.begin():
            rowcount = await execute_dml_rowcount(
                session,
                update(ScheduledJobModel)
                .where(
                    ScheduledJobModel.id == job_id,
                    ScheduledJobModel.status == JobStatus.RUNNING.value,
                    ScheduledJobModel.worker_id == worker,
                )
                .values(
                    status=JobStatus.SUCCEEDED.value,
                    result_summary_json=summary.model_dump(
                        mode="json",
                        exclude_none=True,
                    ),
                    worker_id=None,
                    lease_expires_at=None,
                    updated_at=timestamp,
                    finished_at=timestamp,
                )
            )
            return rowcount == 1

    async def fail(
        self,
        *,
        job_id: str,
        worker_id: str,
        error_code: str,
        now: datetime,
    ) -> ScheduledJob | None:
        validate_safe_label(job_id, name="job_id")
        worker = validate_safe_label(worker_id, name="worker_id")
        error = validate_safe_label(error_code, name="error_code")
        timestamp = required_utc(now)
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(ScheduledJobModel)
                .where(
                    ScheduledJobModel.id == job_id,
                    ScheduledJobModel.status == JobStatus.RUNNING.value,
                    ScheduledJobModel.worker_id == worker,
                )
                .with_for_update()
            )
            if row is None:
                return None
            row.last_error_code = error
            row.worker_id = None
            row.lease_expires_at = None
            row.updated_at = timestamp
            if row.attempt >= row.max_attempts:
                row.status = JobStatus.FAILED.value
                row.finished_at = timestamp
            else:
                row.status = JobStatus.QUEUED.value
                delay_index = min(
                    row.attempt - 1,
                    len(JOB_RETRY_DELAYS_SECONDS) - 1,
                )
                row.run_at = timestamp + timedelta(
                    seconds=JOB_RETRY_DELAYS_SECONDS[delay_index]
                )
            await session.flush()
            result = _scheduled_job(row)
        return result

    async def cancel(
        self,
        *,
        user_id: str,
        job_id: str,
        now: datetime,
    ) -> bool:
        owner = validate_user_id(user_id)
        validate_safe_label(job_id, name="job_id")
        timestamp = required_utc(now)
        async with self._session_factory() as session, session.begin():
            rowcount = await execute_dml_rowcount(
                session,
                update(ScheduledJobModel)
                .where(
                    ScheduledJobModel.id == job_id,
                    ScheduledJobModel.user_id == owner,
                    ScheduledJobModel.status.in_(
                        (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
                    ),
                )
                .values(
                    status=JobStatus.CANCELLED.value,
                    worker_id=None,
                    lease_expires_at=None,
                    updated_at=timestamp,
                    finished_at=timestamp,
                )
            )
            return rowcount == 1

    async def recover_stale(self, *, now: datetime) -> int:
        timestamp = required_utc(now)
        async with self._session_factory() as session, session.begin():
            exhausted = await execute_dml_rowcount(
                session,
                update(ScheduledJobModel)
                .where(
                    ScheduledJobModel.status == JobStatus.RUNNING.value,
                    ScheduledJobModel.lease_expires_at <= timestamp,
                    ScheduledJobModel.attempt >= ScheduledJobModel.max_attempts,
                )
                .values(
                    status=JobStatus.FAILED.value,
                    worker_id=None,
                    lease_expires_at=None,
                    last_error_code="JOB_LEASE_EXPIRED",
                    updated_at=timestamp,
                    finished_at=timestamp,
                )
            )
            recoverable = await execute_dml_rowcount(
                session,
                update(ScheduledJobModel)
                .where(
                    ScheduledJobModel.status == JobStatus.RUNNING.value,
                    ScheduledJobModel.lease_expires_at <= timestamp,
                    ScheduledJobModel.attempt < ScheduledJobModel.max_attempts,
                )
                .values(
                    status=JobStatus.QUEUED.value,
                    run_at=timestamp,
                    worker_id=None,
                    lease_expires_at=None,
                    last_error_code="JOB_LEASE_EXPIRED",
                    updated_at=timestamp,
                )
            )
            return exhausted + recoverable

    async def get(self, *, user_id: str, job_id: str) -> ScheduledJob | None:
        owner = validate_user_id(user_id)
        validate_safe_label(job_id, name="job_id")
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.id == job_id,
                    ScheduledJobModel.user_id == owner,
                )
            )
            return None if row is None else _scheduled_job(row)

    async def get_by_trace(
        self, *, user_id: str, trace_id: str
    ) -> ScheduledJob | None:
        owner = validate_user_id(user_id)
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.user_id == owner,
                    ScheduledJobModel.trace_id == trace_id,
                )
            )
            return None if row is None else _scheduled_job(row)


def _request_fingerprint(request: JobCreate) -> str:
    value = {
        "job_type": request.job_type,
        "max_attempts": request.max_attempts,
        "payload": request.payload,
        "run_at": request.run_at.isoformat(),
        "trace_id": request.trace_id,
    }
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _scheduled_job(
    row: ScheduledJobModel,
    *,
    replayed: bool = False,
) -> ScheduledJob:
    return ScheduledJob(
        id=row.id,
        user_id=row.user_id,
        job_type=row.job_type,
        payload=row.payload_json,
        run_at=row.run_at,
        status=JobStatus(row.status),
        attempt=row.attempt,
        max_attempts=row.max_attempts,
        idempotency_key=row.idempotency_key,
        trace_id=row.trace_id,
        worker_id=row.worker_id,
        lease_expires_at=row.lease_expires_at,
        last_error_code=row.last_error_code,
        result_summary=(
            None
            if row.result_summary_json is None
            else JobResultSummary.model_validate(
                row.result_summary_json,
                strict=True,
            )
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        replayed=replayed,
    )


__all__ = ["PostgresJobQueue"]

"""PostgreSQL JobQueue concurrency, retry, cancellation, and recovery tests."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL, make_url

from app.domain.jobs import JobConflictError, JobCreate, JobStatus, ScheduledJob
from app.infrastructure.db import Database
from app.infrastructure.jobs import PostgresJobQueue
from app.worker.service import JobWorker

USER_ID = "usr_0123456789abcdef0123456789abcdef"
OTHER_USER_ID = "usr_fedcba9876543210fedcba9876543210"
TRACE_ID = "trc_11111111111111111111111111111111"


def _admin_url() -> URL:
    value = os.environ.get("TEST_POSTGRESQL_URL")
    if not value:
        pytest.skip("TEST_POSTGRESQL_URL is not configured")
    url = make_url(value)
    if url.drivername != "postgresql+asyncpg" or not url.database:
        raise AssertionError("TEST_POSTGRESQL_URL must use postgresql+asyncpg")
    return url


async def _connect(url: URL, *, database: str | None = None) -> asyncpg.Connection[object]:
    return await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=database or url.database,
    )


async def _create_database(admin_url: URL, database_name: str) -> None:
    connection = await _connect(admin_url)
    try:
        await connection.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await connection.close()


async def _drop_database(admin_url: URL, database_name: str) -> None:
    connection = await _connect(admin_url)
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await connection.close()


@pytest.fixture
def postgresql_database_url() -> Iterator[str]:
    admin_url = _admin_url()
    database_name = f"shiguang_jobs_{uuid4().hex}"
    database_url = admin_url.set(database=database_name)
    asyncio.run(_create_database(admin_url, database_name))
    old_environment = os.environ.get("APP_ENV")
    old_database_url = os.environ.get("DATABASE_URL")
    try:
        os.environ["APP_ENV"] = "test"
        os.environ["DATABASE_URL"] = database_url.render_as_string(hide_password=False)
        command.upgrade(Config("alembic.ini"), "head")
        yield database_url.render_as_string(hide_password=False)
    finally:
        if old_environment is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = old_environment
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url
        asyncio.run(_drop_database(admin_url, database_name))


def _request(
    *,
    key: str,
    run_at: datetime,
    payload: dict[str, object] | None = None,
    user_id: str = USER_ID,
) -> JobCreate:
    return JobCreate(
        user_id=user_id,
        job_type="deterministic.noop",
        payload=payload or {"operation": "probe"},
        run_at=run_at,
        max_attempts=3,
        idempotency_key=key,
        trace_id=TRACE_ID,
    )


@pytest.mark.postgresql
def test_two_workers_claim_and_execute_one_job_once(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        queue = PostgresJobQueue(database.session_factory)
        executions = 0

        async def handler(job: ScheduledJob) -> dict[str, object]:
            nonlocal executions
            assert job.trace_id == TRACE_ID
            executions += 1
            await asyncio.sleep(0)
            return {"outcome": "completed"}

        try:
            created = await queue.create(
                _request(key="worker-race", run_at=datetime.now(UTC))
            )
            workers = (
                JobWorker(
                    queue=queue,
                    worker_id="worker_one",
                    handlers={"deterministic.noop": handler},
                ),
                JobWorker(
                    queue=queue,
                    worker_id="worker_two",
                    handlers={"deterministic.noop": handler},
                ),
            )
            results = await asyncio.gather(*(worker.run_once() for worker in workers))
            persisted = await queue.get(user_id=USER_ID, job_id=created.id)

            assert executions == 1
            assert sum(result is not None for result in results) == 1
            assert persisted is not None
            assert persisted.status is JobStatus.SUCCEEDED
            assert persisted.attempt == 1
            assert persisted.result_summary == {"outcome": "completed"}
            assert persisted.created_at.tzinfo is not None
            assert persisted.created_at.utcoffset() == timedelta(0)
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.postgresql
def test_job_idempotency_is_user_scoped_and_conflicts_are_rejected(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        queue = PostgresJobQueue(database.session_factory)
        now = datetime.now(UTC)
        try:
            first = await queue.create(_request(key="same-key", run_at=now))
            replay = await queue.create(_request(key="same-key", run_at=now))
            other_user = await queue.create(
                _request(key="same-key", run_at=now, user_id=OTHER_USER_ID)
            )

            assert replay.id == first.id
            assert replay.replayed is True
            assert other_user.id != first.id
            assert await queue.get(user_id=OTHER_USER_ID, job_id=first.id) is None
            with pytest.raises(JobConflictError):
                await queue.create(
                    _request(
                        key="same-key",
                        run_at=now,
                        payload={"operation": "different"},
                    )
                )
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.postgresql
def test_retry_is_bounded_to_three_attempts_without_early_reclaim(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        queue = PostgresJobQueue(database.session_factory)
        start = datetime(2026, 7, 26, 1, tzinfo=UTC)
        try:
            created = await queue.create(_request(key="retry-three", run_at=start))
            first = await queue.claim(worker_id="worker_one", now=start)
            assert first is not None and first.attempt == 1
            retry_one = await queue.fail(
                job_id=created.id,
                worker_id="worker_one",
                error_code="FIXTURE_FAILED",
                now=start,
            )
            assert retry_one is not None
            assert retry_one.status is JobStatus.QUEUED
            assert retry_one.run_at == start + timedelta(seconds=5)
            assert (
                await queue.claim(
                    worker_id="worker_early",
                    now=start + timedelta(seconds=4),
                )
                is None
            )

            second_time = start + timedelta(seconds=5)
            second = await queue.claim(worker_id="worker_two", now=second_time)
            assert second is not None and second.attempt == 2
            retry_two = await queue.fail(
                job_id=created.id,
                worker_id="worker_two",
                error_code="FIXTURE_FAILED",
                now=second_time,
            )
            assert retry_two is not None
            assert retry_two.run_at == second_time + timedelta(seconds=30)

            third_time = second_time + timedelta(seconds=30)
            third = await queue.claim(worker_id="worker_three", now=third_time)
            assert third is not None and third.attempt == 3
            terminal = await queue.fail(
                job_id=created.id,
                worker_id="worker_three",
                error_code="FIXTURE_FAILED",
                now=third_time,
            )
            assert terminal is not None
            assert terminal.status is JobStatus.FAILED
            assert terminal.attempt == 3
            assert await queue.claim(worker_id="worker_four", now=third_time) is None
        finally:
            await database.close()

    asyncio.run(scenario())


@pytest.mark.postgresql
def test_cancelled_completed_and_recovered_jobs_are_not_duplicated(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        queue = PostgresJobQueue(database.session_factory)
        start = datetime(2026, 7, 26, 2, tzinfo=UTC)
        try:
            cancelled = await queue.create(_request(key="cancelled", run_at=start))
            assert await queue.cancel(
                user_id=USER_ID,
                job_id=cancelled.id,
                now=start,
            )
            assert not await queue.cancel(
                user_id=USER_ID,
                job_id=cancelled.id,
                now=start,
            )
            assert await queue.claim(worker_id="worker_one", now=start) is None

            interrupted = await queue.create(_request(key="restart", run_at=start))
            claimed = await queue.claim(worker_id="dead_worker", now=start)
            assert claimed is not None and claimed.id == interrupted.id
            assert await queue.recover_stale(now=start + timedelta(seconds=59)) == 0
            assert await queue.recover_stale(now=start + timedelta(seconds=60)) == 1
            recovered = await queue.claim(
                worker_id="replacement_worker",
                now=start + timedelta(seconds=60),
            )
            assert recovered is not None
            assert recovered.id == interrupted.id
            assert recovered.attempt == 2
            assert await queue.complete(
                job_id=recovered.id,
                worker_id="replacement_worker",
                summary={"outcome": "recovered"},
                now=start + timedelta(seconds=61),
            )
            assert await queue.claim(
                worker_id="another_worker",
                now=start + timedelta(seconds=62),
            ) is None
        finally:
            await database.close()

    asyncio.run(scenario())

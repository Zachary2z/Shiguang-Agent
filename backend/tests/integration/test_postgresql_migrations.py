"""PostgreSQL fresh upgrade, current, check, downgrade, and re-upgrade."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL, make_url


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


@pytest.mark.postgresql
def test_postgresql_migration_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_url = _admin_url()
    database_name = f"shiguang_migration_{uuid4().hex}"
    database_url = admin_url.set(database=database_name)
    asyncio.run(_create_database(admin_url, database_name))
    try:
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv(
            "DATABASE_URL",
            database_url.render_as_string(hide_password=False),
        )
        configuration = Config("alembic.ini")

        command.upgrade(configuration, "head")
        command.current(configuration, check_heads=True)
        command.check(configuration)
        command.downgrade(configuration, "base")
        command.upgrade(configuration, "head")
        command.current(configuration, check_heads=True)
    finally:
        asyncio.run(_drop_database(admin_url, database_name))

"""Test process configuration that explicitly disables developer dotenv loading."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL, make_url

from app.config import Settings

os.environ["APP_ENV"] = "test"


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "app.db"
    demo_database_path = tmp_path / "demo.db"
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{database_path}",
        demo_database_url=f"sqlite+aiosqlite:///{demo_database_path}",
        log_level="DEBUG",
    )


def _postgresql_admin_url() -> URL:
    value = os.environ.get("TEST_POSTGRESQL_URL")
    if not value:
        pytest.skip("TEST_POSTGRESQL_URL is not configured")
    url = make_url(value)
    if url.drivername != "postgresql+asyncpg" or not url.database:
        raise AssertionError("TEST_POSTGRESQL_URL must use postgresql+asyncpg")
    return url


async def _postgresql_connect(
    url: URL,
    *,
    database: str | None = None,
) -> asyncpg.Connection[object]:
    return await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=database or url.database,
    )


async def _create_postgresql_database(admin_url: URL, database_name: str) -> None:
    connection = await _postgresql_connect(admin_url)
    try:
        await connection.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await connection.close()


async def _drop_postgresql_database(admin_url: URL, database_name: str) -> None:
    connection = await _postgresql_connect(admin_url)
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
    """Yield one migrated, disposable PostgreSQL database."""

    admin_url = _postgresql_admin_url()
    database_name = f"shiguang_test_{uuid4().hex}"
    database_url = admin_url.set(database=database_name)
    asyncio.run(_create_postgresql_database(admin_url, database_name))
    old_database_url = os.environ.get("DATABASE_URL")
    try:
        rendered_url = database_url.render_as_string(hide_password=False)
        os.environ["DATABASE_URL"] = rendered_url
        command.upgrade(Config("alembic.ini"), "head")
        yield rendered_url
    finally:
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url
        asyncio.run(_drop_postgresql_database(admin_url, database_name))


@pytest.fixture
def postgresql_database_pair_urls() -> Iterator[tuple[str, str]]:
    """Yield separately migrated real and Demo PostgreSQL databases."""

    admin_url = _postgresql_admin_url()
    database_names = (
        f"shiguang_real_test_{uuid4().hex}",
        f"shiguang_demo_test_{uuid4().hex}",
    )
    for database_name in database_names:
        asyncio.run(_create_postgresql_database(admin_url, database_name))
    old_database_url = os.environ.get("DATABASE_URL")
    try:
        rendered_urls: list[str] = []
        for database_name in database_names:
            database_url = admin_url.set(database=database_name).render_as_string(
                hide_password=False
            )
            os.environ["DATABASE_URL"] = database_url
            command.upgrade(Config("alembic.ini"), "head")
            rendered_urls.append(database_url)
        yield rendered_urls[0], rendered_urls[1]
    finally:
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url
        for database_name in database_names:
            asyncio.run(_drop_postgresql_database(admin_url, database_name))

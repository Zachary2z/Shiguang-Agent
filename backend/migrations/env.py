"""Alembic environment using the application's validated database setting."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import Connection, make_url, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import load_settings
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import (
    AgentRunModel,
    CollectionItemModel,
    CollectionSourceModel,
    CollectionWriteOperationItemModel,
    CollectionWriteOperationModel,
    MessageModel,
    RunEventModel,
    ScheduledJobModel,
    SessionModel,
    SourceModel,
    ToolRunModel,
    UserModel,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = load_settings()
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata = Base.metadata
assert AgentRunModel.metadata is target_metadata
assert ToolRunModel.metadata is target_metadata
assert UserModel.metadata is target_metadata
assert SessionModel.metadata is target_metadata
assert MessageModel.metadata is target_metadata
assert RunEventModel.metadata is target_metadata
assert ScheduledJobModel.metadata is target_metadata
assert SourceModel.metadata is target_metadata
assert CollectionItemModel.metadata is target_metadata
assert CollectionSourceModel.metadata is target_metadata
assert CollectionWriteOperationModel.metadata is target_metadata
assert CollectionWriteOperationItemModel.metadata is target_metadata


def ensure_sqlite_directory(database_url: str) -> None:
    """Create the configured local SQLite parent directory when necessary."""

    if make_url(database_url).get_backend_name() != "sqlite":
        return
    database_path = make_url(database_url).database
    if database_path and database_path != ":memory:":
        Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create the async engine and run migrations on its synchronous facade."""

    ensure_sqlite_directory(settings.database_url)
    configuration = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

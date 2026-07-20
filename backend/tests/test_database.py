"""Asynchronous SQLite engine and session lifecycle tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.infrastructure.db import Database


@pytest.mark.asyncio
async def test_async_connection_session_rollback_and_close(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'database.db'}"
    database = Database(database_url)

    await database.connect()
    async with database.session() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
        await session.execute(text("CREATE TABLE rollback_probe (value INTEGER NOT NULL)"))
        await session.commit()

    with pytest.raises(RuntimeError, match="trigger rollback"):
        async with database.session() as session:
            await session.execute(text("INSERT INTO rollback_probe (value) VALUES (1)"))
            raise RuntimeError("trigger rollback")

    async with database.session() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM rollback_probe"))
        assert result.scalar_one() == 0

    await database.close()

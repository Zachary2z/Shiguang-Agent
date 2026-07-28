"""PostgreSQL proof for M1-7 idempotency and owner constraints."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from app.application.memories import MemoryService
from app.domain.collections import User, UserMode
from app.domain.identifiers import generate_user_id
from app.domain.memories import MemoryNotFoundError, MemoryType
from app.domain.time import utc_now
from app.infrastructure.db import Database
from app.infrastructure.db.models import MemoryModel, MemoryOperationModel
from app.infrastructure.repositories import SqlAlchemyCollectionRepository


async def _create(database: Database, *, user_id: str, key: str, content: str):
    async with database.session() as session:
        return await MemoryService(session).create_explicit(
            user_id=user_id,
            memory_type=MemoryType.POSITIVE_PREFERENCE,
            content=content,
            value="室内",
            expires_at=None,
            explicit_authorization=True,
            location_granularity=None,
            client_idempotency_key=key,
        )


@pytest.mark.postgresql
def test_postgresql_memory_concurrency_and_owner_scope(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        user_id, other_user_id = generate_user_id(), generate_user_id()
        try:
            async with database.session() as session:
                repository = SqlAlchemyCollectionRepository(session)
                for candidate in (user_id, other_user_id):
                    await repository.add_user(
                        user_id=candidate,
                        user=User(
                            id=candidate,
                            mode=UserMode.REAL,
                            created_at=utc_now(),
                        ),
                    )
                await session.commit()
            first, second = await asyncio.gather(
                _create(
                    database,
                    user_id=user_id,
                    key="postgres-concurrent-memory",
                    content="喜欢安静的室内空间",
                ),
                _create(
                    database,
                    user_id=user_id,
                    key="postgres-concurrent-memory",
                    content="喜欢安静的室内空间",
                ),
            )
            assert sorted((first.replayed, second.replayed)) == [False, True]
            assert first.memory.id == second.memory.id
            async with database.session() as session:
                assert await session.scalar(
                    select(func.count()).select_from(MemoryModel)
                ) == 1
                assert await session.scalar(
                    select(func.count()).select_from(MemoryOperationModel)
                ) == 1
                with pytest.raises(MemoryNotFoundError):
                    await MemoryService(session).detail(
                        user_id=other_user_id,
                        memory_id=first.memory.id,
                    )
        finally:
            await database.close()

    asyncio.run(scenario())

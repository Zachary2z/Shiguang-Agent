"""PostgreSQL row-lock proofs for M1-7 Memory writes."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select

from app.application.memories import MemoryService, MemoryWriteResult
from app.domain.collections import IdempotencyConflictError, User, UserMode
from app.domain.identifiers import generate_user_id
from app.domain.memories import (
    MemoryNotFoundError,
    MemoryType,
    MemoryVersionConflictError,
)
from app.domain.time import utc_now
from app.infrastructure.db import Database
from app.infrastructure.db.models import MemoryModel, MemoryOperationModel
from app.infrastructure.repositories import (
    SqlAlchemyCollectionRepository,
    SqlAlchemyMemoryRepository,
)


async def _create(database: Database, *, user_id: str, key: str) -> MemoryWriteResult:
    async with database.session() as session:
        return await MemoryService(session).create_explicit(
            user_id=user_id,
            memory_type=MemoryType.POSITIVE_PREFERENCE,
            content="喜欢安静的室内空间",
            value="室内",
            expires_at=None,
            explicit_authorization=True,
            location_granularity=None,
            client_idempotency_key=key,
        )


async def _update(
    database: Database,
    *,
    user_id: str,
    memory_id: str,
    version: int,
    key: str,
    content: str,
) -> MemoryWriteResult:
    async with database.session() as session:
        return await MemoryService(session).update(
            user_id=user_id,
            memory_id=memory_id,
            expected_version=version,
            content=content,
            value=None,
            enabled=None,
            expires_at=None,
            change_expiry=False,
            client_idempotency_key=key,
        )


async def _delete(
    database: Database,
    *,
    user_id: str,
    memory_id: str,
    version: int,
    key: str,
) -> MemoryWriteResult:
    async with database.session() as session:
        return await MemoryService(session).delete(
            user_id=user_id,
            memory_id=memory_id,
            expected_version=version,
            client_idempotency_key=key,
        )


@dataclass
class ReplayGate:
    calls: int
    first_initial_check_done: asyncio.Event
    both_initial_checks_done: asyncio.Event


async def _race_after_initial_replay_checks(
    database: Database,
    *,
    user_id: str,
    memory_id: str,
    gate: ReplayGate,
    first: Callable[[], Awaitable[MemoryWriteResult]],
    second: Callable[[], Awaitable[MemoryWriteResult]],
) -> tuple[object, object]:
    async with database.session() as blocker:
        locked = await blocker.scalar(
            select(MemoryModel)
            .where(MemoryModel.id == memory_id, MemoryModel.user_id == user_id)
            .with_for_update()
        )
        assert locked is not None
        first_task = asyncio.create_task(first())
        await asyncio.wait_for(gate.first_initial_check_done.wait(), timeout=5)
        second_task = asyncio.create_task(second())
        await asyncio.wait_for(gate.both_initial_checks_done.wait(), timeout=5)
        assert not first_task.done()
        assert not second_task.done()
        await blocker.commit()
    results = await asyncio.gather(first_task, second_task, return_exceptions=True)
    return results[0], results[1]


@pytest.mark.postgresql
def test_postgresql_memory_update_delete_lock_replay_and_owner_scope(
    postgresql_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        database = Database(postgresql_database_url)
        user_id, other_user_id = generate_user_id(), generate_user_id()
        original_replay = SqlAlchemyMemoryRepository.operation_replay
        gate = ReplayGate(
            calls=0,
            first_initial_check_done=asyncio.Event(),
            both_initial_checks_done=asyncio.Event(),
        )

        async def observed_replay(self, **kwargs):
            result = await original_replay(self, **kwargs)
            gate.calls += 1
            if gate.calls == 1:
                gate.first_initial_check_done.set()
            if gate.calls == 2:
                gate.both_initial_checks_done.set()
            return result

        monkeypatch.setattr(
            SqlAlchemyMemoryRepository,
            "operation_replay",
            observed_replay,
        )

        def reset_gate() -> None:
            gate.calls = 0
            gate.first_initial_check_done = asyncio.Event()
            gate.both_initial_checks_done = asyncio.Event()

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

            same_update = await _create(
                database, user_id=user_id, key="update-same-seed"
            )
            reset_gate()
            update_results = await _race_after_initial_replay_checks(
                database,
                user_id=user_id,
                memory_id=same_update.memory.id,
                gate=gate,
                first=lambda: _update(
                    database,
                    user_id=user_id,
                    memory_id=same_update.memory.id,
                    version=1,
                    key="update-same-key",
                    content="喜欢室内艺术空间",
                ),
                second=lambda: _update(
                    database,
                    user_id=user_id,
                    memory_id=same_update.memory.id,
                    version=1,
                    key="update-same-key",
                    content="喜欢室内艺术空间",
                ),
            )
            assert all(isinstance(result, MemoryWriteResult) for result in update_results)
            assert sorted(result.replayed for result in update_results) == [False, True]  # type: ignore[union-attr]

            conflict_update = await _create(
                database, user_id=user_id, key="update-conflict-seed"
            )
            reset_gate()
            update_conflicts = await _race_after_initial_replay_checks(
                database,
                user_id=user_id,
                memory_id=conflict_update.memory.id,
                gate=gate,
                first=lambda: _update(
                    database,
                    user_id=user_id,
                    memory_id=conflict_update.memory.id,
                    version=1,
                    key="update-conflict-key",
                    content="喜欢展览",
                ),
                second=lambda: _update(
                    database,
                    user_id=user_id,
                    memory_id=conflict_update.memory.id,
                    version=1,
                    key="update-conflict-key",
                    content="喜欢公园",
                ),
            )
            assert sum(
                isinstance(result, MemoryWriteResult) for result in update_conflicts
            ) == 1
            assert sum(
                isinstance(result, IdempotencyConflictError)
                for result in update_conflicts
            ) == 1

            version_update = await _create(
                database, user_id=user_id, key="update-version-seed"
            )
            reset_gate()
            update_versions = await _race_after_initial_replay_checks(
                database,
                user_id=user_id,
                memory_id=version_update.memory.id,
                gate=gate,
                first=lambda: _update(
                    database,
                    user_id=user_id,
                    memory_id=version_update.memory.id,
                    version=1,
                    key="update-version-one",
                    content="喜欢美术馆",
                ),
                second=lambda: _update(
                    database,
                    user_id=user_id,
                    memory_id=version_update.memory.id,
                    version=1,
                    key="update-version-two",
                    content="喜欢博物馆",
                ),
            )
            assert sum(
                isinstance(result, MemoryWriteResult) for result in update_versions
            ) == 1
            assert sum(
                isinstance(result, MemoryVersionConflictError)
                for result in update_versions
            ) == 1

            same_delete = await _create(
                database, user_id=user_id, key="delete-same-seed"
            )
            reset_gate()
            delete_results = await _race_after_initial_replay_checks(
                database,
                user_id=user_id,
                memory_id=same_delete.memory.id,
                gate=gate,
                first=lambda: _delete(
                    database,
                    user_id=user_id,
                    memory_id=same_delete.memory.id,
                    version=1,
                    key="delete-same-key",
                ),
                second=lambda: _delete(
                    database,
                    user_id=user_id,
                    memory_id=same_delete.memory.id,
                    version=1,
                    key="delete-same-key",
                ),
            )
            assert all(isinstance(result, MemoryWriteResult) for result in delete_results)
            assert sorted(result.replayed for result in delete_results) == [False, True]  # type: ignore[union-attr]
            replay_after_delete = await _delete(
                database,
                user_id=user_id,
                memory_id=same_delete.memory.id,
                version=1,
                key="delete-same-key",
            )
            assert replay_after_delete.replayed is True

            conflict_delete = await _create(
                database, user_id=user_id, key="delete-conflict-seed"
            )
            reset_gate()
            delete_conflicts = await _race_after_initial_replay_checks(
                database,
                user_id=user_id,
                memory_id=conflict_delete.memory.id,
                gate=gate,
                first=lambda: _delete(
                    database,
                    user_id=user_id,
                    memory_id=conflict_delete.memory.id,
                    version=1,
                    key="delete-conflict-key",
                ),
                second=lambda: _delete(
                    database,
                    user_id=user_id,
                    memory_id=conflict_delete.memory.id,
                    version=2,
                    key="delete-conflict-key",
                ),
            )
            assert sum(
                isinstance(result, MemoryWriteResult) for result in delete_conflicts
            ) == 1
            assert sum(
                isinstance(result, IdempotencyConflictError)
                for result in delete_conflicts
            ) == 1

            version_delete = await _create(
                database, user_id=user_id, key="delete-version-seed"
            )
            reset_gate()
            delete_versions = await _race_after_initial_replay_checks(
                database,
                user_id=user_id,
                memory_id=version_delete.memory.id,
                gate=gate,
                first=lambda: _delete(
                    database,
                    user_id=user_id,
                    memory_id=version_delete.memory.id,
                    version=1,
                    key="delete-version-one",
                ),
                second=lambda: _delete(
                    database,
                    user_id=user_id,
                    memory_id=version_delete.memory.id,
                    version=1,
                    key="delete-version-two",
                ),
            )
            assert sum(
                isinstance(result, MemoryWriteResult) for result in delete_versions
            ) == 1
            assert sum(
                isinstance(result, MemoryNotFoundError)
                for result in delete_versions
            ) == 1

            async with database.session() as session:
                rows = (
                    await session.scalars(
                        select(MemoryModel).where(MemoryModel.user_id == user_id)
                    )
                ).all()
                operations = (
                    await session.scalars(
                        select(MemoryOperationModel).where(
                            MemoryOperationModel.user_id == user_id
                        )
                    )
                ).all()
                assert len(rows) == 6
                assert await session.scalar(
                    select(func.count())
                    .select_from(MemoryOperationModel)
                    .where(MemoryOperationModel.operation == "update")
                ) == 3
                assert await session.scalar(
                    select(func.count())
                    .select_from(MemoryOperationModel)
                    .where(MemoryOperationModel.operation == "delete")
                ) == 3
                assert len(operations) == 12
                assert sum(row.version == 2 for row in rows) == 6
                with pytest.raises(MemoryNotFoundError):
                    await MemoryService(session).detail(
                        user_id=other_user_id,
                        memory_id=same_update.memory.id,
                    )
        finally:
            await database.close()

    asyncio.run(scenario())

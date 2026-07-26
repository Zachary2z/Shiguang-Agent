"""Bounded lifecycle and race coverage for the one process-local idempotency lock."""

from __future__ import annotations

import asyncio

import pytest

from app.application.text_collection_workflow import IdempotencyLockRegistry


@pytest.mark.asyncio
async def test_same_key_holder_and_waiter_share_one_lock_and_cleanup() -> None:
    registry = IdempotencyLockRegistry()
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()
    waiter_entered = asyncio.Event()

    async def holder() -> None:
        async with registry.lock(user_id="usr_one", idempotency_key="same"):
            holder_entered.set()
            await release_holder.wait()

    async def waiter() -> None:
        waiter_attempting.set()
        async with registry.lock(user_id="usr_one", idempotency_key="same"):
            waiter_entered.set()

    waiter_attempting = asyncio.Event()
    holder_task = asyncio.create_task(holder())
    await holder_entered.wait()
    waiter_task = asyncio.create_task(waiter())
    await waiter_attempting.wait()

    assert registry.active_key_count == 1
    assert not waiter_entered.is_set()

    release_holder.set()
    await asyncio.gather(holder_task, waiter_task)
    assert waiter_entered.is_set()
    assert registry.active_key_count == 0


@pytest.mark.asyncio
async def test_different_users_and_keys_do_not_block_each_other() -> None:
    registry = IdempotencyLockRegistry()
    release = asyncio.Event()
    entered = [asyncio.Event() for _ in range(3)]
    scopes = (
        ("usr_one", "shared"),
        ("usr_one", "different"),
        ("usr_two", "shared"),
    )

    async def participant(index: int) -> None:
        user_id, key = scopes[index]
        async with registry.lock(user_id=user_id, idempotency_key=key):
            entered[index].set()
            await release.wait()

    tasks = [asyncio.create_task(participant(index)) for index in range(3)]
    await asyncio.gather(*(event.wait() for event in entered))
    assert registry.active_key_count == 3

    release.set()
    await asyncio.gather(*tasks)
    assert registry.active_key_count == 0


@pytest.mark.asyncio
async def test_high_cardinality_keys_are_reclaimed() -> None:
    registry = IdempotencyLockRegistry()

    async def use_key(index: int) -> None:
        async with registry.lock(
            user_id=f"usr_{index % 17}",
            idempotency_key=f"key_{index}",
        ):
            pass

    await asyncio.gather(*(use_key(index) for index in range(10_000)))
    assert registry.active_key_count == 0


@pytest.mark.asyncio
async def test_exception_and_holder_cancellation_cleanup() -> None:
    registry = IdempotencyLockRegistry()

    with pytest.raises(RuntimeError, match="expected"):
        async with registry.lock(user_id="usr_one", idempotency_key="exception"):
            raise RuntimeError("expected")
    assert registry.active_key_count == 0

    entered = asyncio.Event()
    never = asyncio.Event()

    async def holder() -> None:
        async with registry.lock(user_id="usr_one", idempotency_key="cancel-holder"):
            entered.set()
            await never.wait()

    task = asyncio.create_task(holder())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert registry.active_key_count == 0


@pytest.mark.asyncio
async def test_cancelled_waiter_leaves_holder_entry_intact_then_cleanup() -> None:
    registry = IdempotencyLockRegistry()
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder() -> None:
        async with registry.lock(user_id="usr_one", idempotency_key="cancel-waiter"):
            holder_entered.set()
            await release_holder.wait()

    async def waiter() -> None:
        async with registry.lock(user_id="usr_one", idempotency_key="cancel-waiter"):
            raise AssertionError("cancelled waiter entered")

    holder_task = asyncio.create_task(holder())
    await holder_entered.wait()
    waiter_attempting = asyncio.Event()

    async def announced_waiter() -> None:
        waiter_attempting.set()
        await waiter()

    waiter_task = asyncio.create_task(announced_waiter())
    await waiter_attempting.wait()
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    assert registry.active_key_count == 1
    release_holder.set()
    await holder_task
    assert registry.active_key_count == 0


@pytest.mark.asyncio
async def test_eviction_race_never_allows_two_effective_locks_for_one_key() -> None:
    registry = IdempotencyLockRegistry()
    active = 0
    maximum_active = 0

    async def participant() -> None:
        nonlocal active, maximum_active
        async with registry.lock(user_id="usr_one", idempotency_key="race"):
            active += 1
            maximum_active = max(maximum_active, active)
            first_entered.set()
            await release.wait()
            active -= 1

    for _ in range(100):
        first_entered = asyncio.Event()
        release = asyncio.Event()
        tasks = [asyncio.create_task(participant()) for _ in range(20)]
        await first_entered.wait()
        release.set()
        await asyncio.gather(*tasks)
        assert registry.active_key_count == 0

    assert maximum_active == 1

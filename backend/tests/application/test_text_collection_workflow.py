"""Cancellation-safe lifecycle coverage for the workflow's idempotency lock."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.application.input_contracts import UrlInput
from app.application.text_collection_workflow import (
    IdempotencyLockRegistry,
    _IdempotencyLockEntry,
)
from app.domain.places import inspect_amap_official_link


class _CoordinatedCleanupRegistry(IdempotencyLockRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.cleanup_started = asyncio.Event()
        self.allow_cleanup = asyncio.Event()

    async def _leave(
        self,
        key: tuple[str, str],
        entry: _IdempotencyLockEntry,
    ) -> None:
        self.cleanup_started.set()
        await self.allow_cleanup.wait()
        await super()._leave(key, entry)


@pytest.mark.parametrize(
    ("url", "official", "poi_id"),
    [
        ("https://www.amap.com/place/B0SZ000001", True, "B0SZ000001"),
        ("http://ditu.amap.com/place/B0SZ000001", True, "B0SZ000001"),
        ("https://uri.amap.com/marker?poiid=B0SZ000001", True, "B0SZ000001"),
        ("https://surl.amap.com/abc123", True, None),
        ("https://amap.com.evil.example/place/B0SZ000001", False, None),
        ("http://127.0.0.1/place/B0SZ000001", False, None),
    ],
)
def test_official_amap_link_boundary_is_exact_and_never_guesses(
    url: str,
    official: bool,
    poi_id: str | None,
) -> None:
    inspected = inspect_amap_official_link(url)

    assert inspected.is_official is official
    assert inspected.poi_id == poi_id


def test_official_amap_link_rejects_url_credentials_before_persistence() -> None:
    with pytest.raises(ValidationError, match="cannot contain credentials"):
        UrlInput(url="https://www.amap.com/place/B0SZ000001?key=must-not-persist")


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


@pytest.mark.asyncio
async def test_cancellation_during_exit_waits_for_cleanup_before_propagating() -> None:
    registry = _CoordinatedCleanupRegistry()
    entered = asyncio.Event()
    leave_body = asyncio.Event()
    observed: list[asyncio.CancelledError] = []

    async def holder() -> None:
        try:
            async with registry.lock(
                user_id="usr_one",
                idempotency_key="cancel-during-exit",
            ):
                entered.set()
                await leave_body.wait()
        except asyncio.CancelledError as cancellation:
            observed.append(cancellation)
            raise

    task = asyncio.create_task(holder())
    await entered.wait()
    leave_body.set()
    await registry.cleanup_started.wait()

    task.cancel("first cancellation")
    task.cancel("second cancellation")
    registry.allow_cleanup.set()

    with pytest.raises(asyncio.CancelledError) as caught:
        await task
    assert observed == [caught.value]
    assert registry.active_key_count == 0
    assert all(
        candidate.done()
        for candidate in asyncio.all_tasks()
        if candidate is not asyncio.current_task()
        and candidate.get_coro().__qualname__.endswith(
            "IdempotencyLockRegistry._release"
        )
    )


@pytest.mark.asyncio
async def test_waiter_cancellation_cleanup_survives_repeated_cancellation() -> None:
    registry = _CoordinatedCleanupRegistry()
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()
    waiter_attempting = asyncio.Event()

    async def holder() -> None:
        async with registry.lock(
            user_id="usr_one",
            idempotency_key="cancel-waiter-cleanup",
        ):
            holder_entered.set()
            await release_holder.wait()

    async def waiter() -> None:
        waiter_attempting.set()
        async with registry.lock(
            user_id="usr_one",
            idempotency_key="cancel-waiter-cleanup",
        ):
            raise AssertionError("cancelled waiter entered")

    holder_task = asyncio.create_task(holder())
    await holder_entered.wait()
    waiter_task = asyncio.create_task(waiter())
    await waiter_attempting.wait()
    waiter_task.cancel("first cancellation")
    await registry.cleanup_started.wait()
    waiter_task.cancel("second cancellation")
    registry.allow_cleanup.set()

    with pytest.raises(asyncio.CancelledError):
        await waiter_task
    assert registry.active_key_count == 1

    release_holder.set()
    await holder_task
    assert registry.active_key_count == 0


@pytest.mark.asyncio
async def test_body_cancelled_error_object_propagates_after_exit_cleanup() -> None:
    registry = _CoordinatedCleanupRegistry()
    original = asyncio.CancelledError("body cancellation")

    async def holder() -> None:
        async with registry.lock(
            user_id="usr_one",
            idempotency_key="body-cancellation",
        ):
            raise original

    task = asyncio.create_task(holder())
    await registry.cleanup_started.wait()
    registry.allow_cleanup.set()

    with pytest.raises(asyncio.CancelledError) as caught:
        await task
    assert caught.value is original
    assert registry.active_key_count == 0

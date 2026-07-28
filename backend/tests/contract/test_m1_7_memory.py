"""M1-7 structured Memory, data-control, and export contracts."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.application.memories import MemoryPlanningService, MemoryService
from app.domain.identifiers import generate_user_id
from app.domain.memories import (
    MemoryNotFoundError,
    MemorySuggestionDecision,
    MemorySuggestionUnavailableError,
    MemoryType,
)
from app.domain.time import utc_now
from app.infrastructure.db.models import (
    MemoryModel,
    MemoryOperationModel,
    MemoryPlanUsageModel,
    MemorySuggestionDecisionModel,
    UserModel,
)
from tests.contract.test_m0_2d_api import _client, _demo
from tests.contract.test_m1_6_execution import _seed_plan


async def _current_user_id(api) -> str:
    async with api.state.demo_database.session_factory() as session:
        user_id = await session.scalar(select(UserModel.id))
        assert user_id is not None
        return user_id


async def _create_memory(client, *, key: str = "explicit-memory", **overrides):
    payload = {
        "idempotency_key": key,
        "type": "positive_preference",
        "content": "喜欢安静的室内展览",
        "value": "室内 安静 展览",
        "expires_at": None,
        "explicit_authorization": True,
        "location_granularity": None,
    }
    payload.update(overrides)
    return await client.post("/api/v1/memories", json=payload)


@pytest.mark.asyncio
async def test_explicit_memory_idempotency_version_disable_delete_and_ownership(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        created = await _create_memory(client)
        replay = await _create_memory(client)
        conflict = await _create_memory(
            client,
            content="同一个键不能代表另一项记忆",
        )
        assert created.status_code == replay.status_code == 200, created.text
        assert replay.json()["replayed"] is True
        assert replay.json()["memory"]["id"] == created.json()["memory"]["id"]
        assert conflict.status_code == 409

        memory = created.json()["memory"]
        changed = await client.patch(
            f"/api/v1/memories/{memory['id']}",
            json={
                "idempotency_key": "edit-memory",
                "expected_version": memory["version"],
                "content": "更喜欢安静、留白充足的室内展览",
                "value": "室内 安静 展览",
                "enabled": None,
                "expires_at": None,
                "change_expiry": False,
            },
        )
        stale = await client.patch(
            f"/api/v1/memories/{memory['id']}",
            json={
                "idempotency_key": "stale-edit",
                "expected_version": memory["version"],
                "content": "迟到的旧修改",
                "value": None,
                "enabled": None,
                "expires_at": None,
                "change_expiry": False,
            },
        )
        assert changed.status_code == 200
        assert stale.status_code == 409

        disabled = await client.patch(
            f"/api/v1/memories/{memory['id']}",
            json={
                "idempotency_key": "disable-memory",
                "expected_version": changed.json()["memory"]["version"],
                "content": None,
                "value": None,
                "enabled": False,
                "expires_at": None,
                "change_expiry": False,
            },
        )
        assert disabled.status_code == 200
        user_id = await _current_user_id(api)
        async with api.state.demo_database.session_factory() as session:
            assert await MemoryPlanningService(session).effective(
                user_id=user_id, at=utc_now()
            ) == ()
            foreign_user_id = generate_user_id()
            session.add(
                UserModel(
                    id=foreign_user_id,
                    mode="demo",
                    default_plan_city="shenzhen",
                    timezone="Asia/Shanghai",
                    created_at=utc_now(),
                )
            )
            await session.commit()
            with pytest.raises(MemoryNotFoundError):
                await MemoryService(session).detail(
                    user_id=foreign_user_id, memory_id=memory["id"]
                )

        deleted = await client.request(
            "DELETE",
            f"/api/v1/memories/{memory['id']}",
            json={
                "idempotency_key": "delete-memory",
                "expected_version": disabled.json()["memory"]["version"],
            },
        )
        assert deleted.status_code == 200
        assert (await client.get(f"/api/v1/memories/{memory['id']}")).status_code == 404
        assert (await client.get("/api/v1/memories")).json()["items"] == []


@pytest.mark.asyncio
async def test_concurrent_explicit_memory_replay_creates_one_aggregate(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        first, second = await asyncio.gather(
            _create_memory(client, key="concurrent-memory"),
            _create_memory(client, key="concurrent-memory"),
        )
        assert first.status_code == second.status_code == 200
        assert sorted(
            (first.json()["replayed"], second.json()["replayed"])
        ) == [False, True]
        assert first.json()["memory"]["id"] == second.json()["memory"]["id"]
        async with api.state.demo_database.session_factory() as session:
            assert await session.scalar(
                select(func.count()).select_from(MemoryModel)
            ) == 1


@pytest.mark.asyncio
async def test_feedback_suggestion_confirm_reject_and_evidence_is_not_reasked(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        plan_id, _collection_id, item_ids = await _seed_plan(api, confirmed=True)
        feedback = await client.post(
            f"/api/v1/plans/{plan_id}/feedback",
            json={
                "idempotency_key": "feedback-memory-one",
                "completion_status": "partially_completed",
                "visited_plan_item_ids": [item_ids[0]],
                "reason": "这次节奏太赶，只完成了一半",
                "expected_revision": None,
            },
        )
        suggestion = feedback.json()["feedback"]["preference_suggestion"]
        assert suggestion["confirmation_status"] == "pending"
        pending = await client.get("/api/v1/memory-suggestions")
        assert len(pending.json()["items"]) == 1
        suggestion_id = pending.json()["items"][0]["id"]
        async with api.state.demo_database.session_factory() as session:
            foreign_user_id = generate_user_id()
            session.add(
                UserModel(
                    id=foreign_user_id,
                    mode="demo",
                    default_plan_city="shenzhen",
                    timezone="Asia/Shanghai",
                    created_at=utc_now(),
                )
            )
            await session.commit()
            with pytest.raises(MemorySuggestionUnavailableError):
                await MemoryService(session).decide_suggestion(
                    user_id=foreign_user_id,
                    suggestion_id=suggestion_id,
                    decision=MemorySuggestionDecision.CONFIRMED,
                    client_idempotency_key="foreign-suggestion",
                )
            foreign_user = await session.get(UserModel, foreign_user_id)
            assert foreign_user is not None
            await session.delete(foreign_user)
            await session.commit()

        confirmed = await client.post(
            f"/api/v1/memory-suggestions/{suggestion_id}/decision",
            json={"idempotency_key": "confirm-suggestion", "decision": "confirmed"},
        )
        replay = await client.post(
            f"/api/v1/memory-suggestions/{suggestion_id}/decision",
            json={"idempotency_key": "confirm-suggestion", "decision": "confirmed"},
        )
        assert confirmed.status_code == replay.status_code == 200
        assert confirmed.json()["memory"]["type"] == "pace_preference"
        assert confirmed.json()["memory"]["source"] == {
            "type": "feedback_inference",
            "summary": "来自你对本次计划的反馈：这次节奏太赶，只完成了一半",
            "feedback_id": suggestion_id,
            "plan_id": plan_id,
        }
        assert replay.json()["replayed"] is True
        assert (await client.get("/api/v1/memory-suggestions")).json()["items"] == []

        second_plan_id, _collection_id, second_items = await _seed_plan(
            api, confirmed=True
        )
        second_feedback = await client.post(
            f"/api/v1/plans/{second_plan_id}/feedback",
            json={
                "idempotency_key": "feedback-memory-two",
                "completion_status": "partially_completed",
                "visited_plan_item_ids": [second_items[0]],
                "reason": "只是临时有事",
                "expected_revision": None,
            },
        )
        assert second_feedback.status_code == 200
        pending_ids = [
            item["id"]
            for item in (await client.get("/api/v1/memory-suggestions")).json()["items"]
        ]
        assert len(pending_ids) == 1
        second_id = pending_ids[0]
        rejected = await client.post(
            f"/api/v1/memory-suggestions/{second_id}/decision",
            json={"idempotency_key": "reject-suggestion", "decision": "rejected"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["memory"] is None
        assert (await client.get("/api/v1/memory-suggestions")).json()["items"] == []
        reverse = await client.post(
            f"/api/v1/memory-suggestions/{second_id}/decision",
            json={"idempotency_key": "reverse-rejection", "decision": "confirmed"},
        )
        assert reverse.status_code == 409

        async with api.state.demo_database.session_factory() as session:
            assert await session.scalar(
                select(func.count()).select_from(MemorySuggestionDecisionModel)
            ) == 2
            assert await session.scalar(
                select(func.count()).select_from(MemoryModel)
            ) == 1


@pytest.mark.asyncio
async def test_only_effective_memories_are_used_and_usage_is_owner_plan_scoped(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        plan_id, _collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        active = await _create_memory(client, key="active")
        expired = await _create_memory(
            client,
            key="expired",
            content="过去一段时间偏好室内",
            expires_at=(utc_now() + timedelta(hours=1)).isoformat(),
        )
        assert active.status_code == expired.status_code == 200
        user_id = await _current_user_id(api)
        active_id = active.json()["memory"]["id"]
        expiring_id = expired.json()["memory"]["id"]
        async with api.state.demo_database.session_factory() as session:
            planning = MemoryPlanningService(session)
            effective = await planning.effective(
                user_id=user_id, at=utc_now() + timedelta(hours=2)
            )
            assert [memory.id for memory in effective] == [active_id]
            await planning.record_usage(
                user_id=user_id,
                plan_id=plan_id,
                usages={active_id: "主方案采用了偏好的室内展览"},
                used_at=utc_now(),
            )
            await session.commit()
        detail = await client.get(f"/api/v1/memories/{active_id}")
        assert detail.status_code == 200
        assert detail.json()["memory"]["last_used_at"] is not None
        assert detail.json()["usages"][0]["plan_id"] == plan_id
        assert detail.json()["usages"][0]["basis"] == "主方案采用了偏好的室内展览"

        disabled = await client.patch(
            f"/api/v1/memories/{active_id}",
            json={
                "idempotency_key": "disable-after-use",
                "expected_version": detail.json()["memory"]["version"],
                "content": None,
                "value": None,
                "enabled": False,
                "expires_at": None,
                "change_expiry": False,
            },
        )
        assert disabled.status_code == 200
        async with api.state.demo_database.session_factory() as session:
            effective_now = await MemoryPlanningService(session).effective(
                user_id=user_id, at=utc_now()
            )
            assert [memory.id for memory in effective_now] == [expiring_id]
            foreign_user_id = generate_user_id()
            session.add(
                UserModel(
                    id=foreign_user_id,
                    mode="demo",
                    default_plan_city="shenzhen",
                    timezone="Asia/Shanghai",
                    created_at=utc_now(),
                )
            )
            await session.commit()
            await MemoryPlanningService(session).record_usage(
                user_id=foreign_user_id,
                plan_id=plan_id,
                usages={active_id: "不得跨用户记录"},
                used_at=utc_now(),
            )
            assert await session.scalar(
                select(func.count()).select_from(MemoryPlanUsageModel)
            ) == 1


@pytest.mark.asyncio
async def test_sensitive_location_and_failed_commit_leave_no_partial_memory(
    test_settings,
    monkeypatch,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        rejected = await _create_memory(
            client,
            key="exact-home",
            type="usual_area",
            content="记住我家附近",
            value="深圳市福田区某小区 2 栋 201",
            location_granularity=None,
        )
        unauthorized = await _create_memory(
            client,
            key="unauthorized-area",
            type="usual_area",
            content="常用区域",
            value="福田区",
            explicit_authorization=False,
            location_granularity="coarse",
        )
        assert rejected.status_code == unauthorized.status_code == 422

        user_id = await _current_user_id(api)
        async with api.state.demo_database.session_factory() as session:
            service = MemoryService(session)

            async def fail_commit() -> None:
                raise RuntimeError("forced commit failure")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="forced commit failure"):
                await service.create_explicit(
                    user_id=user_id,
                    memory_type=MemoryType.POSITIVE_PREFERENCE,
                    content="这项写入必须整体回滚",
                    value="回滚",
                    expires_at=None,
                    explicit_authorization=True,
                    location_granularity=None,
                    client_idempotency_key="rollback",
                )
        async with api.state.demo_database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(MemoryModel)) == 0
            assert await session.scalar(
                select(func.count()).select_from(MemoryOperationModel)
            ) == 0


@pytest.mark.asyncio
async def test_private_export_is_current_user_allowlist_and_no_store(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        plan_id, collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        memory = await _create_memory(client, key="export-memory")
        assert memory.status_code == 200
        response = await client.get("/api/v1/data-export.json")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["content-disposition"].endswith(
            'filename="shiguang-data.json"'
        )
        payload = json.loads(response.content)
        assert [item["id"] for item in payload["collections"]] == [collection_id]
        assert [item["id"] for item in payload["plans"]] == [plan_id]
        assert [item["id"] for item in payload["memories"]] == [
            memory.json()["memory"]["id"]
        ]
        serialized = json.dumps(payload).lower()
        for forbidden in ("cookie", "token", "secret", "password", "idempotency"):
            assert forbidden not in serialized

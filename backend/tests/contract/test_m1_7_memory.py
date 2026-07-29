"""M1-7 structured Memory, data-control, and export contracts."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

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
from app.domain.plans import PlanPace, PlanPaceSource
from app.domain.time import utc_now
from app.infrastructure.db.models import (
    MemoryModel,
    MemoryOperationModel,
    MemoryPlanUsageModel,
    MemorySuggestionDecisionModel,
    PlanFeedbackAuditModel,
    PlanFeedbackStateModel,
    UserModel,
)
from app.infrastructure.repositories import SqlAlchemyPlanRepository
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
        assert feedback.json()["feedback"]["preference_suggestion"] is None
        suggestion_id = feedback.json()["feedback"]["id"]
        async with api.state.demo_database.session_factory() as session:
            audit = await session.get(PlanFeedbackAuditModel, suggestion_id)
            state = await session.get(PlanFeedbackStateModel, plan_id)
            assert audit is not None and state is not None
            legacy_json = {
                "content": "一次历史反馈留下的待确认建议",
                "confirmation_status": "pending",
            }
            audit.preference_suggestion_json = legacy_json
            state.preference_suggestion_json = legacy_json
            await session.commit()
        pending = await client.get("/api/v1/memory-suggestions")
        assert len(pending.json()["items"]) == 1
        pending_item = pending.json()["items"][0]
        assert pending_item == {
            "id": suggestion_id,
            "plan_id": plan_id,
            "memory_type": None,
            "content": "一次历史反馈留下的待确认建议",
            "value": None,
            "evidence_summary": "来自一次历史反馈建议，尚未形成长期偏好",
            "created_at": pending_item["created_at"],
        }
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
                    memory_type=MemoryType.PACE_PREFERENCE,
                    content="以后优先安排轻松节奏",
                    value="relaxed",
                    client_idempotency_key="foreign-suggestion",
                )
            foreign_user = await session.get(UserModel, foreign_user_id)
            assert foreign_user is not None
            await session.delete(foreign_user)
            await session.commit()

        missing_fields = await client.post(
            f"/api/v1/memory-suggestions/{suggestion_id}/decision",
            json={"idempotency_key": "missing-fields", "decision": "confirmed"},
        )
        assert missing_fields.status_code == 422
        confirmed = await client.post(
            f"/api/v1/memory-suggestions/{suggestion_id}/decision",
            json={
                "idempotency_key": "confirm-suggestion",
                "decision": "confirmed",
                "memory_type": "pace_preference",
                "content": "以后优先安排轻松节奏",
                "value": "relaxed",
            },
        )
        replay = await client.post(
            f"/api/v1/memory-suggestions/{suggestion_id}/decision",
            json={
                "idempotency_key": "confirm-suggestion",
                "decision": "confirmed",
                "memory_type": "pace_preference",
                "content": "以后优先安排轻松节奏",
                "value": "relaxed",
            },
        )
        assert confirmed.status_code == replay.status_code == 200
        assert confirmed.json()["memory"]["type"] == "pace_preference"
        assert confirmed.json()["memory"]["source"] == {
            "type": "feedback_inference",
            "summary": "由你根据一次历史反馈建议明确确认",
            "feedback_id": suggestion_id,
            "plan_id": plan_id,
        }
        assert replay.json()["replayed"] is True
        changed_payload = await client.post(
            f"/api/v1/memory-suggestions/{suggestion_id}/decision",
            json={
                "idempotency_key": "confirm-suggestion",
                "decision": "confirmed",
                "memory_type": "positive_preference",
                "content": "改成另一项长期含义",
                "value": "展览",
            },
        )
        assert changed_payload.status_code == 409
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
        assert second_feedback.json()["feedback"]["preference_suggestion"] is None
        second_id = second_feedback.json()["feedback"]["id"]
        async with api.state.demo_database.session_factory() as session:
            audit = await session.get(PlanFeedbackAuditModel, second_id)
            state = await session.get(PlanFeedbackStateModel, second_plan_id)
            assert audit is not None and state is not None
            legacy_json = {
                "content": "另一次历史反馈候选",
                "confirmation_status": "pending",
            }
            audit.preference_suggestion_json = legacy_json
            state.preference_suggestion_json = legacy_json
            await session.commit()
        pending_ids = [
            item["id"]
            for item in (await client.get("/api/v1/memory-suggestions")).json()["items"]
        ]
        assert len(pending_ids) == 1
        assert pending_ids[0] == second_id
        rejected = await client.post(
            f"/api/v1/memory-suggestions/{second_id}/decision",
            json={"idempotency_key": "reject-suggestion", "decision": "rejected"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["memory"] is None
        assert (await client.get("/api/v1/memory-suggestions")).json()["items"] == []
        reverse = await client.post(
            f"/api/v1/memory-suggestions/{second_id}/decision",
            json={
                "idempotency_key": "reverse-rejection",
                "decision": "confirmed",
                "memory_type": "positive_preference",
                "content": "以后喜欢安静地点",
                "value": "安静",
            },
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
async def test_structured_feedback_candidate_is_pending_and_auditable(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        plan_id, _collection_id, item_ids = await _seed_plan(api, confirmed=True)
        candidate = {
            "memory_type": "pace_preference",
            "content": "以后默认使用轻松节奏",
            "value": "relaxed",
            "evidence_summary": "你在反馈表单中明确选择保存这项节奏候选",
        }
        body = {
            "idempotency_key": "structured-candidate",
            "completion_status": "partially_completed",
            "visited_plan_item_ids": [item_ids[0]],
            "reason": "任何自由文本都不是候选依据",
            "expected_revision": None,
            "preference_candidate": candidate,
        }
        submitted = await client.post(
            f"/api/v1/plans/{plan_id}/feedback", json=body
        )
        replay = await client.post(f"/api/v1/plans/{plan_id}/feedback", json=body)
        assert submitted.status_code == replay.status_code == 200
        assert replay.json()["replayed"] is True
        suggestion = submitted.json()["feedback"]["preference_suggestion"]
        assert suggestion == {**candidate, "confirmation_status": "pending"}
        assert (await client.get("/api/v1/memories")).json()["items"] == []
        pending = (await client.get("/api/v1/memory-suggestions")).json()["items"]
        assert len(pending) == 1
        assert pending[0]["memory_type"] == "pace_preference"
        assert pending[0]["value"] == "relaxed"
        assert pending[0]["evidence_summary"] == candidate["evidence_summary"]

        conflict = await client.post(
            f"/api/v1/plans/{plan_id}/feedback",
            json={
                **body,
                "preference_candidate": {**candidate, "value": "packed"},
            },
        )
        assert conflict.status_code == 409
        suggestion_id = submitted.json()["feedback"]["id"]
        rejected = await client.post(
            f"/api/v1/memory-suggestions/{suggestion_id}/decision",
            json={"idempotency_key": "reject-structured", "decision": "rejected"},
        )
        assert rejected.status_code == 200
        corrected = await client.post(
            f"/api/v1/plans/{plan_id}/feedback",
            json={
                **body,
                "idempotency_key": "structured-candidate-correction",
                "expected_revision": 1,
            },
        )
        assert corrected.status_code == 200
        assert corrected.json()["feedback"]["preference_suggestion"] is None
        assert (await client.get("/api/v1/memory-suggestions")).json()["items"] == []


@pytest.mark.asyncio
async def test_effective_pace_constraint_is_persisted_and_public(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        await _demo(client)
        request = {
            "idempotency_key": "memory-default-pace-plan",
            "start_at": "2026-07-30T10:00:00+08:00",
            "end_at": "2026-07-30T18:00:00+08:00",
            "area": {"districts": ["南山区"], "labels": []},
            "transport_modes": ["transit"],
        }
        created = await client.post("/api/v1/plans", json=request)
        assert created.status_code == 202, created.text
        plan_id = created.json()["plan_id"]
        user_id = await _current_user_id(api)
        async with api.state.demo_database.session_factory() as session:
            plans = SqlAlchemyPlanRepository(session)
            plan = await plans.require(user_id=user_id, plan_id=plan_id)
            assert plan.constraints.pace is PlanPace.BALANCED
            assert plan.constraints.pace_source is PlanPaceSource.SYSTEM_DEFAULT
            effective = plan.constraints.model_copy(
                update={
                    "pace": PlanPace.RELAXED,
                    "pace_source": PlanPaceSource.MEMORY_DEFAULT,
                }
            )
            await plans.set_effective_constraints(
                user_id=user_id,
                plan_id=plan_id,
                constraints=effective,
                now=utc_now(),
            )
            await session.commit()
        public = await client.get(f"/api/v1/plans/{plan_id}")
        assert public.status_code == 200
        assert public.json()["constraints"]["pace"] == "relaxed"
        assert public.json()["constraints"]["pace_source"] == "memory_default"
        explicit = await client.post(
            "/api/v1/plans",
            json={
                **request,
                "idempotency_key": "explicit-balanced-pace-plan",
                "pace": "balanced",
            },
        )
        assert explicit.status_code == 202
        explicit_public = await client.get(
            f"/api/v1/plans/{explicit.json()['plan_id']}"
        )
        assert explicit_public.json()["constraints"]["pace"] == "balanced"
        assert explicit_public.json()["constraints"]["pace_source"] == "user_request"


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
        disguised_exact = await _create_memory(
            client,
            key="disguised-exact-area",
            type="usual_area",
            content="常用区域：福田区",
            value="深圳市福田区某小区 2 栋 201",
            location_granularity="coarse",
        )
        assert (
            rejected.status_code
            == unauthorized.status_code
            == disguised_exact.status_code
            == 422
        )

        coarse_memories = []
        for index, area in enumerate(
            (
                {"districts": ["南山区"], "labels": []},
                {"districts": [], "labels": ["大学城附近"]},
                {"districts": ["大鹏新区"], "labels": []},
            )
        ):
            response = await client.post(
                "/api/v1/memories",
                json={
                    "idempotency_key": f"coarse-area-{index}",
                    "type": "usual_area",
                    "content": None,
                    "value": None,
                    "area": area,
                    "expires_at": None,
                    "explicit_authorization": True,
                    "location_granularity": "coarse",
                },
            )
            assert response.status_code == 200, response.text
            coarse_memories.append(response.json()["memory"])
        coarse = coarse_memories[0]
        edited = await client.patch(
            f"/api/v1/memories/{coarse['id']}",
            json={
                "idempotency_key": "edit-coarse-area",
                "expected_version": coarse["version"],
                "content": None,
                "value": None,
                "area": {"districts": [], "labels": ["大学城附近"]},
                "enabled": None,
                "expires_at": None,
                "change_expiry": False,
            },
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["memory"]["content"] == "常用区域：大学城附近"
        for unsafe in (
            {"origin": {"longitude": 114.0, "latitude": 22.5}},
            {"coordinates": [114.0, 22.5]},
            {"poi_id": "B0PRIVATE"},
            {"address": "深圳市福田区某小区 2 栋 201"},
        ):
            rejected_update = await client.patch(
                f"/api/v1/memories/{coarse['id']}",
                json={
                    "idempotency_key": f"unsafe-{next(iter(unsafe))}",
                    "expected_version": edited.json()["memory"]["version"],
                    "area": unsafe,
                },
            )
            assert rejected_update.status_code == 422
        disabled = await client.patch(
            f"/api/v1/memories/{coarse['id']}",
            json={
                "idempotency_key": "disable-coarse-area",
                "expected_version": edited.json()["memory"]["version"],
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
            assert await session.scalar(select(func.count()).select_from(MemoryModel)) == 3
            assert await session.scalar(
                select(func.count()).select_from(MemoryOperationModel)
            ) == 5


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


def test_memory_repairs_keep_one_service_and_no_location_or_inference_lists() -> None:
    application = Path(__file__).resolve().parents[2] / "app"
    production = "\n".join(
        path.read_text()
        for path in application.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    assert "_SHENZHEN_ADMIN_DISTRICTS" not in production
    assert "PreferenceSuggestionService" not in production
    assert production.count("class MemoryService:") == 1
    assert production.count("class SqlAlchemyMemoryRepository:") == 1

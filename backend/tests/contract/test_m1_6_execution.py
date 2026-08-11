"""M1-6 confirmed-plan calendar, navigation, and feedback contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from icalendar import Calendar
from sqlalchemy import func, select

from app.application.plan_execution import PlanFeedbackService
from app.domain.collections import CollectionItem, CollectionKind, CollectionStatus, PlanCity
from app.domain.identifiers import (
    generate_collection_item_id,
    generate_plan_id,
    generate_trace_id,
)
from app.domain.places import PoiProvider, TransportMode
from app.domain.plans import (
    ActivityArea,
    PlanCompletionStatus,
    PlanConstraints,
    PlanDraftOutcome,
    PlanDraftResult,
    PlanItem,
    PlanItemRole,
    PlanItemSourceKind,
    PlanOperation,
    PlanOption,
    PlanOptionRole,
    PlanPace,
    PlanSelectionReasonCode,
    PlanStatus,
    PlanVersion,
)
from app.domain.plans.drafts import (
    SELECTION_REASON_SUMMARIES,
    PlanItemSource,
    PlanRouteLeg,
)
from app.infrastructure.db.models import (
    CollectionItemModel,
    CollectionVisitSourceModel,
    PlanFeedbackAuditModel,
    PlanFeedbackStateModel,
    PlanItemModel,
    PlanModel,
    UserModel,
)
from app.infrastructure.repositories import (
    SqlAlchemyCollectionRepository,
    SqlAlchemyPlanRepository,
    plan_request_fingerprint,
)
from tests.contract.test_m0_2d_api import _client, _demo
from tests.fixtures.maps import (
    SHENZHEN_CHAIN_CAFE_ONE,
    SHENZHEN_MUSEUM,
    make_stub_map_provider,
)


def _constraints() -> PlanConstraints:
    created = datetime(2026, 7, 28, 0, tzinfo=UTC)
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=datetime(2026, 7, 29, 2, tzinfo=UTC),
        end_at=datetime(2026, 7, 29, 7, tzinfo=UTC),
        area=ActivityArea(districts=("福田区",), labels=("市民中心",)),
        pace=PlanPace.BALANCED,
        transport_modes=(TransportMode.WALKING,),
        created_at=created,
        expires_at=created + timedelta(days=2),
    )


def _draft(collection_id: str) -> PlanDraftResult:
    start = datetime(2026, 7, 29, 2, 30, tzinfo=UTC)
    reason = SELECTION_REASON_SUMMARIES[
        PlanSelectionReasonCode.MODEL_PROPOSAL
    ]
    first = PlanItem(
        role=PlanItemRole.CORE,
        title="深圳当代艺术与城市规划馆，夏季特展",
        kind=CollectionKind.PLACE,
        start_at=start,
        end_at=start + timedelta(hours=1),
        visit_duration_seconds=3600,
        inbound_route=PlanRouteLeg(
            to_collection_item_ids=(collection_id,),
            duration_seconds=900,
            distance_meters=3200,
            transport_mode=TransportMode.TRANSIT,
        ),
        source=PlanItemSource(
            collection_item_ids=(collection_id,),
            concrete_poi=SHENZHEN_MUSEUM,
        ),
        selection_reason_code=PlanSelectionReasonCode.MODEL_PROPOSAL,
        selection_reason=reason,
    )
    second = PlanItem(
        role=PlanItemRole.AUXILIARY,
        title="未名咖啡；市民中心店",
        kind=CollectionKind.PLACE,
        start_at=start + timedelta(hours=1, minutes=15),
        end_at=start + timedelta(hours=2, minutes=15),
        visit_duration_seconds=3600,
        inbound_route=PlanRouteLeg(
            from_collection_item_ids=(collection_id,),
            to_external_provider=PoiProvider.AMAP,
            to_external_poi_id=SHENZHEN_CHAIN_CAFE_ONE.poi_id,
            duration_seconds=900,
            distance_meters=850,
            transport_mode=TransportMode.WALKING,
        ),
        source=PlanItemSource(
            kind=PlanItemSourceKind.EXTERNAL_PLACE,
            concrete_poi=SHENZHEN_CHAIN_CAFE_ONE,
            poi_queried_at=datetime(2026, 7, 28, 1, tzinfo=UTC),
            supplement_reason="补足休息环节",
            source_label="高德补充 · 未收藏",
        ),
        selection_reason_code=PlanSelectionReasonCode.MODEL_PROPOSAL,
        selection_reason=reason,
    )
    return PlanDraftResult(
        outcome=PlanDraftOutcome.GENERATED,
        options=(
            PlanOption(
                role=PlanOptionRole.MAIN,
                items=(first, second),
                switch_buffer_seconds=900,
                end_buffer_seconds=1200,
            ),
        ),
    )


async def _seed_plan(
    api,
    *,
    confirmed: bool,
    collection_id: str | None = None,
) -> tuple[str, str, tuple[str, str]]:
    database = api.state.demo_database
    async with database.session_factory() as session:
        user_id = await session.scalar(select(UserModel.id))
        assert user_id is not None
        # Keep this shared historical plan fixture inside its approval window.
        # Wall-clock time would make every M1-6/M1-7 consumer fail after the
        # fixed 2026-07-29 itinerary ends.
        now = datetime(2026, 7, 28, 2, tzinfo=UTC)
        if collection_id is None:
            collection_id = generate_collection_item_id()
            collection = CollectionItem(
                id=collection_id,
                user_id=user_id,
                kind=CollectionKind.PLACE,
                title="深圳当代艺术与城市规划馆",
                status=CollectionStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            await SqlAlchemyCollectionRepository(session).add_collection_item(
                user_id=user_id,
                item=collection,
            )
        plan_id = generate_plan_id()
        plan = PlanVersion(
            id=plan_id,
            root_plan_id=plan_id,
            user_id=user_id,
            version=1,
            operation=PlanOperation.GENERATE,
            status=PlanStatus.GENERATING,
            constraints=_constraints(),
            trace_id=generate_trace_id(),
            idempotency_key=f"seed-{plan_id}",
            created_at=now,
            updated_at=now,
        )
        repository = SqlAlchemyPlanRepository(session)
        await repository.add(plan, request_fingerprint=plan_request_fingerprint("seed"))
        await repository.complete_generation(
            user_id=user_id,
            plan_id=plan_id,
            draft=_draft(collection_id),
            now=now,
        )
        if confirmed:
            await repository.confirm(
                user_id=user_id,
                plan_id=plan_id,
                idempotency_key=f"confirm-{plan_id}",
                request_fingerprint=plan_request_fingerprint("confirm"),
                now=now,
            )
        await session.commit()
        item_ids = tuple(
            (
                await session.scalars(
                    select(PlanItemModel.id)
                    .where(PlanItemModel.plan_id == plan_id)
                    .order_by(PlanItemModel.item_index)
                )
            ).all()
        )
        assert len(item_ids) == 2
        assert collection_id is not None
        return plan_id, collection_id, (item_ids[0], item_ids[1])


async def _seed_adjusted_plan(
    api,
    *,
    root_id: str,
    collection_id: str,
    confirmed: bool,
) -> tuple[str, tuple[str, str]]:
    database = api.state.demo_database
    async with database.session_factory() as session:
        user_id = await session.scalar(select(UserModel.id))
        assert user_id is not None
        now = datetime(2026, 7, 28, 3, tzinfo=UTC)
        adjusted_id = generate_plan_id()
        adjusted = PlanVersion(
            id=adjusted_id,
            root_plan_id=root_id,
            parent_plan_id=root_id,
            user_id=user_id,
            version=2,
            operation=PlanOperation.ADJUST,
            status=PlanStatus.GENERATING,
            constraints=_constraints(),
            adjustment_text="稍微调整",
            trace_id=generate_trace_id(),
            idempotency_key=f"seed-{adjusted_id}",
            created_at=now,
            updated_at=now,
        )
        repository = SqlAlchemyPlanRepository(session)
        await repository.add(
            adjusted,
            request_fingerprint=plan_request_fingerprint("adjusted"),
        )
        await repository.complete_generation(
            user_id=user_id,
            plan_id=adjusted_id,
            draft=_draft(collection_id),
            now=now,
        )
        if confirmed:
            await repository.confirm(
                user_id=user_id,
                plan_id=adjusted_id,
                idempotency_key=f"confirm-{adjusted_id}",
                request_fingerprint=plan_request_fingerprint("confirm-adjusted"),
                now=now + timedelta(hours=1),
            )
        await session.commit()
        item_ids = tuple(
            (
                await session.scalars(
                    select(PlanItemModel.id)
                    .where(PlanItemModel.plan_id == adjusted_id)
                    .order_by(PlanItemModel.item_index)
                )
            ).all()
        )
        assert len(item_ids) == 2
        return adjusted_id, (item_ids[0], item_ids[1])


@pytest.mark.asyncio
async def test_unconfirmed_plan_rejects_all_execution_surfaces(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        plan_id, _collection_id, item_ids = await _seed_plan(api, confirmed=False)
        calendar = await client.get(f"/api/v1/plans/{plan_id}/calendar.ics")
        execution = await client.get(f"/api/v1/plans/{plan_id}/execution")
        feedback = await client.post(
            f"/api/v1/plans/{plan_id}/feedback",
            json={
                "idempotency_key": "unconfirmed",
                "completion_status": "partially_completed",
                "visited_plan_item_ids": [item_ids[0]],
                "expected_revision": None,
            },
        )
        assert calendar.status_code == execution.status_code == feedback.status_code == 409
        assert calendar.json()["error_code"] == "PLAN_NOT_CONFIRMED"


@pytest.mark.asyncio
async def test_calendar_and_navigation_are_stable_safe_and_parseable(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        plan_id, _collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        first = await client.get(f"/api/v1/plans/{plan_id}/calendar.ics")
        second = await client.get(f"/api/v1/plans/{plan_id}/calendar.ics")
        assert first.status_code == second.status_code == 200
        assert first.content == second.content
        assert first.headers["content-type"].startswith("text/calendar")
        assert "attachment;" in first.headers["content-disposition"]
        text = first.content.decode()
        parsed = Calendar.from_ical(first.content)
        events = tuple(parsed.walk("VEVENT"))
        assert len(events) == 1
        event = events[0]
        assert "BEGIN:VCALENDAR\r\n" in text
        assert "BEGIN:VEVENT\r\n" in text
        assert f"UID:{plan_id}@shiguang.local" in text
        assert "DTSTART;TZID=Asia/Shanghai:20260729T100000" in text
        assert "DTEND;TZID=Asia/Shanghai:20260729T150000" in text
        assert "福中路184号" in text
        assert "未名咖啡\\；" not in text
        assert all(len(line.encode()) <= 75 for line in text.split("\r\n") if line)
        assert "Cookie" not in text and "/Users/" not in text
        assert str(event["UID"]) == f"{plan_id}@shiguang.local"
        assert event.decoded("DTSTART").tzinfo == ZoneInfo("Asia/Shanghai")
        assert event.decoded("DTEND").tzinfo == ZoneInfo("Asia/Shanghai")
        assert "URL" not in event

        execution = await client.get(f"/api/v1/plans/{plan_id}/execution")
        assert execution.status_code == 200
        items = execution.json()["items"]
        assert [item["address"] for item in items] == ["福中路184号", "福中一路1号"]
        assert all(item["navigation_uri"].startswith("geo:") for item in items)
        assert "key=" not in execution.text.lower()


@pytest.mark.asyncio
async def test_calendar_and_navigation_follow_latest_confirmed_version(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        root_id, collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        adjusted_id, _adjusted_items = await _seed_adjusted_plan(
            api,
            root_id=root_id,
            collection_id=collection_id,
            confirmed=False,
        )

        before_calendar = await client.get(f"/api/v1/plans/{adjusted_id}/calendar.ics")
        before_execution = await client.get(f"/api/v1/plans/{adjusted_id}/execution")
        assert before_calendar.status_code == before_execution.status_code == 200
        assert f"UID:{root_id}@shiguang.local" in before_calendar.text
        assert before_execution.json()["plan_id"] == root_id

        database = api.state.demo_database
        async with database.session_factory() as session:
            user_id = await session.scalar(select(UserModel.id))
            assert user_id is not None
            await SqlAlchemyPlanRepository(session).confirm(
                user_id=user_id,
                plan_id=adjusted_id,
                idempotency_key=f"confirm-{adjusted_id}",
                request_fingerprint=plan_request_fingerprint("confirm-adjusted"),
                now=datetime(2026, 7, 28, 4, tzinfo=UTC),
            )
            await session.commit()

        after_calendar = await client.get(f"/api/v1/plans/{root_id}/calendar.ics")
        after_execution = await client.get(f"/api/v1/plans/{root_id}/execution")
        assert after_calendar.status_code == after_execution.status_code == 200
        assert f"UID:{adjusted_id}@shiguang.local" in after_calendar.text
        assert after_execution.json()["plan_id"] == adjusted_id


@pytest.mark.parametrize(
    ("completion_status", "visited_index", "expected_item_statuses"),
    [
        ("completed", None, ("visited", "visited")),
        ("partially_completed", 0, ("visited", "not_visited")),
    ],
)
@pytest.mark.asyncio
async def test_feedback_through_historical_version_only_updates_latest_confirmed(
    test_settings,
    completion_status: str,
    visited_index: int | None,
    expected_item_statuses: tuple[str, str],
) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        root_id, collection_id, root_items = await _seed_plan(api, confirmed=True)
        adjusted_id, adjusted_items = await _seed_adjusted_plan(
            api,
            root_id=root_id,
            collection_id=collection_id,
            confirmed=True,
        )
        body = {
            "idempotency_key": f"historical-{completion_status}",
            "completion_status": completion_status,
            "visited_plan_item_ids": (
                [] if visited_index is None else [adjusted_items[visited_index]]
            ),
            "expected_revision": None,
        }

        submitted = await client.post(f"/api/v1/plans/{root_id}/feedback", json=body)
        replay = await client.post(
            f"/api/v1/plans/{adjusted_id}/feedback",
            json=body,
        )
        assert submitted.status_code == replay.status_code == 200
        assert submitted.json()["feedback"]["plan_id"] == adjusted_id
        assert replay.json()["replayed"] is True

        stale = await client.post(
            f"/api/v1/plans/{root_id}/feedback",
            json={**body, "idempotency_key": f"stale-{completion_status}"},
        )
        illegal = await client.post(
            f"/api/v1/plans/{root_id}/feedback",
            json={
                **body,
                "idempotency_key": f"illegal-{completion_status}",
                "visited_plan_item_ids": [root_items[0]],
                "completion_status": "partially_completed",
                "expected_revision": 1,
            },
        )
        assert stale.status_code == 409
        assert illegal.status_code == 422

        execution = await client.get(f"/api/v1/plans/{root_id}/execution")
        assert execution.status_code == 200
        assert execution.json()["plan_id"] == adjusted_id
        assert execution.json()["feedback"]["plan_id"] == adjusted_id

        async with api.state.demo_database.session_factory() as session:
            user_id = await session.scalar(select(UserModel.id))
            assert user_id is not None
            current = await PlanFeedbackService().current(
                session=session,
                user_id=user_id,
                plan_id=root_id,
            )
            assert current is not None and current.plan_id == adjusted_id
            assert await session.get(PlanFeedbackStateModel, root_id) is None
            assert await session.get(PlanFeedbackStateModel, adjusted_id) is not None
            assert tuple(
                (
                    await session.scalars(
                        select(PlanFeedbackAuditModel.plan_id)
                    )
                ).all()
            ) == (adjusted_id,)
            root_statuses = tuple(
                (
                    await session.scalars(
                        select(PlanItemModel.execution_status)
                        .where(PlanItemModel.plan_id == root_id)
                        .order_by(PlanItemModel.item_index)
                    )
                ).all()
            )
            adjusted_statuses = tuple(
                (
                    await session.scalars(
                        select(PlanItemModel.execution_status)
                        .where(PlanItemModel.plan_id == adjusted_id)
                        .order_by(PlanItemModel.item_index)
                    )
                ).all()
            )
            assert root_statuses == ("pending", "pending")
            assert adjusted_statuses == expected_item_statuses
            visit_plan_ids = tuple(
                (
                    await session.scalars(
                        select(PlanItemModel.plan_id)
                        .join(
                            CollectionVisitSourceModel,
                            CollectionVisitSourceModel.plan_item_id == PlanItemModel.id,
                        )
                    )
                ).all()
            )
            assert visit_plan_ids == (adjusted_id,)
            root = await session.get(PlanModel, root_id)
            adjusted = await session.get(PlanModel, adjusted_id)
            assert root is not None and root.status == PlanStatus.SUPERSEDED.value
            assert adjusted is not None and adjusted.status == completion_status


@pytest.mark.asyncio
async def test_partial_feedback_correction_is_audited_and_recomputes_collection(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        plan_id, collection_id, item_ids = await _seed_plan(api, confirmed=True)
        body = {
            "idempotency_key": "partial-once",
            "completion_status": "partially_completed",
            "visited_plan_item_ids": [item_ids[0]],
            "reason": "临时缩短行程",
            "expected_revision": None,
        }
        submitted = await client.post(f"/api/v1/plans/{plan_id}/feedback", json=body)
        replay = await client.post(f"/api/v1/plans/{plan_id}/feedback", json=body)
        assert submitted.status_code == replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert submitted.json()["feedback"]["revision"] == 1
        assert submitted.json()["feedback"]["preference_suggestion"] is None

        database = api.state.demo_database
        async with database.session_factory() as session:
            collection = await session.get(CollectionItemModel, collection_id)
            assert collection is not None
            assert collection.status == "visited"
            assert await session.scalar(
                select(func.count()).select_from(CollectionItemModel)
            ) == 1

        corrected = await client.post(
            f"/api/v1/plans/{plan_id}/feedback",
            json={
                "idempotency_key": "correction",
                "completion_status": "not_completed",
                "visited_plan_item_ids": [],
                "reason": None,
                "expected_revision": 1,
            },
        )
        assert corrected.status_code == 200
        assert corrected.json()["feedback"]["revision"] == 2
        restored = await client.get(f"/api/v1/plans/{plan_id}/execution")
        assert [item["status"] for item in restored.json()["items"]] == [
            "not_visited",
            "not_visited",
        ]
        assert restored.json()["feedback"]["completion_status"] == "not_completed"
        async with database.session_factory() as session:
            collection = await session.get(CollectionItemModel, collection_id)
            assert collection is not None
            assert collection.status == "active"
            assert await session.scalar(
                select(func.count()).select_from(PlanFeedbackAuditModel)
            ) == 2


@pytest.mark.asyncio
async def test_feedback_rejects_empty_foreign_and_conflicting_replays(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        plan_id, _collection_id, item_ids = await _seed_plan(api, confirmed=True)
        other_plan_id, _other_collection_id, other_item_ids = await _seed_plan(
            api, confirmed=True
        )
        empty = await client.post(
            f"/api/v1/plans/{plan_id}/feedback",
            json={
                "idempotency_key": "empty",
                "completion_status": "partially_completed",
                "visited_plan_item_ids": [],
                "expected_revision": None,
            },
        )
        foreign = await client.post(
            f"/api/v1/plans/{plan_id}/feedback",
            json={
                "idempotency_key": "foreign",
                "completion_status": "partially_completed",
                "visited_plan_item_ids": [other_item_ids[0]],
                "expected_revision": None,
            },
        )
        assert empty.status_code == foreign.status_code == 422

        first = {
            "idempotency_key": "same",
            "completion_status": "partially_completed",
            "visited_plan_item_ids": [item_ids[0]],
            "expected_revision": None,
        }
        responses = await asyncio.gather(
            client.post(f"/api/v1/plans/{plan_id}/feedback", json=first),
            client.post(f"/api/v1/plans/{plan_id}/feedback", json=first),
        )
        assert sorted(response.status_code for response in responses) == [200, 200]
        conflict = await client.post(
            f"/api/v1/plans/{plan_id}/feedback",
            json={**first, "completion_status": "completed"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error_code"] == "IDEMPOTENCY_CONFLICT"

        assert other_plan_id != plan_id


@pytest.mark.asyncio
async def test_correction_keeps_visited_when_another_valid_visit_supports_it(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        first_plan_id, collection_id, _first_items = await _seed_plan(
            api, confirmed=True
        )
        second_plan_id, _same_collection_id, _second_items = await _seed_plan(
            api,
            confirmed=True,
            collection_id=collection_id,
        )
        for key, plan_id in (("first-visit", first_plan_id), ("second-visit", second_plan_id)):
            response = await client.post(
                f"/api/v1/plans/{plan_id}/feedback",
                json={
                    "idempotency_key": key,
                    "completion_status": "completed",
                    "visited_plan_item_ids": [],
                    "expected_revision": None,
                },
            )
            assert response.status_code == 200

        corrected = await client.post(
            f"/api/v1/plans/{first_plan_id}/feedback",
            json={
                "idempotency_key": "remove-first-visit",
                "completion_status": "not_completed",
                "visited_plan_item_ids": [],
                "expected_revision": 1,
            },
        )
        assert corrected.status_code == 200
        async with api.state.demo_database.session_factory() as session:
            collection = await session.get(CollectionItemModel, collection_id)
            assert collection is not None
            assert collection.status == CollectionStatus.VISITED.value


@pytest.mark.asyncio
async def test_execution_surfaces_are_user_isolated(test_settings) -> None:
    async with _client(test_settings) as (api, owner_client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(owner_client)
        plan_id, _collection_id, _item_ids = await _seed_plan(api, confirmed=True)

        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as other_client:
            await _demo(other_client)
            responses = (
                await other_client.get(f"/api/v1/plans/{plan_id}/calendar.ics"),
                await other_client.get(f"/api/v1/plans/{plan_id}/execution"),
                await other_client.post(
                    f"/api/v1/plans/{plan_id}/feedback",
                    json={
                        "idempotency_key": "other-user",
                        "completion_status": "not_completed",
                        "visited_plan_item_ids": [],
                        "expected_revision": None,
                    },
                ),
            )
        assert [response.status_code for response in responses] == [404, 404, 404]


@pytest.mark.asyncio
async def test_feedback_transaction_rolls_back_after_mid_write_failure(
    test_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        plan_id, collection_id, item_ids = await _seed_plan(api, confirmed=True)

        async def fail_recompute(**_kwargs) -> None:
            raise RuntimeError("transaction rollback fixture")

        monkeypatch.setattr(
            PlanFeedbackService,
            "_recompute_collections",
            staticmethod(fail_recompute),
        )
        database = api.state.demo_database
        async with database.session_factory() as session:
            user_id = await session.scalar(select(UserModel.id))
            assert user_id is not None
            with pytest.raises(RuntimeError, match="rollback fixture"):
                await PlanFeedbackService().submit(
                    session=session,
                    user_id=user_id,
                    plan_id=plan_id,
                    completion_status=PlanCompletionStatus.PARTIALLY_COMPLETED,
                    visited_plan_item_ids=(item_ids[0],),
                    reason=None,
                    client_idempotency_key="rollback",
                    expected_revision=None,
                )
            await session.rollback()

        async with database.session_factory() as session:
            collection = await session.get(CollectionItemModel, collection_id)
            assert collection is not None
            assert collection.status == CollectionStatus.ACTIVE.value
            assert await session.scalar(
                select(func.count()).select_from(PlanFeedbackAuditModel)
            ) == 0
            statuses = tuple(
                (
                    await session.scalars(
                        select(PlanItemModel.execution_status)
                        .where(PlanItemModel.plan_id == plan_id)
                        .order_by(PlanItemModel.item_index)
                    )
                ).all()
            )
            assert statuses == ("pending", "pending")

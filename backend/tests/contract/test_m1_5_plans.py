"""M1-5 plan creation, immutable adjustment, ownership, and confirmation contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.application.plan_experience import (
    PLAN_GENERATION_JOB_TYPE,
    PlanGenerationJobHandler,
    PlanGenerationOutcome,
    PlanGenerationResult,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.domain.collections import CollectionKind
from app.domain.places import TransportMode
from app.domain.plans import (
    ApprovalStatus,
    ExternalPlaceApprovalRequirement,
    PlanExecutionNotAllowedError,
)
from app.domain.plans.drafts import (
    RISK_SUMMARIES,
    SELECTION_REASON_SUMMARIES,
    PlanDraftOutcome,
    PlanDraftResult,
    PlanItem,
    PlanItemRole,
    PlanItemSource,
    PlanOption,
    PlanOptionRole,
    PlanRiskCode,
    PlanRouteLeg,
    PlanSelectionReasonCode,
)
from app.infrastructure.db.models import PlanModel
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import SqlAlchemyPlanRepository
from app.worker.service import JobWorker
from tests.contract.test_m0_2d_api import _client, _demo

COLLECTION_ID = "col_0123456789abcdef0123456789abcdef"


def _request(key: str) -> dict[str, object]:
    return {
        "idempotency_key": key,
        "start_at": "2026-07-29T10:00:00+08:00",
        "end_at": "2026-07-29T18:00:00+08:00",
        "area": {"districts": ["南山区"], "labels": ["海上世界"]},
        "pace": "balanced",
        "transport_modes": ["walking", "transit"],
        "include": ["咖啡"],
        "exclude": ["商场"],
        "collection_only": False,
    }


def _draft(*, title: str = "海边咖啡") -> PlanDraftResult:
    start = datetime(2026, 7, 29, 2, 15, tzinfo=UTC)
    risk_codes = (PlanRiskCode.PRICE_UNKNOWN,)
    item = PlanItem(
        role=PlanItemRole.CORE,
        title=title,
        kind=CollectionKind.PLACE,
        start_at=start,
        end_at=start + timedelta(hours=1),
        visit_duration_seconds=3600,
        inbound_route=PlanRouteLeg(
            to_collection_item_ids=(COLLECTION_ID,),
            duration_seconds=900,
            distance_meters=3200,
            transport_mode=TransportMode.TRANSIT,
        ),
        source=PlanItemSource(collection_item_ids=(COLLECTION_ID,)),
        selection_reason_code=PlanSelectionReasonCode.PRIMARY_STABLE_RANK,
        selection_reason=SELECTION_REASON_SUMMARIES[
            PlanSelectionReasonCode.PRIMARY_STABLE_RANK
        ],
        risk_codes=risk_codes,
        risks=tuple(RISK_SUMMARIES[code] for code in risk_codes),
    )
    return PlanDraftResult(
        outcome=PlanDraftOutcome.GENERATED,
        options=(
            PlanOption(
                role=PlanOptionRole.MAIN,
                items=(item,),
                end_buffer_seconds=1200,
                risk_codes=risk_codes,
                risks=tuple(RISK_SUMMARIES[code] for code in risk_codes),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_plan_api_preserves_constraints_versions_and_authoritative_state(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        created = await client.post("/api/v1/plans", json=_request("m15-create"))
        replay = await client.post("/api/v1/plans", json=_request("m15-create"))
        assert created.status_code == replay.status_code == 202
        assert replay.json()["plan_id"] == created.json()["plan_id"]
        assert replay.json()["replayed"] is True
        plan_id = created.json()["plan_id"]

        database = api.state.demo_database
        async with database.session_factory() as session:
            repository = SqlAlchemyPlanRepository(session)
            user_id = await session.scalar(
                select(PlanModel.user_id).where(PlanModel.id == plan_id)
            )
            assert user_id is not None
            await repository.complete_generation(
                user_id=user_id,
                plan_id=plan_id,
                draft=_draft(),
                now=datetime.now(UTC),
            )
            with pytest.raises(PlanExecutionNotAllowedError):
                await repository.require_confirmed_for_execution(
                    user_id=user_id,
                    plan_id=plan_id,
                )
            await session.commit()

        adjusted = await client.post(
            f"/api/v1/plans/{plan_id}/adjustments",
            json={
                "idempotency_key": "m15-adjust",
                "instruction": "节奏轻松一点",
            },
        )
        assert adjusted.status_code == 202
        adjusted_id = adjusted.json()["plan_id"]
        current = await client.get(f"/api/v1/plans/{adjusted_id}")
        assert current.status_code == 200
        body = current.json()
        assert body["version"] == 2
        assert body["parent_plan_id"] == plan_id
        assert body["constraints"]["pace"] == "relaxed"
        assert body["constraints"]["area_districts"] == ["南山区"]
        assert body["constraints"]["transport_modes"] == ["walking", "transit"]
        assert body["constraints"]["include"] == ["咖啡"]
        assert body["constraints"]["exclude"] == ["商场"]
        assert body["constraints"]["budget"] is None

        listed = await client.get("/api/v1/plans")
        assert [item["id"] for item in listed.json()["items"]] == [adjusted_id]


@pytest.mark.asyncio
async def test_confirmation_is_explicit_idempotent_current_version_only_and_owned(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        created = await client.post("/api/v1/plans", json=_request("m15-confirm"))
        plan_id = created.json()["plan_id"]

        database = api.state.demo_database
        async with database.session_factory() as session:
            repository = SqlAlchemyPlanRepository(session)
            user_id = await session.scalar(
                select(PlanModel.user_id).where(PlanModel.id == plan_id)
            )
            assert user_id is not None
            await repository.complete_generation(
                user_id=user_id,
                plan_id=plan_id,
                draft=_draft(),
                now=datetime.now(UTC),
            )
            await session.commit()

        confirmed = await client.post(
            f"/api/v1/plans/{plan_id}/confirm",
            json={"idempotency_key": "m15-confirm-action"},
        )
        replay = await client.post(
            f"/api/v1/plans/{plan_id}/confirm",
            json={"idempotency_key": "m15-confirm-action"},
        )
        assert confirmed.status_code == replay.status_code == 200
        assert confirmed.json()["plan"]["status"] == "confirmed"
        assert replay.json()["replayed"] is True

        async with database.session_factory() as session:
            executable = await SqlAlchemyPlanRepository(
                session
            ).require_confirmed_for_execution(
                user_id=user_id,
                plan_id=plan_id,
            )
            assert executable.status.value == "confirmed"

        other = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://test",
        )
        async with other:
            await _demo(other)
            assert (await other.get(f"/api/v1/plans/{plan_id}")).status_code == 404
            isolated_confirm = await other.post(
                f"/api/v1/plans/{plan_id}/confirm",
                json={"idempotency_key": "other-user-confirm"},
            )
            assert isolated_confirm.status_code == 404


@pytest.mark.asyncio
async def test_worker_approval_resume_and_repeat_decision_use_existing_state(
    test_settings,
) -> None:
    class ApprovalExecutor:
        async def execute(self, *, user_id, constraints, approval):
            del user_id, constraints
            if approval is None:
                return PlanGenerationResult(
                    outcome=PlanGenerationOutcome.WAITING_APPROVAL,
                    approval_requirement=ExternalPlaceApprovalRequirement(
                        approval_id="approval_" + "a" * 32
                    ),
                )
            assert approval.status is ApprovalStatus.APPROVED
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.DRAFT,
                draft=_draft(title="授权后的外部补充方案"),
            )

    async with _client(test_settings) as (api, client):
        await _demo(client)
        accepted = await client.post("/api/v1/plans", json=_request("m15-approval"))
        plan_id = accepted.json()["plan_id"]
        database = api.state.demo_database
        handler = PlanGenerationJobHandler(
            session_factory=database.session_factory,
            pricing=ConfiguredPricingPolicy.from_settings(test_settings),
            executor_factory=lambda session: ApprovalExecutor(),
        )
        worker = JobWorker(
            queue=PostgresJobQueue(database.session_factory),
            worker_id="worker_m15_approval",
            handlers={PLAN_GENERATION_JOB_TYPE: handler},
            poll_seconds=0.01,
        )
        assert await worker.run_once() is not None

        waiting = await client.get(f"/api/v1/plans/{plan_id}")
        assert waiting.json()["status"] == "waiting_approval"
        approval_id = waiting.json()["approval"]["id"]
        approved = await client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": "approved"},
        )
        assert approved.status_code == 202
        assert await worker.run_once() is not None

        ready = await client.get(f"/api/v1/plans/{plan_id}")
        assert ready.json()["status"] == "draft"
        assert (
            ready.json()["draft"]["options"][0]["items"][0]["title"]
            == "授权后的外部补充方案"
        )
        repeated = await client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": "approved"},
        )
        assert repeated.status_code == 202
        assert repeated.json()["replayed"] is True

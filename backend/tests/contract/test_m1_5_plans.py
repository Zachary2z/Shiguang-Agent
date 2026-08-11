"""M1-5 plan creation, immutable adjustment, ownership, and confirmation contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
import pytest
from sqlalchemy import func, select

from app.application.plan_adjustments import PlanAdjustmentParser
from app.application.plan_experience import (
    PLAN_GENERATION_JOB_TYPE,
    PlanExperienceService,
    PlanGenerationJobHandler,
    PlanGenerationOutcome,
    PlanGenerationResult,
)
from app.application.pricing import ConfiguredPricingPolicy
from app.domain.collections import CollectionKind, PlanCity
from app.domain.places import TransportMode
from app.domain.plans import (
    ActivityArea,
    ApprovalStatus,
    ExternalPlaceApprovalRequirement,
    PlanConstraints,
    PlanExecutionNotAllowedError,
    PlanPace,
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
from app.infrastructure.db.models import (
    AgentRunModel,
    PlanModel,
    ScheduledJobModel,
    UserModel,
)
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import SqlAlchemyPlanRepository
from app.providers.jobs import JobQueue
from app.worker.service import JobWorker
from nanobot_core.providers import (
    ProviderError,
    ProviderErrorCode,
    StructuredOutputMode,
)
from tests.contract.test_m0_2d_api import _client, _demo
from tests.core.fakes import FakeProvider, fake_response

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


def _draft(
    *,
    title: str = "海边咖啡",
    start_at: datetime | None = None,
) -> PlanDraftResult:
    start = start_at or datetime(2026, 7, 29, 2, 15, tzinfo=UTC)
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
        selection_reason_code=PlanSelectionReasonCode.MODEL_PROPOSAL,
        selection_reason=SELECTION_REASON_SUMMARIES[
            PlanSelectionReasonCode.MODEL_PROPOSAL
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


def _constraints() -> PlanConstraints:
    created_at = datetime(2026, 7, 28, 1, tzinfo=UTC)
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=datetime(2026, 7, 29, 2, tzinfo=UTC),
        end_at=datetime(2026, 7, 29, 10, tzinfo=UTC),
        area=ActivityArea(districts=("南山区",), labels=("海上世界",)),
        pace=PlanPace.BALANCED,
        transport_modes=(TransportMode.TRANSIT,),
        created_at=created_at,
        expires_at=created_at + timedelta(days=2),
    )


class _FailingQueue:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    async def create(self, request):
        del request
        raise self.error

    async def get_by_trace(self, *, user_id, trace_id):
        del user_id, trace_id
        return None


@pytest.mark.asyncio
async def test_direct_plan_lifetime_uses_the_same_future_end_rule(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        await _demo(client)
        start_at = datetime.now(UTC) + timedelta(days=5)
        end_at = start_at + timedelta(hours=4)
        payload = _request("m15-future-lifetime")
        payload.update(
            start_at=start_at.isoformat(),
            end_at=end_at.isoformat(),
        )

        created = await client.post("/api/v1/plans", json=payload)

        assert created.status_code == 202
        async with api.state.demo_database.session() as session:
            row = await session.get(PlanModel, created.json()["plan_id"])
            assert row is not None
            expires_at = datetime.fromisoformat(row.constraints_json["expires_at"])
            assert expires_at == end_at + timedelta(hours=1)
            assert expires_at > start_at


@pytest.mark.asyncio
async def test_plan_api_preserves_constraints_versions_and_authoritative_state(
    test_settings,
) -> None:
    worker_origins: list[object] = []

    class DraftExecutor:
        async def execute(self, *, user_id, constraints, approval):
            del user_id, approval
            worker_origins.append(constraints.origin)
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.DRAFT,
                draft=_draft(),
            )

    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        provider = FakeProvider(
            [fake_response(content='{"pace":"relaxed"}')]
        )
        api.state.text_provider = provider
        await _demo(client)
        create_payload = _request("m15-create")
        create_payload["origin"] = {
            "latitude": 22.555,
            "longitude": 114.055,
            "coordinate_system": "gcj_02",
        }
        created = await client.post("/api/v1/plans", json=create_payload)
        replay = await client.post("/api/v1/plans", json=create_payload)
        assert created.status_code == replay.status_code == 202
        assert replay.json()["plan_id"] == created.json()["plan_id"]
        assert replay.json()["replayed"] is True
        plan_id = created.json()["plan_id"]

        database = api.state.demo_database
        handler = PlanGenerationJobHandler(
            session_factory=database.session_factory,
            pricing=ConfiguredPricingPolicy.from_settings(test_settings),
            executor_factory=lambda session: DraftExecutor(),
            adjustment_parser=PlanAdjustmentParser(
                provider,
                structured_output_mode=StructuredOutputMode.JSON_OBJECT,
            ),
        )
        worker = JobWorker(
            queue=PostgresJobQueue(database.session_factory),
            worker_id="worker_m15_versions",
            handlers={PLAN_GENERATION_JOB_TYPE: handler},
            poll_seconds=0.01,
        )
        assert await worker.run_once() is not None
        assert worker_origins[-1] is not None
        async with database.session_factory() as session:
            repository = SqlAlchemyPlanRepository(session)
            user_id = await session.scalar(
                select(PlanModel.user_id).where(PlanModel.id == plan_id)
            )
            assert user_id is not None
            persisted = await repository.require(user_id=user_id, plan_id=plan_id)
            assert persisted.constraints.origin is not None
            assert persisted.constraints.origin.latitude == 22.555
            with pytest.raises(PlanExecutionNotAllowedError):
                await repository.require_confirmed_for_execution(
                    user_id=user_id,
                    plan_id=plan_id,
                )

        adjusted = await client.post(
            f"/api/v1/plans/{plan_id}/adjustments",
            json={
                "idempotency_key": "m15-adjust",
                "instruction": "节奏轻松一点",
            },
        )
        assert adjusted.status_code == 202
        assert adjusted.json()["base_plan_id"] == plan_id
        assert "plan_id" not in adjusted.json()
        assert len(provider.calls) == 0
        assert await worker.run_once() is not None
        assert worker_origins[-1] == worker_origins[0]
        assert len(provider.calls) == 1
        listed = await client.get("/api/v1/plans")
        adjusted_id = listed.json()["items"][0]["id"]
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
        assert body["constraints"]["has_exact_origin"] is True
        assert "latitude" not in current.text and "longitude" not in current.text

        assert [item["id"] for item in listed.json()["items"]] == [adjusted_id]
        async with database.session_factory() as session:
            run = await session.scalar(
                select(AgentRunModel).where(
                    AgentRunModel.trace_id == adjusted.json()["trace_id"]
                )
            )
            assert run is not None
            assert run.total_tokens == 5
            assert run.duration_ms is not None
            assert run.model_calls_json[0]["model_name"] == "fixture-model"
            assert run.model_calls_json[0]["latency_ms"] == 4
            assert run.model_calls_json[0]["finish_reason"] == "stop"
            adjusted_row = await session.get(PlanModel, adjusted_id)
            assert adjusted_row is not None
            assert adjusted_row.constraints_json["origin"]["latitude"] == 22.555


@pytest.mark.asyncio
async def test_different_origins_have_different_plan_request_identity(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        await _demo(client)
        first = _request("origin-fingerprint")
        first["origin"] = {
            "latitude": 22.555,
            "longitude": 114.055,
            "coordinate_system": "gcj_02",
        }
        second = _request("origin-fingerprint")
        second["origin"] = {
            "latitude": 22.556,
            "longitude": 114.055,
            "coordinate_system": "gcj_02",
        }

        created = await client.post("/api/v1/plans", json=first)
        conflict = await client.post("/api/v1/plans", json=second)

        assert created.status_code == 202
        assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_location_adjustment_is_recoverable_without_creating_a_version(
    test_settings,
) -> None:
    class DraftExecutor:
        async def execute(self, *, user_id, constraints, approval):
            del user_id, constraints, approval
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.DRAFT,
                draft=_draft(),
            )

    provider = FakeProvider([fake_response(content="{}")])
    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        api.state.text_provider = provider
        await _demo(client)
        created = await client.post("/api/v1/plans", json=_request("location-base"))
        plan_id = created.json()["plan_id"]
        handler = PlanGenerationJobHandler(
            session_factory=api.state.demo_database.session_factory,
            pricing=ConfiguredPricingPolicy.from_settings(test_settings),
            executor_factory=lambda session: DraftExecutor(),
            adjustment_parser=PlanAdjustmentParser(
                provider,
                structured_output_mode=StructuredOutputMode.JSON_OBJECT,
            ),
        )
        worker = JobWorker(
            queue=PostgresJobQueue(api.state.demo_database.session_factory),
            worker_id="worker_m15_unsupported",
            handlers={PLAN_GENERATION_JOB_TYPE: handler},
            poll_seconds=0.01,
        )
        assert await worker.run_once() is not None

        unsupported = await client.post(
            f"/api/v1/plans/{plan_id}/adjustments",
            json={
                "idempotency_key": "location-unsupported",
                "instruction": "把地点换成广州塔",
            },
        )
        assert unsupported.status_code == 202
        assert len(provider.calls) == 0
        terminal = await worker.run_once()
        assert terminal is not None
        assert terminal.status.value == "succeeded"
        async with api.state.demo_database.session_factory() as session:
            plan_count = int(await session.scalar(select(func.count(PlanModel.id))) or 0)
            job_count = int(
                await session.scalar(select(func.count(ScheduledJobModel.id))) or 0
            )
            run = await session.scalar(
                select(AgentRunModel).where(
                    AgentRunModel.trace_id == unsupported.json()["trace_id"]
                )
            )

    assert unsupported.json()["base_plan_id"] == plan_id
    assert plan_count == 1
    assert job_count == 2
    assert len(provider.calls) == 1
    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "PLAN_ADJUSTMENT_UNSUPPORTED"
    assert len(run.model_calls_json) == 1
    assert "location_intent" not in str(provider.calls[0].response_format)


@pytest.mark.asyncio
async def test_adjustment_concurrent_and_serial_replay_runs_model_and_version_once(
    test_settings,
) -> None:
    class DraftExecutor:
        async def execute(self, *, user_id, constraints, approval):
            del user_id, constraints, approval
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.DRAFT,
                draft=_draft(),
            )

    provider = FakeProvider([fake_response(content='{"pace":"relaxed"}')])
    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        api.state.text_provider = provider
        await _demo(client)
        created = await client.post("/api/v1/plans", json=_request("replay-base"))
        plan_id = created.json()["plan_id"]
        database = api.state.demo_database
        handler = PlanGenerationJobHandler(
            session_factory=database.session_factory,
            pricing=ConfiguredPricingPolicy.from_settings(test_settings),
            executor_factory=lambda session: DraftExecutor(),
            adjustment_parser=PlanAdjustmentParser(
                provider,
                structured_output_mode=StructuredOutputMode.JSON_OBJECT,
            ),
        )
        worker = JobWorker(
            queue=PostgresJobQueue(database.session_factory),
            worker_id="worker_m15_replay",
            handlers={PLAN_GENERATION_JOB_TYPE: handler},
            poll_seconds=0.01,
        )
        assert await worker.run_once() is not None

        request = {
            "idempotency_key": "same-adjustment",
            "instruction": "节奏轻松一点",
        }
        first, concurrent_replay = await asyncio.gather(
            client.post(f"/api/v1/plans/{plan_id}/adjustments", json=request),
            client.post(f"/api/v1/plans/{plan_id}/adjustments", json=request),
        )
        assert first.status_code == concurrent_replay.status_code == 202
        assert first.json()["trace_id"] == concurrent_replay.json()["trace_id"]
        assert len(provider.calls) == 0
        async with database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 1
            assert (
                await session.scalar(select(func.count()).select_from(AgentRunModel))
                == 2
            )
            assert (
                await session.scalar(select(func.count()).select_from(ScheduledJobModel))
                == 2
            )

        assert await worker.run_once() is not None
        assert await worker.run_once() is None
        assert len(provider.calls) == 1
        serial_replay = await client.post(
            f"/api/v1/plans/{plan_id}/adjustments",
            json=request,
        )
        assert serial_replay.status_code == 202
        assert serial_replay.json()["trace_id"] == first.json()["trace_id"]
        assert serial_replay.json()["replayed"] is True
        conflict = await client.post(
            f"/api/v1/plans/{plan_id}/adjustments",
            json={
                "idempotency_key": "same-adjustment",
                "instruction": "改成紧凑节奏",
            },
        )
        assert conflict.status_code == 409
        stale = await client.post(
            f"/api/v1/plans/{plan_id}/adjustments",
            json={
                "idempotency_key": "stale-adjustment",
                "instruction": "改成紧凑节奏",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error_code"] == "PLAN_VERSION_CONFLICT"
        assert len(provider.calls) == 1
        async with database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 2
            assert (
                await session.scalar(select(func.count()).select_from(AgentRunModel))
                == 2
            )
            assert (
                await session.scalar(select(func.count()).select_from(ScheduledJobModel))
                == 2
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_outcome", "expected_run_status", "expected_error", "cancelled"),
    [
        (
            ProviderError(code=ProviderErrorCode.TIMEOUT),
            "failed",
            "PROVIDER_TIMEOUT",
            False,
        ),
        (
            ProviderError(code=ProviderErrorCode.AUTHENTICATION_FAILED),
            "failed",
            "PROVIDER_AUTHENTICATION_FAILED",
            False,
        ),
        (
            ProviderError(code=ProviderErrorCode.RATE_LIMITED),
            "failed",
            "PROVIDER_RATE_LIMITED",
            False,
        ),
        (
            fake_response(content="not-json"),
            "failed",
            "PLAN_ADJUSTMENT_NOT_UNDERSTOOD",
            False,
        ),
        (asyncio.CancelledError(), "cancelled", "RUN_CANCELLED", True),
    ],
)
async def test_adjustment_worker_failures_never_create_a_version_or_live_job(
    test_settings,
    provider_outcome,
    expected_run_status,
    expected_error,
    cancelled,
) -> None:
    class DraftExecutor:
        async def execute(self, *, user_id, constraints, approval):
            del user_id, constraints, approval
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.DRAFT,
                draft=_draft(),
            )

    provider = FakeProvider([provider_outcome])
    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        api.state.text_provider = provider
        await _demo(client)
        created = await client.post("/api/v1/plans", json=_request("failure-base"))
        plan_id = created.json()["plan_id"]
        database = api.state.demo_database
        handler = PlanGenerationJobHandler(
            session_factory=database.session_factory,
            pricing=ConfiguredPricingPolicy.from_settings(test_settings),
            executor_factory=lambda session: DraftExecutor(),
            adjustment_parser=PlanAdjustmentParser(
                provider,
                structured_output_mode=StructuredOutputMode.JSON_OBJECT,
            ),
        )
        worker = JobWorker(
            queue=PostgresJobQueue(database.session_factory),
            worker_id="worker_m15_failure",
            handlers={PLAN_GENERATION_JOB_TYPE: handler},
            poll_seconds=0.01,
        )
        assert await worker.run_once() is not None
        accepted = await client.post(
            f"/api/v1/plans/{plan_id}/adjustments",
            json={
                "idempotency_key": "failing-adjustment",
                "instruction": "节奏轻松一点",
            },
        )
        assert accepted.status_code == 202
        if cancelled:
            with pytest.raises(asyncio.CancelledError):
                await worker.run_once()
        else:
            assert await worker.run_once() is not None
        async with database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 1
            run = await session.scalar(
                select(AgentRunModel).where(
                    AgentRunModel.trace_id == accepted.json()["trace_id"]
                )
            )
            job = await session.scalar(
                select(ScheduledJobModel).where(
                    ScheduledJobModel.trace_id == accepted.json()["trace_id"]
                )
            )
            assert run is not None
            assert job is not None
            assert run.status == expected_run_status
            assert run.error_code == expected_error
            assert job.status in {"failed", "succeeded", "cancelled"}
            assert job.status != "queued"
            assert job.status != "running"


@pytest.mark.asyncio
async def test_confirmation_is_explicit_idempotent_current_version_only_and_owned(
    test_settings,
) -> None:
    reference_now = datetime.now(UTC)
    plan_start = reference_now + timedelta(days=1)
    plan_end = plan_start + timedelta(hours=8)
    request = _request("m15-confirm")
    request["start_at"] = plan_start.isoformat()
    request["end_at"] = plan_end.isoformat()

    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        await _demo(client)
        created = await client.post("/api/v1/plans", json=request)
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
                draft=_draft(start_at=plan_start + timedelta(minutes=15)),
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
@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_error"),
    [
        ("approved", "draft", None),
        ("rejected", "failed", "ADD_COLLECTIONS"),
    ],
)
async def test_worker_approval_decisions_resume_and_repeat_existing_state(
    test_settings,
    decision,
    expected_status,
    expected_error,
) -> None:
    original_request = "周六想去海上世界喝咖啡，再沿海边散步"
    observed_requests: list[str | None] = []

    class ApprovalExecutor:
        async def execute(self, *, user_id, constraints, approval):
            del user_id
            observed_requests.append(constraints.original_request)
            if approval is None:
                return PlanGenerationResult(
                    outcome=PlanGenerationOutcome.WAITING_APPROVAL,
                    approval_requirement=ExternalPlaceApprovalRequirement(
                        approval_id="approval_" + "a" * 32
                    ),
                )
            if approval.status is ApprovalStatus.REJECTED:
                return PlanGenerationResult(
                    outcome=PlanGenerationOutcome.FAILED,
                    error_code="ADD_COLLECTIONS",
                )
            assert approval.status is ApprovalStatus.APPROVED
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.DRAFT,
                draft=_draft(title="授权后的外部补充方案"),
            )

    async with _client(test_settings) as (api, client):
        api.state.map_provider = object()
        await _demo(client)
        accepted = await client.post("/api/v1/plans", json=_request("m15-approval"))
        plan_id = accepted.json()["plan_id"]
        database = api.state.demo_database
        async with database.session() as session:
            row = await session.get(PlanModel, plan_id)
            assert row is not None
            row.constraints_json = {
                **row.constraints_json,
                "original_request": original_request,
            }
            await session.commit()
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
        decided = await client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": decision},
        )
        assert decided.status_code == 202
        assert await worker.run_once() is not None

        ready = await client.get(f"/api/v1/plans/{plan_id}")
        assert ready.json()["status"] == expected_status
        assert ready.json()["error_code"] == expected_error
        if decision == "approved":
            assert (
                ready.json()["draft"]["options"][0]["items"][0]["title"]
                == "授权后的外部补充方案"
            )
        else:
            assert ready.json()["draft"] is None
        repeated = await client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": decision},
        )
        assert repeated.status_code == 202
        assert repeated.json()["replayed"] is True
        assert observed_requests == [original_request, original_request]


@pytest.mark.asyncio
async def test_queue_failure_compensates_plan_and_run_then_key_is_reusable(
    test_settings,
    monkeypatch,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        database = api.state.demo_database
        async with database.session_factory() as session:
            user_id = await session.scalar(select(UserModel.id))
        assert user_id is not None

        original = SqlAlchemyPlanRepository.delete_unqueued_generation
        attempts = 0

        async def fail_first_cleanup(self, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient cleanup failure")
            return await original(self, **kwargs)

        monkeypatch.setattr(
            SqlAlchemyPlanRepository,
            "delete_unqueued_generation",
            fail_first_cleanup,
        )
        async with database.session_factory() as session:
            service = PlanExperienceService(
                session=session,
                session_factory=database.session_factory,
                pricing=ConfiguredPricingPolicy.from_settings(test_settings),
                queue=cast(JobQueue, _FailingQueue(RuntimeError("queue failed"))),
            )
            with pytest.raises(RuntimeError, match="queue failed"):
                await service.create(
                    user_id=user_id,
                    constraints=_constraints(),
                    client_idempotency_key="queue-reusable",
                )

        async with database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 0
            assert (
                await session.scalar(select(func.count()).select_from(AgentRunModel))
                == 0
            )
            assert (
                await session.scalar(select(func.count()).select_from(ScheduledJobModel))
                == 0
            )

        async with database.session_factory() as session:
            service = PlanExperienceService(
                session=session,
                session_factory=database.session_factory,
                pricing=ConfiguredPricingPolicy.from_settings(test_settings),
            )
            first = await service.create(
                user_id=user_id,
                constraints=_constraints(),
                client_idempotency_key="queue-reusable",
            )
            replay = await service.create(
                user_id=user_id,
                constraints=_constraints(),
                client_idempotency_key="queue-reusable",
            )
            second_root = await service.create(
                user_id=user_id,
                constraints=_constraints(),
                client_idempotency_key="queue-other",
            )
        assert replay.replayed is True
        assert replay.plan.id == first.plan.id
        assert second_root.plan.root_plan_id != first.plan.root_plan_id
        async with database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 2
            assert (
                await session.scalar(select(func.count()).select_from(AgentRunModel))
                == 2
            )
            assert (
                await session.scalar(select(func.count()).select_from(ScheduledJobModel))
                == 2
            )


@pytest.mark.asyncio
async def test_queue_cancellation_leaves_no_generating_plan_or_run(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        database = api.state.demo_database
        async with database.session_factory() as session:
            user_id = await session.scalar(select(UserModel.id))
        assert user_id is not None
        async with database.session_factory() as session:
            service = PlanExperienceService(
                session=session,
                session_factory=database.session_factory,
                pricing=ConfiguredPricingPolicy.from_settings(test_settings),
                queue=cast(JobQueue, _FailingQueue(asyncio.CancelledError())),
            )
            with pytest.raises(asyncio.CancelledError):
                await service.create(
                    user_id=user_id,
                    constraints=_constraints(),
                    client_idempotency_key="queue-cancelled",
                )
        async with database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 0
            assert (
                await session.scalar(select(func.count()).select_from(AgentRunModel))
                == 0
            )


@pytest.mark.asyncio
async def test_missing_map_configuration_rejects_before_persistence(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        response = await client.post(
            "/api/v1/plans",
            json=_request("missing-map"),
        )
        assert response.status_code == 503
        assert response.json()["error_code"] == "PLAN_PROVIDER_NOT_CONFIGURED"
        async with api.state.demo_database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(PlanModel)) == 0
            assert (
                await session.scalar(select(func.count()).select_from(AgentRunModel))
                == 0
            )
            assert (
                await session.scalar(select(func.count()).select_from(ScheduledJobModel))
                == 0
            )

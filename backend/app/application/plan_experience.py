"""M1-5 orchestration over the existing planner, JobQueue, Worker, and SSE."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import timedelta
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.external_place_supplement import ExternalPlaceSupplementService
from app.application.memories import MemoryPlanningService
from app.application.place_matching import PlaceMatchingService
from app.application.plan_adjustments import (
    PlanAdjustmentNotUnderstoodError,
    PlanAdjustmentParser,
    PlanAdjustmentUnsupportedError,
    apply_plan_adjustment,
)
from app.application.plan_drafts import PlanDraftService
from app.application.pricing import PricingPolicy
from app.application.run_tracking import (
    AgentRunService,
    ApplicationRunObserver,
    ApplicationToolOutcome,
)
from app.application.structured_collection_retrieval import (
    StructuredCollectionRetrievalService,
)
from app.domain.identifiers import generate_approval_id, generate_plan_id, generate_trace_id
from app.domain.jobs import JobConflictError, JobCreate, JobResultSummary, ScheduledJob
from app.domain.places import PlaceMatchingPolicy
from app.domain.plans import (
    ApprovalAction,
    ApprovalStatus,
    ExternalApprovalDecision,
    ExternalPlaceApprovalDecision,
    ExternalPlaceApprovalRequirement,
    ExternalSupplementOutcome,
    PlanApproval,
    PlanConstraints,
    PlanDraftFactSnapshot,
    PlanDraftResult,
    PlanningFactSnapshot,
    PlanOperation,
    PlanStatus,
    PlanVersion,
    RequiredPlanGap,
)
from app.domain.plans.contracts import PlanContract
from app.domain.runs import AgentRunCreate, AgentRunStatus
from app.domain.time import utc_now
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import (
    AgentRunRepository,
    SqlAlchemyCollectionRepository,
    SqlAlchemyPlanRepository,
    plan_request_fingerprint,
)
from app.providers.jobs import JobQueue
from app.providers.map import MapProvider

PLAN_GENERATION_JOB_TYPE = "plan.generate"
_APPROVAL_TTL = timedelta(minutes=15)


class PlanGenerationFacts(PlanContract):
    retrieval: PlanningFactSnapshot
    draft: PlanDraftFactSnapshot
    required_gap: RequiredPlanGap | None = None


class PlanFactResolver(Protocol):
    async def resolve(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
    ) -> PlanGenerationFacts: ...


class PlanGenerationOutcome(StrEnum):
    DRAFT = "draft"
    WAITING_APPROVAL = "waiting_approval"
    FAILED = "failed"


class PlanGenerationResult(PlanContract):
    outcome: PlanGenerationOutcome
    draft: PlanDraftResult | None = None
    approval_requirement: ExternalPlaceApprovalRequirement | None = None
    error_code: str | None = None
    memory_usages: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self) -> PlanGenerationResult:
        if self.outcome is PlanGenerationOutcome.DRAFT:
            if self.draft is None or self.approval_requirement is not None or self.error_code:
                raise ValueError("draft outcomes require only a draft")
        elif self.outcome is PlanGenerationOutcome.WAITING_APPROVAL:
            if self.approval_requirement is None or self.draft is not None or self.error_code:
                raise ValueError("approval outcomes require only a requirement")
        elif self.draft is not None or self.approval_requirement is not None:
            raise ValueError("failed outcomes cannot carry a draft or approval")
        return self


class PlanDraftExecutor(Protocol):
    async def execute(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
        approval: PlanApproval | None,
    ) -> PlanGenerationResult: ...


class ExistingPlanServicesExecutor:
    """Compose the existing M0-5 services; it owns no planning rules."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        map_provider: MapProvider,
        matching_policy: PlaceMatchingPolicy,
        facts: PlanFactResolver,
    ) -> None:
        self._session = session
        self._map_provider = map_provider
        self._matching = PlaceMatchingService(
            map_provider=map_provider,
            policy=matching_policy,
        )
        self._facts = facts

    async def execute(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
        approval: PlanApproval | None,
    ) -> PlanGenerationResult:
        now = utc_now()
        memory_service = MemoryPlanningService(self._session)
        memories = await memory_service.effective(user_id=user_id, at=now)
        memory_usages: dict[str, str] = {}
        facts = await self._facts.resolve(
            user_id=user_id, constraints=constraints
        )
        collections = await StructuredCollectionRetrievalService(
            repository=SqlAlchemyCollectionRepository(self._session),
        ).retrieve(
            user_id=user_id,
            constraints=constraints,
            facts=facts.retrieval,
            now=now,
            memories=memories,
        )
        decision: ExternalPlaceApprovalDecision | None = None
        if approval is not None and facts.required_gap is not None:
            if approval.status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
                assert approval.external_requirement_id is not None
                decision = ExternalPlaceApprovalDecision(
                    approval_id=approval.external_requirement_id,
                    decision=(
                        ExternalApprovalDecision.APPROVED
                        if approval.status is ApprovalStatus.APPROVED
                        else ExternalApprovalDecision.REJECTED
                    ),
                )
        result = await ExternalPlaceSupplementService(
            map_provider=self._map_provider,
            place_matching=self._matching,
            plan_drafts=PlanDraftService(),
        ).generate(
            constraints=constraints,
            collections=collections,
            facts=facts.draft,
            required_gap=facts.required_gap,
            approval_decision=decision,
            queried_at=utc_now(),
        )
        if result.outcome is ExternalSupplementOutcome.WAITING_APPROVAL:
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.WAITING_APPROVAL,
                approval_requirement=result.approval,
            )
        if result.draft is not None:
            selected_ids = {
                collection_id
                for item in result.draft.options[0].items
                for collection_id in item.source.collection_item_ids
            }
            for decision_item in collections.included:
                if not selected_ids.intersection(decision_item.collection_item_ids):
                    continue
                for memory_id in decision_item.applied_memory_ids:
                    memory_usages[memory_id] = (
                        f"该偏好影响了计划地点排序：{decision_item.title}"
                    )
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.DRAFT,
                draft=result.draft,
                memory_usages=memory_usages,
            )
        return PlanGenerationResult(
            outcome=PlanGenerationOutcome.FAILED,
            error_code=(
                "PLAN_GENERATION_FAILED"
                if result.recovery_code is None
                else result.recovery_code.value
            ),
        )


class PlanJobPayload(PlanContract):
    operation: Literal["generate"] = "generate"
    plan_id: str


class PlanAdjustmentJobPayload(PlanContract):
    operation: Literal["adjust"] = "adjust"
    base_plan_id: str
    instruction: str


class PlanSubmission(PlanContract):
    plan: PlanVersion
    replayed: bool


class PlanAdjustmentSubmission(PlanContract):
    base_plan_id: str
    trace_id: str
    replayed: bool


class PlanApprovalSubmission(PlanContract):
    approval: PlanApproval
    trace_id: str | None = None
    replayed: bool


def scoped_plan_key(*, user_id: str, client_key: str) -> str:
    digest = hashlib.sha256(f"{user_id}\0{client_key}".encode()).hexdigest()
    return f"plan.{digest}"


class PlanExperienceService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        pricing: PricingPolicy,
        queue: JobQueue | None = None,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
        self._pricing = pricing
        self._queue = queue or PostgresJobQueue(session_factory)
        self._plans = SqlAlchemyPlanRepository(session)

    async def create(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
        client_idempotency_key: str,
    ) -> PlanSubmission:
        key = scoped_plan_key(user_id=user_id, client_key=client_idempotency_key)
        fingerprint = plan_request_fingerprint(
            {
                "operation": "generate",
                "constraints": constraints.model_dump(
                    mode="json",
                    exclude={"created_at", "expires_at"},
                ),
            }
        )
        existing = await self._plans.find_by_idempotency_key(
            user_id=user_id,
            idempotency_key=key,
            request_fingerprint=fingerprint,
        )
        if existing is not None:
            await self._ensure_generating_job(existing)
            return PlanSubmission(plan=existing, replayed=True)
        plan_id = generate_plan_id()
        timestamp = utc_now()
        plan = PlanVersion(
            id=plan_id,
            root_plan_id=plan_id,
            user_id=user_id,
            version=1,
            operation=PlanOperation.GENERATE,
            status=PlanStatus.GENERATING,
            constraints=constraints,
            trace_id=generate_trace_id(),
            idempotency_key=key,
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            await self._plans.add(plan, request_fingerprint=fingerprint)
        except IntegrityError:
            await self._session.rollback()
            replay = await self._plans.find_by_idempotency_key(
                user_id=user_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
            )
            if replay is None:
                raise
            await self._ensure_generating_job(replay)
            return PlanSubmission(plan=replay, replayed=True)
        await self._queue_plan(plan)
        return PlanSubmission(plan=plan, replayed=False)

    async def adjust(
        self,
        *,
        user_id: str,
        base_plan_id: str,
        instruction: str,
        client_idempotency_key: str,
    ) -> PlanAdjustmentSubmission:
        key = scoped_plan_key(user_id=user_id, client_key=client_idempotency_key)
        base = await self._plans.require(user_id=user_id, plan_id=base_plan_id)
        trace_id = f"trc_{hashlib.sha256(key.encode()).hexdigest()[:32]}"
        payload = PlanAdjustmentJobPayload(
            base_plan_id=base_plan_id,
            instruction=instruction,
        )
        request = JobCreate(
            user_id=user_id,
            idempotency_key=key,
            job_type=PLAN_GENERATION_JOB_TYPE,
            payload=payload.model_dump(mode="json"),
            run_at=base.created_at,
            trace_id=trace_id,
            max_attempts=1,
        )
        existing_job = await self._queue.get_by_trace(
            user_id=user_id,
            trace_id=trace_id,
        )
        if existing_job is not None:
            replay = await self._queue.create(request)
            return PlanAdjustmentSubmission(
                base_plan_id=base_plan_id,
                trace_id=trace_id,
                replayed=replay.replayed,
            )
        versions = await self._plans.list_versions(
            user_id=user_id,
            root_plan_id=base.root_plan_id,
        )
        if not versions or versions[-1].id != base_plan_id:
            from app.domain.plans import PlanVersionConflictError

            raise PlanVersionConflictError
        await AgentRunService(
            session=self._session,
            runner=None,
            pricing=self._pricing,
        ).queue_application(
            AgentRunCreate(
                trace_id=trace_id,
                user_id=user_id,
                intent=PlanOperation.ADJUST.value,
                workflow="plan.experience",
            )
        )
        try:
            job = await self._queue.create(request)
        except BaseException as error:
            existing_job = await asyncio.shield(
                self._queue.get_by_trace(
                    user_id=user_id,
                    trace_id=trace_id,
                )
            )
            if existing_job is None:
                await asyncio.shield(
                    self._compensate_unqueued_run(
                        user_id=user_id,
                        trace_id=trace_id,
                    )
                )
            if (
                isinstance(error, (asyncio.CancelledError, JobConflictError))
                or existing_job is None
            ):
                raise
            job = existing_job
        if job.trace_id != trace_id:
            raise RuntimeError("plan adjustment job trace does not match its queued run")
        return PlanAdjustmentSubmission(
            base_plan_id=base_plan_id,
            trace_id=trace_id,
            replayed=job.replayed,
        )

    async def _compensate_unqueued_run(
        self,
        *,
        user_id: str,
        trace_id: str,
    ) -> None:
        async with self._session_factory() as cleanup:
            await AgentRunRepository(cleanup).delete_queued_by_trace_id(
                user_id=user_id,
                trace_id=trace_id,
            )
            await cleanup.commit()
        await self._session.rollback()

    async def confirm(
        self,
        *,
        user_id: str,
        plan_id: str,
        client_idempotency_key: str,
    ) -> tuple[PlanVersion, bool]:
        key = scoped_plan_key(user_id=user_id, client_key=client_idempotency_key)
        fingerprint = plan_request_fingerprint(
            {"operation": "confirm", "plan_id": plan_id}
        )
        result = await self._plans.confirm(
            user_id=user_id,
            plan_id=plan_id,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            now=utc_now(),
        )
        await self._session.commit()
        return result

    async def decide_external_approval(
        self,
        *,
        user_id: str,
        approval_id: str,
        approved: bool,
    ) -> PlanApprovalSubmission:
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        existing = await self._plans.decide_external_approval(
            user_id=user_id,
            approval_id=approval_id,
            decision=status,
            now=utc_now(),
        )
        if existing.status is ApprovalStatus.EXPIRED:
            await self._session.commit()
            return PlanApprovalSubmission(
                approval=existing,
                trace_id=None,
                replayed=False,
            )
        key = scoped_plan_key(
            user_id=user_id,
            client_key=f"approval:{approval_id}:{status.value}",
        )
        trace_id = f"trc_{hashlib.sha256(key.encode()).hexdigest()[:32]}"
        run = await AgentRunService(
            session=self._session,
            runner=None,
            pricing=self._pricing,
        ).queue_application(
            AgentRunCreate(
                trace_id=trace_id,
                user_id=user_id,
                intent="external_approval",
                workflow="plan.experience",
            )
        )
        job = await self._queue.create(
            JobCreate(
                user_id=user_id,
                job_type=PLAN_GENERATION_JOB_TYPE,
                payload=PlanJobPayload(
                    plan_id=existing.target_plan_id
                ).model_dump(mode="json"),
                run_at=existing.decided_at or existing.created_at,
                idempotency_key=key,
                trace_id=run.trace_id,
                max_attempts=1,
            )
        )
        return PlanApprovalSubmission(
            approval=existing,
            trace_id=job.trace_id,
            replayed=job.replayed,
        )

    async def _queue_plan(self, plan: PlanVersion) -> None:
        await AgentRunService(
            session=self._session,
            runner=None,
            pricing=self._pricing,
        ).queue_application(
            AgentRunCreate(
                trace_id=plan.trace_id,
                user_id=plan.user_id,
                intent=plan.operation.value,
                workflow="plan.experience",
            )
        )
        try:
            job = await self._queue.create(
                JobCreate(
                    user_id=plan.user_id,
                    job_type=PLAN_GENERATION_JOB_TYPE,
                    payload=PlanJobPayload(plan_id=plan.id).model_dump(mode="json"),
                    run_at=plan.created_at,
                    idempotency_key=plan.idempotency_key,
                    trace_id=plan.trace_id,
                    max_attempts=1,
                )
            )
        except BaseException as error:
            existing = await asyncio.shield(
                self._queue.get_by_trace(
                    user_id=plan.user_id,
                    trace_id=plan.trace_id,
                )
            )
            if existing is None:
                await asyncio.shield(self._compensate_unqueued_plan(plan))
            if isinstance(error, asyncio.CancelledError) or existing is None:
                raise
            job = existing
        if job.trace_id != plan.trace_id:
            raise RuntimeError("plan job trace does not match its queued run")

    async def _ensure_generating_job(self, plan: PlanVersion) -> None:
        if plan.status is not PlanStatus.GENERATING:
            return
        job = await self._queue.get_by_trace(
            user_id=plan.user_id,
            trace_id=plan.trace_id,
        )
        if job is None:
            await self._queue_plan(plan)

    async def _compensate_unqueued_plan(self, plan: PlanVersion) -> None:
        last_error: BaseException | None = None
        for _attempt in range(2):
            try:
                async with self._session_factory() as cleanup:
                    plans = SqlAlchemyPlanRepository(cleanup)
                    await plans.delete_unqueued_generation(
                        user_id=plan.user_id,
                        plan_id=plan.id,
                        trace_id=plan.trace_id,
                    )
                    await AgentRunRepository(cleanup).delete_queued_by_trace_id(
                        user_id=plan.user_id,
                        trace_id=plan.trace_id,
                    )
                    await cleanup.commit()
                await self._session.rollback()
                return
            except BaseException as error:
                last_error = error
        assert last_error is not None
        raise last_error


class PlanGenerationJobHandler:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        pricing: PricingPolicy,
        executor_factory: Callable[[AsyncSession], PlanDraftExecutor],
        adjustment_parser: PlanAdjustmentParser | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._pricing = pricing
        self._executor_factory = executor_factory
        self._adjustment_parser = adjustment_parser

    async def __call__(self, job: ScheduledJob) -> JobResultSummary:
        trace_id = job.trace_id
        if trace_id is None:
            raise ValueError("plan jobs require a trace id")
        operation = job.payload.get("operation", "generate")
        generation_payload: PlanJobPayload | None = None
        adjustment_payload: PlanAdjustmentJobPayload | None = None
        if operation == "generate":
            generation_payload = PlanJobPayload.model_validate(job.payload, strict=True)
        else:
            adjustment_payload = PlanAdjustmentJobPayload.model_validate(
                job.payload,
                strict=True,
            )
        async with self._session_factory() as session:
            plans = SqlAlchemyPlanRepository(session)
            plan: PlanVersion | None = None
            if generation_payload is not None:
                plan = await plans.require(
                    user_id=job.user_id,
                    plan_id=generation_payload.plan_id,
                )
                if plan.status is PlanStatus.WAITING_APPROVAL:
                    await plans.resume_after_approval(
                        user_id=job.user_id,
                        plan_id=plan.id,
                        now=utc_now(),
                    )
                    await session.commit()
                    plan = await plans.require(user_id=job.user_id, plan_id=plan.id)
            executor: PlanDraftExecutor = self._executor_factory(session)

            async def generate(observer: ApplicationRunObserver) -> PlanGenerationResult:
                nonlocal plan
                if adjustment_payload is not None:
                    parser = self._adjustment_parser
                    if parser is None:
                        raise RuntimeError("plan adjustment parser is not configured")
                    base = await plans.require(
                        user_id=job.user_id,
                        plan_id=adjustment_payload.base_plan_id,
                    )
                    await observer.set_stage("adjustment.parsing")
                    try:
                        patch = await parser.parse(
                            constraints=base.constraints,
                            instruction=adjustment_payload.instruction,
                            response_observer=observer.record_model_response,
                        )
                    except PlanAdjustmentUnsupportedError:
                        return PlanGenerationResult(
                            outcome=PlanGenerationOutcome.FAILED,
                            error_code="PLAN_ADJUSTMENT_UNSUPPORTED",
                        )
                    except PlanAdjustmentNotUnderstoodError:
                        return PlanGenerationResult(
                            outcome=PlanGenerationOutcome.FAILED,
                            error_code="PLAN_ADJUSTMENT_NOT_UNDERSTOOD",
                        )
                    adjusted_constraints = apply_plan_adjustment(base.constraints, patch)
                    versions = await plans.list_versions(
                        user_id=job.user_id,
                        root_plan_id=base.root_plan_id,
                        lock=True,
                    )
                    if not versions or versions[-1].id != base.id:
                        return PlanGenerationResult(
                            outcome=PlanGenerationOutcome.FAILED,
                            error_code="STALE_VERSION",
                        )
                    timestamp = utc_now()
                    plan = PlanVersion(
                        id=generate_plan_id(),
                        root_plan_id=base.root_plan_id,
                        parent_plan_id=base.id,
                        user_id=job.user_id,
                        version=base.version + 1,
                        operation=PlanOperation.ADJUST,
                        status=PlanStatus.GENERATING,
                        constraints=adjusted_constraints,
                        adjustment_text=adjustment_payload.instruction,
                        trace_id=trace_id,
                        idempotency_key=job.idempotency_key,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    await plans.add(
                        plan,
                        request_fingerprint=plan_request_fingerprint(
                            adjustment_payload.model_dump(mode="json")
                        ),
                    )
                    await session.commit()
                assert plan is not None
                approval = await plans.get_external_approval(
                    user_id=job.user_id,
                    plan_id=plan.id,
                )
                await observer.set_stage("collections.filtered")
                result = await observer.run_tool(
                    tool_name="plan_draft",
                    arguments_fingerprint=plan_request_fingerprint(
                        plan.constraints.model_dump(mode="json")
                    ),
                    input_summary=f"plan_version:{plan.version}",
                    operation=lambda: executor.execute(
                        user_id=job.user_id,
                        constraints=plan.constraints,
                        approval=approval,
                    ),
                    summarize=lambda value: ApplicationToolOutcome(
                        succeeded=value.outcome is not PlanGenerationOutcome.FAILED,
                        output_summary=value.outcome.value,
                        error_code=value.error_code,
                    ),
                )
                if result.outcome is PlanGenerationOutcome.WAITING_APPROVAL:
                    assert result.approval_requirement is not None
                    timestamp = utc_now()
                    approval_expires_at = min(
                        timestamp + _APPROVAL_TTL,
                        plan.constraints.expires_at,
                    )
                    if approval_expires_at <= timestamp:
                        await plans.fail_generation(
                            user_id=job.user_id,
                            plan_id=plan.id,
                            error_code="PLAN_CONSTRAINTS_EXPIRED",
                            now=timestamp,
                        )
                        await session.commit()
                        return PlanGenerationResult(
                            outcome=PlanGenerationOutcome.FAILED,
                            error_code="PLAN_CONSTRAINTS_EXPIRED",
                        )
                    approval_record = PlanApproval(
                        id=generate_approval_id(),
                        user_id=job.user_id,
                        action=ApprovalAction.EXTERNAL_PLACE_SUPPLEMENT,
                        target_plan_id=plan.id,
                        external_requirement_id=(
                            result.approval_requirement.approval_id
                        ),
                        display_text=result.approval_requirement.display_text,
                        status=ApprovalStatus.PENDING,
                        created_at=timestamp,
                        expires_at=approval_expires_at,
                    )
                    approval_record = await plans.create_approval(approval_record)
                    await plans.wait_for_approval(
                        user_id=job.user_id,
                        plan_id=plan.id,
                        now=timestamp,
                    )
                    await session.commit()
                    await observer.require_approval(approval_record.id)
                elif result.outcome is PlanGenerationOutcome.DRAFT:
                    assert result.draft is not None
                    await MemoryPlanningService(session).record_usage(
                        user_id=job.user_id,
                        plan_id=plan.id,
                        usages=result.memory_usages,
                        used_at=utc_now(),
                    )
                    await plans.complete_generation(
                        user_id=job.user_id,
                        plan_id=plan.id,
                        draft=result.draft,
                        now=utc_now(),
                    )
                    await session.commit()
                    await observer.set_stage("plan.ready")
                else:
                    await plans.fail_generation(
                        user_id=job.user_id,
                        plan_id=plan.id,
                        error_code=result.error_code or "PLAN_GENERATION_FAILED",
                        now=utc_now(),
                    )
                    await session.commit()
                return result

            try:
                intent = PlanOperation.ADJUST.value
                if adjustment_payload is None:
                    assert plan is not None
                    intent = plan.operation.value
                execution = await AgentRunService(
                    session=session,
                    runner=None,
                    pricing=self._pricing,
                ).execute_application(
                    AgentRunCreate(
                        trace_id=trace_id,
                        user_id=job.user_id,
                        intent=intent,
                        workflow="plan.experience",
                    ),
                    generate,
                    reuse_queued=True,
                    outcome=lambda result: (
                        (
                            AgentRunStatus.FAILED,
                            result.error_code or "PLAN_GENERATION_FAILED",
                        )
                        if result.outcome is PlanGenerationOutcome.FAILED
                        else (AgentRunStatus.SUCCEEDED, None)
                    ),
                )
            except asyncio.CancelledError:
                if plan is not None:
                    await plans.cancel_generation(
                        user_id=job.user_id,
                        plan_id=plan.id,
                        now=utc_now(),
                    )
                    await asyncio.shield(session.commit())
                raise
            except Exception:
                if plan is not None:
                    await plans.fail_generation(
                        user_id=job.user_id,
                        plan_id=plan.id,
                        error_code="PLAN_GENERATION_FAILED",
                        now=utc_now(),
                    )
                    await session.commit()
                raise
            return JobResultSummary(outcome=execution.result.outcome.value)


__all__ = [
    "ExistingPlanServicesExecutor",
    "PLAN_GENERATION_JOB_TYPE",
    "PlanDraftExecutor",
    "PlanApprovalSubmission",
    "PlanAdjustmentJobPayload",
    "PlanAdjustmentSubmission",
    "PlanExperienceService",
    "PlanFactResolver",
    "PlanGenerationFacts",
    "PlanGenerationJobHandler",
    "PlanGenerationOutcome",
    "PlanGenerationResult",
    "PlanJobPayload",
    "PlanSubmission",
]

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
from app.application.plan_drafts import PlanDraftService
from app.application.plan_proposals import PlanProposalService
from app.application.plan_sharing import PlanShareService
from app.application.pricing import PricingPolicy
from app.application.run_tracking import (
    AgentRunService,
    ApplicationRunObserver,
    ApplicationToolOutcome,
)
from app.application.structured_collection_retrieval import (
    StructuredCollectionRetrievalService,
)
from app.domain.collections import (
    CandidateField,
    CollectionKind,
    CollectionStatus,
    PlaceCandidate,
    ResourceNotFoundError,
)
from app.domain.identifiers import generate_approval_id, generate_plan_id, generate_trace_id
from app.domain.jobs import JobConflictError, JobCreate, JobResultSummary, ScheduledJob
from app.domain.places import PlaceMatchingPolicy
from app.domain.plans import (
    ApprovalAction,
    ApprovalStatus,
    CandidateReasonCode,
    ExternalApprovalDecision,
    ExternalDraftCandidate,
    ExternalPlaceApprovalDecision,
    ExternalPlaceApprovalRequirement,
    ExternalPlaceCandidate,
    ExternalRecoveryCode,
    ExternalSupplementOutcome,
    PlanApproval,
    PlanConstraints,
    PlanDraftFactSnapshot,
    PlanDraftResult,
    PlanningFactSnapshot,
    PlanOperation,
    PlanOption,
    PlanProposalCandidate,
    PlanProposalItem,
    PlanProposalSet,
    PlanStatus,
    PlanVersion,
    RequiredGapKind,
    RequiredPlanGap,
    StructuredCollectionResult,
    plan_constraints_internal_dump,
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
from nanobot_core.providers import ModelResponse

PLAN_GENERATION_JOB_TYPE = "plan.generate"
_APPROVAL_TTL = timedelta(minutes=15)
_PUBLIC_FAILURE_REASON_PRIORITY = (
    CandidateReasonCode.EVENT_TIME_UNKNOWN,
    CandidateReasonCode.LOCATION_UNCONFIRMED,
    CandidateReasonCode.CITY_UNCONFIRMED,
    CandidateReasonCode.CITY_MISMATCH,
    CandidateReasonCode.ROUTE_PROVIDER_FAILED,
    CandidateReasonCode.WEATHER_PROVIDER_FAILED,
    CandidateReasonCode.AVAILABILITY_PROVIDER_FAILED,
    CandidateReasonCode.BRANCH_PROVIDER_FAILED,
)


def _proposal_request(constraints: PlanConstraints) -> str:
    if constraints.original_request is not None:
        return constraints.original_request
    facts = [
        f"时间 {constraints.start_at.isoformat()} 至 {constraints.end_at.isoformat()}",
        f"城市 {constraints.city_code.value}",
    ]
    if constraints.area is not None:
        facts.append("区域 " + "、".join((*constraints.area.districts, *constraints.area.labels)))
    elif constraints.origin is not None:
        facts.append("已提供精确起点")
    if constraints.include:
        facts.append("希望包含 " + "、".join(constraints.include))
    if constraints.exclude:
        facts.append("明确排除 " + "、".join(constraints.exclude))
    if constraints.budget is not None:
        facts.append(f"预算 {constraints.budget} 元")
    facts.append(f"节奏 {constraints.pace.value}")
    return "计划条件：" + "；".join(facts)


def plan_failure_code_for_retrieval(
    *,
    recovery_code: ExternalRecoveryCode | None,
    collections: StructuredCollectionResult,
) -> str:
    """Preserve an existing retrieval cause when no candidate can be planned."""

    fallback = "PLAN_GENERATION_FAILED" if recovery_code is None else recovery_code.value
    if recovery_code is not ExternalRecoveryCode.NO_EXECUTABLE_DRAFT:
        return fallback
    if collections.included:
        return fallback
    if not collections.decisions:
        return ExternalRecoveryCode.ADD_COLLECTIONS.value
    common_reasons = set(collections.decisions[0].reason_codes)
    for decision in collections.decisions[1:]:
        common_reasons.intersection_update(decision.reason_codes)
    return next(
        (reason.value for reason in _PUBLIC_FAILURE_REASON_PRIORITY if reason in common_reasons),
        fallback,
    )


class PlanGenerationFacts(PlanContract):
    retrieval: PlanningFactSnapshot
    draft: PlanDraftFactSnapshot


class PlanFactResolver(Protocol):
    async def resolve(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
    ) -> PlanGenerationFacts: ...

    async def resolve_proposal_routes(
        self,
        *,
        proposals: PlanProposalSet,
        candidate_keys: dict[str, tuple[str, ...]],
        base: PlanDraftFactSnapshot,
    ) -> PlanDraftFactSnapshot: ...

    async def resolve_external_routes(
        self,
        *,
        proposals: PlanProposalSet,
        external_key: str,
        candidate: ExternalPlaceCandidate,
        candidate_keys: dict[str, tuple[str, ...]],
    ) -> ExternalDraftCandidate: ...


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
    effective_constraints: PlanConstraints | None = None

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
        adjustment: PlanAdjustmentContext | None = None,
        response_observer: Callable[[ModelResponse], None] | None = None,
    ) -> PlanGenerationResult: ...


class PlanAdjustmentContext(PlanContract):
    instruction: str
    base_option_index: int = Field(ge=0, le=2)
    base_option: PlanOption


class ExistingPlanServicesExecutor:
    """Compose the existing M0-5 services; it owns no planning rules."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        map_provider: MapProvider,
        matching_policy: PlaceMatchingPolicy,
        facts: PlanFactResolver,
        proposals: PlanProposalService,
    ) -> None:
        self._session = session
        self._map_provider = map_provider
        self._matching = PlaceMatchingService(
            map_provider=map_provider,
            policy=matching_policy,
        )
        self._facts = facts
        self._proposals = proposals

    async def execute(
        self,
        *,
        user_id: str,
        constraints: PlanConstraints,
        approval: PlanApproval | None,
        adjustment: PlanAdjustmentContext | None = None,
        response_observer: Callable[[ModelResponse], None] | None = None,
    ) -> PlanGenerationResult:
        now = utc_now()
        memory_service = MemoryPlanningService(self._session)
        memories = await memory_service.effective(user_id=user_id, at=now)
        effective_constraints, memory_usages = memory_service.apply_pace_default(
            constraints=constraints,
            memories=memories,
        )
        facts = await self._facts.resolve(user_id=user_id, constraints=effective_constraints)
        collections = await StructuredCollectionRetrievalService(
            repository=SqlAlchemyCollectionRepository(self._session),
        ).retrieve(
            user_id=user_id,
            constraints=effective_constraints,
            facts=facts.retrieval,
            now=now,
            memories=memories,
        )
        candidate_keys = {
            f"candidate_{index}": decision.collection_item_ids
            for index, decision in enumerate(collections.included)
        }
        candidates = tuple(
            PlanProposalCandidate(
                candidate_key=key,
                title=decision.title,
                kind=decision.kind,
                district=None if decision.poi is None else decision.poi.district,
                tags=decision.tags,
                preferred=bool(
                    set(decision.collection_item_ids)
                    & set(effective_constraints.selected_collection_item_ids)
                ),
                required=bool(
                    set(decision.collection_item_ids)
                    & set(effective_constraints.required_collection_item_ids)
                ),
            )
            for key, decision in zip(candidate_keys, collections.included, strict=True)
        )
        included_ids = {
            collection_id
            for decision in collections.included
            for collection_id in decision.collection_item_ids
        }
        if not set(effective_constraints.required_collection_item_ids).issubset(included_ids):
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.FAILED,
                error_code="REQUIRED_COLLECTION_CONFLICT",
                effective_constraints=effective_constraints,
            )
        request = _proposal_request(effective_constraints)
        change_summary: str | None = None
        if adjustment is None:
            proposals = (
                None
                if not candidates
                else await self._proposals.propose(
                    request=request,
                    constraints=effective_constraints,
                    candidates=candidates,
                    now=now,
                )
            )
        else:
            key_by_ids = {ids: key for key, ids in candidate_keys.items()}
            try:
                base_items = tuple(
                    PlanProposalItem(
                        candidate_key=key_by_ids[item.source.collection_item_ids],
                        visit_duration_seconds=item.visit_duration_seconds,
                    )
                    for item in adjustment.base_option.items
                )
            except KeyError:
                return PlanGenerationResult(
                    outcome=PlanGenerationOutcome.FAILED,
                    error_code="PLAN_ADJUSTMENT_UNSUPPORTED",
                    effective_constraints=effective_constraints,
                )
            try:
                proposals, effective_constraints, change_summary = (
                    await self._proposals.adjust(
                        instruction=adjustment.instruction,
                        constraints=effective_constraints,
                        base_items=base_items,
                        candidates=candidates,
                        now=now,
                        response_observer=response_observer,
                    )
                )
            except ValueError:
                return PlanGenerationResult(
                    outcome=PlanGenerationOutcome.FAILED,
                    error_code="PLAN_ADJUSTMENT_NOT_UNDERSTOOD",
                    effective_constraints=effective_constraints,
                )
            if effective_constraints != constraints:
                facts = await self._facts.resolve(
                    user_id=user_id,
                    constraints=effective_constraints,
                )
                collections = await StructuredCollectionRetrievalService(
                    repository=SqlAlchemyCollectionRepository(self._session),
                ).retrieve(
                    user_id=user_id,
                    constraints=effective_constraints,
                    facts=facts.retrieval,
                    now=now,
                    memories=memories,
                )
                available_ids = {
                    decision.collection_item_ids for decision in collections.included
                }
                if any(
                    candidate_keys[item.candidate_key] not in available_ids
                    for item in proposals.options[0].items
                ):
                    return PlanGenerationResult(
                        outcome=PlanGenerationOutcome.FAILED,
                        error_code="PLAN_ADJUSTMENT_CONFLICT",
                        effective_constraints=effective_constraints,
                    )
        gap = next(
            (
                (option.external_gap_description, option.external_gap_kind)
                for option in (() if proposals is None else proposals.options)
                if option.external_gap_description is not None
            ),
            None,
        )
        if not candidates and effective_constraints.include:
            gap = (effective_constraints.include[0], CollectionKind.PLACE)
        external_candidates: dict[str, ExternalDraftCandidate] = {}
        if gap is not None:
            gap_description, gap_kind = gap
            assert gap_description is not None and gap_kind is not None
            required_gap = RequiredPlanGap(
                kind=(
                    RequiredGapKind.PLACE
                    if gap_kind is CollectionKind.PLACE
                    else RequiredGapKind.EVENT
                ),
                place_candidate=(
                    PlaceCandidate(
                        title=gap_description,
                        city_hint="深圳",
                        missing_fields=(
                            CandidateField.ADDRESS,
                            CandidateField.PRICE,
                        ),
                    )
                    if gap_kind is CollectionKind.PLACE
                    else None
                ),
                supplement_reason=gap_description,
                visit_duration_seconds=1,
            )
            approval_decision = None
            if approval is not None and approval.status in {
                ApprovalStatus.APPROVED,
                ApprovalStatus.REJECTED,
            }:
                assert approval.external_requirement_id is not None
                approval_decision = ExternalPlaceApprovalDecision(
                    approval_id=approval.external_requirement_id,
                    decision=(
                        ExternalApprovalDecision.APPROVED
                        if approval.status is ApprovalStatus.APPROVED
                        else ExternalApprovalDecision.REJECTED
                    ),
                )
            supplement = await ExternalPlaceSupplementService(
                place_matching=self._matching,
            ).generate(
                constraints=effective_constraints,
                collections=collections,
                required_gap=required_gap,
                approval_decision=approval_decision,
                queried_at=utc_now(),
            )
            if supplement.outcome is ExternalSupplementOutcome.WAITING_APPROVAL:
                return PlanGenerationResult(
                    outcome=PlanGenerationOutcome.WAITING_APPROVAL,
                    approval_requirement=supplement.approval,
                    memory_usages=memory_usages,
                    effective_constraints=effective_constraints,
                )
            if supplement.candidate is not None:
                external_key = "external_0"
                candidates = (
                    *candidates,
                    PlanProposalCandidate(
                        candidate_key=external_key,
                        title=supplement.candidate.poi.name,
                        kind=CollectionKind.PLACE,
                        district=supplement.candidate.poi.district,
                        required=True,
                    ),
                )
                proposals = await self._proposals.propose(
                    request=request,
                    constraints=effective_constraints,
                    candidates=candidates,
                    now=now,
                )
                external_candidates[external_key] = await self._facts.resolve_external_routes(
                    proposals=proposals,
                    external_key=external_key,
                    candidate=supplement.candidate,
                    candidate_keys=candidate_keys,
                )
        if proposals is None:
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.FAILED,
                error_code=plan_failure_code_for_retrieval(
                    recovery_code=ExternalRecoveryCode.NO_EXECUTABLE_DRAFT,
                    collections=collections,
                ),
                effective_constraints=effective_constraints,
            )
        draft_facts = await self._facts.resolve_proposal_routes(
            proposals=proposals,
            candidate_keys=candidate_keys,
            base=facts.draft,
        )
        draft = PlanDraftService().generate(
            constraints=effective_constraints,
            collections=collections,
            facts=draft_facts,
            proposals=proposals,
            candidate_keys=candidate_keys,
            external_candidates=external_candidates,
        )
        if draft.outcome.value == "generated":
            if adjustment is not None:
                assert change_summary is not None
                draft = draft.model_copy(
                    update={
                        "base_option_index": adjustment.base_option_index,
                        "change_summary": change_summary,
                    }
                )
            selected_ids = {
                collection_id
                for option in draft.options
                for item in option.items
                for collection_id in item.source.collection_item_ids
            }
            for decision_item in collections.included:
                if not selected_ids.intersection(decision_item.collection_item_ids):
                    continue
                for memory_id in decision_item.applied_memory_ids:
                    memory_usages[memory_id] = f"该偏好影响了计划地点选择：{decision_item.title}"
            return PlanGenerationResult(
                outcome=PlanGenerationOutcome.DRAFT,
                draft=draft,
                memory_usages=memory_usages,
                effective_constraints=effective_constraints,
            )
        return PlanGenerationResult(
            outcome=PlanGenerationOutcome.FAILED,
            error_code=(
                "PLAN_GENERATION_FAILED"
                if draft.failure_code is None
                else draft.failure_code.value
            ),
            effective_constraints=effective_constraints,
        )


class PlanJobPayload(PlanContract):
    operation: Literal["generate"] = "generate"
    plan_id: str


class PlanAdjustmentJobPayload(PlanContract):
    operation: Literal["adjust"] = "adjust"
    base_plan_id: str
    base_option_index: int = Field(ge=0, le=2)
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
        if constraints.selected_collection_item_ids:
            items = await SqlAlchemyCollectionRepository(self._session).list_collection_items(
                user_id=user_id, include_inactive=True
            )
            by_id = {item.id: item for item in items}
            if any(
                identifier not in by_id or by_id[identifier].status is CollectionStatus.DELETED
                for identifier in constraints.selected_collection_item_ids
            ):
                raise ResourceNotFoundError
        key = scoped_plan_key(user_id=user_id, client_key=client_idempotency_key)
        fingerprint_constraints = plan_constraints_internal_dump(
            constraints,
            mode="json",
        )
        fingerprint_constraints.pop("created_at")
        fingerprint_constraints.pop("expires_at")
        fingerprint = plan_request_fingerprint(
            {
                "operation": "generate",
                "constraints": fingerprint_constraints,
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
        base_option_index: int,
        instruction: str,
        client_idempotency_key: str,
    ) -> PlanAdjustmentSubmission:
        key = scoped_plan_key(user_id=user_id, client_key=client_idempotency_key)
        base = await self._plans.require(user_id=user_id, plan_id=base_plan_id)
        if (
            base.draft is None
            or base_option_index < 0
            or base_option_index >= len(base.draft.options)
            or base.status not in {PlanStatus.DRAFT, PlanStatus.CONFIRMED}
        ):
            from app.domain.plans import PlanNotReadyError

            raise PlanNotReadyError
        trace_id = f"trc_{hashlib.sha256(key.encode()).hexdigest()[:32]}"
        payload = PlanAdjustmentJobPayload(
            base_plan_id=base_plan_id,
            base_option_index=base_option_index,
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
        option_index: int,
        client_idempotency_key: str,
    ) -> tuple[PlanVersion, bool]:
        target = await self._plans.require(user_id=user_id, plan_id=plan_id)
        if target.constraints.origin is None:
            from app.domain.plans import PlanOriginRequiredError

            raise PlanOriginRequiredError
        key = scoped_plan_key(user_id=user_id, client_key=client_idempotency_key)
        fingerprint = plan_request_fingerprint(
            {"operation": "confirm", "plan_id": plan_id, "option_index": option_index}
        )
        result = await self._plans.confirm(
            user_id=user_id,
            plan_id=plan_id,
            option_index=option_index,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            now=utc_now(),
        )
        await PlanShareService(self._session).sync_expiry_after_confirmation(result[0])
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
                payload=PlanJobPayload(plan_id=existing.target_plan_id).model_dump(mode="json"),
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
    ) -> None:
        self._session_factory = session_factory
        self._pricing = pricing
        self._executor_factory = executor_factory

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
                adjustment_context: PlanAdjustmentContext | None = None
                if adjustment_payload is not None:
                    base = await plans.require(
                        user_id=job.user_id,
                        plan_id=adjustment_payload.base_plan_id,
                    )
                    adjustment_now = utc_now()
                    if (
                        base.draft is None
                        or adjustment_payload.base_option_index >= len(base.draft.options)
                    ):
                        return PlanGenerationResult(
                            outcome=PlanGenerationOutcome.FAILED,
                            error_code="PLAN_ADJUSTMENT_CONFLICT",
                        )
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
                    timestamp = adjustment_now
                    plan = PlanVersion(
                        id=generate_plan_id(),
                        root_plan_id=base.root_plan_id,
                        parent_plan_id=base.id,
                        user_id=job.user_id,
                        version=base.version + 1,
                        operation=PlanOperation.ADJUST,
                        status=PlanStatus.GENERATING,
                        constraints=base.constraints,
                        adjustment_text=adjustment_payload.instruction,
                        trace_id=trace_id,
                        idempotency_key=job.idempotency_key,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    await session.commit()
                    adjustment_context = PlanAdjustmentContext(
                        instruction=adjustment_payload.instruction,
                        base_option_index=adjustment_payload.base_option_index,
                        base_option=base.draft.options[adjustment_payload.base_option_index],
                    )
                assert plan is not None
                current_plan = plan
                approval = await plans.get_external_approval(
                    user_id=job.user_id,
                    plan_id=current_plan.id,
                )
                await observer.set_stage("collections.filtered")

                async def execute_draft() -> PlanGenerationResult:
                    if adjustment_context is None:
                        return await executor.execute(
                            user_id=job.user_id,
                            constraints=current_plan.constraints,
                            approval=approval,
                        )
                    return await executor.execute(
                        user_id=job.user_id,
                        constraints=current_plan.constraints,
                        approval=approval,
                        adjustment=adjustment_context,
                        response_observer=observer.record_model_response,
                    )

                result = await observer.run_tool(
                    tool_name="plan_draft",
                    arguments_fingerprint=plan_request_fingerprint(
                        plan_constraints_internal_dump(
                            current_plan.constraints,
                            mode="json",
                        )
                    ),
                    input_summary=f"plan_version:{current_plan.version}",
                    operation=execute_draft,
                    summarize=lambda value: ApplicationToolOutcome(
                        succeeded=value.outcome is not PlanGenerationOutcome.FAILED,
                        output_summary=value.outcome.value,
                        error_code=value.error_code,
                    ),
                )
                assert plan is not None
                if adjustment_payload is not None:
                    if result.outcome is PlanGenerationOutcome.FAILED:
                        return result
                    await plans.add(
                        plan,
                        request_fingerprint=plan_request_fingerprint(
                            adjustment_payload.model_dump(mode="json")
                        ),
                    )
                if (
                    result.effective_constraints is not None
                    and result.effective_constraints != plan.constraints
                ):
                    timestamp = utc_now()
                    await plans.set_effective_constraints(
                        user_id=job.user_id,
                        plan_id=plan.id,
                        constraints=result.effective_constraints,
                        now=timestamp,
                    )
                    plan = plan.model_copy(
                        update={
                            "constraints": result.effective_constraints,
                            "updated_at": timestamp,
                        }
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
                        external_requirement_id=(result.approval_requirement.approval_id),
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
    "PlanAdjustmentContext",
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

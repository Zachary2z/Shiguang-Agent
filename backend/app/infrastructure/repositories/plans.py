"""User-scoped persistence for the single M1-5 plan version lifecycle."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import IdempotencyConflictError, ResourceNotFoundError
from app.domain.identifiers import generate_approval_id, generate_plan_item_id
from app.domain.plans import (
    ApprovalAction,
    ApprovalStatus,
    PlanApproval,
    PlanConstraints,
    PlanDraftResult,
    PlanExecutionNotAllowedError,
    PlanNotReadyError,
    PlanOperation,
    PlanStatus,
    PlanVersion,
    PlanVersionConflictError,
    parse_plan_constraints_json,
    plan_constraints_internal_dump,
    plan_option_index,
)
from app.domain.time import as_utc, require_aware_utc
from app.infrastructure.db.dml import execute_dml_rowcount
from app.infrastructure.db.models import ApprovalModel, PlanItemModel, PlanModel


def plan_request_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _stored_time(value: datetime) -> datetime:
    normalized = as_utc(value)
    assert normalized is not None
    return normalized


class SqlAlchemyPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_idempotency_key(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> PlanVersion | None:
        row = await self._session.scalar(
            select(PlanModel).where(
                PlanModel.user_id == user_id,
                PlanModel.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            return None
        if row.request_fingerprint != request_fingerprint:
            raise IdempotencyConflictError
        return self._plan(row)

    async def add(self, plan: PlanVersion, *, request_fingerprint: str) -> PlanVersion:
        row = PlanModel(
            id=plan.id,
            root_plan_id=plan.root_plan_id,
            parent_plan_id=plan.parent_plan_id,
            user_id=plan.user_id,
            version=plan.version,
            operation=plan.operation.value,
            status=plan.status.value,
            constraints_json=plan_constraints_internal_dump(plan.constraints, mode="json"),
            adjustment_text=plan.adjustment_text,
            draft_json=None,
            trace_id=plan.trace_id,
            idempotency_key=plan.idempotency_key,
            request_fingerprint=request_fingerprint,
            error_code=None,
            confirmed_at=None,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._plan(row)

    async def delete_unqueued_generation(
        self,
        *,
        user_id: str,
        plan_id: str,
        trace_id: str,
    ) -> bool:
        rowcount = await execute_dml_rowcount(
            self._session,
            delete(PlanModel).where(
                PlanModel.id == plan_id,
                PlanModel.user_id == user_id,
                PlanModel.trace_id == trace_id,
                PlanModel.status == PlanStatus.GENERATING.value,
            ),
        )
        return rowcount == 1

    async def get(self, *, user_id: str, plan_id: str) -> PlanVersion | None:
        row = await self._session.scalar(
            select(PlanModel).where(
                PlanModel.user_id == user_id,
                PlanModel.id == plan_id,
            )
        )
        return None if row is None else self._plan(row)

    async def require(self, *, user_id: str, plan_id: str) -> PlanVersion:
        plan = await self.get(user_id=user_id, plan_id=plan_id)
        if plan is None:
            raise ResourceNotFoundError
        return plan

    async def require_confirmed_for_execution(
        self,
        *,
        user_id: str,
        plan_id: str,
    ) -> PlanVersion:
        """Resolve any version in a plan root to its latest confirmed execution version."""

        requested = await self.require(user_id=user_id, plan_id=plan_id)
        plan = await self.latest_confirmed(
            user_id=user_id,
            root_plan_id=requested.root_plan_id,
        )
        if plan is None:
            raise PlanExecutionNotAllowedError
        return plan

    async def list_latest(self, *, user_id: str) -> tuple[PlanVersion, ...]:
        latest = (
            select(
                PlanModel.root_plan_id,
                PlanModel.user_id,
                func.max(PlanModel.version).label("latest_version"),
            )
            .where(PlanModel.user_id == user_id)
            .group_by(PlanModel.root_plan_id, PlanModel.user_id)
            .subquery()
        )
        rows = (
            await self._session.scalars(
                select(PlanModel)
                .join(
                    latest,
                    (PlanModel.root_plan_id == latest.c.root_plan_id)
                    & (PlanModel.user_id == latest.c.user_id)
                    & (PlanModel.version == latest.c.latest_version),
                )
                .order_by(PlanModel.created_at.desc(), PlanModel.id.desc())
            )
        ).all()
        return tuple(self._plan(row) for row in rows)

    async def list_versions(
        self,
        *,
        user_id: str,
        root_plan_id: str,
        lock: bool = False,
    ) -> tuple[PlanVersion, ...]:
        statement = (
            select(PlanModel)
            .where(
                PlanModel.user_id == user_id,
                PlanModel.root_plan_id == root_plan_id,
            )
            .order_by(PlanModel.version)
        )
        if lock:
            statement = statement.with_for_update()
        rows = (await self._session.scalars(statement)).all()
        return tuple(self._plan(row) for row in rows)

    async def latest_confirmed(
        self,
        *,
        user_id: str,
        root_plan_id: str,
    ) -> PlanVersion | None:
        """Return the newest version that crossed the existing confirmation gate."""

        row = await self._session.scalar(
            select(PlanModel)
            .where(
                PlanModel.user_id == user_id,
                PlanModel.root_plan_id == root_plan_id,
                PlanModel.status.in_(
                    {
                        PlanStatus.CONFIRMED.value,
                        PlanStatus.COMPLETED.value,
                        PlanStatus.PARTIALLY_COMPLETED.value,
                        PlanStatus.NOT_COMPLETED.value,
                    }
                ),
            )
            .order_by(PlanModel.version.desc())
        )
        return None if row is None else self._plan(row)

    async def complete_generation(
        self,
        *,
        user_id: str,
        plan_id: str,
        draft: PlanDraftResult,
        now: datetime,
    ) -> PlanVersion:
        timestamp = require_aware_utc(now)
        rowcount = await execute_dml_rowcount(
            self._session,
            update(PlanModel)
            .where(
                PlanModel.id == plan_id,
                PlanModel.user_id == user_id,
                PlanModel.status == PlanStatus.GENERATING.value,
            )
            .values(
                status=PlanStatus.DRAFT.value,
                draft_json=draft.model_dump(mode="json"),
                error_code=None,
                updated_at=timestamp,
            )
        )
        if rowcount != 1:
            current = await self.require(user_id=user_id, plan_id=plan_id)
            if current.status is PlanStatus.DRAFT and current.draft == draft:
                return current
            raise PlanVersionConflictError
        await self._replace_items(
            user_id=user_id,
            plan_id=plan_id,
            draft=draft,
            created_at=timestamp,
        )
        return await self.require(user_id=user_id, plan_id=plan_id)

    async def set_effective_constraints(
        self,
        *,
        user_id: str,
        plan_id: str,
        constraints: PlanConstraints,
        now: datetime,
    ) -> None:
        rowcount = await execute_dml_rowcount(
            self._session,
            update(PlanModel)
            .where(
                PlanModel.id == plan_id,
                PlanModel.user_id == user_id,
                PlanModel.status.in_(
                    {
                        PlanStatus.GENERATING.value,
                        PlanStatus.WAITING_APPROVAL.value,
                    }
                ),
            )
            .values(
                constraints_json=plan_constraints_internal_dump(constraints, mode="json"),
                updated_at=require_aware_utc(now),
            ),
        )
        if rowcount != 1:
            raise PlanVersionConflictError

    async def wait_for_approval(
        self, *, user_id: str, plan_id: str, now: datetime
    ) -> PlanVersion:
        timestamp = require_aware_utc(now)
        rowcount = await execute_dml_rowcount(
            self._session,
            update(PlanModel)
            .where(
                PlanModel.id == plan_id,
                PlanModel.user_id == user_id,
                PlanModel.status == PlanStatus.GENERATING.value,
            )
            .values(status=PlanStatus.WAITING_APPROVAL.value, updated_at=timestamp)
        )
        if rowcount != 1:
            current = await self.require(user_id=user_id, plan_id=plan_id)
            if current.status is PlanStatus.WAITING_APPROVAL:
                return current
            raise PlanVersionConflictError
        return await self.require(user_id=user_id, plan_id=plan_id)

    async def resume_after_approval(
        self, *, user_id: str, plan_id: str, now: datetime
    ) -> PlanVersion:
        timestamp = require_aware_utc(now)
        rowcount = await execute_dml_rowcount(
            self._session,
            update(PlanModel)
            .where(
                PlanModel.id == plan_id,
                PlanModel.user_id == user_id,
                PlanModel.status == PlanStatus.WAITING_APPROVAL.value,
            )
            .values(status=PlanStatus.GENERATING.value, updated_at=timestamp)
        )
        if rowcount != 1:
            raise PlanVersionConflictError
        return await self.require(user_id=user_id, plan_id=plan_id)

    async def set_generating_constraints(
        self,
        *,
        user_id: str,
        plan_id: str,
        constraints: PlanConstraints,
        now: datetime,
    ) -> PlanVersion:
        timestamp = require_aware_utc(now)
        rowcount = await execute_dml_rowcount(
            self._session,
            update(PlanModel)
            .where(
                PlanModel.id == plan_id,
                PlanModel.user_id == user_id,
                PlanModel.status == PlanStatus.GENERATING.value,
                PlanModel.operation == PlanOperation.ADJUST.value,
            )
            .values(
                constraints_json=plan_constraints_internal_dump(constraints, mode="json"),
                updated_at=timestamp,
            ),
        )
        if rowcount != 1:
            raise PlanVersionConflictError
        return await self.require(user_id=user_id, plan_id=plan_id)

    async def fail_generation(
        self,
        *,
        user_id: str,
        plan_id: str,
        error_code: str,
        now: datetime,
    ) -> PlanVersion:
        timestamp = require_aware_utc(now)
        await self._session.execute(
            update(PlanModel)
            .where(
                PlanModel.id == plan_id,
                PlanModel.user_id == user_id,
                PlanModel.status == PlanStatus.GENERATING.value,
            )
            .values(
                status=PlanStatus.FAILED.value,
                error_code=error_code,
                updated_at=timestamp,
            )
        )
        return await self.require(user_id=user_id, plan_id=plan_id)

    async def cancel_generation(
        self, *, user_id: str, plan_id: str, now: datetime
    ) -> PlanVersion:
        timestamp = require_aware_utc(now)
        await self._session.execute(
            update(PlanModel)
            .where(
                PlanModel.id == plan_id,
                PlanModel.user_id == user_id,
                PlanModel.status == PlanStatus.GENERATING.value,
            )
            .values(status=PlanStatus.CANCELLED.value, updated_at=timestamp)
        )
        return await self.require(user_id=user_id, plan_id=plan_id)

    async def create_approval(self, approval: PlanApproval) -> PlanApproval:
        existing = await self._session.scalar(
            select(ApprovalModel).where(
                ApprovalModel.id == approval.id,
                ApprovalModel.user_id == approval.user_id,
            )
        )
        if existing is not None:
            return self._approval(existing)
        row = ApprovalModel(
            id=approval.id,
            user_id=approval.user_id,
            action=approval.action.value,
            target_plan_id=approval.target_plan_id,
            external_requirement_id=approval.external_requirement_id,
            display_text=approval.display_text,
            status=approval.status.value,
            idempotency_key=approval.idempotency_key,
            request_fingerprint=None,
            created_at=approval.created_at,
            expires_at=approval.expires_at,
            decided_at=approval.decided_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._approval(row)

    async def get_external_approval(
        self, *, user_id: str, plan_id: str
    ) -> PlanApproval | None:
        row = await self._session.scalar(
            select(ApprovalModel)
            .where(
                ApprovalModel.user_id == user_id,
                ApprovalModel.target_plan_id == plan_id,
                ApprovalModel.action
                == ApprovalAction.EXTERNAL_PLACE_SUPPLEMENT.value,
            )
            .order_by(ApprovalModel.created_at.desc())
        )
        return None if row is None else self._approval(row)

    async def decide_external_approval(
        self,
        *,
        user_id: str,
        approval_id: str,
        decision: ApprovalStatus,
        now: datetime,
    ) -> PlanApproval:
        if decision not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise ValueError("external approval decision must approve or reject")
        timestamp = require_aware_utc(now)
        row = await self._session.scalar(
            select(ApprovalModel)
            .where(
                ApprovalModel.id == approval_id,
                ApprovalModel.user_id == user_id,
                ApprovalModel.action
                == ApprovalAction.EXTERNAL_PLACE_SUPPLEMENT.value,
            )
            .with_for_update()
        )
        if row is None:
            raise ResourceNotFoundError
        if row.status == decision.value:
            return self._approval(row)
        if row.status != ApprovalStatus.PENDING.value:
            raise PlanVersionConflictError
        if _stored_time(row.expires_at) <= timestamp:
            row.status = ApprovalStatus.EXPIRED.value
            row.decided_at = timestamp
            await self._session.flush()
            return self._approval(row)
        row.status = decision.value
        row.decided_at = timestamp
        await self._session.flush()
        return self._approval(row)

    async def confirm(
        self,
        *,
        user_id: str,
        plan_id: str,
        option_index: int,
        idempotency_key: str,
        request_fingerprint: str,
        now: datetime,
    ) -> tuple[PlanVersion, bool]:
        timestamp = require_aware_utc(now)
        replay = await self._session.scalar(
            select(ApprovalModel).where(
                ApprovalModel.user_id == user_id,
                ApprovalModel.action == ApprovalAction.CONFIRM_PLAN.value,
                ApprovalModel.idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if replay.request_fingerprint != request_fingerprint:
                raise IdempotencyConflictError
            return (
                await self.require(user_id=user_id, plan_id=replay.target_plan_id),
                True,
            )

        target = await self.require(user_id=user_id, plan_id=plan_id)
        versions = await self.list_versions(
            user_id=user_id,
            root_plan_id=target.root_plan_id,
            lock=True,
        )
        if not versions or versions[-1].id != plan_id:
            raise PlanVersionConflictError
        target = versions[-1]
        if target.status is PlanStatus.CONFIRMED:
            if target.draft is None or plan_option_index(target.draft) != option_index:
                raise PlanVersionConflictError
            return target, True
        if target.status is not PlanStatus.DRAFT:
            raise PlanNotReadyError
        if (
            target.draft is None
            or option_index < 0
            or option_index >= len(target.draft.options)
        ):
            raise PlanNotReadyError
        confirmed_draft = target.draft.model_copy(
            update={"confirmed_option_index": option_index}
        )
        await self._session.execute(
            update(PlanModel)
            .where(
                PlanModel.user_id == user_id,
                PlanModel.root_plan_id == target.root_plan_id,
                PlanModel.status == PlanStatus.CONFIRMED.value,
            )
            .values(status=PlanStatus.SUPERSEDED.value, updated_at=timestamp)
        )
        await self._session.execute(
            update(PlanModel)
            .where(PlanModel.id == plan_id, PlanModel.user_id == user_id)
            .values(
                status=PlanStatus.CONFIRMED.value,
                draft_json=confirmed_draft.model_dump(mode="json"),
                confirmed_at=timestamp,
                updated_at=timestamp,
            )
        )
        self._session.add(
            ApprovalModel(
                id=generate_approval_id(),
                user_id=user_id,
                action=ApprovalAction.CONFIRM_PLAN.value,
                target_plan_id=plan_id,
                external_requirement_id=None,
                display_text=(
                    f"Confirm plan version {target.version}, option {option_index}."
                ),
                status=ApprovalStatus.APPROVED.value,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                created_at=timestamp,
                expires_at=target.constraints.end_at,
                decided_at=timestamp,
            )
        )
        await self._session.flush()
        return await self.require(user_id=user_id, plan_id=plan_id), False

    async def _replace_items(
        self,
        *,
        user_id: str,
        plan_id: str,
        draft: PlanDraftResult,
        created_at: datetime,
    ) -> None:
        await self._session.execute(
            delete(PlanItemModel).where(
                PlanItemModel.plan_id == plan_id,
                PlanItemModel.user_id == user_id,
            )
        )
        for option_index, option in enumerate(draft.options):
            for item_index, item in enumerate(option.items):
                self._session.add(
                    PlanItemModel(
                        id=generate_plan_item_id(),
                        plan_id=plan_id,
                        user_id=user_id,
                        option_index=option_index,
                        item_index=item_index,
                        start_at=item.start_at,
                        end_at=item.end_at,
                        source_kind=item.source.kind.value,
                        snapshot_json=item.model_dump(mode="json"),
                        created_at=created_at,
                    )
                )
        await self._session.flush()

    @staticmethod
    def _plan(row: PlanModel) -> PlanVersion:
        return PlanVersion(
            id=row.id,
            root_plan_id=row.root_plan_id,
            parent_plan_id=row.parent_plan_id,
            user_id=row.user_id,
            version=row.version,
            operation=PlanOperation(row.operation),
            status=PlanStatus(row.status),
            constraints=parse_plan_constraints_json(
                json.dumps(row.constraints_json, separators=(",", ":"))
            ),
            adjustment_text=row.adjustment_text,
            draft=(
                None
                if row.draft_json is None
                else PlanDraftResult.model_validate_json(
                    json.dumps(row.draft_json, separators=(",", ":"))
                )
            ),
            trace_id=row.trace_id,
            idempotency_key=row.idempotency_key,
            created_at=_stored_time(row.created_at),
            updated_at=_stored_time(row.updated_at),
            confirmed_at=None if row.confirmed_at is None else as_utc(row.confirmed_at),
            error_code=row.error_code,
        )

    @staticmethod
    def _approval(row: ApprovalModel) -> PlanApproval:
        return PlanApproval(
            id=row.id,
            user_id=row.user_id,
            action=ApprovalAction(row.action),
            target_plan_id=row.target_plan_id,
            external_requirement_id=row.external_requirement_id,
            display_text=row.display_text,
            status=ApprovalStatus(row.status),
            idempotency_key=row.idempotency_key,
            created_at=_stored_time(row.created_at),
            expires_at=_stored_time(row.expires_at),
            decided_at=None if row.decided_at is None else as_utc(row.decided_at),
        )


__all__ = ["SqlAlchemyPlanRepository", "plan_request_fingerprint"]

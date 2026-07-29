"""Single application boundary for Memory control and suggestion decisions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import IdempotencyConflictError
from app.domain.identifiers import generate_memory_id, generate_memory_operation_id
from app.domain.memories import (
    Memory,
    MemoryConfirmationStatus,
    MemoryNotFoundError,
    MemorySource,
    MemorySourceType,
    MemorySuggestion,
    MemorySuggestionDecision,
    MemorySuggestionUnavailableError,
    MemoryType,
    MemoryUsage,
    MemoryVersionConflictError,
    SensitiveMemoryRejectedError,
)
from app.domain.plans import ActivityArea, PlanConstraints, PlanPace, PlanPaceSource
from app.domain.time import utc_now
from app.infrastructure.db.models import (
    MemoryModel,
    MemoryOperationModel,
    MemoryPlanUsageModel,
    MemorySuggestionDecisionModel,
)
from app.infrastructure.repositories import (
    SqlAlchemyMemoryRepository,
    plan_request_fingerprint,
)


@dataclass(frozen=True)
class MemoryWriteResult:
    memory: Memory
    replayed: bool


@dataclass(frozen=True)
class SuggestionDecisionResult:
    decision: MemorySuggestionDecision
    memory: Memory | None
    replayed: bool


def _scoped_key(user_id: str, client_key: str) -> str:
    if not client_key or len(client_key) > 128:
        raise ValueError("idempotency key is invalid")
    return "memory." + hashlib.sha256(f"{user_id}\0{client_key}".encode()).hexdigest()


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = SqlAlchemyMemoryRepository(session)

    async def list(self, *, user_id: str) -> tuple[Memory, ...]:
        return await self._repository.list(user_id=user_id)

    async def detail(
        self, *, user_id: str, memory_id: str
    ) -> tuple[Memory, tuple[MemoryUsage, ...]]:
        memory = await self._repository.get(user_id=user_id, memory_id=memory_id)
        if memory is None:
            raise MemoryNotFoundError
        return memory, await self._repository.usages(
            user_id=user_id, memory_id=memory_id
        )

    async def suggestions(self, *, user_id: str) -> tuple[MemorySuggestion, ...]:
        return await self._repository.pending_suggestions(user_id=user_id)

    async def create_explicit(
        self,
        *,
        user_id: str,
        memory_type: MemoryType,
        content: str | None,
        value: str | None,
        expires_at: datetime | None,
        explicit_authorization: bool,
        location_granularity: str | None,
        client_idempotency_key: str,
        area: ActivityArea | None = None,
    ) -> MemoryWriteResult:
        self._require_safe_explicit_write(
            memory_type=memory_type,
            area=area,
            explicit_authorization=explicit_authorization,
            location_granularity=location_granularity,
        )
        if memory_type is MemoryType.USUAL_AREA:
            assert area is not None
            content = f"常用区域：{area.display_name}"
            value = area.as_memory_value()
        elif content is None or value is None:
            raise ValueError("preference memories require content and value")
        key = _scoped_key(user_id, client_idempotency_key)
        fingerprint = plan_request_fingerprint(
            {
                "operation": "create",
                "type": memory_type.value,
                "content": content,
                "value": value,
                "area": None if area is None else area.model_dump(mode="json"),
                "expires_at": None if expires_at is None else expires_at.isoformat(),
                "explicit_authorization": explicit_authorization,
                "location_granularity": location_granularity,
            }
        )
        replay = await self._repository.operation_replay(
            user_id=user_id, idempotency_key=key, fingerprint=fingerprint
        )
        if replay is not None:
            return MemoryWriteResult(replay, True)
        now = utc_now()
        memory = Memory(
            id=generate_memory_id(),
            type=memory_type,
            content=content,
            value=value,
            source=MemorySource(
                type=MemorySourceType.EXPLICIT_USER,
                summary="由你明确设置并授权保存",
            ),
            confirmation_status=MemoryConfirmationStatus.CONFIRMED,
            confidence=100,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
            version=1,
        )
        self._session.add(self._row(user_id=user_id, memory=memory))
        self._add_operation(
            user_id=user_id,
            memory=memory,
            operation="create",
            key=key,
            fingerprint=fingerprint,
            now=now,
        )
        return await self._commit_write(
            user_id=user_id, key=key, fingerprint=fingerprint, memory=memory
        )

    async def update(
        self,
        *,
        user_id: str,
        memory_id: str,
        expected_version: int,
        content: str | None,
        value: str | None,
        enabled: bool | None,
        expires_at: datetime | None,
        change_expiry: bool,
        client_idempotency_key: str,
        area: ActivityArea | None = None,
    ) -> MemoryWriteResult:
        key = _scoped_key(user_id, client_idempotency_key)
        fingerprint = plan_request_fingerprint(
            {
                "operation": "update",
                "memory_id": memory_id,
                "expected_version": expected_version,
                "content": content,
                "value": value,
                "area": None if area is None else area.model_dump(mode="json"),
                "enabled": enabled,
                "expires_at": None if expires_at is None else expires_at.isoformat(),
                "change_expiry": change_expiry,
            }
        )
        replay = await self._repository.operation_replay(
            user_id=user_id, idempotency_key=key, fingerprint=fingerprint
        )
        if replay is not None:
            return MemoryWriteResult(replay, True)
        row = await self._repository.row(
            user_id=user_id, memory_id=memory_id, lock=True, include_deleted=True
        )
        replay = await self._repository.operation_replay(
            user_id=user_id, idempotency_key=key, fingerprint=fingerprint
        )
        if replay is not None:
            return MemoryWriteResult(replay, True)
        if row is None or row.deleted_at is not None:
            raise MemoryNotFoundError
        if row.version != expected_version:
            raise MemoryVersionConflictError
        if row.type == MemoryType.USUAL_AREA.value:
            if content is not None or value is not None:
                raise SensitiveMemoryRejectedError
            if area is not None:
                content = f"常用区域：{area.display_name}"
                value = area.as_memory_value()
        elif area is not None:
            raise SensitiveMemoryRejectedError
        now = utc_now()
        candidate = SqlAlchemyMemoryRepository.to_domain(row).model_copy(
            update={
                "content": row.content if content is None else content,
                "value": row.value if value is None else value,
                "disabled_at": (
                    row.disabled_at
                    if enabled is None
                    else None
                    if enabled
                    else now
                ),
                "expires_at": row.expires_at if not change_expiry else expires_at,
                "updated_at": now,
                "version": row.version + 1,
            }
        )
        candidate = Memory.model_validate(candidate.model_dump())
        row.content = candidate.content
        row.value = candidate.value
        row.disabled_at = candidate.disabled_at
        row.expires_at = candidate.expires_at
        row.updated_at = candidate.updated_at
        row.version = candidate.version
        self._add_operation(
            user_id=user_id,
            memory=candidate,
            operation="update",
            key=key,
            fingerprint=fingerprint,
            now=now,
        )
        return await self._commit_write(
            user_id=user_id, key=key, fingerprint=fingerprint, memory=candidate
        )

    async def delete(
        self,
        *,
        user_id: str,
        memory_id: str,
        expected_version: int,
        client_idempotency_key: str,
    ) -> MemoryWriteResult:
        key = _scoped_key(user_id, client_idempotency_key)
        fingerprint = plan_request_fingerprint(
            {
                "operation": "delete",
                "memory_id": memory_id,
                "expected_version": expected_version,
            }
        )
        replay = await self._repository.operation_replay(
            user_id=user_id, idempotency_key=key, fingerprint=fingerprint
        )
        if replay is not None:
            return MemoryWriteResult(replay, True)
        row = await self._repository.row(
            user_id=user_id, memory_id=memory_id, lock=True, include_deleted=True
        )
        replay = await self._repository.operation_replay(
            user_id=user_id, idempotency_key=key, fingerprint=fingerprint
        )
        if replay is not None:
            return MemoryWriteResult(replay, True)
        if row is None or row.deleted_at is not None:
            raise MemoryNotFoundError
        if row.version != expected_version:
            raise MemoryVersionConflictError
        now = utc_now()
        row.deleted_at = now
        row.updated_at = now
        row.version += 1
        memory = SqlAlchemyMemoryRepository.to_domain(row)
        self._add_operation(
            user_id=user_id,
            memory=memory,
            operation="delete",
            key=key,
            fingerprint=fingerprint,
            now=now,
        )
        return await self._commit_write(
            user_id=user_id, key=key, fingerprint=fingerprint, memory=memory
        )

    async def decide_suggestion(
        self,
        *,
        user_id: str,
        suggestion_id: str,
        decision: MemorySuggestionDecision,
        memory_type: MemoryType | None,
        content: str | None,
        value: str | None,
        client_idempotency_key: str,
    ) -> SuggestionDecisionResult:
        if decision is MemorySuggestionDecision.CONFIRMED:
            if memory_type is None or content is None or value is None:
                raise ValueError("confirmed suggestion requires explicit memory fields")
            self._require_safe_inferred_write(
                memory_type=memory_type,
                content=content,
                value=value,
            )
        elif memory_type is not None or content is not None or value is not None:
            raise ValueError("rejected suggestion cannot include memory fields")
        key = _scoped_key(user_id, client_idempotency_key)
        fingerprint = plan_request_fingerprint(
            {
                "operation": "suggestion_decision",
                "suggestion_id": suggestion_id,
                "decision": decision.value,
                "memory_type": None if memory_type is None else memory_type.value,
                "content": content,
                "value": value,
            }
        )
        existing_key = await self._session.scalar(
            select(MemorySuggestionDecisionModel).where(
                MemorySuggestionDecisionModel.user_id == user_id,
                MemorySuggestionDecisionModel.idempotency_key == key,
            )
        )
        if existing_key is not None:
            if existing_key.request_fingerprint != fingerprint:
                raise IdempotencyConflictError
            return await self._decision_result(user_id=user_id, row=existing_key)
        existing = await self._session.scalar(
            select(MemorySuggestionDecisionModel).where(
                MemorySuggestionDecisionModel.suggestion_id == suggestion_id,
                MemorySuggestionDecisionModel.user_id == user_id,
            )
        )
        if existing is not None:
            if (
                existing.decision != decision.value
                or existing.request_fingerprint != fingerprint
            ):
                raise IdempotencyConflictError
            result = await self._decision_result(user_id=user_id, row=existing)
            return SuggestionDecisionResult(result.decision, result.memory, True)
        suggestion = await self._repository.suggestion(
            user_id=user_id, suggestion_id=suggestion_id, lock=True
        )
        if suggestion is None:
            raise MemorySuggestionUnavailableError
        audit, suggestion_payload = suggestion
        now = utc_now()
        memory: Memory | None = None
        if decision is MemorySuggestionDecision.CONFIRMED:
            assert memory_type is not None and content is not None and value is not None
            memory = Memory(
                id=generate_memory_id(),
                type=memory_type,
                content=content,
                value=value,
                source=MemorySource(
                    type=MemorySourceType.FEEDBACK_INFERENCE,
                    summary=(
                        suggestion_payload.evidence_summary
                        or "由你根据一次历史反馈建议明确确认"
                    ),
                    feedback_id=audit.id,
                    plan_id=audit.plan_id,
                ),
                confirmation_status=MemoryConfirmationStatus.CONFIRMED,
                confidence=70,
                created_at=now,
                updated_at=now,
                version=1,
            )
            self._session.add(self._row(user_id=user_id, memory=memory))
        decision_row = MemorySuggestionDecisionModel(
            suggestion_id=audit.id,
            plan_id=audit.plan_id,
            user_id=user_id,
            decision=decision.value,
            memory_id=None if memory is None else memory.id,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            decided_at=now,
        )
        self._session.add(decision_row)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._session.scalar(
                select(MemorySuggestionDecisionModel).where(
                    MemorySuggestionDecisionModel.suggestion_id == suggestion_id,
                    MemorySuggestionDecisionModel.user_id == user_id,
                )
            )
            if (
                existing is None
                or existing.decision != decision.value
                or existing.request_fingerprint != fingerprint
            ):
                raise IdempotencyConflictError from None
            result = await self._decision_result(user_id=user_id, row=existing)
            return SuggestionDecisionResult(result.decision, result.memory, True)
        except BaseException:
            await self._session.rollback()
            raise
        return SuggestionDecisionResult(decision, memory, False)

    async def _decision_result(
        self, *, user_id: str, row: MemorySuggestionDecisionModel
    ) -> SuggestionDecisionResult:
        memory = (
            None
            if row.memory_id is None
            else await self._repository.get(
                user_id=user_id, memory_id=row.memory_id, include_deleted=True
            )
        )
        return SuggestionDecisionResult(
            decision=MemorySuggestionDecision(row.decision),
            memory=memory,
            replayed=True,
        )

    @staticmethod
    def _require_safe_explicit_write(
        *,
        memory_type: MemoryType,
        area: ActivityArea | None,
        explicit_authorization: bool,
        location_granularity: str | None,
    ) -> None:
        if not explicit_authorization:
            raise SensitiveMemoryRejectedError
        if memory_type is MemoryType.USUAL_AREA:
            if location_granularity != "coarse" or area is None:
                raise SensitiveMemoryRejectedError
            try:
                area.as_memory_value()
            except ValueError:
                raise SensitiveMemoryRejectedError from None
        elif location_granularity is not None or area is not None:
            raise SensitiveMemoryRejectedError

    @staticmethod
    def _require_safe_inferred_write(
        *, memory_type: MemoryType, content: str, value: str
    ) -> None:
        if memory_type is MemoryType.USUAL_AREA:
            raise SensitiveMemoryRejectedError

    @staticmethod
    def _row(*, user_id: str, memory: Memory) -> MemoryModel:
        return MemoryModel(
            id=memory.id,
            user_id=user_id,
            type=memory.type.value,
            content=memory.content,
            value=memory.value,
            source_type=memory.source.type.value,
            source_summary=memory.source.summary,
            source_feedback_id=memory.source.feedback_id,
            source_plan_id=memory.source.plan_id,
            confirmation_status=memory.confirmation_status.value,
            confidence=memory.confidence,
            expires_at=memory.expires_at,
            disabled_at=memory.disabled_at,
            deleted_at=memory.deleted_at,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            last_used_at=memory.last_used_at,
            version=memory.version,
        )

    def _add_operation(
        self,
        *,
        user_id: str,
        memory: Memory,
        operation: str,
        key: str,
        fingerprint: str,
        now: datetime,
    ) -> None:
        self._session.add(
            MemoryOperationModel(
                id=generate_memory_operation_id(),
                user_id=user_id,
                memory_id=memory.id,
                operation=operation,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                result_json=memory.model_dump(mode="json"),
                created_at=now,
            )
        )

    async def _commit_write(
        self,
        *,
        user_id: str,
        key: str,
        fingerprint: str,
        memory: Memory,
    ) -> MemoryWriteResult:
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            replay = await self._repository.operation_replay(
                user_id=user_id, idempotency_key=key, fingerprint=fingerprint
            )
            if replay is None:
                raise
            return MemoryWriteResult(replay, True)
        except BaseException:
            await self._session.rollback()
            raise
        return MemoryWriteResult(memory, False)


class MemoryPlanningService:
    """Load effective memories and persist only actual plan influence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = SqlAlchemyMemoryRepository(session)

    async def effective(self, *, user_id: str, at: datetime) -> tuple[Memory, ...]:
        return await self._repository.list_effective(user_id=user_id, at=at)

    @staticmethod
    def apply_pace_default(
        *,
        constraints: PlanConstraints,
        memories: tuple[Memory, ...],
    ) -> tuple[PlanConstraints, dict[str, str]]:
        """Apply one deterministic pace default without overriding this request."""

        if constraints.pace_source is PlanPaceSource.USER_REQUEST:
            return constraints, {}
        candidates = tuple(
            memory
            for memory in memories
            if memory.type is MemoryType.PACE_PREFERENCE
        )
        if not candidates:
            return constraints, {}
        selected = candidates[-1]
        pace = PlanPace(selected.value)
        if (
            constraints.pace_source is PlanPaceSource.SYSTEM_DEFAULT
            and pace is constraints.pace
        ):
            return constraints, {}
        effective = constraints.model_copy(
            update={"pace": pace, "pace_source": PlanPaceSource.MEMORY_DEFAULT}
        )
        return effective, {
            selected.id: f"该节奏记忆将本次计划默认节奏调整为{pace.value}"
        }

    async def record_usage(
        self,
        *,
        user_id: str,
        plan_id: str,
        usages: dict[str, str],
        used_at: datetime,
    ) -> None:
        for memory_id, basis in usages.items():
            memory = await self._repository.row(
                user_id=user_id, memory_id=memory_id, lock=True
            )
            if memory is None:
                continue
            domain = SqlAlchemyMemoryRepository.to_domain(memory)
            if not domain.is_effective(used_at):
                continue
            existing = await self._session.get(
                MemoryPlanUsageModel, (memory_id, plan_id)
            )
            if existing is None:
                self._session.add(
                    MemoryPlanUsageModel(
                        memory_id=memory_id,
                        plan_id=plan_id,
                        user_id=user_id,
                        basis=basis,
                        used_at=used_at,
                    )
                )
            memory.last_used_at = used_at


__all__ = [
    "MemoryPlanningService",
    "MemoryService",
    "MemoryWriteResult",
    "SuggestionDecisionResult",
]

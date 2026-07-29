"""User-scoped persistence for the single structured Memory aggregate."""

from __future__ import annotations

import json
from datetime import datetime
from unicodedata import normalize

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import IdempotencyConflictError
from app.domain.memories import (
    Memory,
    MemoryConfirmationStatus,
    MemorySource,
    MemorySourceType,
    MemorySuggestion,
    MemoryType,
    MemoryUsage,
)
from app.domain.plans import PreferenceSuggestion
from app.domain.time import as_utc
from app.infrastructure.db.models import (
    MemoryModel,
    MemoryOperationModel,
    MemoryPlanUsageModel,
    MemorySuggestionDecisionModel,
    PlanFeedbackAuditModel,
    PlanFeedbackStateModel,
)


def _time(value: datetime) -> datetime:
    normalized = as_utc(value)
    assert normalized is not None
    return normalized


class SqlAlchemyMemoryRepository:
    """Every public method requires the owner id."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, user_id: str, memory_id: str, include_deleted: bool = False
    ) -> Memory | None:
        statement = select(MemoryModel).where(
            MemoryModel.id == memory_id,
            MemoryModel.user_id == user_id,
        )
        if not include_deleted:
            statement = statement.where(MemoryModel.deleted_at.is_(None))
        row = await self._session.scalar(statement)
        return None if row is None else self.to_domain(row)

    async def row(
        self,
        *,
        user_id: str,
        memory_id: str,
        lock: bool = False,
        include_deleted: bool = False,
    ) -> MemoryModel | None:
        statement = select(MemoryModel).where(
            MemoryModel.id == memory_id,
            MemoryModel.user_id == user_id,
        )
        if not include_deleted:
            statement = statement.where(MemoryModel.deleted_at.is_(None))
        if lock:
            statement = statement.with_for_update()
        row: MemoryModel | None = await self._session.scalar(statement)
        return row

    async def list(self, *, user_id: str) -> tuple[Memory, ...]:
        rows = (
            await self._session.scalars(
                select(MemoryModel)
                .where(
                    MemoryModel.user_id == user_id,
                    MemoryModel.deleted_at.is_(None),
                )
                .order_by(MemoryModel.updated_at.desc(), MemoryModel.id.desc())
            )
        ).all()
        return tuple(self.to_domain(row) for row in rows)

    async def list_effective(
        self, *, user_id: str, at: datetime
    ) -> tuple[Memory, ...]:
        rows = (
            await self._session.scalars(
                select(MemoryModel)
                .where(
                    MemoryModel.user_id == user_id,
                    MemoryModel.confirmation_status
                    == MemoryConfirmationStatus.CONFIRMED.value,
                    MemoryModel.disabled_at.is_(None),
                    MemoryModel.deleted_at.is_(None),
                    (MemoryModel.expires_at.is_(None) | (MemoryModel.expires_at > at)),
                )
                .order_by(MemoryModel.created_at, MemoryModel.id)
            )
        ).all()
        return tuple(self.to_domain(row) for row in rows)

    async def usages(
        self, *, user_id: str, memory_id: str
    ) -> tuple[MemoryUsage, ...]:
        rows = (
            await self._session.scalars(
                select(MemoryPlanUsageModel)
                .where(
                    MemoryPlanUsageModel.user_id == user_id,
                    MemoryPlanUsageModel.memory_id == memory_id,
                )
                .order_by(MemoryPlanUsageModel.used_at.desc())
            )
        ).all()
        return tuple(
            MemoryUsage(
                memory_id=row.memory_id,
                plan_id=row.plan_id,
                basis=row.basis,
                used_at=_time(row.used_at),
            )
            for row in rows
        )

    async def pending_suggestions(self, *, user_id: str) -> tuple[MemorySuggestion, ...]:
        terminal_evidence = await self._terminal_suggestion_evidence(user_id=user_id)
        rows = (
            await self._session.execute(
                select(PlanFeedbackAuditModel)
                .join(
                    PlanFeedbackStateModel,
                    (PlanFeedbackStateModel.current_feedback_id == PlanFeedbackAuditModel.id)
                    & (PlanFeedbackStateModel.user_id == PlanFeedbackAuditModel.user_id),
                )
                .outerjoin(
                    MemorySuggestionDecisionModel,
                    (MemorySuggestionDecisionModel.suggestion_id == PlanFeedbackAuditModel.id)
                    & (MemorySuggestionDecisionModel.user_id == PlanFeedbackAuditModel.user_id),
                )
                .where(
                    PlanFeedbackAuditModel.user_id == user_id,
                    PlanFeedbackAuditModel.preference_suggestion_json.is_not(None),
                    MemorySuggestionDecisionModel.suggestion_id.is_(None),
                )
                .order_by(PlanFeedbackAuditModel.created_at.desc())
            )
        ).scalars()
        suggestions: list[MemorySuggestion] = []
        for row in rows:
            payload = PreferenceSuggestion.model_validate_json(
                json.dumps(row.preference_suggestion_json)
            )
            identity = self._suggestion_evidence_identity(
                user_id=user_id,
                plan_id=row.plan_id,
                suggestion=payload,
            )
            if identity is not None and identity in terminal_evidence:
                continue
            suggestions.append(
                MemorySuggestion(
                    id=row.id,
                    plan_id=row.plan_id,
                    memory_type=payload.memory_type,
                    content=payload.content,
                    value=payload.value,
                    evidence_summary=(
                        payload.evidence_summary
                        or "来自一次历史反馈建议，尚未形成长期偏好"
                    ),
                    created_at=_time(row.created_at),
                )
            )
        return tuple(suggestions)

    async def suggestion(
        self, *, user_id: str, suggestion_id: str, lock: bool = False
    ) -> tuple[PlanFeedbackAuditModel, PreferenceSuggestion] | None:
        statement = (
            select(PlanFeedbackAuditModel)
            .join(
                PlanFeedbackStateModel,
                (PlanFeedbackStateModel.current_feedback_id == PlanFeedbackAuditModel.id)
                & (PlanFeedbackStateModel.user_id == PlanFeedbackAuditModel.user_id),
            )
            .where(
                PlanFeedbackAuditModel.id == suggestion_id,
                PlanFeedbackAuditModel.user_id == user_id,
                PlanFeedbackAuditModel.preference_suggestion_json.is_not(None),
            )
        )
        if lock:
            statement = statement.with_for_update()
        row = await self._session.scalar(statement)
        if row is None:
            return None
        payload = PreferenceSuggestion.model_validate_json(
            json.dumps(row.preference_suggestion_json)
        )
        identity = self._suggestion_evidence_identity(
            user_id=user_id,
            plan_id=row.plan_id,
            suggestion=payload,
        )
        if (
            identity is not None
            and identity in await self._terminal_suggestion_evidence(user_id=user_id)
        ):
            return None
        return row, payload

    async def _terminal_suggestion_evidence(
        self, *, user_id: str
    ) -> set[tuple[str, str, str]]:
        rows = (
            await self._session.execute(
                select(
                    PlanFeedbackAuditModel.plan_id,
                    PlanFeedbackAuditModel.preference_suggestion_json,
                )
                .join(
                    MemorySuggestionDecisionModel,
                    (
                        MemorySuggestionDecisionModel.suggestion_id
                        == PlanFeedbackAuditModel.id
                    )
                    & (
                        MemorySuggestionDecisionModel.user_id
                        == PlanFeedbackAuditModel.user_id
                    ),
                )
                .where(
                    PlanFeedbackAuditModel.user_id == user_id,
                    MemorySuggestionDecisionModel.decision.in_(
                        ("confirmed", "rejected")
                    ),
                )
            )
        ).all()
        identities: set[tuple[str, str, str]] = set()
        for plan_id, payload_json in rows:
            if payload_json is None:
                continue
            payload = PreferenceSuggestion.model_validate_json(json.dumps(payload_json))
            identity = self._suggestion_evidence_identity(
                user_id=user_id,
                plan_id=plan_id,
                suggestion=payload,
            )
            if identity is not None:
                identities.add(identity)
        return identities

    async def suggestion_evidence_is_terminal(
        self,
        *,
        user_id: str,
        plan_id: str,
        suggestion: PreferenceSuggestion,
    ) -> bool:
        identity = self._suggestion_evidence_identity(
            user_id=user_id,
            plan_id=plan_id,
            suggestion=suggestion,
        )
        return (
            identity is not None
            and identity in await self._terminal_suggestion_evidence(user_id=user_id)
        )

    @staticmethod
    def _suggestion_evidence_identity(
        *,
        user_id: str,
        plan_id: str,
        suggestion: PreferenceSuggestion,
    ) -> tuple[str, str, str] | None:
        if suggestion.evidence_summary is None:
            return None
        normalized = normalize(
            "NFKC", " ".join(suggestion.evidence_summary.split())
        ).casefold()
        return (
            user_id,
            plan_id,
            normalized,
        )

    async def operation_replay(
        self, *, user_id: str, idempotency_key: str, fingerprint: str
    ) -> Memory | None:
        row = await self._session.scalar(
            select(MemoryOperationModel).where(
                MemoryOperationModel.user_id == user_id,
                MemoryOperationModel.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            return None
        if row.request_fingerprint != fingerprint:
            raise IdempotencyConflictError
        return Memory.model_validate_json(json.dumps(row.result_json))

    @staticmethod
    def to_domain(row: MemoryModel) -> Memory:
        return Memory(
            id=row.id,
            type=MemoryType(row.type),
            content=row.content,
            value=row.value,
            source=MemorySource(
                type=MemorySourceType(row.source_type),
                summary=row.source_summary,
                feedback_id=row.source_feedback_id,
                plan_id=row.source_plan_id,
            ),
            confirmation_status=MemoryConfirmationStatus(row.confirmation_status),
            confidence=row.confidence,
            expires_at=None if row.expires_at is None else _time(row.expires_at),
            disabled_at=None if row.disabled_at is None else _time(row.disabled_at),
            deleted_at=None if row.deleted_at is None else _time(row.deleted_at),
            created_at=_time(row.created_at),
            updated_at=_time(row.updated_at),
            last_used_at=None if row.last_used_at is None else _time(row.last_used_at),
            version=row.version,
        )


__all__ = ["SqlAlchemyMemoryRepository"]

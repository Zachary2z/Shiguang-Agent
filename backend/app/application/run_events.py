"""Application boundary for persistent, replayable AgentRun progress."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.runs.events import PublicRunEvent, RunEventType
from app.domain.time import utc_now
from app.infrastructure.repositories import RunEventRepository


class RunEventService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = RunEventRepository(session)

    async def publish(
        self,
        *,
        user_id: str,
        trace_id: str,
        event_type: RunEventType,
        summary: dict[str, Any],
        created_at: datetime | None = None,
    ) -> PublicRunEvent:
        event = await self._repository.append(
            user_id=user_id,
            trace_id=trace_id,
            event_type=event_type,
            summary=summary,
            created_at=created_at or utc_now(),
        )
        await self._session.commit()
        return event

    async def list_after(
        self,
        *,
        user_id: str,
        trace_id: str,
        after_sequence: int,
        limit: int = 100,
    ) -> list[PublicRunEvent]:
        return await self._repository.list_after(
            user_id=user_id,
            trace_id=trace_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    async def run_exists(self, *, user_id: str, trace_id: str) -> bool:
        return await self._repository.run_exists(user_id=user_id, trace_id=trace_id)


__all__ = ["RunEventService"]

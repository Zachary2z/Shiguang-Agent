"""SSE framing and database-backed replay for public AgentRun events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.runs.events import TERMINAL_RUN_EVENT_TYPES, PublicRunEvent
from app.infrastructure.repositories import RunEventRepository

SSE_POLL_SECONDS = 0.25


def encode_run_event(event: PublicRunEvent) -> str:
    data = {
        "trace_id": event.trace_id,
        "type": event.event_type.value,
        "sequence": event.sequence,
        "summary": event.summary.model_dump(mode="json", exclude_none=True),
        "created_at": event.created_at.isoformat(),
    }
    payload = json.dumps(
        data,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"id: {event.sequence}\nevent: {event.event_type.value}\ndata: {payload}\n\n"


async def stream_run_events(
    *,
    request: Request,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: str,
    trace_id: str,
    after_sequence: int,
) -> AsyncIterator[str]:
    cursor = after_sequence
    while True:
        async with session_factory() as session:
            events = await RunEventRepository(session).list_after(
                user_id=user_id,
                trace_id=trace_id,
                after_sequence=cursor,
                limit=100,
            )
        for event in events:
            cursor = event.sequence
            yield encode_run_event(event)
            if event.event_type in TERMINAL_RUN_EVENT_TYPES:
                return
        if await request.is_disconnected():
            return
        await asyncio.sleep(SSE_POLL_SECONDS)


__all__ = ["SSE_POLL_SECONDS", "encode_run_event", "stream_run_events"]

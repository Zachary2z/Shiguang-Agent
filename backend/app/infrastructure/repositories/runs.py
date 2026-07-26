"""Single repository for AgentRun and its ordered ToolRun children."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identifiers import (
    generate_agent_run_id,
    generate_tool_run_id,
    generate_trace_id,
    validate_trace_id,
    validate_user_id,
)
from app.domain.runs.events import (
    PublicRunEvent,
    RunEventSummary,
    RunEventType,
    parse_run_event_summary,
    serialize_run_event_summary,
)
from app.domain.runs.inputs import AgentRunCreate
from app.domain.runs.statuses import (
    TERMINAL_AGENT_RUN_STATUSES,
    AgentRunStatus,
    ToolRunStatus,
    ensure_run_transition,
)
from app.domain.time import as_utc, required_utc
from app.infrastructure.db.models import AgentRunModel, RunEventModel, ToolRunModel


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolRunWrite:
    sequence: int
    tool_call_id: str
    tool_name: str
    arguments_fingerprint: str
    input_summary: str
    status: ToolRunStatus
    output_summary: str | None
    latency_ms: int | None
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class RunFinalization:
    status: AgentRunStatus
    model_names: list[str]
    model_calls: list[dict[str, object]]
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost: Decimal | None
    cost_currency: str | None
    cost_estimation_source: str
    cost_unknown_reason: str | None
    duration_ms: int
    error_code: str | None
    finished_at: datetime
    tool_runs: list[ToolRunWrite]


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredToolRun:
    id: str
    sequence: int
    tool_call_id: str
    tool_name: str
    arguments_fingerprint: str
    input_summary: str
    status: ToolRunStatus
    output_summary: str | None
    latency_ms: int | None
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredAgentRun:
    id: str
    trace_id: str
    user_id: str | None
    session_id: str | None
    intent: str
    workflow: str
    status: AgentRunStatus
    model_names: list[str]
    model_calls: list[dict[str, object]]
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost: Decimal | None
    cost_currency: str | None
    cost_estimation_source: str
    cost_unknown_reason: str | None
    duration_ms: int | None
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tool_runs: list[StoredToolRun]


class AgentRunRepository:
    """Persist state transitions and return a complete trace summary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_queued(
        self,
        request: AgentRunCreate,
        *,
        now: datetime,
    ) -> AgentRunModel:
        row = AgentRunModel(
            id=generate_agent_run_id(),
            trace_id=request.trace_id or generate_trace_id(),
            user_id=request.user_id,
            session_id=request.session_id,
            intent=request.intent,
            workflow=request.workflow,
            status=AgentRunStatus.QUEUED.value,
            model_names_json=[],
            model_calls_json=[],
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            estimated_cost=None,
            cost_currency=None,
            cost_estimation_source="not_evaluated",
            cost_unknown_reason="not_evaluated",
            duration_ms=None,
            error_code=None,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def mark_running(self, run_id: str, *, started_at: datetime) -> bool:
        row = await self._require(run_id)
        current = AgentRunStatus(row.status)
        if current is AgentRunStatus.RUNNING:
            return False
        ensure_run_transition(current, AgentRunStatus.RUNNING)
        row.status = AgentRunStatus.RUNNING.value
        row.started_at = started_at
        row.updated_at = started_at
        await self._session.flush()
        return True

    async def finalize(self, run_id: str, finalization: RunFinalization) -> bool:
        row = await self._require(run_id)
        current = AgentRunStatus(row.status)
        if current in TERMINAL_AGENT_RUN_STATUSES:
            return False
        ensure_run_transition(current, finalization.status)
        if finalization.status not in TERMINAL_AGENT_RUN_STATUSES:
            raise ValueError("finalization requires a terminal AgentRun status")

        sequences = [tool_run.sequence for tool_run in finalization.tool_runs]
        if len(sequences) != len(set(sequences)):
            raise ValueError("ToolRun sequences must be unique within one AgentRun")

        existing_sequences = set(
            (
                await self._session.scalars(
                    select(ToolRunModel.sequence).where(
                        ToolRunModel.agent_run_id == run_id
                    )
                )
            ).all()
        )
        for tool_run in finalization.tool_runs:
            if tool_run.sequence in existing_sequences:
                continue
            self._session.add(
                ToolRunModel(
                    id=generate_tool_run_id(),
                    agent_run_id=run_id,
                    sequence=tool_run.sequence,
                    tool_call_id=tool_run.tool_call_id,
                    tool_name=tool_run.tool_name,
                    arguments_fingerprint=tool_run.arguments_fingerprint,
                    input_summary=tool_run.input_summary,
                    status=tool_run.status.value,
                    output_summary=tool_run.output_summary,
                    latency_ms=tool_run.latency_ms,
                    error_code=tool_run.error_code,
                    started_at=tool_run.started_at,
                    finished_at=tool_run.finished_at,
                    created_at=tool_run.created_at,
                )
            )

        row.status = finalization.status.value
        row.model_names_json = list(finalization.model_names)
        row.model_calls_json = list(finalization.model_calls)
        row.input_tokens = finalization.input_tokens
        row.output_tokens = finalization.output_tokens
        row.total_tokens = finalization.total_tokens
        row.estimated_cost = finalization.estimated_cost
        row.cost_currency = finalization.cost_currency
        row.cost_estimation_source = finalization.cost_estimation_source
        row.cost_unknown_reason = finalization.cost_unknown_reason
        row.duration_ms = finalization.duration_ms
        row.error_code = finalization.error_code
        row.finished_at = finalization.finished_at
        row.updated_at = finalization.finished_at
        await self._session.flush()
        return True

    async def get_by_trace_id(
        self,
        *,
        user_id: str,
        trace_id: str,
    ) -> StoredAgentRun | None:
        owner = validate_user_id(user_id)
        validated_trace_id = validate_trace_id(trace_id)
        row = await self._session.scalar(
            select(AgentRunModel).where(
                AgentRunModel.trace_id == validated_trace_id,
                AgentRunModel.user_id == owner,
            )
        )
        if row is None:
            return None
        tool_rows = (
            await self._session.scalars(
                select(ToolRunModel)
                .where(ToolRunModel.agent_run_id == row.id)
                .order_by(ToolRunModel.sequence)
            )
        ).all()
        return StoredAgentRun(
            id=row.id,
            trace_id=row.trace_id,
            user_id=row.user_id,
            session_id=row.session_id,
            intent=row.intent,
            workflow=row.workflow,
            status=AgentRunStatus(row.status),
            model_names=list(row.model_names_json),
            model_calls=list(row.model_calls_json),
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.total_tokens,
            estimated_cost=row.estimated_cost,
            cost_currency=row.cost_currency,
            cost_estimation_source=row.cost_estimation_source,
            cost_unknown_reason=row.cost_unknown_reason,
            duration_ms=row.duration_ms,
            error_code=row.error_code,
            started_at=as_utc(row.started_at),
            finished_at=as_utc(row.finished_at),
            created_at=required_utc(row.created_at),
            updated_at=required_utc(row.updated_at),
            tool_runs=[self._stored_tool(tool_row) for tool_row in tool_rows],
        )

    async def _require(self, run_id: str) -> AgentRunModel:
        row = await self._session.get(AgentRunModel, run_id)
        if row is None:
            raise LookupError("AgentRun does not exist")
        return row

    @staticmethod
    def _stored_tool(row: ToolRunModel) -> StoredToolRun:
        return StoredToolRun(
            id=row.id,
            sequence=row.sequence,
            tool_call_id=row.tool_call_id,
            tool_name=row.tool_name,
            arguments_fingerprint=row.arguments_fingerprint,
            input_summary=row.input_summary,
            status=ToolRunStatus(row.status),
            output_summary=row.output_summary,
            latency_ms=row.latency_ms,
            error_code=row.error_code,
            started_at=required_utc(row.started_at),
            finished_at=as_utc(row.finished_at),
            created_at=required_utc(row.created_at),
        )


class RunEventRepository:
    """Append monotonic events while locking their one parent AgentRun."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        user_id: str,
        trace_id: str,
        event_type: RunEventType,
        summary: RunEventSummary,
        created_at: datetime,
    ) -> PublicRunEvent:
        owner = validate_user_id(user_id)
        trace = validate_trace_id(trace_id)
        run = await self._session.scalar(
            select(AgentRunModel)
            .where(
                AgentRunModel.trace_id == trace,
                AgentRunModel.user_id == owner,
            )
            .with_for_update()
        )
        if run is None:
            raise LookupError("AgentRun does not exist")
        return await self._append_to_run(
            run,
            event_type=event_type,
            summary=summary,
            created_at=created_at,
        )

    async def append_for_run(
        self,
        *,
        run_id: str,
        event_type: RunEventType,
        summary: RunEventSummary,
        created_at: datetime,
    ) -> PublicRunEvent | None:
        run = await self._session.scalar(
            select(AgentRunModel)
            .where(AgentRunModel.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise LookupError("AgentRun does not exist")
        if run.user_id is None:
            return None
        return await self._append_to_run(
            run,
            event_type=event_type,
            summary=summary,
            created_at=created_at,
        )

    async def _append_to_run(
        self,
        run: AgentRunModel,
        *,
        event_type: RunEventType,
        summary: RunEventSummary,
        created_at: datetime,
    ) -> PublicRunEvent:
        owner = run.user_id
        if owner is None:
            raise ValueError("public RunEvents require an owned AgentRun")
        public_summary = serialize_run_event_summary(event_type, summary)
        timestamp = required_utc(created_at)
        last_sequence = await self._session.scalar(
            select(func.coalesce(func.max(RunEventModel.sequence), 0)).where(
                RunEventModel.trace_id == run.trace_id
            )
        )
        sequence = int(last_sequence or 0) + 1
        row = RunEventModel(
            id=f"evt_{secrets.token_hex(16)}",
            agent_run_id=run.id,
            trace_id=run.trace_id,
            user_id=owner,
            sequence=sequence,
            event_type=event_type.value,
            summary_json=public_summary,
            created_at=timestamp,
        )
        self._session.add(row)
        await self._session.flush()
        return _public_run_event(row)

    async def list_after(
        self,
        *,
        user_id: str,
        trace_id: str,
        after_sequence: int,
        limit: int = 100,
    ) -> list[PublicRunEvent]:
        owner = validate_user_id(user_id)
        trace = validate_trace_id(trace_id)
        if isinstance(after_sequence, bool) or after_sequence < 0:
            raise ValueError("after_sequence must be nonnegative")
        if isinstance(limit, bool) or limit < 1 or limit > 1000:
            raise ValueError("limit must be in [1, 1000]")
        rows = (
            await self._session.scalars(
                select(RunEventModel)
                .where(
                    RunEventModel.user_id == owner,
                    RunEventModel.trace_id == trace,
                    RunEventModel.sequence > after_sequence,
                )
                .order_by(RunEventModel.sequence)
                .limit(limit)
            )
        ).all()
        return [_public_run_event(row) for row in rows]

    async def run_exists(self, *, user_id: str, trace_id: str) -> bool:
        owner = validate_user_id(user_id)
        trace = validate_trace_id(trace_id)
        run_id = await self._session.scalar(
            select(AgentRunModel.id).where(
                AgentRunModel.trace_id == trace,
                AgentRunModel.user_id == owner,
            )
        )
        return run_id is not None


def _public_run_event(row: RunEventModel) -> PublicRunEvent:
    event_type = RunEventType(row.event_type)
    return PublicRunEvent(
        trace_id=row.trace_id,
        event_type=event_type,
        sequence=row.sequence,
        summary=parse_run_event_summary(event_type, row.summary_json),
        created_at=required_utc(row.created_at),
    )

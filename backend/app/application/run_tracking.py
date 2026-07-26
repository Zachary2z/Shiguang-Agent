"""Application orchestration for durable, queryable Agent runs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import isfinite
from time import monotonic
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.pricing import PricingPolicy
from app.domain.runs.contracts import (
    AgentRunSummary,
    ModelCallStatus,
    ModelCallSummary,
    ToolRunSummary,
)
from app.domain.runs.events import (
    ResultUpdatedSummary,
    RunCompletedSummary,
    RunEventSummary,
    RunEventType,
    RunFailedSummary,
    RunStartedSummary,
    StageChangedSummary,
    ToolCompletedSummary,
)
from app.domain.runs.inputs import AgentRunCreate
from app.domain.runs.statuses import AgentRunStatus, RunErrorCode, ToolRunStatus
from app.domain.time import utc_now
from app.infrastructure.repositories import (
    AgentRunRepository,
    RunEventRepository,
    RunFinalization,
    StoredAgentRun,
    ToolRunWrite,
)
from nanobot_core.agent import (
    MAX_RUN_TIMEOUT_SECONDS,
    AgentRunner,
    ModelCallCancelled,
    ModelCallFailed,
    ModelCallFinished,
    RunEvent,
    RunResult,
    RunTermination,
    ToolCallBlocked,
    ToolCallCancelled,
    ToolCallFinished,
    ToolCallStarted,
)
from nanobot_core.providers import Message, ModelResponse, ProviderError, TokenUsage

T = TypeVar("T")
U = TypeVar("U")
ModelResponseObserver = Callable[[ModelResponse], None]


class ApplicationRunTimeoutError(TimeoutError):
    """A synchronous application workflow exhausted the shared run deadline."""


class ApplicationRunFailureError(RuntimeError):
    """A stable application failure that may safely terminate an AgentRun."""

    def __init__(self, *, error_code: str) -> None:
        if not isinstance(error_code, str) or not error_code:
            raise ValueError("error_code must be non-empty")
        super().__init__("application workflow failed")
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class TrackedRunExecution:
    """The runner result paired with the trace created before execution."""

    trace_id: str
    result: RunResult


@dataclass(frozen=True, slots=True)
class TrackedApplicationExecution(Generic[T]):
    """A synchronous application-workflow result paired with its durable trace."""

    trace_id: str
    result: T


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationToolOutcome:
    """Safe summary of one real application tool result."""

    succeeded: bool
    output_summary: str | None
    error_code: str | None = None


class ApplicationRunObserver:
    """Record model calls and actual application tools in the existing run contract."""

    def __init__(
        self,
        collector: _RunEventCollector,
        *,
        clock: Callable[[], float],
    ) -> None:
        self._collector = collector
        self._clock = clock

    def record_model_response(self, response: ModelResponse) -> None:
        self._collector.record_model_response(response)

    async def run_tool(
        self,
        *,
        tool_name: str,
        arguments_fingerprint: str,
        input_summary: str,
        operation: Callable[[], Awaitable[U]],
        summarize: Callable[[U], ApplicationToolOutcome],
    ) -> U:
        sequence = self._collector.start_application_tool(
            tool_name=tool_name,
            arguments_fingerprint=arguments_fingerprint,
            input_summary=input_summary,
        )
        started = self._clock()
        try:
            result = await operation()
        except asyncio.CancelledError:
            self._collector.finish_application_tool(
                sequence=sequence,
                status=ToolRunStatus.CANCELLED,
                output_summary=None,
                latency_ms=self._elapsed_ms(started),
                error_code=RunErrorCode.CANCELLED.value,
            )
            raise
        except ProviderError as exc:
            self._collector.finish_application_tool(
                sequence=sequence,
                status=ToolRunStatus.FAILED,
                output_summary=None,
                latency_ms=self._elapsed_ms(started),
                error_code=exc.code.value,
            )
            raise
        except Exception as exc:
            code = getattr(getattr(exc, "code", None), "value", None)
            self._collector.finish_application_tool(
                sequence=sequence,
                status=ToolRunStatus.FAILED,
                output_summary=None,
                latency_ms=self._elapsed_ms(started),
                error_code=(
                    code if isinstance(code, str) else RunErrorCode.INTERNAL_ERROR.value
                ),
            )
            raise
        outcome = summarize(result)
        self._collector.finish_application_tool(
            sequence=sequence,
            status=(
                ToolRunStatus.SUCCEEDED if outcome.succeeded else ToolRunStatus.FAILED
            ),
            output_summary=outcome.output_summary,
            latency_ms=self._elapsed_ms(started),
            error_code=outcome.error_code,
        )
        return result

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((self._clock() - started_at) * 1000))


@dataclass(slots=True, kw_only=True)
class _ToolDraft:
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


class _RunEventCollector:
    """Convert core events to application contracts without retaining raw values."""

    def __init__(
        self,
        pricing: PricingPolicy,
        *,
        now: Callable[[], datetime],
    ) -> None:
        self._pricing = pricing
        self._now = now
        self.model_calls: list[ModelCallSummary] = []
        self.tools: dict[int, _ToolDraft] = {}

    def __call__(self, event: RunEvent) -> None:
        if isinstance(event, ModelCallFinished):
            estimate = self._pricing.estimate(event.model_name, event.usage)
            self.model_calls.append(
                ModelCallSummary(
                    sequence=event.sequence,
                    status=ModelCallStatus.SUCCEEDED,
                    model_name=event.model_name,
                    usage=event.usage,
                    latency_ms=event.latency_ms,
                    finish_reason=event.finish_reason,
                    error_code=None,
                    estimated_cost=estimate.amount,
                    cost_currency=estimate.currency,
                    cost_estimation_source=estimate.source,
                    cost_unknown_reason=estimate.unknown_reason,
                )
            )
        elif isinstance(event, ModelCallFailed):
            self.model_calls.append(
                self._unfinished_model_call(
                    sequence=event.sequence,
                    status=ModelCallStatus.FAILED,
                    latency_ms=event.latency_ms,
                    error_code=event.error_code or RunErrorCode.INTERNAL_ERROR.value,
                )
            )
        elif isinstance(event, ModelCallCancelled):
            self.model_calls.append(
                self._unfinished_model_call(
                    sequence=event.sequence,
                    status=ModelCallStatus.CANCELLED,
                    latency_ms=event.latency_ms,
                    error_code=RunErrorCode.CANCELLED.value,
                )
            )
        elif isinstance(event, ToolCallStarted):
            event_time = self._now()
            self.tools[event.sequence] = _ToolDraft(
                sequence=event.sequence,
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                arguments_fingerprint=event.arguments_fingerprint,
                input_summary=event.input_summary,
                status=ToolRunStatus.RUNNING,
                output_summary=None,
                latency_ms=None,
                error_code=None,
                started_at=event_time,
                finished_at=None,
                created_at=event_time,
            )

        elif isinstance(event, ToolCallFinished):
            draft = self._require_tool(event.sequence)
            draft.status = (
                ToolRunStatus.SUCCEEDED if event.success else ToolRunStatus.FAILED
            )
            draft.output_summary = event.output_summary
            draft.latency_ms = event.latency_ms
            draft.error_code = event.error_code
            draft.finished_at = self._now()
        elif isinstance(event, ToolCallCancelled):
            draft = self._require_tool(event.sequence)
            draft.status = ToolRunStatus.CANCELLED
            draft.latency_ms = event.latency_ms
            draft.error_code = RunErrorCode.CANCELLED.value
            draft.finished_at = self._now()
        elif isinstance(event, ToolCallBlocked):
            event_time = self._now()
            error_code = (
                RunErrorCode.TOOL_CALL_LIMIT.value
                if event.reason is RunTermination.MAX_TOOL_CALLS
                else RunErrorCode.REPEATED_TOOL_CALL.value
            )
            self.tools[event.sequence] = _ToolDraft(
                sequence=event.sequence,
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                arguments_fingerprint=event.arguments_fingerprint,
                input_summary=event.input_summary,
                status=ToolRunStatus.BLOCKED,
                output_summary=None,
                latency_ms=0,
                error_code=error_code,
                started_at=event_time,
                finished_at=event_time,
                created_at=event_time,
            )

    def record_model_response(self, response: ModelResponse) -> None:
        """Record provider metadata while deliberately discarding response content."""

        estimate = self._pricing.estimate(response.model_name, response.usage)
        self.model_calls.append(
            ModelCallSummary(
                sequence=len(self.model_calls) + 1,
                status=ModelCallStatus.SUCCEEDED,
                model_name=response.model_name,
                usage=response.usage,
                latency_ms=response.latency_ms,
                finish_reason=response.finish_reason,
                error_code=None,
                estimated_cost=estimate.amount,
                cost_currency=estimate.currency,
                cost_estimation_source=estimate.source,
                cost_unknown_reason=estimate.unknown_reason,
            )
        )

    def start_application_tool(
        self,
        *,
        tool_name: str,
        arguments_fingerprint: str,
        input_summary: str,
    ) -> int:
        sequence = len(self.tools) + 1
        event_time = self._now()
        self.tools[sequence] = _ToolDraft(
            sequence=sequence,
            tool_call_id=f"application-tool-{sequence}",
            tool_name=tool_name,
            arguments_fingerprint=arguments_fingerprint,
            input_summary=input_summary[:512],
            status=ToolRunStatus.RUNNING,
            output_summary=None,
            latency_ms=None,
            error_code=None,
            started_at=event_time,
            finished_at=None,
            created_at=event_time,
        )
        return sequence

    def finish_application_tool(
        self,
        *,
        sequence: int,
        status: ToolRunStatus,
        output_summary: str | None,
        latency_ms: int,
        error_code: str | None,
    ) -> None:
        draft = self._require_tool(sequence)
        draft.status = status
        draft.output_summary = None if output_summary is None else output_summary[:512]
        draft.latency_ms = max(0, latency_ms)
        draft.error_code = error_code
        draft.finished_at = self._now()

    def finalization(
        self,
        *,
        status: AgentRunStatus,
        error_code: str | None,
        duration_ms: int,
        finished_at: datetime,
    ) -> RunFinalization:
        cancellation_code = (
            RunErrorCode.TIMEOUT.value
            if error_code == RunErrorCode.TIMEOUT.value
            else RunErrorCode.CANCELLED.value
        )
        self.model_calls = [
            call.model_copy(update={"error_code": cancellation_code})
            if call.status is ModelCallStatus.CANCELLED
            else call
            for call in self.model_calls
        ]
        for draft in self.tools.values():
            if draft.status is ToolRunStatus.RUNNING:
                draft.status = (
                    ToolRunStatus.CANCELLED
                    if status is AgentRunStatus.CANCELLED
                    or error_code == RunErrorCode.TIMEOUT.value
                    else ToolRunStatus.FAILED
                )
                draft.latency_ms = draft.latency_ms or 0
                draft.error_code = (
                    cancellation_code
                    if draft.status is ToolRunStatus.CANCELLED
                    else RunErrorCode.INTERNAL_ERROR.value
                )
                draft.finished_at = finished_at
            elif draft.status is ToolRunStatus.CANCELLED:
                draft.error_code = cancellation_code

        usage = self.aggregate_usage()
        amount, currency, cost_source, cost_unknown_reason = self.aggregate_cost()
        return RunFinalization(
            status=status,
            model_names=self.model_names(),
            model_calls=[
                call.model_dump(mode="json")
                for call in sorted(self.model_calls, key=lambda item: item.sequence)
            ],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost=amount,
            cost_currency=currency,
            cost_estimation_source=cost_source,
            cost_unknown_reason=cost_unknown_reason,
            duration_ms=max(0, duration_ms),
            error_code=error_code,
            finished_at=finished_at,
            tool_runs=[
                ToolRunWrite(
                    sequence=draft.sequence,
                    tool_call_id=draft.tool_call_id,
                    tool_name=draft.tool_name,
                    arguments_fingerprint=draft.arguments_fingerprint,
                    input_summary=draft.input_summary,
                    status=draft.status,
                    output_summary=draft.output_summary,
                    latency_ms=draft.latency_ms,
                    error_code=draft.error_code,
                    started_at=draft.started_at,
                    finished_at=draft.finished_at,
                    created_at=draft.created_at,
                )
                for draft in sorted(self.tools.values(), key=lambda item: item.sequence)
            ],
        )

    def has_unsuccessful_tool(self) -> bool:
        return any(draft.status is not ToolRunStatus.SUCCEEDED for draft in self.tools.values())

    def aggregate_usage(self) -> TokenUsage:
        return TokenUsage(
            input_tokens=self._aggregate_token_field("input_tokens"),
            output_tokens=self._aggregate_token_field("output_tokens"),
            total_tokens=self._aggregate_token_field("total_tokens"),
        )

    def aggregate_cost(self) -> tuple[Decimal | None, str | None, str, str | None]:
        if not self.model_calls:
            return None, None, "not_evaluated", "no_model_calls"
        if any(call.estimated_cost is None for call in self.model_calls):
            sources = {call.cost_estimation_source for call in self.model_calls}
            source = sources.pop() if len(sources) == 1 else "multiple_pricing_sources"
            reasons = {
                call.cost_unknown_reason
                for call in self.model_calls
                if call.cost_unknown_reason is not None
            }
            reason = reasons.pop() if len(reasons) == 1 else "multiple_unknown_cost_reasons"
            return None, None, source, reason
        currencies = {call.cost_currency for call in self.model_calls}
        if len(currencies) != 1 or None in currencies:
            return None, None, "multiple_pricing_sources", "mixed_cost_currencies"
        sources = {call.cost_estimation_source for call in self.model_calls}
        source = sources.pop() if len(sources) == 1 else "multiple_pricing_sources"
        amount = sum(
            (call.estimated_cost for call in self.model_calls if call.estimated_cost is not None),
            start=Decimal(0),
        )
        return amount, currencies.pop(), source, None

    def model_names(self) -> list[str]:
        names: list[str] = []
        for call in self.model_calls:
            if call.model_name is not None and call.model_name not in names:
                names.append(call.model_name)
        return names

    def _aggregate_token_field(self, field_name: str) -> int | None:
        if not self.model_calls:
            return None
        values: list[int] = []
        for call in self.model_calls:
            if call.usage is None:
                return None
            value = getattr(call.usage, field_name)
            if value is None:
                return None
            values.append(value)
        return sum(values)

    @staticmethod
    def _unfinished_model_call(
        *,
        sequence: int,
        status: ModelCallStatus,
        latency_ms: int,
        error_code: str,
    ) -> ModelCallSummary:
        return ModelCallSummary(
            sequence=sequence,
            status=status,
            model_name=None,
            usage=None,
            latency_ms=latency_ms,
            finish_reason=None,
            error_code=error_code,
            estimated_cost=None,
            cost_currency=None,
            cost_estimation_source="not_evaluated",
            cost_unknown_reason="model_call_not_completed",
        )

    def _require_tool(self, sequence: int) -> _ToolDraft:
        try:
            return self.tools[sequence]
        except KeyError as exc:
            raise RuntimeError("tool completion event had no matching start event") from exc


class AgentRunService:
    """Run the one core AgentRunner and durably finalize every observable outcome."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        runner: AgentRunner | None,
        pricing: PricingPolicy,
        timeout_seconds: float = MAX_RUN_TIMEOUT_SECONDS,
        now: Callable[[], datetime] = utc_now,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int | float)
            or not isfinite(timeout_seconds)
            or timeout_seconds <= 0
            or timeout_seconds > MAX_RUN_TIMEOUT_SECONDS
        ):
            raise ValueError(
                f"timeout_seconds must be in (0, {MAX_RUN_TIMEOUT_SECONDS:g}]"
            )
        self._session = session
        self._repository = AgentRunRepository(session)
        self._events = RunEventRepository(session)
        self._runner = runner
        self._pricing = pricing
        self._timeout_seconds = float(timeout_seconds)
        self._now = now
        self._clock = clock

    async def execute(
        self,
        request: AgentRunCreate,
        messages: list[Message],
    ) -> TrackedRunExecution:
        if self._runner is None:
            raise RuntimeError("AgentRunner is required for core Agent execution")
        queued_at = self._now()
        row = await self._repository.create_queued(request, now=queued_at)
        await self._session.commit()

        started_at = self._now()
        await self._repository.mark_running(row.id, started_at=started_at)
        await self._record_start_events(row.id, started_at=started_at)
        await self._session.commit()
        run_id = row.id
        trace_id = row.trace_id

        collector = _RunEventCollector(self._pricing, now=self._now)
        execution_started = self._clock()
        try:
            result = await self._runner.run(messages, observer=collector)
        except asyncio.CancelledError:
            await self._persist_final(
                run_id,
                collector,
                status=AgentRunStatus.CANCELLED,
                error_code=RunErrorCode.CANCELLED.value,
                duration_ms=self._elapsed_ms(execution_started),
            )
            raise
        except ProviderError as exc:
            await self._persist_final(
                run_id,
                collector,
                status=AgentRunStatus.FAILED,
                error_code=exc.code.value,
                duration_ms=self._elapsed_ms(execution_started),
            )
            raise
        except Exception:
            await self._persist_final(
                run_id,
                collector,
                status=AgentRunStatus.FAILED,
                error_code=RunErrorCode.INTERNAL_ERROR.value,
                duration_ms=self._elapsed_ms(execution_started),
            )
            raise

        status, error_code = self._outcome(result, collector)
        await self._persist_final(
            run_id,
            collector,
            status=status,
            error_code=error_code,
            duration_ms=result.duration_ms,
        )
        return TrackedRunExecution(trace_id=trace_id, result=result)

    async def execute_application(
        self,
        request: AgentRunCreate,
        operation: Callable[[ApplicationRunObserver], Awaitable[T]],
        *,
        outcome: Callable[[T], tuple[AgentRunStatus, str | None]] | None = None,
    ) -> TrackedApplicationExecution[T]:
        """Track one synchronous application workflow without a second AgentRunner."""

        queued_at = self._now()
        row = await self._repository.create_queued(request, now=queued_at)
        await self._session.commit()

        started_at = self._now()
        await self._repository.mark_running(row.id, started_at=started_at)
        await self._record_start_events(row.id, started_at=started_at)
        await self._session.commit()
        run_id = row.id
        trace_id = row.trace_id

        collector = _RunEventCollector(self._pricing, now=self._now)
        observer = ApplicationRunObserver(collector, clock=self._clock)
        execution_started = self._clock()
        try:
            result = await asyncio.wait_for(
                operation(observer),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            await self._persist_final(
                run_id,
                collector,
                status=AgentRunStatus.FAILED,
                error_code=RunErrorCode.TIMEOUT.value,
                duration_ms=self._elapsed_ms(execution_started),
            )
            raise ApplicationRunTimeoutError from None
        except asyncio.CancelledError:
            await self._persist_final(
                run_id,
                collector,
                status=AgentRunStatus.CANCELLED,
                error_code=RunErrorCode.CANCELLED.value,
                duration_ms=self._elapsed_ms(execution_started),
            )
            raise
        except ProviderError as exc:
            await self._persist_final(
                run_id,
                collector,
                status=AgentRunStatus.FAILED,
                error_code=exc.code.value,
                duration_ms=self._elapsed_ms(execution_started),
            )
            raise
        except ApplicationRunFailureError as exc:
            await self._persist_final(
                run_id,
                collector,
                status=AgentRunStatus.FAILED,
                error_code=exc.error_code,
                duration_ms=self._elapsed_ms(execution_started),
            )
            raise
        except Exception:
            await self._persist_final(
                run_id,
                collector,
                status=AgentRunStatus.FAILED,
                error_code=RunErrorCode.INTERNAL_ERROR.value,
                duration_ms=self._elapsed_ms(execution_started),
            )
            raise

        status, error_code = (
            (AgentRunStatus.SUCCEEDED, None)
            if outcome is None
            else outcome(result)
        )
        await self._persist_final(
            run_id,
            collector,
            status=status,
            error_code=error_code,
            duration_ms=self._elapsed_ms(execution_started),
        )
        return TrackedApplicationExecution(trace_id=trace_id, result=result)

    async def get_by_trace_id(
        self,
        *,
        user_id: str,
        trace_id: str,
    ) -> AgentRunSummary | None:
        stored = await self._repository.get_by_trace_id(
            user_id=user_id,
            trace_id=trace_id,
        )
        return None if stored is None else self._summary(stored)

    async def _persist_final(
        self,
        run_id: str,
        collector: _RunEventCollector,
        *,
        status: AgentRunStatus,
        error_code: str | None,
        duration_ms: int,
    ) -> None:
        finalization = collector.finalization(
            status=status,
            error_code=error_code,
            duration_ms=duration_ms,
            finished_at=self._now(),
        )
        await self._repository.finalize(run_id, finalization)
        for tool_run in finalization.tool_runs:
            await self._events.append_for_run(
                run_id=run_id,
                event_type=RunEventType.TOOL_COMPLETED,
                summary=ToolCompletedSummary(
                    tool_name=tool_run.tool_name,
                    status=tool_run.status,
                    tool_sequence=tool_run.sequence,
                ),
                created_at=finalization.finished_at,
            )
        await self._events.append_for_run(
            run_id=run_id,
            event_type=RunEventType.RESULT_UPDATED,
            summary=ResultUpdatedSummary(status=status),
            created_at=finalization.finished_at,
        )
        terminal_summary: RunEventSummary
        if status is AgentRunStatus.SUCCEEDED:
            terminal_event_type = RunEventType.RUN_COMPLETED
            terminal_summary = RunCompletedSummary(
                status=AgentRunStatus.SUCCEEDED
            )
        elif status is AgentRunStatus.PARTIALLY_SUCCEEDED:
            terminal_event_type = RunEventType.RUN_COMPLETED
            terminal_summary = RunCompletedSummary(
                status=AgentRunStatus.PARTIALLY_SUCCEEDED
            )
        elif status in {AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}:
            if error_code is None:
                raise ValueError("failed RunEvent requires an error code")
            terminal_event_type = RunEventType.RUN_FAILED
            terminal_summary = RunFailedSummary(
                status=(
                    AgentRunStatus.FAILED
                    if status is AgentRunStatus.FAILED
                    else AgentRunStatus.CANCELLED
                ),
                error_code=error_code,
            )
        else:
            raise ValueError("terminal RunEvent requires a terminal status")
        await self._events.append_for_run(
            run_id=run_id,
            event_type=terminal_event_type,
            summary=terminal_summary,
            created_at=finalization.finished_at,
        )
        await self._session.commit()

    async def _record_start_events(
        self,
        run_id: str,
        *,
        started_at: datetime,
    ) -> None:
        await self._events.append_for_run(
            run_id=run_id,
            event_type=RunEventType.RUN_STARTED,
            summary=RunStartedSummary(status=AgentRunStatus.RUNNING),
            created_at=started_at,
        )
        await self._events.append_for_run(
            run_id=run_id,
            event_type=RunEventType.STAGE_CHANGED,
            summary=StageChangedSummary(stage="execution"),
            created_at=started_at,
        )

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((self._clock() - started_at) * 1000))

    @staticmethod
    def _summary(stored: StoredAgentRun) -> AgentRunSummary:
        error_code = stored.error_code
        return AgentRunSummary(
            id=stored.id,
            trace_id=stored.trace_id,
            user_id=stored.user_id,
            session_id=stored.session_id,
            intent=stored.intent,
            workflow=stored.workflow,
            status=stored.status,
            model_names=stored.model_names,
            model_calls=[
                ModelCallSummary.model_validate(call, strict=False)
                for call in stored.model_calls
            ],
            usage=TokenUsage(
                input_tokens=stored.input_tokens,
                output_tokens=stored.output_tokens,
                total_tokens=stored.total_tokens,
            ),
            estimated_cost=stored.estimated_cost,
            cost_currency=stored.cost_currency,
            cost_estimation_source=stored.cost_estimation_source,
            cost_unknown_reason=stored.cost_unknown_reason,
            duration_ms=stored.duration_ms,
            error_code=error_code,
            started_at=stored.started_at,
            finished_at=stored.finished_at,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
            tool_runs=[
                ToolRunSummary(
                    id=tool.id,
                    sequence=tool.sequence,
                    tool_call_id=tool.tool_call_id,
                    tool_name=tool.tool_name,
                    arguments_fingerprint=tool.arguments_fingerprint,
                    input_summary=tool.input_summary,
                    status=tool.status,
                    output_summary=tool.output_summary,
                    latency_ms=tool.latency_ms,
                    error_code=tool.error_code,
                    started_at=tool.started_at,
                    finished_at=tool.finished_at,
                    created_at=tool.created_at,
                )
                for tool in stored.tool_runs
            ],
            ended_due_to_timeout=bool(error_code and error_code.endswith("TIMEOUT")),
            ended_due_to_tool_limit=error_code == RunErrorCode.TOOL_CALL_LIMIT.value,
            ended_due_to_repeated_tool_call=(
                error_code == RunErrorCode.REPEATED_TOOL_CALL.value
            ),
            ended_due_to_external_cancellation=(
                error_code == RunErrorCode.CANCELLED.value
            ),
        )

    @staticmethod
    def _outcome(
        result: RunResult,
        collector: _RunEventCollector,
    ) -> tuple[AgentRunStatus, str | None]:
        if result.termination is RunTermination.COMPLETED:
            status = (
                AgentRunStatus.PARTIALLY_SUCCEEDED
                if collector.has_unsuccessful_tool()
                else AgentRunStatus.SUCCEEDED
            )
            return status, None
        outcomes = {
            RunTermination.EMPTY_RESPONSE: RunErrorCode.EMPTY_RESPONSE,
            RunTermination.MAX_ITERATIONS: RunErrorCode.MAX_ITERATIONS,
            RunTermination.MAX_TOOL_CALLS: RunErrorCode.TOOL_CALL_LIMIT,
            RunTermination.REPEATED_TOOL_CALL: RunErrorCode.REPEATED_TOOL_CALL,
            RunTermination.TIMEOUT: RunErrorCode.TIMEOUT,
        }
        return AgentRunStatus.FAILED, outcomes[result.termination].value

"""Offline AgentRun/ToolRun orchestration, persistence, and query tests."""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.application.pricing import ConfiguredPricingPolicy
from app.application.run_tracking import AgentRunService
from app.domain.runs import AgentRunCreate, AgentRunStatus, RunErrorCode, ToolRunStatus
from app.infrastructure.db import Database
from app.infrastructure.db.models import ToolRunModel
from app.infrastructure.repositories import AgentRunRepository, RunFinalization
from nanobot_core.agent import AgentRunner, RunTermination
from nanobot_core.providers import (
    Message,
    ModelProvider,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    StructuredOutput,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from nanobot_core.tools import Tool, ToolErrorCode, ToolInput, ToolRegistry, ToolResult
from tests.core.fakes import EchoTool, ExplodingTool, FakeProvider, fake_response

BACKEND_ROOT = Path(__file__).resolve().parents[2]
USER_ID = "usr_0123456789abcdef0123456789abcdef"
OTHER_USER_ID = "usr_fedcba9876543210fedcba9876543210"


@pytest.fixture
def migrated_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> str:
    database_path = tmp_path / "run-tracking.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_url


def _trace(index: int) -> str:
    return f"trc_{index:032d}"


def _pricing(
    *,
    model_name: str | None = "fixture-model",
    input_price: Decimal | None = Decimal("2"),
    output_price: Decimal | None = Decimal("4"),
) -> ConfiguredPricingPolicy:
    return ConfiguredPricingPolicy(
        model_name=model_name,
        input_price_per_million_tokens=input_price,
        output_price_per_million_tokens=output_price,
        currency="CNY",
        source="fixture_rates_v1",
    )


def _request(index: int, *, user_id: str = USER_ID) -> AgentRunCreate:
    return AgentRunCreate(
        trace_id=_trace(index),
        user_id=user_id,
        session_id="ses_fixture",
        intent="test_intent",
        workflow="test_workflow",
    )


@pytest.mark.parametrize(
    "method",
    [AgentRunService.get_by_trace_id, AgentRunRepository.get_by_trace_id],
)
def test_public_trace_query_requires_explicit_keyword_user_id(method: object) -> None:
    signature = inspect.signature(method)
    user_parameter = signature.parameters["user_id"]

    assert user_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert user_parameter.default is inspect.Parameter.empty


@pytest.mark.asyncio
async def test_no_tool_success_persists_model_usage_cost_and_trace_query(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        provider = FakeProvider(
            [
                fake_response(
                    content="done",
                    usage=TokenUsage(input_tokens=10, output_tokens=5),
                    latency_ms=12,
                )
            ]
        )
        service = AgentRunService(
            session=session,
            runner=AgentRunner(provider, ToolRegistry()),
            pricing=_pricing(),
        )

        execution = await service.execute(
            _request(1), [{"role": "user", "content": "safe input"}]
        )
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=execution.trace_id,
        )

        assert summary is not None
        assert summary.status is AgentRunStatus.SUCCEEDED
        assert summary.trace_id == _trace(1)
        assert summary.model_names == ["fixture-model"]
        assert summary.usage == TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15)
        assert summary.estimated_cost == Decimal("0.00004000")
        assert summary.cost_currency == "CNY"
        assert summary.model_calls[0].latency_ms == 12
        assert summary.model_calls[0].finish_reason.value == "stop"
        assert summary.tool_runs == []
        assert summary.started_at is not None and summary.started_at.tzinfo is UTC
        assert summary.finished_at is not None and summary.finished_at.tzinfo is UTC
    await database.close()


@pytest.mark.asyncio
async def test_trace_query_requires_owner_and_hides_cross_user_like_missing(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider([fake_response(content="done")]),
                ToolRegistry(),
            ),
            pricing=_pricing(),
        )
        execution = await service.execute(_request(3), [])

        same_user = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=execution.trace_id,
        )
        cross_user = await service.get_by_trace_id(
            user_id=OTHER_USER_ID,
            trace_id=execution.trace_id,
        )
        missing = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(999),
        )

        assert same_user is not None and same_user.user_id == USER_ID
        assert cross_user is None
        assert missing is None
        assert cross_user is missing
    await database.close()


@pytest.mark.asyncio
async def test_tool_success_is_ordered_safe_and_model_calls_are_aggregated(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        calls: list[str] = []
        registry = ToolRegistry()
        registry.register(EchoTool(calls))
        provider = FakeProvider(
            [
                fake_response(
                    tool_calls=[ToolCall("call-1", "echo", {"text": "sensitive-value"})],
                    model_name="fixture-model",
                    usage=TokenUsage(input_tokens=2, output_tokens=1),
                ),
                fake_response(
                    content="done",
                    model_name="second-model",
                    usage=TokenUsage(input_tokens=3, output_tokens=4),
                ),
            ]
        )
        service = AgentRunService(
            session=session,
            runner=AgentRunner(provider, registry),
            pricing=_pricing(),
        )

        execution = await service.execute(_request(2), [])
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=execution.trace_id,
        )

        assert summary is not None
        assert calls == ["sensitive-value"]
        assert summary.status is AgentRunStatus.SUCCEEDED
        assert summary.model_names == ["fixture-model", "second-model"]
        assert summary.usage == TokenUsage(input_tokens=5, output_tokens=5, total_tokens=10)
        assert summary.estimated_cost is None
        assert summary.cost_unknown_reason == "model_price_not_configured"
        assert len(summary.model_calls) == 2
        assert summary.model_calls[0].estimated_cost is not None
        assert summary.model_calls[1].cost_unknown_reason == "model_price_not_configured"
        assert [tool.sequence for tool in summary.tool_runs] == [1]
        tool_run = summary.tool_runs[0]
        assert tool_run.status is ToolRunStatus.SUCCEEDED
        assert tool_run.latency_ms is not None and tool_run.latency_ms >= 0
        assert "sensitive-value" not in tool_run.input_summary
        assert "sensitive-value" not in (tool_run.output_summary or "")
        assert len(tool_run.arguments_fingerprint) == 64
    await database.close()


@pytest.mark.asyncio
async def test_service_generated_trace_is_opaque_and_immediately_queryable(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider([fake_response(content="done")]), ToolRegistry()
            ),
            pricing=_pricing(),
        )

        execution = await service.execute(
            AgentRunCreate(
                user_id=USER_ID,
                intent="test_intent",
                workflow="test_workflow",
            ),
            [],
        )
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=execution.trace_id,
        )

        assert execution.trace_id.startswith("trc_")
        assert len(execution.trace_id) == 36
        assert summary is not None and summary.trace_id == execution.trace_id
    await database.close()


@pytest.mark.parametrize(
    ("code", "index"),
    [
        (ProviderErrorCode.TIMEOUT, 10),
        (ProviderErrorCode.RATE_LIMITED, 11),
        (ProviderErrorCode.AUTHENTICATION_FAILED, 12),
        (ProviderErrorCode.INVALID_RESPONSE, 13),
        (ProviderErrorCode.PROVIDER_ERROR, 14),
    ],
)
@pytest.mark.asyncio
async def test_all_provider_errors_are_persisted_then_propagated(
    migrated_database_url: str,
    code: ProviderErrorCode,
    index: int,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        error = ProviderError(code=code)
        service = AgentRunService(
            session=session,
            runner=AgentRunner(FakeProvider([error]), ToolRegistry()),
            pricing=_pricing(),
        )

        with pytest.raises(ProviderError) as caught:
            await service.execute(_request(index), [])
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(index),
        )

        assert caught.value is error
        assert summary is not None
        assert summary.status is AgentRunStatus.FAILED
        assert summary.error_code == code.value
        assert summary.model_calls[0].error_code == code.value
        assert summary.usage == TokenUsage()
        assert summary.estimated_cost is None
        assert summary.ended_due_to_timeout is (code is ProviderErrorCode.TIMEOUT)
    await database.close()


@pytest.mark.parametrize("response", [None, fake_response(content="   ")])
@pytest.mark.asyncio
async def test_none_or_empty_response_is_a_queryable_failure(
    migrated_database_url: str,
    response: ModelResponse | None,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        service = AgentRunService(
            session=session,
            runner=AgentRunner(FakeProvider([response]), ToolRegistry()),
            pricing=_pricing(),
        )

        execution = await service.execute(_request(20), [])
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=execution.trace_id,
        )

        assert execution.result.termination is RunTermination.EMPTY_RESPONSE
        assert summary is not None
        assert summary.status is AgentRunStatus.FAILED
        assert summary.error_code == RunErrorCode.EMPTY_RESPONSE.value
    await database.close()


@pytest.mark.parametrize(
    ("call", "registry_factory", "expected_error"),
    [
        (
            ToolCall("call-missing", "missing", {}),
            ToolRegistry,
            ToolErrorCode.NOT_FOUND,
        ),
        (
            ToolCall("call-invalid", "echo", "{secret-invalid-json"),
            lambda: _registry_with(EchoTool()),
            ToolErrorCode.INVALID_ARGUMENTS,
        ),
        (
            ToolCall("call-explode", "explode", {"text": "secret-exception"}),
            lambda: _registry_with(ExplodingTool()),
            ToolErrorCode.EXECUTION_FAILED,
        ),
    ],
)
@pytest.mark.asyncio
async def test_tool_failures_are_safe_queryable_partial_successes(
    migrated_database_url: str,
    call: ToolCall,
    registry_factory: object,
    expected_error: ToolErrorCode,
) -> None:
    database = Database(migrated_database_url)
    registry = registry_factory()  # type: ignore[operator]
    async with database.session() as session:
        service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider(
                    [fake_response(tool_calls=[call]), fake_response(content="recovered")]
                ),
                registry,
            ),
            pricing=_pricing(),
        )

        execution = await service.execute(_request(30), [])
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=execution.trace_id,
        )

        assert summary is not None
        assert summary.status is AgentRunStatus.PARTIALLY_SUCCEEDED
        assert summary.error_code is None
        assert summary.tool_runs[0].status is ToolRunStatus.FAILED
        assert summary.tool_runs[0].error_code == expected_error.value
        assert "secret" not in repr(summary.tool_runs[0])
    await database.close()


def _registry_with(tool: object) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(tool)  # type: ignore[arg-type]
    return registry


@pytest.mark.asyncio
async def test_loop_limit_tool_limit_and_repeat_each_persist_stable_end_reason(
    migrated_database_url: str,
) -> None:
    scenarios = [
        (
            40,
            AgentRunner(
                FakeProvider(
                    [
                        fake_response(
                            tool_calls=[ToolCall("call-1", "missing", {"attempt": 1})]
                        )
                    ]
                ),
                ToolRegistry(),
                max_iterations=1,
            ),
            RunErrorCode.MAX_ITERATIONS,
        ),
        (
            41,
            AgentRunner(
                FakeProvider(
                    [
                        fake_response(
                            tool_calls=[
                                ToolCall("call-1", "missing", {"attempt": 1}),
                                ToolCall("call-2", "missing", {"attempt": 2}),
                            ]
                        )
                    ]
                ),
                ToolRegistry(),
                max_tool_calls=1,
            ),
            RunErrorCode.TOOL_CALL_LIMIT,
        ),
        (
            42,
            AgentRunner(
                FakeProvider(
                    [
                        fake_response(tool_calls=[ToolCall("call-1", "missing", {})]),
                        fake_response(tool_calls=[ToolCall("call-2", "missing", " { } ")]),
                    ]
                ),
                ToolRegistry(),
            ),
            RunErrorCode.REPEATED_TOOL_CALL,
        ),
    ]
    database = Database(migrated_database_url)
    async with database.session() as session:
        for index, runner, expected_error in scenarios:
            service = AgentRunService(session=session, runner=runner, pricing=_pricing())
            execution = await service.execute(_request(index), [])
            summary = await service.get_by_trace_id(
                user_id=USER_ID,
                trace_id=execution.trace_id,
            )
            assert summary is not None
            assert summary.status is AgentRunStatus.FAILED
            assert summary.error_code == expected_error.value

        tool_limit = await AgentRunRepository(session).get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(41),
        )
        repeated = await AgentRunRepository(session).get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(42),
        )
        assert tool_limit is not None
        assert tool_limit.error_code == RunErrorCode.TOOL_CALL_LIMIT.value
        assert [tool.status for tool in tool_limit.tool_runs] == [
            ToolRunStatus.FAILED,
            ToolRunStatus.BLOCKED,
        ]
        assert repeated is not None
        assert repeated.error_code == RunErrorCode.REPEATED_TOOL_CALL.value
        assert repeated.tool_runs[-1].status is ToolRunStatus.BLOCKED
    await database.close()


class _BlockingProvider(ModelProvider):
    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_format: StructuredOutput | None = None,
    ) -> ModelResponse:
        del messages, tools, response_format
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class _EmptyInput(ToolInput):
    pass


class _BlockingTool(Tool[_EmptyInput]):
    name = "blocking"
    description = "Wait until the total run deadline cancels this tool."
    input_model = _EmptyInput

    def __init__(self) -> None:
        self.cancelled = False

    async def execute(self, arguments: _EmptyInput) -> ToolResult:
        del arguments
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_total_timeout_and_external_cancel_are_distinct_and_queryable(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        timeout_service = AgentRunService(
            session=session,
            runner=AgentRunner(
                _BlockingProvider(), ToolRegistry(), timeout_seconds=0.01
            ),
            pricing=_pricing(),
        )
        timeout_execution = await timeout_service.execute(_request(50), [])
        timeout_summary = await timeout_service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=timeout_execution.trace_id,
        )

        cancel_service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider([asyncio.CancelledError()]), ToolRegistry()
            ),
            pricing=_pricing(),
        )
        with pytest.raises(asyncio.CancelledError):
            await cancel_service.execute(_request(51), [])
        cancel_summary = await cancel_service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(51),
        )

        assert timeout_summary is not None
        assert timeout_summary.status is AgentRunStatus.FAILED
        assert timeout_summary.ended_due_to_timeout is True
        assert timeout_summary.duration_ms is not None
        assert timeout_summary.duration_ms <= 10
        assert cancel_summary is not None
        assert cancel_summary.status is AgentRunStatus.CANCELLED
        assert cancel_summary.ended_due_to_external_cancellation is True
    await database.close()


@pytest.mark.asyncio
async def test_timeout_during_tool_persists_cancelled_toolrun_with_timeout_code(
    migrated_database_url: str,
) -> None:
    blocking_tool = _BlockingTool()
    registry = ToolRegistry()
    registry.register(blocking_tool)
    database = Database(migrated_database_url)
    async with database.session() as session:
        service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider(
                    [fake_response(tool_calls=[ToolCall("call-1", "blocking", {})])]
                ),
                registry,
                timeout_seconds=0.01,
            ),
            pricing=_pricing(),
        )

        execution = await service.execute(_request(52), [])
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=execution.trace_id,
        )

        assert blocking_tool.cancelled is True
        assert summary is not None and summary.ended_due_to_timeout is True
        assert summary.tool_runs[0].status is ToolRunStatus.CANCELLED
        assert summary.tool_runs[0].error_code == RunErrorCode.TIMEOUT.value
    await database.close()


@pytest.mark.asyncio
async def test_partial_unknown_and_zero_tokens_are_not_conflated(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        partial_service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider(
                    [
                        fake_response(
                            content="partial",
                            usage=TokenUsage(input_tokens=None, output_tokens=0),
                        )
                    ]
                ),
                ToolRegistry(),
            ),
            pricing=_pricing(),
        )
        zero_service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider(
                    [
                        fake_response(
                            content="zero",
                            usage=TokenUsage(input_tokens=0, output_tokens=0),
                        )
                    ]
                ),
                ToolRegistry(),
            ),
            pricing=_pricing(),
        )
        await partial_service.execute(_request(60), [])
        await zero_service.execute(_request(61), [])
        partial = await partial_service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(60),
        )
        zero = await zero_service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(61),
        )

        assert partial is not None and zero is not None
        assert partial.usage.input_tokens is None
        assert partial.usage.output_tokens == 0
        assert partial.estimated_cost is None
        assert partial.cost_unknown_reason == "token_usage_incomplete"
        assert partial.model_calls[0].cost_unknown_reason == "token_usage_incomplete"
        assert zero.usage == TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)
        assert zero.estimated_cost == Decimal("0E-8")
        assert zero.cost_unknown_reason is None
    await database.close()


@pytest.mark.asyncio
async def test_trace_conflict_rolls_back_and_terminal_finalization_is_idempotent(
    migrated_database_url: str,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        registry = ToolRegistry()
        registry.register(EchoTool())
        service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider(
                    [
                        fake_response(
                            tool_calls=[ToolCall("call-1", "echo", {"text": "one"})]
                        ),
                        fake_response(content="done"),
                    ]
                ),
                registry,
            ),
            pricing=_pricing(),
        )
        execution = await service.execute(_request(70), [])
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=execution.trace_id,
        )
        assert summary is not None

        repository = AgentRunRepository(session)
        with pytest.raises(IntegrityError):
            await repository.create_queued(_request(70), now=datetime.now(UTC))
        await session.rollback()
        still_present = await repository.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(70),
        )
        assert still_present is not None

        changed = await repository.finalize(
            summary.id,
            RunFinalization(
                status=AgentRunStatus.FAILED,
                model_names=[],
                model_calls=[],
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                estimated_cost=None,
                cost_currency=None,
                cost_estimation_source="not_evaluated",
                cost_unknown_reason="not_evaluated",
                duration_ms=0,
                error_code=RunErrorCode.INTERNAL_ERROR.value,
                finished_at=datetime.now(UTC),
                tool_runs=[],
            ),
        )
        await session.commit()
        tool_count = await session.scalar(
            select(func.count()).select_from(ToolRunModel).where(
                ToolRunModel.agent_run_id == summary.id
            )
        )
        unchanged = await repository.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(70),
        )

        assert changed is False
        assert tool_count == 1
        assert unchanged is not None and unchanged.status is AgentRunStatus.SUCCEEDED
    await database.close()


@pytest.mark.asyncio
async def test_unexpected_error_after_tool_is_persisted_without_exception_detail(
    migrated_database_url: str,
) -> None:
    secret_exception = "third-party-secret-stack-detail"
    database = Database(migrated_database_url)
    async with database.session() as session:
        registry = ToolRegistry()
        registry.register(EchoTool())
        service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider(
                    [
                        fake_response(
                            tool_calls=[ToolCall("call-1", "echo", {"text": "safe"})]
                        ),
                        RuntimeError(secret_exception),
                    ]
                ),
                registry,
            ),
            pricing=_pricing(),
        )

        with pytest.raises(RuntimeError, match=secret_exception):
            await service.execute(_request(71), [])
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(71),
        )

        assert summary is not None
        assert summary.status is AgentRunStatus.FAILED
        assert summary.error_code == RunErrorCode.INTERNAL_ERROR.value
        assert summary.tool_runs[0].status is ToolRunStatus.SUCCEEDED
        assert secret_exception not in repr(summary)
    await database.close()


@pytest.mark.asyncio
async def test_final_database_failure_propagates_and_never_persists_success(
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(migrated_database_url)
    async with database.session() as session:
        service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider([fake_response(content="runner succeeded")]), ToolRegistry()
            ),
            pricing=_pricing(),
        )
        original_commit = session.commit
        commit_count = 0

        async def fail_only_final_commit() -> None:
            nonlocal commit_count
            commit_count += 1
            if commit_count == 3:
                raise RuntimeError("database finalization failed")
            await original_commit()

        monkeypatch.setattr(session, "commit", fail_only_final_commit)
        with pytest.raises(RuntimeError, match="database finalization failed"):
            await service.execute(_request(72), [])
        await session.rollback()

    async with database.session() as verification_session:
        summary = await AgentRunRepository(verification_session).get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(72),
        )
        assert summary is not None
        assert summary.status is AgentRunStatus.RUNNING
    await database.close()


@pytest.mark.asyncio
async def test_sensitive_values_never_enter_database_or_public_summary(
    migrated_database_url: str,
) -> None:
    secret = "api-key-pseudo-secret-Authorization-Cookie"
    database = Database(migrated_database_url)
    async with database.session() as session:
        registry = ToolRegistry()
        registry.register(EchoTool())
        service = AgentRunService(
            session=session,
            runner=AgentRunner(
                FakeProvider(
                    [
                        fake_response(
                            tool_calls=[ToolCall("call-secret", "echo", {"text": secret})]
                        ),
                        fake_response(content="done"),
                    ]
                ),
                registry,
            ),
            pricing=_pricing(),
        )
        await service.execute(_request(80), [{"role": "user", "content": secret}])
        summary = await service.get_by_trace_id(
            user_id=USER_ID,
            trace_id=_trace(80),
        )
        assert summary is not None
        assert secret not in repr(summary)
    await database.close()

    database_path = Path(migrated_database_url.removeprefix("sqlite+aiosqlite:///"))
    with sqlite3.connect(database_path) as connection:
        dump = "\n".join(connection.iterdump())
    assert secret not in dump

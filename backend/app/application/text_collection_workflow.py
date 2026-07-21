"""The single M0-2D workflow from a user text message to saved collections."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.collection_writes import CollectionWriteService
from app.application.pricing import PricingPolicy
from app.application.run_tracking import (
    AgentRunService,
    ApplicationRunTimeoutError,
    ModelResponseObserver,
)
from app.application.text_extraction import TextExtractionService
from app.domain.collections import (
    AutoSaveResult,
    ExtractionResult,
    IdempotencyConflictError,
    Message,
    MessageContentType,
    MessageRole,
    ResourceNotFoundError,
    Source,
    SourceParseStatus,
    SourceType,
)
from app.domain.collections.writes import IDEMPOTENCY_KEY_PATTERN
from app.domain.runs import AgentRunCreate, AgentRunStatus
from app.domain.time import utc_now
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from nanobot_core.providers import ModelProvider, ProviderError


class IdempotentRequestInProgressError(RuntimeError):
    """The same synchronous request is still being handled elsewhere."""


class TextCollectionProviderError(RuntimeError):
    """A provider failure with only a stable public code and durable trace."""

    def __init__(self, *, trace_id: str, error_code: str) -> None:
        super().__init__("text collection provider failed")
        self.trace_id = trace_id
        self.error_code = error_code


class TextCollectionTimeoutError(RuntimeError):
    """The synchronous text workflow exhausted the shared run deadline."""

    def __init__(self, *, trace_id: str) -> None:
        super().__init__("text collection timed out")
        self.trace_id = trace_id


class TextCollectionRunError(RuntimeError):
    """A non-provider terminal run failure exposed without internal details."""

    def __init__(self, *, trace_id: str, error_code: str) -> None:
        super().__init__("text collection run failed")
        self.trace_id = trace_id
        self.error_code = error_code


@dataclass(frozen=True, slots=True, kw_only=True)
class TextCollectionWorkflowResult:
    message: Message
    trace_id: str
    run_status: AgentRunStatus
    extraction_result: ExtractionResult | None
    auto_save_result: AutoSaveResult | None
    replayed: bool


class IdempotencyLockRegistry:
    """Serialize same-process M0 retries while database uniqueness remains authoritative."""

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def lock(self, *, user_id: str, idempotency_key: str) -> asyncio.Lock:
        return self._locks.setdefault((user_id, idempotency_key), asyncio.Lock())


class TextCollectionWorkflow:
    """Persist one user message, track extraction, and invoke the existing write service."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        provider: ModelProvider,
        pricing: PricingPolicy,
        locks: IdempotencyLockRegistry,
        timeout_seconds: float,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._provider = provider
        self._pricing = pricing
        self._locks = locks
        self._timeout_seconds = timeout_seconds
        self._now = now
        self._repository = SqlAlchemyCollectionRepository(session)

    async def submit(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        text: str,
    ) -> TextCollectionWorkflowResult:
        if IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key) is None:
            raise ValueError("idempotency_key must use safe visible characters")
        async with self._locks.lock(user_id=user_id, idempotency_key=idempotency_key):
            return await self._submit_locked(
                user_id=user_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
                text=text,
            )

    async def _submit_locked(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        text: str,
    ) -> TextCollectionWorkflowResult:
        owned_session = await self._repository.get_session(
            user_id=user_id,
            session_id=session_id,
        )
        if owned_session is None:
            await self._session.rollback()
            raise ResourceNotFoundError

        message_id = self._opaque_id("msg", user_id, idempotency_key)
        source_id = self._opaque_id("src", user_id, idempotency_key)
        trace_id = self._trace_id(user_id, idempotency_key)
        created_at = self._now()
        desired_message = Message(
            id=message_id,
            session_id=session_id,
            role=MessageRole.USER,
            content_type=MessageContentType.TEXT,
            content=text,
            trace_id=trace_id,
            created_at=created_at,
        )
        message, message_replayed = await self._ensure_message(
            user_id=user_id,
            desired=desired_message,
        )

        run_service = AgentRunService(
            session=self._session,
            runner=None,
            pricing=self._pricing,
            timeout_seconds=self._timeout_seconds,
            now=self._now,
        )
        existing_run = await run_service.get_by_trace_id(
            user_id=user_id,
            trace_id=trace_id,
        )
        if existing_run is not None:
            if existing_run.status in {AgentRunStatus.QUEUED, AgentRunStatus.RUNNING}:
                raise IdempotentRequestInProgressError
            if existing_run.status is AgentRunStatus.FAILED:
                if existing_run.error_code == "RUN_TIMEOUT":
                    raise TextCollectionTimeoutError(trace_id=trace_id)
                if (existing_run.error_code or "").startswith("PROVIDER_"):
                    raise TextCollectionProviderError(
                        trace_id=trace_id,
                        error_code=existing_run.error_code or "PROVIDER_UNKNOWN",
                    )
                raise TextCollectionRunError(
                    trace_id=trace_id,
                    error_code=existing_run.error_code or "RUN_INTERNAL_ERROR",
                )
            if existing_run.status is AgentRunStatus.CANCELLED:
                raise TextCollectionRunError(
                    trace_id=trace_id,
                    error_code=existing_run.error_code or "RUN_CANCELLED",
                )
            previous = await CollectionWriteService(
                session=self._session,
                now=self._now,
            ).get_idempotent_result(
                user_id=user_id,
                idempotency_key=idempotency_key,
            )
            return TextCollectionWorkflowResult(
                message=message,
                trace_id=trace_id,
                run_status=existing_run.status,
                extraction_result=None,
                auto_save_result=previous,
                replayed=True,
            )

        async def operation(
            response_observer: ModelResponseObserver,
        ) -> tuple[ExtractionResult, AutoSaveResult]:
            extraction = await TextExtractionService(
                self._provider,
                response_observer=response_observer,
            ).extract(text)
            timestamp = self._now()
            source = Source(
                id=source_id,
                user_id=user_id,
                type=SourceType.TEXT,
                parse_status=SourceParseStatus.PARSED,
                created_at=timestamp,
                updated_at=timestamp,
            )
            saved = await CollectionWriteService(
                session=self._session,
                now=self._now,
            ).auto_save(
                user_id=user_id,
                idempotency_key=idempotency_key,
                source=source,
                extraction_result=extraction,
            )
            return extraction, saved

        try:
            execution = await run_service.execute_application(
                AgentRunCreate(
                    trace_id=trace_id,
                    user_id=user_id,
                    session_id=session_id,
                    intent="text_collection",
                    workflow="m0_2d_text_collection",
                ),
                operation,
            )
        except ProviderError as exc:
            raise TextCollectionProviderError(
                trace_id=trace_id,
                error_code=exc.code.value,
            ) from None
        except ApplicationRunTimeoutError:
            raise TextCollectionTimeoutError(trace_id=trace_id) from None

        extraction, saved = execution.result
        return TextCollectionWorkflowResult(
            message=message,
            trace_id=execution.trace_id,
            run_status=AgentRunStatus.SUCCEEDED,
            extraction_result=extraction,
            auto_save_result=saved,
            replayed=message_replayed or saved.replayed,
        )

    async def _ensure_message(
        self,
        *,
        user_id: str,
        desired: Message,
    ) -> tuple[Message, bool]:
        existing = await self._repository.get_message(
            user_id=user_id,
            message_id=desired.id,
        )
        if existing is not None:
            self._ensure_same_message(existing, desired)
            return existing, True
        try:
            await self._repository.add_message(user_id=user_id, message=desired)
            await self._session.commit()
            return desired, False
        except IntegrityError:
            await self._session.rollback()
            existing = await self._repository.get_message(
                user_id=user_id,
                message_id=desired.id,
            )
            if existing is None:
                raise
            self._ensure_same_message(existing, desired)
            return existing, True

    @staticmethod
    def _ensure_same_message(existing: Message, desired: Message) -> None:
        if (
            existing.session_id != desired.session_id
            or existing.role is not desired.role
            or existing.content_type is not desired.content_type
            or existing.content != desired.content
            or existing.trace_id != desired.trace_id
        ):
            raise IdempotencyConflictError

    @staticmethod
    def _opaque_id(prefix: str, user_id: str, idempotency_key: str) -> str:
        digest = hashlib.sha256(
            f"{prefix}\0{user_id}\0{idempotency_key}".encode()
        ).hexdigest()[:32]
        return f"{prefix}_{digest}"

    @staticmethod
    def _trace_id(user_id: str, idempotency_key: str) -> str:
        digest = hashlib.sha256(
            f"trace\0{user_id}\0{idempotency_key}".encode()
        ).hexdigest()[:32]
        return f"trc_{digest}"

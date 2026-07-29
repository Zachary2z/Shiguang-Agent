"""The single Text/URL/Image input workflow for collection ingestion."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.collection_writes import CollectionWriteService
from app.application.image_recognition import (
    ImageRecognitionError,
    ImageRecognitionService,
)
from app.application.input_contracts import CollectionInput, ImageInput, TextInput, UrlInput
from app.application.place_matching import PlaceMatchingService
from app.application.place_targets import PlaceTargetSelectionService
from app.application.pricing import PricingPolicy
from app.application.run_tracking import (
    AgentRunService,
    ApplicationRunFailureError,
    ApplicationRunObserver,
    ApplicationRunTimeoutError,
    ApplicationToolOutcome,
)
from app.application.text_extraction import MAX_TEXT_INPUT_CHARS, TextExtractionService
from app.config import StorageProviderSettings
from app.domain.collections import (
    AutoSaveResult,
    CandidateField,
    CollectionItem,
    CollectionKind,
    EventCandidate,
    ExtractionOutcome,
    ExtractionResult,
    IdempotencyConflictError,
    Message,
    MessageContentType,
    MessageRole,
    PlaceCandidate,
    PlanCity,
    ResourceNotFoundError,
    Source,
    SourceMetadata,
    SourceParseStatus,
    SourceType,
)
from app.domain.collections.writes import validate_idempotency_key
from app.domain.places import CityScope, PlaceMatchRequest, resolve_city_hint
from app.domain.runs import AgentRunCreate, AgentRunStatus
from app.domain.time import utc_now
from app.domain.web import WebFetchFailure, WebPageContent
from app.domain.web.security import UrlPolicyError, validate_web_url
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.providers.map import MapProviderError
from app.providers.storage import PrivateFileMetadata, StorageProvider, StorageProviderError
from app.providers.web import WebContentProvider
from nanobot_core.providers import ModelProvider, ProviderError, StructuredOutputMode

MAX_RICH_INPUT_WORKFLOW_SECONDS = 60.0
_RECOVERY_SUPPLY_TEXT = "supply_text"
_RECOVERY_SEND_SCREENSHOT = "send_screenshot"
_RECOVERY_REUPLOAD_IMAGE = "reupload_image"


class IdempotentRequestInProgressError(RuntimeError):
    """The same synchronous request is still being handled elsewhere."""


class TextCollectionProviderError(RuntimeError):
    """A provider failure with only a stable public code and durable trace."""

    def __init__(self, *, trace_id: str, error_code: str) -> None:
        super().__init__("collection input provider failed")
        self.trace_id = trace_id
        self.error_code = error_code


class TextCollectionTimeoutError(RuntimeError):
    """The synchronous input workflow exhausted its shared deadline."""

    def __init__(self, *, trace_id: str) -> None:
        super().__init__("collection input timed out")
        self.trace_id = trace_id


class TextCollectionRunError(RuntimeError):
    """A non-provider terminal run failure exposed without internal details."""

    def __init__(self, *, trace_id: str, error_code: str) -> None:
        super().__init__("collection input run failed")
        self.trace_id = trace_id
        self.error_code = error_code


@dataclass(frozen=True, slots=True, kw_only=True)
class TextCollectionWorkflowResult:
    message: Message
    source: Source | None
    trace_id: str
    run_status: AgentRunStatus
    extraction_result: ExtractionResult | None
    auto_save_result: AutoSaveResult | None
    recovery_actions: tuple[str, ...] = ()
    error_code: str | None = None
    replayed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PreparedCollectionImport:
    message: Message
    trace_id: str
    run_status: AgentRunStatus
    run_created_at: datetime
    replayed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class _OperationResult:
    source: Source | None
    extraction: ExtractionResult | None
    saved: AutoSaveResult | None
    recovery_actions: tuple[str, ...] = ()
    error_code: str | None = None


class IdempotencyLockRegistry:
    """Serialize same-process retries while database uniqueness stays authoritative."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _IdempotencyLockEntry] = {}
        self._registry_lock = asyncio.Lock()

    def lock(
        self,
        *,
        user_id: str,
        session_id: str = "legacy",
        idempotency_key: str,
    ) -> _IdempotencyLockLease:
        del session_id
        return _IdempotencyLockLease(
            registry=self,
            key=(user_id, idempotency_key),
        )

    @property
    def active_key_count(self) -> int:
        """Return keys with an active holder or waiter."""

        return len(self._entries)

    async def _acquire(
        self,
        key: tuple[str, str],
    ) -> _IdempotencyLockEntry:
        async with self._registry_lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _IdempotencyLockEntry(lock=asyncio.Lock())
                self._entries[key] = entry
            entry.participants += 1
        try:
            await entry.lock.acquire()
        except asyncio.CancelledError as cancellation:
            await self._await_cleanup(
                self._leave(key, entry),
                cancellation=cancellation,
            )
            raise cancellation from None
        except BaseException:
            await self._await_cleanup(self._leave(key, entry))
            raise
        return entry

    async def _release(
        self,
        key: tuple[str, str],
        entry: _IdempotencyLockEntry,
    ) -> None:
        entry.lock.release()
        await self._leave(key, entry)

    async def _leave(
        self,
        key: tuple[str, str],
        entry: _IdempotencyLockEntry,
    ) -> None:
        async with self._registry_lock:
            entry.participants -= 1
            if entry.participants == 0:
                assert not entry.lock.locked()
                if self._entries.get(key) is entry:
                    del self._entries[key]

    @staticmethod
    async def _await_cleanup(
        cleanup: Coroutine[object, object, None],
        *,
        cancellation: asyncio.CancelledError | None = None,
    ) -> None:
        cleanup_task = asyncio.create_task(cleanup)
        pending_cancellation = cancellation
        while not cleanup_task.done():
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError as caught:
                if pending_cancellation is None:
                    pending_cancellation = caught
        cleanup_task.result()
        if pending_cancellation is not None:
            raise pending_cancellation


@dataclass(slots=True)
class _IdempotencyLockEntry:
    lock: asyncio.Lock
    participants: int = 0


@dataclass(slots=True)
class _IdempotencyLockLease:
    registry: IdempotencyLockRegistry
    key: tuple[str, str]
    entry: _IdempotencyLockEntry | None = None

    async def __aenter__(self) -> None:
        if self.entry is not None:
            raise RuntimeError("idempotency lock lease cannot be reused")
        self.entry = await self.registry._acquire(self.key)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, traceback
        entry, self.entry = self.entry, None
        if entry is None:
            raise RuntimeError("idempotency lock lease was not acquired")
        await self.registry._await_cleanup(
            self.registry._release(self.key, entry),
            cancellation=(
                exc_value if isinstance(exc_value, asyncio.CancelledError) else None
            ),
        )


class TextCollectionWorkflow:
    """Persist and process all three P0 inputs through one collection state machine."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        provider: ModelProvider | None,
        pricing: PricingPolicy,
        locks: IdempotencyLockRegistry,
        timeout_seconds: float,
        web_provider: WebContentProvider | None = None,
        storage: StorageProvider | None = None,
        storage_config: StorageProviderSettings | None = None,
        structured_output_mode: StructuredOutputMode | None = None,
        event_place_matching: PlaceMatchingService | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._provider = provider
        self._pricing = pricing
        self._locks = locks
        self._timeout_seconds = timeout_seconds
        self._web_provider = web_provider
        self._storage = storage
        self._storage_config = storage_config
        self._structured_output_mode = structured_output_mode
        self._event_place_matching = event_place_matching
        self._now = now
        self._repository = SqlAlchemyCollectionRepository(session)

    def _require_provider(self) -> ModelProvider:
        if self._provider is None:
            raise ApplicationRunFailureError(error_code="MODEL_PROVIDER_NOT_CONFIGURED")
        return self._provider

    @classmethod
    def message_id_for(
        cls, *, user_id: str, session_id: str, idempotency_key: str
    ) -> str:
        return cls._opaque_id("msg", user_id, session_id, idempotency_key)

    @classmethod
    def source_id_for(
        cls, *, user_id: str, session_id: str, idempotency_key: str
    ) -> str:
        return cls._opaque_id("src", user_id, session_id, idempotency_key)

    @classmethod
    def trace_id_for(
        cls, *, user_id: str, session_id: str, idempotency_key: str
    ) -> str:
        return cls._trace_id(user_id, session_id, idempotency_key)

    async def submit(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        text: str,
    ) -> TextCollectionWorkflowResult:
        """Backward-compatible M0-2D text entry point."""

        return await self.submit_input(
            user_id=user_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
            input=TextInput(text=text),
        )

    async def submit_input(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        input: CollectionInput,
        resume_queued: bool = False,
    ) -> TextCollectionWorkflowResult:
        idempotency_key = validate_idempotency_key(idempotency_key)
        async with self._locks.lock(
            user_id=user_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        ):
            return await self._submit_locked(
                user_id=user_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
                input=input,
                resume_queued=resume_queued,
            )

    async def fail_queued(
        self,
        *,
        user_id: str,
        session_id: str,
        trace_id: str,
        error_code: str,
    ) -> None:
        """Finalize an import that failed before its durable job was created."""

        run_service = AgentRunService(
            session=self._session,
            runner=None,
            pricing=self._pricing,
            timeout_seconds=self._timeout_seconds,
            now=self._now,
        )

        async def fail_operation(
            observer: ApplicationRunObserver,
        ) -> _OperationResult:
            del observer
            raise ApplicationRunFailureError(error_code=error_code)

        try:
            await run_service.execute_application(
                AgentRunCreate(
                    trace_id=trace_id,
                    user_id=user_id,
                    session_id=session_id,
                    intent="collect_content",
                    workflow="m0_4d_unified_input",
                ),
                fail_operation,
                outcome=self._run_outcome,
                reuse_queued=True,
            )
        except ApplicationRunFailureError:
            raise TextCollectionRunError(
                trace_id=trace_id,
                error_code=error_code,
            ) from None

    async def read_result(
        self,
        *,
        user_id: str,
        message_id: str,
        source_id: str,
        idempotency_key: str,
    ) -> TextCollectionWorkflowResult:
        """Read the authoritative persisted state without rerunning any provider."""

        message = await self._repository.get_message(
            user_id=user_id,
            message_id=message_id,
        )
        if message is None or message.trace_id is None:
            raise ResourceNotFoundError
        run = await AgentRunService(
            session=self._session,
            runner=None,
            pricing=self._pricing,
            timeout_seconds=self._timeout_seconds,
            now=self._now,
        ).get_by_trace_id(user_id=user_id, trace_id=message.trace_id)
        if run is None:
            raise ResourceNotFoundError
        source = await self._repository.get_source(
            user_id=user_id,
            source_id=source_id,
        )
        saved = await CollectionWriteService(
            session=self._session,
            now=self._now,
        ).get_idempotent_result(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if saved is None and source is not None:
            saved = AutoSaveResult(source_id=source.id, replayed=True)
        return TextCollectionWorkflowResult(
            message=message,
            source=source,
            trace_id=message.trace_id,
            run_status=run.status,
            extraction_result=self._extraction_from_source(source, saved),
            auto_save_result=saved,
            recovery_actions=(
                ("retry_later",)
                if source is None and run.error_code is not None
                else ()
                if source is None
                else source.metadata.workflow_recovery_actions
            ),
            error_code=run.error_code,
            replayed=True,
        )

    async def prepare_input(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        input: CollectionInput,
    ) -> PreparedCollectionImport:
        """Persist the user message and queued AgentRun without doing provider work."""

        idempotency_key = validate_idempotency_key(idempotency_key)
        async with self._locks.lock(
            user_id=user_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        ):
            owned_session = await self._repository.get_session(
                user_id=user_id,
                session_id=session_id,
            )
            if owned_session is None:
                await self._session.rollback()
                raise ResourceNotFoundError
            message_id = self.message_id_for(
                user_id=user_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
            )
            trace_id = self.trace_id_for(
                user_id=user_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
            )
            message_content, content_type = self._message_projection(input)
            desired = Message(
                id=message_id,
                session_id=session_id,
                role=MessageRole.USER,
                content_type=content_type,
                content=message_content,
                trace_id=trace_id,
                created_at=self._now(),
            )
            message, message_replayed = await self._ensure_message(
                user_id=user_id,
                desired=desired,
            )
            run = await AgentRunService(
                session=self._session,
                runner=None,
                pricing=self._pricing,
                timeout_seconds=self._timeout_seconds,
                now=self._now,
            ).queue_application(
                AgentRunCreate(
                    trace_id=trace_id,
                    user_id=user_id,
                    session_id=session_id,
                    intent="collect_content",
                    workflow="m1_3_content_import",
                )
            )
            return PreparedCollectionImport(
                message=message,
                trace_id=trace_id,
                run_status=run.status,
                run_created_at=run.created_at,
                replayed=message_replayed,
            )

    async def _submit_locked(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        input: CollectionInput,
        resume_queued: bool = False,
    ) -> TextCollectionWorkflowResult:
        owned_session = await self._repository.get_session(
            user_id=user_id,
            session_id=session_id,
        )
        if owned_session is None:
            await self._session.rollback()
            raise ResourceNotFoundError

        message_id = self.message_id_for(
            user_id=user_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        )
        source_id = self.source_id_for(
            user_id=user_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        )
        trace_id = self.trace_id_for(
            user_id=user_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        )
        message_content, content_type = self._message_projection(input)
        desired_message = Message(
            id=message_id,
            session_id=session_id,
            role=MessageRole.USER,
            content_type=content_type,
            content=message_content,
            trace_id=trace_id,
            created_at=self._now(),
        )
        message, message_replayed = await self._ensure_message(
            user_id=user_id,
            desired=desired_message,
        )
        scoped_key = await self._select_write_key(
            user_id=user_id,
            session_id=session_id,
            source_id=source_id,
            idempotency_key=idempotency_key,
        )

        run_service = AgentRunService(
            session=self._session,
            runner=None,
            pricing=self._pricing,
            timeout_seconds=(
                min(self._timeout_seconds, MAX_RICH_INPUT_WORKFLOW_SECONDS)
                if isinstance(input, UrlInput | ImageInput)
                else self._timeout_seconds
            ),
            now=self._now,
        )
        existing_run = await run_service.get_by_trace_id(
            user_id=user_id,
            trace_id=trace_id,
        )
        if existing_run is not None and not (
            resume_queued and existing_run.status is AgentRunStatus.QUEUED
        ):
            return await self._replay(
                user_id=user_id,
                idempotency_key=scoped_key,
                message=message,
                source_id=source_id,
                existing_status=existing_run.status,
                existing_error_code=existing_run.error_code,
                trace_id=trace_id,
            )

        async def operation(observer: ApplicationRunObserver) -> _OperationResult:
            if isinstance(input, TextInput):
                return await self._process_text(
                    user_id=user_id,
                    idempotency_key=scoped_key,
                    source_id=source_id,
                    input=input,
                    observer=observer,
                )
            if isinstance(input, UrlInput):
                return await self._process_url(
                    user_id=user_id,
                    idempotency_key=scoped_key,
                    source_id=source_id,
                    input=input,
                    observer=observer,
                )
            return await self._process_image(
                user_id=user_id,
                idempotency_key=scoped_key,
                source_id=source_id,
                input=input,
                observer=observer,
            )

        try:
            execution = await run_service.execute_application(
                AgentRunCreate(
                    trace_id=trace_id,
                    user_id=user_id,
                    session_id=session_id,
                    intent="collect_content",
                    workflow="m0_4d_unified_input",
                ),
                operation,
                outcome=self._run_outcome,
                reuse_queued=resume_queued,
            )
        except ProviderError as exc:
            raise TextCollectionProviderError(
                trace_id=trace_id,
                error_code=exc.code.value,
            ) from None
        except ApplicationRunTimeoutError:
            raise TextCollectionTimeoutError(trace_id=trace_id) from None
        except ApplicationRunFailureError as exc:
            raise TextCollectionRunError(
                trace_id=trace_id,
                error_code=exc.error_code,
            ) from None
        except (IdempotencyConflictError, ResourceNotFoundError):
            raise
        except SQLAlchemyError:
            raise TextCollectionRunError(
                trace_id=trace_id,
                error_code="RUN_DATABASE_ERROR",
            ) from None
        result = execution.result
        run_status, _ = self._run_outcome(result)
        return TextCollectionWorkflowResult(
            message=message,
            source=result.source,
            trace_id=execution.trace_id,
            run_status=run_status,
            extraction_result=result.extraction,
            auto_save_result=result.saved,
            recovery_actions=result.recovery_actions,
            error_code=result.error_code,
            replayed=message_replayed or bool(result.saved and result.saved.replayed),
        )

    async def _process_text(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        source_id: str,
        input: TextInput,
        observer: ApplicationRunObserver,
    ) -> _OperationResult:
        await observer.set_stage("place_recognition")
        timestamp = self._now()
        try:
            extraction = await TextExtractionService(
                self._require_provider(),
                structured_output_mode=self._structured_output_mode,
                response_observer=observer.record_model_response,
            ).extract(input.text)
        except ProviderError:
            await self._persist_source(
                Source(
                    id=source_id,
                    user_id=user_id,
                    type=SourceType.TEXT,
                    parse_status=SourceParseStatus.FAILED,
                    created_at=timestamp,
                    updated_at=self._now(),
                )
            )
            raise
        recovery_actions = (
            () if extraction.outcome is ExtractionOutcome.CANDIDATES else (_RECOVERY_SUPPLY_TEXT,)
        )
        source = self._with_extraction_summary(
            Source(
                id=source_id,
                user_id=user_id,
                type=SourceType.TEXT,
                parse_status=self._parse_status(extraction),
                created_at=timestamp,
                updated_at=self._now(),
            ),
            extraction=extraction,
            recovery_actions=recovery_actions,
        )
        await observer.set_stage("result_organizing")
        saved = await self._save_extraction(
            user_id=user_id,
            idempotency_key=idempotency_key,
            source=source,
            extraction=extraction,
        )
        return _OperationResult(
            source=source,
            extraction=extraction,
            saved=saved,
            recovery_actions=recovery_actions,
        )

    async def _process_url(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        source_id: str,
        input: UrlInput,
        observer: ApplicationRunObserver,
    ) -> _OperationResult:
        if self._web_provider is None:
            raise ApplicationRunFailureError(error_code="WEB_PROVIDER_NOT_CONFIGURED")
        web_provider = self._web_provider
        fingerprint = self._input_fingerprint(input)
        fetched = await observer.run_tool(
            tool_name="web_content_fetch",
            arguments_fingerprint=fingerprint,
            input_summary='{"input_type":"url"}',
            operation=lambda: web_provider.fetch(input.url),
            summarize=self._summarize_web_fetch,
        )
        await observer.set_stage("place_recognition")
        timestamp = self._now()
        if isinstance(fetched, WebFetchFailure):
            recovery_actions = tuple(action.value for action in fetched.recovery_actions)
            source = Source(
                id=source_id,
                user_id=user_id,
                type=SourceType.URL,
                url=input.url,
                parse_status=SourceParseStatus.FAILED,
                metadata=SourceMetadata(
                    http_status=fetched.http_status,
                    failure_code=fetched.code.value,
                    workflow_recovery_actions=recovery_actions,
                ),
                created_at=timestamp,
                updated_at=timestamp,
            )
            await self._persist_source(source)
            return _OperationResult(
                source=source,
                extraction=None,
                saved=AutoSaveResult(source_id=source.id),
                recovery_actions=recovery_actions,
                error_code=fetched.code.value,
            )

        source = self._url_source(
            source_id=source_id,
            user_id=user_id,
            original_url=input.url,
            fetched=fetched,
            parse_status=SourceParseStatus.PARSED,
            timestamp=timestamp,
        )
        try:
            extraction = await TextExtractionService(
                self._require_provider(),
                structured_output_mode=self._structured_output_mode,
                response_observer=observer.record_model_response,
            ).extract(fetched.text[:MAX_TEXT_INPUT_CHARS])
        except ProviderError:
            await self._persist_source(
                source.model_copy(
                    update={
                        "parse_status": SourceParseStatus.FAILED,
                        "updated_at": self._now(),
                    }
                )
            )
            raise
        recovery_actions = (
            ()
            if extraction.outcome is ExtractionOutcome.CANDIDATES
            else (_RECOVERY_SUPPLY_TEXT, _RECOVERY_SEND_SCREENSHOT)
        )
        source = self._with_extraction_summary(
            source.model_copy(
                update={
                    "parse_status": self._parse_status(extraction),
                    "updated_at": self._now(),
                }
            ),
            extraction=extraction,
            recovery_actions=recovery_actions,
        )
        await observer.set_stage("result_organizing")
        saved = await self._save_extraction(
            user_id=user_id,
            idempotency_key=idempotency_key,
            source=source,
            extraction=extraction,
        )
        return _OperationResult(
            source=source,
            extraction=extraction,
            saved=saved,
            recovery_actions=recovery_actions,
        )

    async def _process_image(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        source_id: str,
        input: ImageInput,
        observer: ApplicationRunObserver,
    ) -> _OperationResult:
        if self._storage is None or self._storage_config is None:
            raise ApplicationRunFailureError(error_code="IMAGE_PROVIDER_NOT_CONFIGURED")
        storage = self._storage
        storage_config = self._storage_config
        metadata = None
        try:
            await observer.set_stage("place_recognition")
            staged_source = await self._repository.get_source(
                user_id=user_id,
                source_id=source_id,
            )
            staged_payload = input.payload
            staged = (
                staged_source is not None
                and staged_source.type is SourceType.IMAGE
                and staged_source.file_key is not None
                and staged_source.parse_status is SourceParseStatus.PENDING
            )
            if staged:
                assert staged_source is not None
                assert staged_source.file_key is not None
                metadata, staged_payload = await storage.read_private(
                    staged_source.file_key
                )
                if (
                    metadata.content_type != input.content_type
                    or hashlib.sha256(staged_payload).hexdigest()
                    != hashlib.sha256(input.payload).hexdigest()
                ):
                    raise ApplicationRunFailureError(
                        error_code="IMAGE_STAGED_CONTENT_MISMATCH"
                    )

            async def recognize_image() -> tuple[PrivateFileMetadata, ExtractionResult]:
                service = ImageRecognitionService(
                    provider=self._require_provider(),
                    storage=storage,
                    storage_config=storage_config,
                    clock=self._now,
                    structured_output_mode=self._structured_output_mode,
                    response_observer=observer.record_model_response,
                )
                if staged:
                    staged_metadata = metadata
                    assert staged_metadata is not None
                    staged_extraction = await service.recognize_existing(
                        _single_chunk(staged_payload),
                        metadata=staged_metadata,
                        supplemental_text=input.supplemental_text,
                    )
                    return staged_metadata, staged_extraction
                return await service.recognize(
                    _single_chunk(input.payload),
                    content_type=input.content_type,
                    supplemental_text=input.supplemental_text,
                )

            metadata, extraction = await observer.run_tool(
                tool_name="image_recognition",
                arguments_fingerprint=self._input_fingerprint(input),
                input_summary=(f'{{"input_type":"image","media_type":"{input.content_type}"}}'),
                operation=recognize_image,
                summarize=lambda result: ApplicationToolOutcome(
                    succeeded=True,
                    output_summary=(
                        '{"outcome":"success","source_count":1,'
                        f'"candidate_count":{len(result[1].candidates)}}}'
                    ),
                ),
            )
            assert metadata is not None
            timestamp = self._now()
            recovery_actions = (
                ()
                if extraction.outcome is ExtractionOutcome.CANDIDATES
                else (_RECOVERY_SUPPLY_TEXT, _RECOVERY_REUPLOAD_IMAGE)
            )
            source = self._with_extraction_summary(
                Source(
                    id=source_id,
                    user_id=user_id,
                    type=SourceType.IMAGE,
                    file_key=metadata.file_key,
                    parse_status=self._parse_status(extraction),
                    fetched_at=metadata.created_at,
                    metadata=SourceMetadata(
                        media_type=metadata.content_type,
                        byte_size=metadata.byte_size,
                        content_sha256=metadata.content_sha256,
                    ),
                    created_at=(
                        staged_source.created_at
                        if staged and staged_source is not None
                        else timestamp
                    ),
                    updated_at=timestamp,
                ),
                extraction=extraction,
                recovery_actions=recovery_actions,
            )
            if staged:
                await self._repository.update_source(user_id=user_id, source=source)
                await self._session.commit()
            await observer.set_stage("result_organizing")
            saved = await self._save_extraction(
                user_id=user_id,
                idempotency_key=idempotency_key,
                source=source,
                extraction=extraction,
            )
            return _OperationResult(
                source=source,
                extraction=extraction,
                saved=saved,
                recovery_actions=recovery_actions,
            )
        except asyncio.CancelledError as cancellation:
            if metadata is not None and not staged:
                await self._cleanup_image_after_cancellation(
                    metadata.file_key,
                    cancellation,
                )
            raise
        except ProviderError:
            raise
        except (ImageRecognitionError, StorageProviderError) as exc:
            raise ApplicationRunFailureError(error_code=exc.code.value) from None
        except Exception:
            if metadata is not None and not staged:
                await self._cleanup_image(metadata.file_key)
            raise

    async def _save_extraction(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        source: Source,
        extraction: ExtractionResult,
    ) -> AutoSaveResult:
        if extraction.outcome is not ExtractionOutcome.CANDIDATES:
            await self._persist_source(source)
            return AutoSaveResult(source_id=source.id)
        saved = await CollectionWriteService(
            session=self._session,
            now=self._now,
        ).auto_save(
            user_id=user_id,
            idempotency_key=idempotency_key,
            source=source,
            extraction_result=extraction,
        )
        await self._record_event_location_candidates(
            user_id=user_id,
            source_id=source.id,
            saved=saved,
        )
        return saved

    async def _record_event_location_candidates(
        self,
        *,
        user_id: str,
        source_id: str,
        saved: AutoSaveResult,
    ) -> None:
        if self._event_place_matching is None or saved.replayed:
            return
        await self._session.rollback()
        for item in saved.items:
            if item.kind is not CollectionKind.EVENT or item.place_target is not None:
                continue
            has_city_hint, city_code = resolve_city_hint(item.city_hint)
            if not has_city_hint or city_code != PlanCity.SHENZHEN.value:
                continue
            candidate = self._event_location_candidate(item)
            try:
                result = await self._event_place_matching.match(
                    PlaceMatchRequest(
                        candidate=candidate,
                        city=CityScope(city_code=PlanCity.SHENZHEN.value),
                    )
                )
            except asyncio.CancelledError:
                raise
            except MapProviderError:
                continue
            await PlaceTargetSelectionService(session=self._session).record_candidates(
                user_id=user_id,
                collection_item_id=item.id,
                source_id=source_id,
                match_result=result,
                queried_at=self._now(),
                expected_version=item.version,
            )

    @staticmethod
    def _event_location_candidate(item: CollectionItem) -> PlaceCandidate:
        values: dict[CandidateField, object | None] = {
            CandidateField.CITY_HINT: item.city_hint,
            CandidateField.DISTRICT: item.district,
            CandidateField.ADDRESS: item.address,
            CandidateField.BUSINESS_DISTRICT: item.business_district,
            CandidateField.LANDMARK: item.landmark,
            CandidateField.METRO_STATION: item.metro_station,
            CandidateField.PRICE: item.price_amount,
            CandidateField.TAGS: item.tags or None,
        }
        return PlaceCandidate(
            title=item.address or item.landmark or item.title,
            city_hint=item.city_hint,
            district=item.district,
            address=item.address,
            business_district=item.business_district,
            landmark=item.landmark,
            metro_station=item.metro_station,
            price_amount=item.price_amount,
            price_currency=item.price_currency,
            tags=item.tags,
            missing_fields=tuple(
                field for field, value in values.items() if value is None
            ),
        )

    async def _persist_source(self, source: Source) -> Source:
        existing = await self._repository.get_source(
            user_id=source.user_id,
            source_id=source.id,
        )
        if existing is not None:
            if existing != source:
                raise IdempotencyConflictError
            return existing
        try:
            stored = await self._repository.add_source(
                user_id=source.user_id,
                source=source,
            )
            await self._session.commit()
            return stored
        except IntegrityError:
            await self._session.rollback()
            existing = await self._repository.get_source(
                user_id=source.user_id,
                source_id=source.id,
            )
            if existing is None or existing != source:
                raise IdempotencyConflictError from None
            return existing

    async def _cleanup_image(self, file_key: str) -> None:
        assert self._storage is not None
        try:
            await self._storage.delete(file_key)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise ApplicationRunFailureError(error_code="IMAGE_CLEANUP_FAILED") from None

    async def _cleanup_image_after_cancellation(
        self,
        file_key: str,
        cancellation: asyncio.CancelledError,
    ) -> None:
        """Preserve the original cancellation unless cleanup is itself cancelled."""

        assert self._storage is not None
        cleanup_cancellation: asyncio.CancelledError | None = None
        try:
            await self._storage.delete(file_key)
        except asyncio.CancelledError as error:
            cleanup_cancellation = error
        except Exception:
            pass
        if cleanup_cancellation is not None:
            raise cleanup_cancellation
        raise cancellation

    async def _replay(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        message: Message,
        source_id: str,
        existing_status: AgentRunStatus,
        existing_error_code: str | None,
        trace_id: str,
    ) -> TextCollectionWorkflowResult:
        if existing_status in {AgentRunStatus.QUEUED, AgentRunStatus.RUNNING}:
            raise IdempotentRequestInProgressError
        if existing_status is AgentRunStatus.FAILED:
            if existing_error_code == "RUN_TIMEOUT":
                raise TextCollectionTimeoutError(trace_id=trace_id)
            if (existing_error_code or "").startswith("PROVIDER_"):
                raise TextCollectionProviderError(
                    trace_id=trace_id,
                    error_code=existing_error_code or "PROVIDER_UNKNOWN",
                )
            raise TextCollectionRunError(
                trace_id=trace_id,
                error_code=existing_error_code or "RUN_INTERNAL_ERROR",
            )
        if existing_status is AgentRunStatus.CANCELLED:
            raise TextCollectionRunError(
                trace_id=trace_id,
                error_code=existing_error_code or "RUN_CANCELLED",
            )
        source = await self._repository.get_source(user_id=user_id, source_id=source_id)
        previous = await CollectionWriteService(
            session=self._session,
            now=self._now,
        ).get_idempotent_result(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if previous is None and source is not None:
            previous = AutoSaveResult(source_id=source.id, replayed=True)
        recovery = () if source is None else source.metadata.workflow_recovery_actions
        extraction = self._extraction_from_source(source, previous)
        return TextCollectionWorkflowResult(
            message=message,
            source=source,
            trace_id=trace_id,
            run_status=existing_status,
            extraction_result=extraction,
            auto_save_result=previous,
            recovery_actions=recovery,
            error_code=(
                existing_error_code
                if source is None or source.metadata.failure_code is None
                else source.metadata.failure_code
            ),
            replayed=True,
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
    def _message_projection(input: CollectionInput) -> tuple[str, MessageContentType]:
        if isinstance(input, TextInput):
            return input.text, MessageContentType.TEXT
        if isinstance(input, UrlInput):
            try:
                value = validate_web_url(input.url).normalized_url
            except UrlPolicyError:
                value = input.url
            return value, MessageContentType.URL
        return (
            input.message_content(),
            MessageContentType.IMAGE,
        )

    @staticmethod
    def _input_fingerprint(input: CollectionInput) -> str:
        if isinstance(input, TextInput):
            value = f"text\0{input.text}"
        elif isinstance(input, UrlInput):
            try:
                url = validate_web_url(input.url).normalized_url
            except UrlPolicyError:
                url = input.url
            value = f"url\0{url}"
        else:
            value = f"image\0{input.content_type}\0{input.content_sha256}"
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _with_extraction_summary(
        source: Source,
        *,
        extraction: ExtractionResult,
        recovery_actions: tuple[str, ...],
    ) -> Source:
        metadata = source.metadata.model_copy(
            update={
                "extraction_outcome": extraction.outcome,
                "extraction_reason_code": extraction.reason_code,
                "extraction_unsupported_reason": extraction.unsupported_reason,
                "extraction_missing_fields": extraction.missing_fields,
                "extraction_uncertainties": extraction.uncertainties,
                "extraction_recovery_suggestions": extraction.recovery_suggestions,
                "workflow_recovery_actions": recovery_actions,
            }
        )
        return source.model_copy(update={"metadata": metadata})

    @staticmethod
    def _extraction_from_source(
        source: Source | None,
        saved: AutoSaveResult | None,
    ) -> ExtractionResult | None:
        if source is None:
            return None
        outcome = source.metadata.extraction_outcome
        if outcome is None:
            return None
        if outcome is ExtractionOutcome.CANDIDATES:
            if saved is None or not saved.items:
                return None
            candidates: list[PlaceCandidate | EventCandidate] = []
            for item in saved.items:
                candidate_data: dict[str, object] = {
                    "kind": item.kind,
                    "title": item.title,
                    "city_hint": item.city_hint,
                    "district": item.district,
                    "address": item.address,
                    "business_district": item.business_district,
                    "landmark": item.landmark,
                    "metro_station": item.metro_station,
                    "price_amount": item.price_amount,
                    "price_currency": item.price_currency,
                    "tags": item.tags,
                    "missing_fields": item.missing_fields,
                    "uncertainties": item.uncertainties,
                }
                if item.kind is CollectionKind.PLACE:
                    candidates.append(PlaceCandidate.model_validate(candidate_data))
                else:
                    candidate_data.update(
                        {
                            "event_start_date": item.event_start_date,
                            "event_end_date": item.event_end_date,
                            "event_start_at": item.event_start_at,
                            "event_end_at": item.event_end_at,
                            "event_start_clue": item.event_start_clue,
                            "event_end_clue": item.event_end_clue,
                        }
                    )
                    candidates.append(
                        EventCandidate.model_validate(candidate_data)
                    )
            return ExtractionResult.with_candidates(tuple(candidates))
        return ExtractionResult(
            outcome=outcome,
            reason_code=source.metadata.extraction_reason_code,
            unsupported_reason=source.metadata.extraction_unsupported_reason,
            missing_fields=source.metadata.extraction_missing_fields,
            uncertainties=source.metadata.extraction_uncertainties,
            recovery_suggestions=source.metadata.extraction_recovery_suggestions,
        )

    @staticmethod
    def _run_outcome(result: _OperationResult) -> tuple[AgentRunStatus, str | None]:
        if result.error_code is not None:
            return AgentRunStatus.PARTIALLY_SUCCEEDED, result.error_code
        return AgentRunStatus.SUCCEEDED, None

    @staticmethod
    def _parse_status(extraction: ExtractionResult) -> SourceParseStatus:
        return (
            SourceParseStatus.PARSED
            if extraction.outcome is ExtractionOutcome.CANDIDATES
            else SourceParseStatus.FAILED
        )

    @staticmethod
    def _url_source(
        *,
        source_id: str,
        user_id: str,
        original_url: str,
        fetched: WebPageContent,
        parse_status: SourceParseStatus,
        timestamp: datetime,
    ) -> Source:
        return Source(
            id=source_id,
            user_id=user_id,
            type=SourceType.URL,
            url=original_url,
            parse_status=parse_status,
            fetched_at=fetched.fetched_at,
            metadata=SourceMetadata(
                media_type=fetched.content_type,
                byte_size=fetched.diagnostics.decoded_byte_size,
                http_status=fetched.diagnostics.http_status,
                final_url=fetched.final_url,
                redirect_count=fetched.diagnostics.redirect_count,
                text_truncated=fetched.diagnostics.text_truncated,
            ),
            created_at=timestamp,
            updated_at=timestamp,
        )

    @staticmethod
    def _summarize_web_fetch(
        result: WebPageContent | WebFetchFailure,
    ) -> ApplicationToolOutcome:
        if isinstance(result, WebFetchFailure):
            return ApplicationToolOutcome(
                succeeded=False,
                output_summary='{"outcome":"failure","source_count":1}',
                error_code=result.code.value,
            )
        return ApplicationToolOutcome(
            succeeded=True,
            output_summary='{"outcome":"success","source_count":1}',
        )

    @staticmethod
    def _scoped_idempotency_key(session_id: str, idempotency_key: str) -> str:
        digest = hashlib.sha256(
            f"collection-write\0{session_id}\0{idempotency_key}".encode()
        ).hexdigest()
        return f"req_{digest}"

    async def _select_write_key(
        self,
        *,
        user_id: str,
        session_id: str,
        source_id: str,
        idempotency_key: str,
    ) -> str:
        existing = await self._repository.get_write_operation_by_idempotency_key(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if existing is None or existing.source_id == source_id:
            return idempotency_key
        return self._scoped_idempotency_key(session_id, idempotency_key)

    @staticmethod
    def _opaque_id(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256((prefix + "\0" + "\0".join(parts)).encode()).hexdigest()[:32]
        return f"{prefix}_{digest}"

    @staticmethod
    def _trace_id(user_id: str, session_id: str, idempotency_key: str) -> str:
        digest = hashlib.sha256(
            f"trace\0{user_id}\0{session_id}\0{idempotency_key}".encode()
        ).hexdigest()[:32]
        return f"trc_{digest}"


async def _single_chunk(payload: bytes):  # type: ignore[no-untyped-def]
    yield payload


__all__ = [
    "IdempotencyLockRegistry",
    "IdempotentRequestInProgressError",
    "MAX_RICH_INPUT_WORKFLOW_SECONDS",
    "PreparedCollectionImport",
    "TextCollectionProviderError",
    "TextCollectionRunError",
    "TextCollectionTimeoutError",
    "TextCollectionWorkflow",
    "TextCollectionWorkflowResult",
]

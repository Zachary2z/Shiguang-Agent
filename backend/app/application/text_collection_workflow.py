"""The single Text/URL/Image input workflow for collection ingestion."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.collection_writes import CollectionWriteService
from app.application.image_recognition import (
    ImageRecognitionError,
    ImageRecognitionService,
)
from app.application.input_contracts import CollectionInput, ImageInput, TextInput, UrlInput
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
    CollectionKind,
    EventCandidate,
    ExtractionOutcome,
    ExtractionResult,
    IdempotencyConflictError,
    Message,
    MessageContentType,
    MessageRole,
    PlaceCandidate,
    ResourceNotFoundError,
    Source,
    SourceMetadata,
    SourceParseStatus,
    SourceType,
)
from app.domain.collections.writes import validate_idempotency_key
from app.domain.runs import AgentRunCreate, AgentRunStatus
from app.domain.time import utc_now
from app.domain.web import WebFetchFailure, WebPageContent
from app.domain.web.security import UrlPolicyError, validate_web_url
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.providers.storage import StorageProvider, StorageProviderError
from app.providers.web import WebContentProvider
from nanobot_core.providers import ModelProvider, ProviderError

MAX_RICH_INPUT_WORKFLOW_SECONDS = 20.0
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
class _OperationResult:
    source: Source | None
    extraction: ExtractionResult | None
    saved: AutoSaveResult | None
    recovery_actions: tuple[str, ...] = ()
    error_code: str | None = None


class IdempotencyLockRegistry:
    """Serialize same-process retries while database uniqueness stays authoritative."""

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def lock(
        self,
        *,
        user_id: str,
        session_id: str = "legacy",
        idempotency_key: str,
    ) -> asyncio.Lock:
        del session_id
        return self._locks.setdefault((user_id, idempotency_key), asyncio.Lock())


class TextCollectionWorkflow:
    """Persist and process all three P0 inputs through one collection state machine."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        provider: ModelProvider,
        pricing: PricingPolicy,
        locks: IdempotencyLockRegistry,
        timeout_seconds: float,
        web_provider: WebContentProvider | None = None,
        storage: StorageProvider | None = None,
        storage_config: StorageProviderSettings | None = None,
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
            )

    async def _submit_locked(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        input: CollectionInput,
    ) -> TextCollectionWorkflowResult:
        owned_session = await self._repository.get_session(
            user_id=user_id,
            session_id=session_id,
        )
        if owned_session is None:
            await self._session.rollback()
            raise ResourceNotFoundError

        message_id = self._opaque_id("msg", user_id, session_id, idempotency_key)
        source_id = self._opaque_id("src", user_id, session_id, idempotency_key)
        trace_id = self._trace_id(user_id, session_id, idempotency_key)
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
        if existing_run is not None:
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
        timestamp = self._now()
        try:
            extraction = await TextExtractionService(
                self._provider,
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
                self._provider,
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
            metadata, extraction = await observer.run_tool(
                tool_name="image_recognition",
                arguments_fingerprint=self._input_fingerprint(input),
                input_summary=(f'{{"input_type":"image","media_type":"{input.content_type}"}}'),
                operation=lambda: ImageRecognitionService(
                    provider=self._provider,
                    storage=storage,
                    storage_config=storage_config,
                    clock=self._now,
                    response_observer=observer.record_model_response,
                ).recognize(
                    _single_chunk(input.payload),
                    content_type=input.content_type,
                ),
                summarize=lambda result: ApplicationToolOutcome(
                    succeeded=True,
                    output_summary=(
                        '{"outcome":"success","source_count":1,'
                        f'"candidate_count":{len(result[1].candidates)}}}'
                    ),
                ),
            )
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
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
                extraction=extraction,
                recovery_actions=recovery_actions,
            )
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
            if metadata is not None:
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
            if metadata is not None:
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
        return await CollectionWriteService(
            session=self._session,
            now=self._now,
        ).auto_save(
            user_id=user_id,
            idempotency_key=idempotency_key,
            source=source,
            extraction_result=extraction,
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
            f"image:{input.content_type}:sha256:{input.content_sha256}",
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
    "TextCollectionProviderError",
    "TextCollectionRunError",
    "TextCollectionTimeoutError",
    "TextCollectionWorkflow",
    "TextCollectionWorkflowResult",
]

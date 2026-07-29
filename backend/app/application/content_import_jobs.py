"""M1-3 asynchronous content import on the existing JobQueue and workflow."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.image_recognition import ORIGINAL_SCREENSHOT_RETENTION_DAYS
from app.application.input_contracts import CollectionInput, ImageInput, TextInput, UrlInput
from app.application.place_matching import PlaceMatchingService
from app.application.pricing import PricingPolicy
from app.application.text_collection_workflow import (
    IdempotencyLockRegistry,
    TextCollectionProviderError,
    TextCollectionRunError,
    TextCollectionTimeoutError,
    TextCollectionWorkflow,
)
from app.config import StorageProviderSettings
from app.domain.collections import (
    IdempotencyConflictError,
    MessageContentType,
    ResourceNotFoundError,
    Source,
    SourceMetadata,
    SourceParseStatus,
    SourceType,
)
from app.domain.jobs import JobCreate, JobResultSummary, ScheduledJob
from app.domain.places import PlaceMatchingPolicy
from app.domain.runs import AgentRunStatus
from app.domain.time import utc_now
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import AgentRunRepository, SqlAlchemyCollectionRepository
from app.providers.jobs import JobQueue
from app.providers.map import MapProvider
from app.providers.storage import (
    RetentionPolicy,
    StorageProvider,
)
from app.providers.web import WebContentProvider
from nanobot_core.providers import ModelProvider, StructuredOutputMode

CONTENT_IMPORT_JOB_TYPE = "content.import"


class ContentImportJobPayload(BaseModel):
    """Allowlisted identifiers only; user content and storage keys stay out of jobs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    session_id: str
    message_id: str
    source_id: str
    input_type: Literal["text", "url", "image"]


class ContentImportSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    message_id: str
    trace_id: str
    input_type: MessageContentType
    run_status: AgentRunStatus
    replayed: bool


def scoped_import_key(*, user_id: str, session_id: str, client_key: str) -> str:
    digest = hashlib.sha256(
        f"{user_id}\0{session_id}\0{client_key}".encode()
    ).hexdigest()
    return f"import.{digest}"


class ContentImportSubmissionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        pricing: PricingPolicy,
        locks: IdempotencyLockRegistry,
        timeout_seconds: float,
        storage: StorageProvider | None,
        queue: JobQueue | None = None,
    ) -> None:
        self._session = session
        self._queue = queue or PostgresJobQueue(session_factory)
        self._pricing = pricing
        self._locks = locks
        self._timeout_seconds = timeout_seconds
        self._storage = storage
        self._repository = SqlAlchemyCollectionRepository(session)

    async def submit(
        self,
        *,
        user_id: str,
        session_id: str,
        client_idempotency_key: str,
        input: CollectionInput,
    ) -> ContentImportSubmission:
        key = scoped_import_key(
            user_id=user_id,
            session_id=session_id,
            client_key=client_idempotency_key,
        )
        workflow = TextCollectionWorkflow(
            session=self._session,
            provider=None,
            pricing=self._pricing,
            locks=self._locks,
            timeout_seconds=self._timeout_seconds,
        )
        source_id = workflow.source_id_for(
            user_id=user_id,
            session_id=session_id,
            idempotency_key=key,
        )
        prepared = None
        try:
            prepared = await workflow.prepare_input(
                user_id=user_id,
                session_id=session_id,
                idempotency_key=key,
                input=input,
            )
            if isinstance(input, ImageInput):
                await self._stage_image(
                    user_id=user_id,
                    source_id=source_id,
                    input=input,
                )
            payload = ContentImportJobPayload(
                session_id=session_id,
                message_id=prepared.message.id,
                source_id=source_id,
                input_type=prepared.message.content_type.value,
            )
            request = JobCreate(
                user_id=user_id,
                job_type=CONTENT_IMPORT_JOB_TYPE,
                payload=payload.model_dump(mode="json"),
                run_at=prepared.run_created_at,
                idempotency_key=key,
                trace_id=prepared.trace_id,
            )
            job = await self._queue.create(request)
        except BaseException as error:
            if prepared is None:
                raise
            existing = await asyncio.shield(
                self._queue.get_by_trace(
                    user_id=user_id,
                    trace_id=prepared.trace_id,
                )
            )
            if existing is None:
                await asyncio.shield(
                    self._compensate_unqueued_import(
                        user_id=user_id,
                        message_id=prepared.message.id,
                        trace_id=prepared.trace_id,
                        source_id=source_id,
                    )
                )
            if isinstance(error, asyncio.CancelledError) or existing is None:
                raise
            job = existing
        return ContentImportSubmission(
            message_id=prepared.message.id,
            trace_id=prepared.trace_id,
            input_type=prepared.message.content_type,
            run_status=prepared.run_status,
            replayed=prepared.replayed or job.replayed,
        )

    async def _compensate_unqueued_import(
        self,
        *,
        user_id: str,
        message_id: str,
        trace_id: str,
        source_id: str,
    ) -> None:
        source = await self._repository.get_source(
            user_id=user_id,
            source_id=source_id,
        )
        file_key = None if source is None else source.file_key
        await self._repository.delete_source(
            user_id=user_id,
            source_id=source_id,
        )
        await self._repository.delete_message(
            user_id=user_id,
            message_id=message_id,
        )
        await AgentRunRepository(self._session).delete_queued_by_trace_id(
            user_id=user_id,
            trace_id=trace_id,
        )
        await self._session.commit()
        if file_key is not None and self._storage is not None:
            await self._storage.delete(file_key)

    async def _stage_image(
        self,
        *,
        user_id: str,
        source_id: str,
        input: ImageInput,
    ) -> None:
        if self._storage is None:
            raise RuntimeError("private storage is required for image imports")
        existing = await self._repository.get_source(
            user_id=user_id,
            source_id=source_id,
        )
        expected_sha = hashlib.sha256(input.payload).hexdigest()
        if existing is not None:
            if (
                existing.type is not SourceType.IMAGE
                or existing.metadata.content_sha256 != expected_sha
                or existing.metadata.media_type != input.content_type
            ):
                raise IdempotencyConflictError
            return
        metadata = await self._storage.put_private(
            _single_chunk(input.payload),
            content_type=input.content_type,
            retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
            expires_at=utc_now() + timedelta(days=ORIGINAL_SCREENSHOT_RETENTION_DAYS),
        )
        timestamp = utc_now()
        source = Source(
            id=source_id,
            user_id=user_id,
            type=SourceType.IMAGE,
            file_key=metadata.file_key,
            parse_status=SourceParseStatus.PENDING,
            fetched_at=metadata.created_at,
            metadata=SourceMetadata(
                media_type=metadata.content_type,
                byte_size=metadata.byte_size,
                content_sha256=metadata.content_sha256,
            ),
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            await self._repository.add_source(user_id=user_id, source=source)
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            await self._storage.delete(metadata.file_key)
            replay = await self._repository.get_source(
                user_id=user_id,
                source_id=source_id,
            )
            if (
                replay is None
                or replay.metadata.content_sha256 != expected_sha
                or replay.metadata.media_type != input.content_type
            ):
                raise IdempotencyConflictError from None
        except BaseException:
            await asyncio.shield(self._session.rollback())
            await asyncio.shield(self._storage.delete(metadata.file_key))
            raise


class ContentImportJobHandler:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        provider: ModelProvider | None,
        pricing: PricingPolicy,
        locks: IdempotencyLockRegistry,
        timeout_seconds: float,
        web_provider: WebContentProvider | None = None,
        storage: StorageProvider | None = None,
        storage_config: StorageProviderSettings | None = None,
        structured_output_mode: StructuredOutputMode | None = None,
        map_provider: MapProvider | None = None,
        matching_policy: PlaceMatchingPolicy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._pricing = pricing
        self._locks = locks
        self._timeout_seconds = timeout_seconds
        self._web_provider = web_provider
        self._storage = storage
        self._storage_config = storage_config
        self._structured_output_mode = structured_output_mode
        self._event_place_matching = (
            None
            if map_provider is None or matching_policy is None
            else PlaceMatchingService(
                map_provider=map_provider,
                policy=matching_policy,
            )
        )

    async def __call__(self, job: ScheduledJob) -> JobResultSummary:
        payload = ContentImportJobPayload.model_validate(job.payload, strict=True)
        async with self._session_factory() as session:
            repository = SqlAlchemyCollectionRepository(session)
            message = await repository.get_message(
                user_id=job.user_id,
                message_id=payload.message_id,
            )
            if message is None or message.session_id != payload.session_id:
                raise ResourceNotFoundError
            input = await self._restore_input(
                repository=repository,
                user_id=job.user_id,
                payload=payload,
                content=message.content,
            )
            try:
                result = await TextCollectionWorkflow(
                    session=session,
                    provider=self._provider,
                    pricing=self._pricing,
                    locks=self._locks,
                    timeout_seconds=self._timeout_seconds,
                    web_provider=self._web_provider,
                    storage=self._storage,
                    storage_config=self._storage_config,
                    structured_output_mode=self._structured_output_mode,
                    event_place_matching=self._event_place_matching,
                ).submit_input(
                    user_id=job.user_id,
                    session_id=payload.session_id,
                    idempotency_key=job.idempotency_key,
                    input=input,
                    resume_queued=True,
                )
            except (
                TextCollectionProviderError,
                TextCollectionRunError,
                TextCollectionTimeoutError,
            ):
                return JobResultSummary(outcome="failed")
            return JobResultSummary(outcome=result.run_status.value)

    async def _restore_input(
        self,
        *,
        repository: SqlAlchemyCollectionRepository,
        user_id: str,
        payload: ContentImportJobPayload,
        content: str,
    ) -> CollectionInput:
        if payload.input_type == MessageContentType.TEXT.value:
            return TextInput(text=content)
        if payload.input_type == MessageContentType.URL.value:
            return UrlInput(url=content)
        if self._storage is None:
            raise RuntimeError("private storage is required for image imports")
        source = await repository.get_source(
            user_id=user_id,
            source_id=payload.source_id,
        )
        if source is None or source.file_key is None:
            raise ResourceNotFoundError
        metadata, file_bytes = await self._storage.read_private(source.file_key)
        return ImageInput.from_bytes(
            file_bytes,
            content_type=metadata.content_type,
            supplemental_text=ImageInput.supplemental_text_from_message(content),
        )


async def _single_chunk(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


__all__ = [
    "CONTENT_IMPORT_JOB_TYPE",
    "ContentImportJobHandler",
    "ContentImportJobPayload",
    "ContentImportSubmission",
    "ContentImportSubmissionService",
    "scoped_import_key",
]

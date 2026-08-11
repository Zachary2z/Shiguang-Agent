"""M1-3 asynchronous content import on the existing JobQueue and workflow."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.agent_intents import (
    AgentIntentError,
    AgentIntentParser,
    AnyBranchIntent,
    CollectionIntent,
    MemoryIntent,
    PlanIntent,
)
from app.application.image_recognition import ORIGINAL_SCREENSHOT_RETENTION_DAYS
from app.application.input_contracts import (
    CollectionInput,
    ImageInput,
    TextInput,
    UrlInput,
)
from app.application.memories import MemoryService
from app.application.place_matching import PlaceMatchingService
from app.application.place_targets import PlaceTargetSelectionService
from app.application.plan_experience import PlanExperienceService
from app.application.pricing import PricingPolicy
from app.application.run_tracking import (
    AgentRunService,
    ApplicationRunFailureError,
    ApplicationRunObserver,
)
from app.application.text_collection_workflow import (
    IdempotencyLockRegistry,
    TextCollectionProviderError,
    TextCollectionRunError,
    TextCollectionTimeoutError,
    TextCollectionWorkflow,
)
from app.config import StorageProviderSettings
from app.domain.collections import (
    CollectionKind,
    CollectionStatus,
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
from app.domain.identifiers import generate_message_id
from app.domain.jobs import MAX_JOB_ATTEMPTS, JobCreate, JobResultSummary, ScheduledJob
from app.domain.memories import MemoryType
from app.domain.places import (
    Coordinate,
    EvidenceField,
    EvidenceOutcome,
    MatchStatus,
    PlaceMatchingPolicy,
    PlaceMatchRequest,
    PlaceMatchResult,
    PlaceSelection,
    PlaceSelectionKind,
    normalize_brand_name,
)
from app.domain.plans import MissingPlanConstraintInfo, resolve_plan_constraints
from app.domain.runs import AgentRunCreate, AgentRunStatus
from app.domain.time import utc_now
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import AgentRunRepository, SqlAlchemyCollectionRepository
from app.providers.jobs import JobQueue
from app.providers.map import MapProvider, MapProviderError
from app.providers.storage import (
    RetentionPolicy,
    StorageProvider,
)
from app.providers.web import WebContentProvider
from nanobot_core.providers import ModelProvider, StructuredOutputMode

CONTENT_IMPORT_JOB_TYPE = "content.import"
AGENT_MESSAGE_JOB_TYPE = "agent.message"


def _plan_origin_coordinate(match: PlaceMatchResult) -> Coordinate | None:
    if match.status is MatchStatus.MATCHED:
        return match.candidates[0].coordinate.model_copy(deep=True)
    exact_candidates = tuple(
        candidate
        for candidate in match.candidates
        if not candidate.has_hard_conflict
        and {EvidenceField.NAME, EvidenceField.CITY}.issubset(
            {
                evidence.field
                for evidence in candidate.evidence
                if evidence.outcome is EvidenceOutcome.MATCH
            }
        )
    )
    if len(exact_candidates) != 1:
        return None
    return exact_candidates[0].coordinate.model_copy(deep=True)


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
        route_agent: bool = False,
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
                intent="route_agent" if route_agent else "collect_content",
                workflow="agent.intent" if route_agent else "m1_3_content_import",
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
                job_type=(
                    AGENT_MESSAGE_JOB_TYPE if route_agent else CONTENT_IMPORT_JOB_TYPE
                ),
                payload=payload.model_dump(mode="json"),
                run_at=prepared.run_created_at,
                idempotency_key=key,
                trace_id=prepared.trace_id,
                max_attempts=1 if route_agent else MAX_JOB_ATTEMPTS,
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
        self._intent_parser = (
            None
            if provider is None
            else AgentIntentParser(
                provider,
                structured_output_mode=structured_output_mode,
            )
        )
        self._place_matching = (
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
            if job.job_type == AGENT_MESSAGE_JOB_TYPE:
                if not isinstance(input, TextInput):
                    raise ApplicationRunFailureError(error_code="AGENT_INPUT_INVALID")
                return await self._execute_agent_message(
                    session=session,
                    repository=repository,
                    job=job,
                    payload=payload,
                    input=input,
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
                    place_matching=self._place_matching,
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

    async def _execute_agent_message(
        self,
        *,
        session: AsyncSession,
        repository: SqlAlchemyCollectionRepository,
        job: ScheduledJob,
        payload: ContentImportJobPayload,
        input: TextInput,
    ) -> JobResultSummary:
        async def operation(observer: ApplicationRunObserver) -> JobResultSummary:
            if self._intent_parser is None:
                raise ApplicationRunFailureError(
                    error_code="MODEL_PROVIDER_NOT_CONFIGURED"
                )
            pending_messages, pending_intent = await self._pending_messages(
                repository=repository,
                user_id=job.user_id,
                session_id=payload.session_id,
                current_message_id=payload.message_id,
            )
            pending_context = (
                "\n".join(
                    f"{message.role.value}: {message.content}"
                    for message in pending_messages
                )
                or None
            )
            try:
                intent = await self._intent_parser.parse(
                    text=input.text,
                    now=utc_now(),
                    pending_context=pending_context,
                    response_observer=observer.record_model_response,
                )
            except AgentIntentError:
                raise ApplicationRunFailureError(error_code=AgentIntentError.code) from None
            if isinstance(intent, CollectionIntent):
                await TextCollectionWorkflow(
                    session=session,
                    provider=None,
                    pricing=self._pricing,
                    locks=self._locks,
                    timeout_seconds=self._timeout_seconds,
                    place_matching=self._place_matching,
                ).save_routed_text(
                    user_id=job.user_id,
                    idempotency_key=job.idempotency_key,
                    source_id=payload.source_id,
                    input=input,
                    extraction=intent.extraction,
                    observer=observer,
                )
                return JobResultSummary(
                    outcome="succeeded",
                    intent="collect_content",
                )
            if isinstance(intent, AnyBranchIntent):
                pending = [
                    item
                    for item in await repository.list_collection_items(
                        user_id=job.user_id,
                        include_inactive=True,
                    )
                    if item.kind is CollectionKind.PLACE
                    and item.status is CollectionStatus.PENDING_SELECTION
                    and item.place_candidate_snapshot is not None
                    and item.place_candidate_snapshot.candidates
                ]
                matches = pending
                if intent.target_title is not None:
                    try:
                        target_title = normalize_brand_name(intent.target_title)
                    except ValueError:
                        matches = []
                    else:
                        matches = []
                        for item in pending:
                            snapshot = item.place_candidate_snapshot
                            assert snapshot is not None
                            for title in (
                                item.title,
                                *(candidate.name for candidate in snapshot.candidates),
                            ):
                                try:
                                    matched = target_title == normalize_brand_name(title)
                                except ValueError:
                                    continue
                                if matched:
                                    matches.append(item)
                                    break
                if len(matches) != 1:
                    question = "请先说明要把哪一条待选择收藏保存为任意分店。"
                    await self._add_assistant_message(
                        repository=repository,
                        user_id=job.user_id,
                        session_id=payload.session_id,
                        trace_id=job.trace_id,
                        content=question,
                    )
                    return JobResultSummary(
                        outcome="waiting_user",
                        intent="select_any_branch",
                        question=question,
                    )
                item = matches[0]
                snapshot = item.place_candidate_snapshot
                assert snapshot is not None
                await session.rollback()
                selection_result = await PlaceTargetSelectionService(
                    session=session
                ).apply_user_selection(
                    user_id=job.user_id,
                    collection_item_id=item.id,
                    selections=(PlaceSelection(kind=PlaceSelectionKind.ANY_BRANCH),),
                    queried_at=snapshot.queried_at,
                    snapshot_fingerprint=snapshot.fingerprint,
                    idempotency_key=job.idempotency_key,
                    expected_version=item.version,
                )
                saved = selection_result.items[0]
                message = f"已把“{saved.title}”保存为任意分店。"
                await self._add_assistant_message(
                    repository=repository,
                    user_id=job.user_id,
                    session_id=payload.session_id,
                    trace_id=job.trace_id,
                    content=message,
                )
                return JobResultSummary(
                    outcome="succeeded",
                    intent="select_any_branch",
                    question=message,
                )
            if isinstance(intent, PlanIntent):
                now = utc_now()
                original_request = "\n".join(
                    [
                        message.content
                        for message in pending_messages
                        if pending_intent in {"plan", "clarify"}
                        and message.role is MessageRole.USER
                    ]
                    + [input.text]
                )
                origin = None
                if intent.origin_query is not None:
                    if self._place_matching is None:
                        raise ApplicationRunFailureError(
                            error_code="MAP_PROVIDER_NOT_CONFIGURED"
                        )
                    district = (
                        intent.area.districts[0]
                        if intent.area is not None
                        and len(intent.area.districts) == 1
                        else None
                    )
                    try:
                        match = await self._place_matching.match(
                            PlaceMatchRequest(
                                candidate=PlaceCandidate(
                                    title=intent.origin_query,
                                    city_hint="深圳",
                                    district=district,
                                ),
                                city=intent.constraints(now=now).city_scope,
                                search_district=district,
                                source_context=SecretStr(input.text),
                            )
                        )
                    except MapProviderError as error:
                        raise ApplicationRunFailureError(
                            error_code=error.code.value
                        ) from None
                    origin = _plan_origin_coordinate(match)
                    if origin is None:
                        question = (
                            "请补充更准确的出发点，例如完整地点名称、地址或地铁站出入口。"
                        )
                        await self._add_assistant_message(
                            repository=repository,
                            user_id=job.user_id,
                            session_id=payload.session_id,
                            trace_id=job.trace_id,
                            content=question,
                        )
                        return JobResultSummary(
                            outcome="waiting_user",
                            intent="plan",
                            question=question,
                        )
                resolved = resolve_plan_constraints(
                    intent.constraints(
                        now=now,
                        origin=origin,
                        original_request=original_request,
                    ),
                    now=now,
                )
                if isinstance(resolved, MissingPlanConstraintInfo):
                    question = (
                        "你什么时候有一段连续空闲时间？"
                        if resolved.field.value == "time_window"
                        else "你想在哪个区域活动或从哪里出发？"
                    )
                    await self._add_assistant_message(
                        repository=repository,
                        user_id=job.user_id,
                        session_id=payload.session_id,
                        trace_id=job.trace_id,
                        content=question,
                    )
                    return JobResultSummary(
                        outcome="waiting_user",
                        intent="plan",
                        question=question,
                    )
                submission = await PlanExperienceService(
                    session=session,
                    session_factory=self._session_factory,
                    pricing=self._pricing,
                ).create(
                    user_id=job.user_id,
                    constraints=resolved,
                    client_idempotency_key=job.idempotency_key,
                )
                return JobResultSummary(
                    outcome="succeeded",
                    intent="plan",
                    plan_id=submission.plan.id,
                )
            if isinstance(intent, MemoryIntent):
                if intent.authorization != "explicit":
                    question = "要把这条偏好记住，供以后的计划使用吗？"
                    await self._add_assistant_message(
                        repository=repository,
                        user_id=job.user_id,
                        session_id=payload.session_id,
                        trace_id=job.trace_id,
                        content=question,
                    )
                    return JobResultSummary(
                        outcome="waiting_user",
                        intent="memory",
                        question=question,
                    )
                result = await MemoryService(session).create_explicit(
                    user_id=job.user_id,
                    memory_type=MemoryType(intent.type),
                    content=intent.content,
                    value=intent.value,
                    expires_at=None,
                    explicit_authorization=True,
                    location_granularity=None,
                    client_idempotency_key=job.idempotency_key,
                )
                return JobResultSummary(
                    outcome="succeeded",
                    intent="memory",
                    question="已记住，可在“我的”中修改或删除。",
                    memory_id=result.memory.id,
                )
            await self._add_assistant_message(
                repository=repository,
                user_id=job.user_id,
                session_id=payload.session_id,
                trace_id=job.trace_id,
                content=intent.question,
            )
            return JobResultSummary(
                outcome="waiting_user",
                intent="clarify",
                question=intent.question,
            )

        execution = await AgentRunService(
            session=session,
            runner=None,
            pricing=self._pricing,
            timeout_seconds=self._timeout_seconds,
        ).execute_application(
            AgentRunCreate(
                trace_id=job.trace_id,
                user_id=job.user_id,
                session_id=payload.session_id,
                intent="route_agent",
                workflow="agent.intent",
            ),
            operation,
            reuse_queued=True,
        )
        return execution.result

    @staticmethod
    async def _add_assistant_message(
        *,
        repository: SqlAlchemyCollectionRepository,
        user_id: str,
        session_id: str,
        trace_id: str | None,
        content: str,
    ) -> None:
        if trace_id is None:
            raise ValueError("routed jobs require a trace")
        await repository.add_message(
            user_id=user_id,
            message=Message(
                id=generate_message_id(),
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content_type=MessageContentType.TEXT,
                content=content,
                trace_id=trace_id,
                created_at=utc_now(),
            ),
        )

    async def _pending_messages(
        self,
        *,
        repository: SqlAlchemyCollectionRepository,
        user_id: str,
        session_id: str,
        current_message_id: str,
    ) -> tuple[tuple[Message, ...], str | None]:
        messages = [
            item
            for item in await repository.list_messages(
                user_id=user_id,
                session_id=session_id,
                limit=3,
            )
            if item.id != current_message_id
        ]
        if not messages or messages[-1].role is not MessageRole.ASSISTANT:
            return (), None
        trace_id = messages[-1].trace_id
        if trace_id is None:
            return (), None
        previous_job = await PostgresJobQueue(self._session_factory).get_by_trace(
            user_id=user_id,
            trace_id=trace_id,
        )
        if (
            previous_job is None
            or previous_job.result_summary is None
            or previous_job.result_summary.outcome != "waiting_user"
        ):
            return (), None
        return tuple(messages[-2:]), previous_job.result_summary.intent

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
    "AGENT_MESSAGE_JOB_TYPE",
    "CONTENT_IMPORT_JOB_TYPE",
    "ContentImportJobHandler",
    "ContentImportJobPayload",
    "ContentImportSubmission",
    "ContentImportSubmissionService",
    "scoped_import_key",
]

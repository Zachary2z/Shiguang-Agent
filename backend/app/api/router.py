"""M0-2D `/api/v1` routes with no duplicated domain algorithms."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.api.dependencies import (
    PlanProviderNotConfiguredError,
    get_agent_timeout_seconds,
    get_current_database,
    get_current_principal,
    get_current_user_id,
    get_db_session,
    get_demo_db_session,
    get_idempotency_locks,
    get_pricing,
    get_storage_provider,
)
from app.api.errors import UndoNotAvailableError
from app.application.collection_queries import (
    CollectionCityGroup,
    CollectionListCriteria,
    CollectionQueryService,
    CollectionSort,
)
from app.application.collection_writes import CollectionWriteService
from app.application.content_import_jobs import (
    ContentImportJobPayload,
    ContentImportSubmissionService,
)
from app.application.data_exports import UserDataExportService
from app.application.demo_sessions import DemoSessionService
from app.application.input_contracts import ImageInput, TextInput, UrlInput
from app.application.memories import MemoryService
from app.application.place_matching import PlaceMatchingService
from app.application.place_targets import PlaceTargetSelectionService
from app.application.plan_execution import (
    PlanCalendarService,
    PlanFeedbackService,
    PlanNavigationService,
)
from app.application.plan_experience import PlanExperienceService
from app.application.plan_sharing import PlanShareService
from app.application.pricing import ConfiguredPricingPolicy
from app.application.run_events import RunEventService
from app.application.run_tracking import AgentRunService
from app.application.sse import stream_run_events
from app.application.text_collection_workflow import (
    IdempotencyLockRegistry,
    TextCollectionWorkflow,
)
from app.application.web_sessions import WebSessionService
from app.config import Settings
from app.domain.collections import (
    IDEMPOTENCY_KEY_JSON_SCHEMA,
    CollectionKind,
    CollectionStatus,
    IdempotencyKey,
    PlanCity,
    ResourceNotFoundError,
    UndoOutcome,
)
from app.domain.identity import SESSION_COOKIE_NAME, CurrentPrincipal
from app.domain.memories import MemorySuggestionDecision, MemoryType
from app.domain.places import PlaceSelection
from app.domain.plans import (
    ActivityArea,
    PlanConstraints,
    PlanPace,
    PlanPaceSource,
    plan_constraint_expires_at,
)
from app.domain.sharing import PublicShareStatus, SharedPlanSnapshot
from app.domain.time import utc_now
from app.infrastructure.db import Database
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import (
    SqlAlchemyCollectionRepository,
    SqlAlchemyPlanRepository,
)
from app.providers.map import MapProvider
from app.providers.storage import StorageProvider
from app.schemas.api import (
    AgentRunResponse,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    CollectionDetailResponse,
    CollectionItemResponse,
    CollectionListResponse,
    CollectionPatchRequest,
    ContentImportAcceptedResponse,
    ContentImportResultResponse,
    ContentImportToolStepResponse,
    ConversationMessageResponse,
    ConversationResponse,
    DemoSessionCreateRequest,
    DemoSessionResponse,
    ExtractionSummaryResponse,
    JsonMessageCreateRequest,
    MemoryCreateRequest,
    MemoryDeleteRequest,
    MemoryListResponse,
    MemoryPatchRequest,
    MemoryResponse,
    MemorySuggestionDecisionRequest,
    MemorySuggestionDecisionResponse,
    MemorySuggestionListResponse,
    MessageCreateRequest,
    OwnerPlanShareResponse,
    PlaceCandidateResponse,
    PlaceCandidatesResponse,
    PlaceSelectionRequest,
    PlaceSelectionResponse,
    PlanAcceptedResponse,
    PlanAdjustmentAcceptedResponse,
    PlanAdjustmentRequest,
    PlanApprovalResponse,
    PlanConfirmationResponse,
    PlanConfirmRequest,
    PlanCreateRequest,
    PlanExecutionResponse,
    PlanFeedbackRequest,
    PlanFeedbackResponse,
    PlanListResponse,
    PlanResponse,
    PublicModelCallResponse,
    PublicPlanShareResponse,
    PublicToolRunResponse,
    SourceSummaryResponse,
    UndoRequest,
    UndoResponse,
    WebSessionRevokedResponse,
)

_SESSION_PATH = r"^ses_[a-f0-9]{32}$"
_COLLECTION_PATH = r"^col_[a-f0-9]{32}$"
_TRACE_PATH = r"^trc_[A-Za-z0-9_-]{32}$"
_PLAN_PATH = r"^pln_[a-f0-9]{32}$"
_APPROVAL_PATH = r"^apr_[a-f0-9]{32}$"
_MEMORY_PATH = r"^mem_[a-f0-9]{32}$"
_SUGGESTION_PATH = r"^fdb_[a-f0-9]{32}$"

api_router = APIRouter(prefix="/api/v1")

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
DemoDbSession = Annotated[AsyncSession, Depends(get_demo_db_session)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
Principal = Annotated[CurrentPrincipal, Depends(get_current_principal)]
CurrentDatabase = Annotated[Database, Depends(get_current_database)]
Pricing = Annotated[ConfiguredPricingPolicy, Depends(get_pricing)]
Locks = Annotated[IdempotencyLockRegistry, Depends(get_idempotency_locks)]
AgentTimeout = Annotated[float, Depends(get_agent_timeout_seconds)]
PrivateStorage = Annotated[StorageProvider | None, Depends(get_storage_provider)]

_JSON_MESSAGE_ADAPTER: TypeAdapter[JsonMessageCreateRequest] = TypeAdapter(JsonMessageCreateRequest)
_IDEMPOTENCY_KEY_ADAPTER: TypeAdapter[str] = TypeAdapter(IdempotencyKey)
_MAX_JSON_MESSAGE_BYTES = 24_000
_IDEMPOTENCY_SCHEMA = IDEMPOTENCY_KEY_JSON_SCHEMA
_MESSAGE_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "oneOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["idempotency_key", "content"],
                        "properties": {
                            "idempotency_key": _IDEMPOTENCY_SCHEMA,
                            "content": {"type": "string", "minLength": 1, "maxLength": 20000},
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "idempotency_key", "text"],
                        "properties": {
                            "type": {"const": "text"},
                            "idempotency_key": _IDEMPOTENCY_SCHEMA,
                            "text": {"type": "string", "minLength": 1, "maxLength": 20000},
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "idempotency_key", "text"],
                        "properties": {
                            "type": {"const": "agent_text"},
                            "idempotency_key": _IDEMPOTENCY_SCHEMA,
                            "text": {"type": "string", "minLength": 1, "maxLength": 20000},
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "idempotency_key", "url"],
                        "properties": {
                            "type": {"const": "url"},
                            "idempotency_key": _IDEMPOTENCY_SCHEMA,
                            "url": {"type": "string", "minLength": 1, "maxLength": 2048},
                        },
                    },
                ]
            }
        },
        "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
        "image/png": {"schema": {"type": "string", "format": "binary"}},
        "image/webp": {"schema": {"type": "string", "format": "binary"}},
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["idempotency_key", "image"],
                "properties": {
                    "idempotency_key": _IDEMPOTENCY_SCHEMA,
                    "text": {"type": "string", "minLength": 1, "maxLength": 20000},
                    "image": {"type": "string", "format": "binary"},
                },
            }
        },
    },
}


@api_router.post(
    "/demo/sessions",
    response_model=DemoSessionResponse,
    status_code=201,
)
async def create_demo_session(
    request: Request,
    response: Response,
    session: DemoDbSession,
    payload: Annotated[DemoSessionCreateRequest | None, Body()] = None,
) -> DemoSessionResponse:
    del payload
    settings: Settings = request.app.state.settings
    created = await DemoSessionService(
        session=session,
        lifetime=timedelta(seconds=settings.demo_web_session_ttl_seconds),
    ).start(session_token=request.cookies.get(SESSION_COOKIE_NAME))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=created.session_token,
        max_age=created.cookie_max_age_seconds,
        expires=created.expires_at,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return DemoSessionResponse(
        session_id=created.message_session.id,
        channel=created.message_session.channel.value,
        status=created.message_session.status.value,
        created_at=created.message_session.created_at,
        expires_at=created.expires_at,
        csrf_token=created.csrf_token,
        resumed=created.resumed,
    )


@api_router.delete(
    "/web-session",
    response_model=WebSessionRevokedResponse,
)
async def revoke_current_web_session(
    request: Request,
    response: Response,
    session: DbSession,
    principal: Principal,
) -> WebSessionRevokedResponse:
    await WebSessionService(session=session).revoke(
        session_id=principal.web_session_id,
    )
    await session.commit()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=request.app.state.settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return WebSessionRevokedResponse()


@api_router.post(
    "/sessions/{session_id}/messages",
    response_model=ContentImportAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "requestBody": _MESSAGE_REQUEST_BODY,
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": False,
                "description": "Required for raw image requests; JSON carries the key in-body.",
                "schema": _IDEMPOTENCY_SCHEMA,
            }
        ],
    },
)
async def create_message(
    session_id: Annotated[str, Path(pattern=_SESSION_PATH)],
    request: Request,
    session: DbSession,
    user_id: CurrentUserId,
    storage: PrivateStorage,
    pricing: Pricing,
    locks: Locks,
    timeout_seconds: AgentTimeout,
    database: CurrentDatabase,
) -> ContentImportAcceptedResponse:
    idempotency_key, collection_input, route_agent = await _parse_collection_input(request)
    result = await ContentImportSubmissionService(
        session=session,
        session_factory=database.session_factory,
        pricing=pricing,
        locks=locks,
        timeout_seconds=timeout_seconds,
        storage=storage,
    ).submit(
        user_id=user_id,
        session_id=session_id,
        client_idempotency_key=idempotency_key,
        input=collection_input,
        route_agent=route_agent,
    )
    return ContentImportAcceptedResponse(
        message_id=result.message_id,
        trace_id=result.trace_id,
        input_type=result.input_type,
        run_status=result.run_status,
        events_url=f"/api/v1/agent-runs/{result.trace_id}/events",
        result_url=f"/api/v1/agent-runs/{result.trace_id}/result",
        replayed=result.replayed,
    )


@api_router.get(
    "/agent-runs/{trace_id}/result",
    response_model=ContentImportResultResponse,
)
async def get_content_import_result(
    trace_id: Annotated[str, Path(pattern=_TRACE_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
    database: CurrentDatabase,
    pricing: Pricing,
    locks: Locks,
    timeout_seconds: AgentTimeout,
) -> ContentImportResultResponse:
    job = await PostgresJobQueue(database.session_factory).get_by_trace(
        user_id=user_id,
        trace_id=trace_id,
    )
    if job is None:
        raise ResourceNotFoundError
    payload = ContentImportJobPayload.model_validate(job.payload, strict=True)
    workflow = TextCollectionWorkflow(
        session=session,
        provider=None,
        pricing=pricing,
        locks=locks,
        timeout_seconds=timeout_seconds,
    )
    result = await workflow.read_result(
        user_id=user_id,
        message_id=payload.message_id,
        source_id=payload.source_id,
        idempotency_key=job.idempotency_key,
    )
    run = await AgentRunService(
        session=session,
        runner=None,
        pricing=pricing,
    ).get_by_trace_id(user_id=user_id, trace_id=trace_id)
    if run is None:
        raise ResourceNotFoundError
    extraction = result.extraction_result
    saved = result.auto_save_result
    return ContentImportResultResponse(
        message_id=result.message.id,
        trace_id=result.trace_id,
        input_type=result.message.content_type,
        run_status=result.run_status,
        extraction=(
            None
            if extraction is None
            else ExtractionSummaryResponse(
                outcome=extraction.outcome,
                reason_code=extraction.reason_code,
                unsupported_reason=extraction.unsupported_reason,
                missing_fields=extraction.missing_fields,
                recovery_suggestions=extraction.recovery_suggestions,
            )
        ),
        collections=(
            ()
            if saved is None
            else tuple(CollectionItemResponse.from_domain(item) for item in saved.items)
        ),
        source_id=None if result.source is None else result.source.id,
        source_type=None if result.source is None else result.source.type,
        source_parse_status=None if result.source is None else result.source.parse_status,
        recovery_actions=result.recovery_actions,
        error_code=result.error_code,
        intent=(None if job.result_summary is None else job.result_summary.intent),
        question=(None if job.result_summary is None else job.result_summary.question),
        plan_id=(None if job.result_summary is None else job.result_summary.plan_id),
        memory_id=(None if job.result_summary is None else job.result_summary.memory_id),
        tool_steps=tuple(
            ContentImportToolStepResponse(
                tool_name=tool.tool_name,
                stage=_tool_stage(tool.tool_name),
                status=tool.status,
                source="user_submission",
                duration_ms=tool.latency_ms,
                error_code=tool.error_code,
            )
            for tool in run.tool_runs
        ),
    )


def _tool_stage(tool_name: str) -> str:
    return {
        "web_content_fetch": "content_receiving",
        "image_recognition": "place_recognition",
    }.get(tool_name, "result_organizing")


@api_router.get(
    "/sessions/{session_id}/messages",
    response_model=ConversationResponse,
)
async def list_conversation_messages(
    session_id: Annotated[str, Path(pattern=_SESSION_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
    pricing: Pricing,
) -> ConversationResponse:
    repository = SqlAlchemyCollectionRepository(session)
    if await repository.get_session(user_id=user_id, session_id=session_id) is None:
        raise ResourceNotFoundError
    run_service = AgentRunService(session=session, runner=None, pricing=pricing)
    messages: list[ConversationMessageResponse] = []
    for message in await repository.list_messages(
        user_id=user_id,
        session_id=session_id,
    ):
        if message.trace_id is None:
            continue
        run = await run_service.get_by_trace_id(
            user_id=user_id,
            trace_id=message.trace_id,
        )
        if run is None:
            continue
        messages.append(
            ConversationMessageResponse(
                message_id=message.id,
                input_type=message.content_type,
                content=(
                    "已上传截图"
                    if message.content_type.value == "image"
                    else message.content
                ),
                trace_id=message.trace_id,
                run_status=run.status,
                events_url=f"/api/v1/agent-runs/{message.trace_id}/events",
                result_url=f"/api/v1/agent-runs/{message.trace_id}/result",
                created_at=message.created_at,
            )
        )
    return ConversationResponse(messages=tuple(messages))


async def _parse_collection_input(
    request: Request,
) -> tuple[str, TextInput | UrlInput | ImageInput, bool]:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type == "application/json":
        raw = await _read_limited_body(request, limit=_MAX_JSON_MESSAGE_BYTES)
        try:
            decoded: Any = json.loads(raw)
            if isinstance(decoded, dict) and set(decoded) <= {"idempotency_key", "content"}:
                legacy = MessageCreateRequest.model_validate(decoded)
                return legacy.idempotency_key, TextInput(text=legacy.content), False
            parsed = _JSON_MESSAGE_ADAPTER.validate_python(decoded)
            if parsed.type == "agent_text":
                return parsed.idempotency_key, TextInput(text=parsed.text), True
            if parsed.type == "text":
                return parsed.idempotency_key, TextInput(text=parsed.text), False
            return parsed.idempotency_key, UrlInput(url=parsed.url), False
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError):
            raise _safe_request_validation_error() from None

    if media_type in {"image/jpeg", "image/png", "image/webp"}:
        key = request.headers.get("idempotency-key", "")
        try:
            validated_key = _IDEMPOTENCY_KEY_ADAPTER.validate_python(key)
            settings: Settings = request.app.state.settings
            payload = await _read_limited_body(
                request,
                limit=settings.storage_max_file_size_bytes,
            )
            return (
                validated_key,
                ImageInput.from_bytes(payload, content_type=media_type),
                False,
            )
        except ValidationError:
            raise _safe_request_validation_error() from None

    if media_type == "multipart/form-data":
        try:
            multipart_settings: Settings = request.app.state.settings
            form = await request.form(
                max_files=1,
                max_fields=2,
                max_part_size=multipart_settings.storage_max_file_size_bytes,
            )
            key_value = form.get("idempotency_key")
            text_value = form.get("text")
            image = form.get("image")
            if not isinstance(key_value, str) or not isinstance(image, UploadFile):
                raise ValueError
            validated_key = _IDEMPOTENCY_KEY_ADAPTER.validate_python(key_value)
            supplemental_text = (
                None if text_value is None else TextInput(text=str(text_value)).text
            )
            image_media_type = (image.content_type or "").lower()
            if image_media_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError
            payload = await _read_limited_upload(
                image,
                limit=multipart_settings.storage_max_file_size_bytes,
            )
            return (
                validated_key,
                ImageInput.from_bytes(
                    payload,
                    content_type=image_media_type,
                    supplemental_text=supplemental_text,
                ),
                False,
            )
        except (ValidationError, ValueError):
            raise _safe_request_validation_error() from None

    raise _safe_request_validation_error()


async def _read_limited_body(request: Request, *, limit: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise _safe_request_validation_error()
        except ValueError:
            raise _safe_request_validation_error() from None
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > limit:
            raise _safe_request_validation_error()
        payload.extend(chunk)
    if not payload:
        raise _safe_request_validation_error()
    return bytes(payload)


async def _read_limited_upload(upload: UploadFile, *, limit: int) -> bytes:
    payload = bytearray()
    while chunk := await upload.read(64 * 1024):
        if len(payload) + len(chunk) > limit:
            raise _safe_request_validation_error()
        payload.extend(chunk)
    if not payload:
        raise _safe_request_validation_error()
    return bytes(payload)


def _safe_request_validation_error() -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body",),
                "msg": "Invalid collection input.",
                "input": None,
                "ctx": {"error": "invalid collection input"},
            }
        ]
    )


@api_router.get(
    "/agent-runs/{trace_id}",
    response_model=AgentRunResponse,
)
async def get_agent_run(
    trace_id: Annotated[str, Path(pattern=_TRACE_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
    pricing: Pricing,
) -> AgentRunResponse:
    summary = await AgentRunService(
        session=session,
        runner=None,
        pricing=pricing,
    ).get_by_trace_id(user_id=user_id, trace_id=trace_id)
    if summary is None:
        raise ResourceNotFoundError
    return AgentRunResponse(
        trace_id=summary.trace_id,
        session_id=summary.session_id,
        intent=summary.intent,
        workflow=summary.workflow,
        status=summary.status,
        model_names=tuple(summary.model_names),
        model_calls=tuple(
            PublicModelCallResponse(
                sequence=call.sequence,
                status=call.status.value,
                model_name=call.model_name,
                usage=call.usage,
                latency_ms=call.latency_ms,
                finish_reason=call.finish_reason,
                error_code=call.error_code,
                estimated_cost=call.estimated_cost,
                cost_currency=call.cost_currency,
                cost_estimation_source=call.cost_estimation_source,
                cost_unknown_reason=call.cost_unknown_reason,
            )
            for call in summary.model_calls
        ),
        usage=summary.usage,
        estimated_cost=summary.estimated_cost,
        cost_currency=summary.cost_currency,
        cost_estimation_source=summary.cost_estimation_source,
        cost_unknown_reason=summary.cost_unknown_reason,
        duration_ms=summary.duration_ms,
        error_code=summary.error_code,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        tool_runs=tuple(
            PublicToolRunResponse(
                sequence=tool.sequence,
                tool_name=tool.tool_name,
                input_summary=tool.input_summary,
                status=tool.status,
                output_summary=tool.output_summary,
                latency_ms=tool.latency_ms,
                error_code=tool.error_code,
                started_at=tool.started_at,
                finished_at=tool.finished_at,
            )
            for tool in summary.tool_runs
        ),
    )


@api_router.get("/agent-runs/{trace_id}/events")
async def get_agent_run_events(
    trace_id: Annotated[str, Path(pattern=_TRACE_PATH)],
    request: Request,
    session: DbSession,
    user_id: CurrentUserId,
    database: CurrentDatabase,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    after_sequence = _parse_last_event_id(last_event_id)
    if not await RunEventService(session).run_exists(
        user_id=user_id,
        trace_id=trace_id,
    ):
        raise ResourceNotFoundError
    return StreamingResponse(
        stream_run_events(
            request=request,
            session_factory=database.session_factory,
            user_id=user_id,
            trace_id=trace_id,
            after_sequence=after_sequence,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _parse_last_event_id(value: str | None) -> int:
    if value is None or value == "":
        return 0
    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("header", "Last-Event-ID"),
                    "msg": "Last-Event-ID must be a nonnegative sequence.",
                    "input": None,
                    "ctx": {"error": "invalid event sequence"},
                }
            ]
        )
    return int(value)


@api_router.post(
    "/plans",
    response_model=PlanAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_plan(
    payload: PlanCreateRequest,
    request: Request,
    session: DbSession,
    user_id: CurrentUserId,
    database: CurrentDatabase,
    pricing: Pricing,
) -> PlanAcceptedResponse:
    _require_plan_providers(request, adjustment=False)
    now = utc_now()
    constraints = PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=payload.start_at,
        end_at=payload.end_at,
        area=(
            None
            if payload.area is None
            else ActivityArea(
                districts=payload.area.districts,
                labels=payload.area.labels,
            )
        ),
        origin=payload.origin,
        budget=payload.budget,
        pace=payload.pace or PlanPace.BALANCED,
        pace_source=(
            PlanPaceSource.USER_REQUEST
            if payload.pace is not None
            else PlanPaceSource.SYSTEM_DEFAULT
        ),
        transport_modes=payload.transport_modes,
        include=payload.include,
        exclude=payload.exclude,
        collection_only=payload.collection_only,
        selected_collection_item_ids=payload.selected_collection_item_ids,
        created_at=now,
        expires_at=plan_constraint_expires_at(
            now=now,
            start_at=payload.start_at,
            end_at=payload.end_at,
        ),
    )
    submission = await PlanExperienceService(
        session=session,
        session_factory=database.session_factory,
        pricing=pricing,
    ).create(
        user_id=user_id,
        constraints=constraints,
        client_idempotency_key=payload.idempotency_key,
    )
    plan = submission.plan
    return PlanAcceptedResponse(
        plan_id=plan.id,
        trace_id=plan.trace_id,
        events_url=f"/api/v1/agent-runs/{plan.trace_id}/events",
        result_url=f"/api/v1/plans/{plan.id}",
        replayed=submission.replayed,
    )


@api_router.get("/plans", response_model=PlanListResponse)
async def list_plans(
    session: DbSession,
    user_id: CurrentUserId,
) -> PlanListResponse:
    repository = SqlAlchemyPlanRepository(session)
    items: list[PlanResponse] = []
    for plan in await repository.list_latest(user_id=user_id):
        versions = await repository.list_versions(
            user_id=user_id,
            root_plan_id=plan.root_plan_id,
        )
        approval = await repository.get_external_approval(
            user_id=user_id,
            plan_id=plan.id,
        )
        items.append(
            PlanResponse.from_domain(
                plan,
                is_current_version=True,
                versions=versions,
                approval=approval,
            )
        )
    return PlanListResponse(items=tuple(items))


@api_router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> PlanResponse:
    repository = SqlAlchemyPlanRepository(session)
    requested = await repository.require(user_id=user_id, plan_id=plan_id)
    versions = await repository.list_versions(
        user_id=user_id,
        root_plan_id=requested.root_plan_id,
    )
    current = versions[-1]
    approval = await repository.get_external_approval(
        user_id=user_id,
        plan_id=requested.id,
    )
    return PlanResponse.from_domain(
        requested,
        is_current_version=requested.id == current.id,
        versions=versions,
        approval=approval,
    )


@api_router.post(
    "/plans/{plan_id}/adjustments",
    response_model=PlanAdjustmentAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def adjust_plan(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    payload: PlanAdjustmentRequest,
    request: Request,
    session: DbSession,
    user_id: CurrentUserId,
    database: CurrentDatabase,
    pricing: Pricing,
) -> PlanAdjustmentAcceptedResponse:
    _require_plan_providers(request, adjustment=True)
    submission = await PlanExperienceService(
        session=session,
        session_factory=database.session_factory,
        pricing=pricing,
    ).adjust(
        user_id=user_id,
        base_plan_id=plan_id,
        instruction=payload.instruction,
        client_idempotency_key=payload.idempotency_key,
    )
    return PlanAdjustmentAcceptedResponse(
        base_plan_id=submission.base_plan_id,
        trace_id=submission.trace_id,
        events_url=f"/api/v1/agent-runs/{submission.trace_id}/events",
        replayed=submission.replayed,
    )


@api_router.post(
    "/plans/{plan_id}/confirm",
    response_model=PlanConfirmationResponse,
)
async def confirm_plan(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    payload: PlanConfirmRequest,
    session: DbSession,
    user_id: CurrentUserId,
    database: CurrentDatabase,
    pricing: Pricing,
) -> PlanConfirmationResponse:
    plan, replayed = await PlanExperienceService(
        session=session,
        session_factory=database.session_factory,
        pricing=pricing,
    ).confirm(
        user_id=user_id,
        plan_id=plan_id,
        client_idempotency_key=payload.idempotency_key,
    )
    versions = await SqlAlchemyPlanRepository(session).list_versions(
        user_id=user_id,
        root_plan_id=plan.root_plan_id,
    )
    return PlanConfirmationResponse(
        plan=PlanResponse.from_domain(
            plan,
            is_current_version=versions[-1].id == plan.id,
            versions=versions,
        ),
        replayed=replayed,
    )


@api_router.get("/plans/{plan_id}/calendar.ics")
async def download_plan_calendar(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> Response:
    content = await PlanCalendarService().generate(
        session=session,
        user_id=user_id,
        plan_id=plan_id,
    )
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="shiguang-{plan_id}.ics"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@api_router.get(
    "/plans/{plan_id}/execution",
    response_model=PlanExecutionResponse,
)
async def get_plan_execution(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    request: Request,
    session: DbSession,
    user_id: CurrentUserId,
) -> PlanExecutionResponse:
    map_provider = request.app.state.map_provider
    if map_provider is None:
        raise PlanProviderNotConfiguredError
    execution_plan_id, items = await PlanNavigationService().list_entries(
        session=session,
        user_id=user_id,
        plan_id=plan_id,
        map_provider=map_provider,
    )
    feedback = await PlanFeedbackService().current(
        session=session,
        user_id=user_id,
        plan_id=execution_plan_id,
    )
    return PlanExecutionResponse(
        plan_id=execution_plan_id,
        items=items,
        feedback=feedback,
    )


@api_router.post(
    "/plans/{plan_id}/feedback",
    response_model=PlanFeedbackResponse,
)
async def submit_plan_feedback(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    payload: PlanFeedbackRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> PlanFeedbackResponse:
    submission = await PlanFeedbackService().submit(
        session=session,
        user_id=user_id,
        plan_id=plan_id,
        completion_status=payload.completion_status,
        visited_plan_item_ids=payload.visited_plan_item_ids,
        reason=payload.reason,
        preference_candidate=(
            None
            if payload.preference_candidate is None
            else payload.preference_candidate.to_domain()
        ),
        client_idempotency_key=payload.idempotency_key,
        expected_revision=payload.expected_revision,
    )
    return PlanFeedbackResponse(
        feedback=submission.feedback,
        replayed=submission.replayed,
    )


@api_router.get(
    "/plans/{plan_id}/share/preview",
    response_model=SharedPlanSnapshot,
)
async def preview_plan_share(
    request: Request,
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> SharedPlanSnapshot:
    return await PlanShareService(
        session,
        map_provider=request.app.state.map_provider,
    ).preview(user_id=user_id, plan_id=plan_id)


@api_router.get(
    "/plans/{plan_id}/share",
    response_model=OwnerPlanShareResponse,
)
async def get_plan_share_status(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> OwnerPlanShareResponse:
    view = await PlanShareService(session).status(
        user_id=user_id,
        plan_id=plan_id,
    )
    return OwnerPlanShareResponse.model_validate(view.model_dump())


@api_router.post(
    "/plans/{plan_id}/share",
    response_model=OwnerPlanShareResponse,
)
async def create_plan_share(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
    idempotency_key: Annotated[IdempotencyKey, Header(alias="Idempotency-Key")],
) -> OwnerPlanShareResponse:
    view = await PlanShareService(session).create(
        user_id=user_id,
        plan_id=plan_id,
        regenerate=False,
        idempotency_key=idempotency_key,
    )
    return OwnerPlanShareResponse.model_validate(view.model_dump())


@api_router.post(
    "/plans/{plan_id}/share/regenerate",
    response_model=OwnerPlanShareResponse,
)
async def regenerate_plan_share(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
    idempotency_key: Annotated[IdempotencyKey, Header(alias="Idempotency-Key")],
) -> OwnerPlanShareResponse:
    view = await PlanShareService(session).create(
        user_id=user_id,
        plan_id=plan_id,
        regenerate=True,
        idempotency_key=idempotency_key,
    )
    return OwnerPlanShareResponse.model_validate(view.model_dump())


@api_router.delete(
    "/plans/{plan_id}/share",
    response_model=OwnerPlanShareResponse,
)
async def revoke_plan_share(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> OwnerPlanShareResponse:
    view = await PlanShareService(session).revoke(
        user_id=user_id,
        plan_id=plan_id,
    )
    return OwnerPlanShareResponse.model_validate(view.model_dump())


@api_router.get(
    "/public/plan-share",
    response_model=PublicPlanShareResponse,
)
async def read_public_plan_share(
    request: Request,
    response: Response,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> PublicPlanShareResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    token = (
        authorization.removeprefix("Share ")
        if authorization is not None and authorization.startswith("Share ")
        else ""
    )
    databases = (request.app.state.database, request.app.state.demo_database)
    available = None
    for database in databases:
        if database is None:
            continue
        async with database.session() as session:
            view = await PlanShareService(
                session,
                map_provider=request.app.state.map_provider,
            ).read_public(token=token)
        if available is None and view.status is not PublicShareStatus.UNAVAILABLE:
            available = view
    if available is not None:
        return PublicPlanShareResponse.model_validate(available.model_dump())
    return PublicPlanShareResponse(
        status=PublicShareStatus.UNAVAILABLE,
        plan=None,
    )


@api_router.get("/memories", response_model=MemoryListResponse)
async def list_memories(
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryListResponse:
    return MemoryListResponse(
        items=await MemoryService(session).list(user_id=user_id)
    )


@api_router.post("/memories", response_model=MemoryResponse)
async def create_memory(
    payload: MemoryCreateRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryResponse:
    result = await MemoryService(session).create_explicit(
        user_id=user_id,
        memory_type=MemoryType(payload.type),
        content=payload.content,
        value=payload.value,
        area=payload.area,
        expires_at=payload.expires_at,
        explicit_authorization=payload.explicit_authorization,
        location_granularity=payload.location_granularity,
        client_idempotency_key=payload.idempotency_key,
    )
    return MemoryResponse(memory=result.memory, replayed=result.replayed)


@api_router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: Annotated[str, Path(pattern=_MEMORY_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryResponse:
    memory, usages = await MemoryService(session).detail(
        user_id=user_id, memory_id=memory_id
    )
    return MemoryResponse(memory=memory, usages=usages)


@api_router.patch("/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: Annotated[str, Path(pattern=_MEMORY_PATH)],
    payload: MemoryPatchRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryResponse:
    result = await MemoryService(session).update(
        user_id=user_id,
        memory_id=memory_id,
        expected_version=payload.expected_version,
        content=payload.content,
        value=payload.value,
        area=payload.area,
        enabled=payload.enabled,
        expires_at=payload.expires_at,
        change_expiry=payload.change_expiry,
        client_idempotency_key=payload.idempotency_key,
    )
    return MemoryResponse(memory=result.memory, replayed=result.replayed)


@api_router.delete("/memories/{memory_id}", response_model=MemoryResponse)
async def delete_memory(
    memory_id: Annotated[str, Path(pattern=_MEMORY_PATH)],
    payload: MemoryDeleteRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryResponse:
    result = await MemoryService(session).delete(
        user_id=user_id,
        memory_id=memory_id,
        expected_version=payload.expected_version,
        client_idempotency_key=payload.idempotency_key,
    )
    return MemoryResponse(memory=result.memory, replayed=result.replayed)


@api_router.get(
    "/memory-suggestions",
    response_model=MemorySuggestionListResponse,
)
async def list_memory_suggestions(
    session: DbSession,
    user_id: CurrentUserId,
) -> MemorySuggestionListResponse:
    return MemorySuggestionListResponse(
        items=await MemoryService(session).suggestions(user_id=user_id)
    )


@api_router.post(
    "/memory-suggestions/{suggestion_id}/decision",
    response_model=MemorySuggestionDecisionResponse,
)
async def decide_memory_suggestion(
    suggestion_id: Annotated[str, Path(pattern=_SUGGESTION_PATH)],
    payload: MemorySuggestionDecisionRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> MemorySuggestionDecisionResponse:
    result = await MemoryService(session).decide_suggestion(
        user_id=user_id,
        suggestion_id=suggestion_id,
        decision=MemorySuggestionDecision(payload.decision),
        memory_type=(
            None if payload.memory_type is None else MemoryType(payload.memory_type)
        ),
        content=payload.content,
        value=payload.value,
        client_idempotency_key=payload.idempotency_key,
    )
    return MemorySuggestionDecisionResponse(
        decision=result.decision,
        memory=result.memory,
        replayed=result.replayed,
    )


@api_router.get("/data-export.json")
async def download_user_data(
    session: DbSession,
    user_id: CurrentUserId,
) -> Response:
    content = await UserDataExportService().build(session=session, user_id=user_id)
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="shiguang-data.json"',
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@api_router.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalDecisionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def decide_plan_approval(
    approval_id: Annotated[str, Path(pattern=_APPROVAL_PATH)],
    payload: ApprovalDecisionRequest,
    session: DbSession,
    user_id: CurrentUserId,
    database: CurrentDatabase,
    pricing: Pricing,
) -> ApprovalDecisionResponse:
    submission = await PlanExperienceService(
        session=session,
        session_factory=database.session_factory,
        pricing=pricing,
    ).decide_external_approval(
        user_id=user_id,
        approval_id=approval_id,
        approved=payload.decision == "approved",
    )
    target = submission.approval.target_plan_id
    return ApprovalDecisionResponse(
        approval=PlanApprovalResponse.from_domain(submission.approval),
        trace_id=submission.trace_id,
        events_url=(
            None
            if submission.trace_id is None
            else f"/api/v1/agent-runs/{submission.trace_id}/events"
        ),
        result_url=f"/api/v1/plans/{target}",
        replayed=submission.replayed,
    )


def _require_plan_providers(request: Request, *, adjustment: bool) -> None:
    settings: Settings = request.app.state.settings
    map_ready = (
        request.app.state.map_provider is not None
        or settings.amap_api_key is not None
    )
    model_ready = (
        request.app.state.text_provider is not None
        or all(
            getattr(settings, field, None) is not None
            for field in ("model_api_base", "model_api_key", "model_name")
        )
    )
    if not map_ready or (adjustment and not model_ready):
        raise PlanProviderNotConfiguredError


@api_router.get("/collections", response_model=CollectionListResponse)
async def list_collections(
    session: DbSession,
    user_id: CurrentUserId,
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    city_hint: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    city_code: Annotated[
        str | None, Query(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    ] = None,
    city_group: Annotated[CollectionCityGroup | None, Query()] = None,
    city_pending: Annotated[bool | None, Query()] = None,
    formal_city_pending: Annotated[bool | None, Query()] = None,
    district: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    kind: Annotated[CollectionKind | None, Query()] = None,
    status: Annotated[CollectionStatus | None, Query()] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = False,
    sort: Annotated[CollectionSort, Query()] = CollectionSort.CREATED_DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionListResponse:
    if city_code is not None and city_group is not None:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "city_group"),
                    "msg": "city_code and city_group cannot be combined.",
                    "input": city_group.value,
                    "ctx": {"error": "conflicting city filters"},
                }
            ]
        )
    result = await CollectionQueryService(session).list(
        user_id=user_id,
        criteria=CollectionListCriteria(
            search=search,
            city_hint=city_hint,
            city_code=city_code,
            city_group=city_group,
            city_pending=city_pending,
            formal_city_pending=formal_city_pending,
            district=district,
            kind=kind,
            status=status,
            tags=tuple(tags or ()),
            include_inactive=include_inactive,
            sort=sort,
            page=page,
            page_size=page_size,
        ),
    )
    return CollectionListResponse(
        items=tuple(CollectionItemResponse.from_domain(item) for item in result.items),
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@api_router.get(
    "/collections/{item_id}",
    response_model=CollectionDetailResponse,
)
async def get_collection(
    item_id: Annotated[str, Path(pattern=_COLLECTION_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> CollectionDetailResponse:
    result = await CollectionQueryService(session).get_detail(
        user_id=user_id,
        collection_item_id=item_id,
    )
    return CollectionDetailResponse(
        item=CollectionItemResponse.from_domain(result.item),
        sources=tuple(SourceSummaryResponse.from_domain(source) for source in result.sources),
    )


@api_router.get(
    "/collections/{item_id}/poi-candidates",
    response_model=PlaceCandidatesResponse,
)
async def get_collection_poi_candidates(
    item_id: Annotated[str, Path(pattern=_COLLECTION_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> PlaceCandidatesResponse:
    detail = await CollectionQueryService(session).get_detail(
        user_id=user_id,
        collection_item_id=item_id,
    )
    snapshot = detail.item.place_candidate_snapshot
    if snapshot is None or not snapshot.candidates:
        raise ResourceNotFoundError
    return PlaceCandidatesResponse(
        collection_item_id=detail.item.id,
        expected_version=detail.item.version,
        snapshot_fingerprint=snapshot.fingerprint,
        queried_at=snapshot.queried_at,
        candidates=tuple(
            PlaceCandidateResponse.from_domain(candidate)
            for candidate in snapshot.candidates
        ),
    )


@api_router.post(
    "/collections/{item_id}/poi-selection",
    response_model=PlaceSelectionResponse,
)
async def select_collection_poi(
    item_id: Annotated[str, Path(pattern=_COLLECTION_PATH)],
    request: PlaceSelectionRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> PlaceSelectionResponse:
    detail = await CollectionQueryService(session).get_detail(
        user_id=user_id,
        collection_item_id=item_id,
    )
    snapshot = detail.item.place_candidate_snapshot
    try:
        result = await PlaceTargetSelectionService(session=session).apply_user_selection(
            user_id=user_id,
            collection_item_id=item_id,
            selections=(
                PlaceSelection(
                    kind=request.selection_kind(),
                    provider=request.poi_provider(),
                    poi_id=request.poi_id,
                ),
            ),
            queried_at=(
                None
                if snapshot is None or not snapshot.candidates
                else snapshot.queried_at
            ),
            snapshot_fingerprint=request.snapshot_fingerprint,
            idempotency_key=request.idempotency_key,
            expected_version=request.expected_version,
        )
    except ValueError:
        raise _safe_request_validation_error() from None
    return PlaceSelectionResponse(
        items=tuple(CollectionItemResponse.from_domain(item) for item in result.items),
        replayed=result.replayed,
    )


@api_router.patch(
    "/collections/{item_id}",
    response_model=CollectionItemResponse,
)
async def patch_collection(
    item_id: Annotated[str, Path(pattern=_COLLECTION_PATH)],
    payload: CollectionPatchRequest,
    request: Request,
    session: DbSession,
    user_id: CurrentUserId,
) -> CollectionItemResponse:
    map_provider: MapProvider | None = request.app.state.map_provider
    item = await CollectionWriteService(session=session).patch(
        user_id=user_id,
        collection_item_id=item_id,
        expected_version=payload.expected_version,
        patch=payload.changes,
        place_matching=(
            None
            if map_provider is None
            else PlaceMatchingService(
                map_provider=map_provider,
                policy=request.app.state.settings.place_matching_policy(),
            )
        ),
    )
    return CollectionItemResponse.from_domain(item)


@api_router.post(
    "/collections/{item_id}/restore",
    response_model=CollectionItemResponse,
)
async def restore_collection(
    item_id: Annotated[str, Path(pattern=_COLLECTION_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
) -> CollectionItemResponse:
    item = await CollectionWriteService(session=session).restore(
        user_id=user_id,
        collection_item_id=item_id,
    )
    return CollectionItemResponse.from_domain(item)


@api_router.delete(
    "/collections/{item_id}",
    response_model=CollectionItemResponse,
)
async def delete_collection(
    item_id: Annotated[str, Path(pattern=_COLLECTION_PATH)],
    session: DbSession,
    user_id: CurrentUserId,
    expected_version: Annotated[int | None, Query(ge=1)] = None,
) -> CollectionItemResponse:
    item = await CollectionWriteService(session=session).delete(
        user_id=user_id,
        collection_item_id=item_id,
        expected_version=expected_version,
    )
    return CollectionItemResponse.from_domain(item)


@api_router.post(
    "/collections/{item_id}/undo",
    response_model=UndoResponse,
)
async def undo_collection(
    item_id: Annotated[str, Path(pattern=_COLLECTION_PATH)],
    request: UndoRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> UndoResponse:
    result = await CollectionWriteService(session=session).undo_collection_item(
        user_id=user_id,
        collection_item_id=item_id,
        undo_token=request.undo_token.get_secret_value(),
    )
    if result.outcome is UndoOutcome.NOT_AVAILABLE:
        raise UndoNotAvailableError
    return UndoResponse(
        outcome=result.outcome,
        collection_item_ids=result.collection_item_ids,
    )

"""M0-2D `/api/v1` routes with no duplicated domain algorithms."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
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
from app.application.demo_sessions import DemoSessionService
from app.application.input_contracts import ImageInput, TextInput, UrlInput
from app.application.place_targets import PlaceTargetSelectionService
from app.application.plan_experience import PlanExperienceService
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
from app.domain.places import PlaceSelection
from app.domain.plans import ActivityArea, PlanConstraints
from app.domain.time import utc_now
from app.infrastructure.db import Database
from app.infrastructure.jobs import PostgresJobQueue
from app.infrastructure.repositories import (
    SqlAlchemyCollectionRepository,
    SqlAlchemyPlanRepository,
)
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
    MessageCreateRequest,
    PlaceCandidateResponse,
    PlaceCandidatesResponse,
    PlaceSelectionRequest,
    PlaceSelectionResponse,
    PlanAcceptedResponse,
    PlanAdjustmentRequest,
    PlanApprovalResponse,
    PlanConfirmationResponse,
    PlanConfirmRequest,
    PlanCreateRequest,
    PlanListResponse,
    PlanResponse,
    PublicModelCallResponse,
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
    idempotency_key, collection_input = await _parse_collection_input(request)
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
) -> tuple[str, TextInput | UrlInput | ImageInput]:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type == "application/json":
        raw = await _read_limited_body(request, limit=_MAX_JSON_MESSAGE_BYTES)
        try:
            decoded: Any = json.loads(raw)
            if isinstance(decoded, dict) and set(decoded) <= {"idempotency_key", "content"}:
                legacy = MessageCreateRequest.model_validate(decoded)
                return legacy.idempotency_key, TextInput(text=legacy.content)
            parsed = _JSON_MESSAGE_ADAPTER.validate_python(decoded)
            if parsed.type == "text":
                return parsed.idempotency_key, TextInput(text=parsed.text)
            return parsed.idempotency_key, UrlInput(url=parsed.url)
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
            return validated_key, ImageInput.from_bytes(payload, content_type=media_type)
        except ValidationError:
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
    session: DbSession,
    user_id: CurrentUserId,
    database: CurrentDatabase,
    pricing: Pricing,
) -> PlanAcceptedResponse:
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
        pace=payload.pace,
        transport_modes=payload.transport_modes,
        include=payload.include,
        exclude=payload.exclude,
        collection_only=payload.collection_only,
        created_at=now,
        expires_at=max(now + timedelta(hours=1), payload.end_at + timedelta(hours=1)),
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
    response_model=PlanAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def adjust_plan(
    plan_id: Annotated[str, Path(pattern=_PLAN_PATH)],
    payload: PlanAdjustmentRequest,
    session: DbSession,
    user_id: CurrentUserId,
    database: CurrentDatabase,
    pricing: Pricing,
) -> PlanAcceptedResponse:
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
    plan = submission.plan
    return PlanAcceptedResponse(
        plan_id=plan.id,
        trace_id=plan.trace_id,
        events_url=f"/api/v1/agent-runs/{plan.trace_id}/events",
        result_url=f"/api/v1/plans/{plan.id}",
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
    if snapshot is None or not snapshot.candidates:
        raise ResourceNotFoundError
    result = await PlaceTargetSelectionService(session=session).apply_selection(
        user_id=user_id,
        collection_item_id=item_id,
        selections=(
            PlaceSelection(
                kind=request.selection_kind(),
                provider=request.poi_provider(),
                poi_id=request.poi_id,
            ),
        ),
        queried_at=snapshot.queried_at,
        snapshot_fingerprint=request.snapshot_fingerprint,
        idempotency_key=request.idempotency_key,
        expected_version=request.expected_version,
    )
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
    request: CollectionPatchRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> CollectionItemResponse:
    item = await CollectionWriteService(session=session).patch(
        user_id=user_id,
        collection_item_id=item_id,
        expected_version=request.expected_version,
        patch=request.changes,
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

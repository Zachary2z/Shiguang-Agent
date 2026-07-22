"""M0-2D `/api/v1` routes with no duplicated domain algorithms."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_agent_timeout_seconds,
    get_current_user_id,
    get_db_session,
    get_idempotency_locks,
    get_pricing,
    get_storage_provider,
    get_text_provider,
    get_web_provider,
)
from app.api.errors import UndoNotAvailableError
from app.application.collection_queries import (
    CollectionListCriteria,
    CollectionQueryService,
    CollectionSort,
)
from app.application.collection_writes import CollectionWriteService
from app.application.demo_sessions import DemoSessionService
from app.application.input_contracts import ImageInput, TextInput, UrlInput
from app.application.pricing import ConfiguredPricingPolicy
from app.application.run_tracking import AgentRunService
from app.application.text_collection_workflow import (
    IdempotencyLockRegistry,
    TextCollectionWorkflow,
)
from app.config import Settings
from app.domain.collections import (
    IDEMPOTENCY_KEY_JSON_SCHEMA,
    CollectionKind,
    CollectionStatus,
    IdempotencyKey,
    ResourceNotFoundError,
    UndoOutcome,
)
from app.providers.storage import StorageProvider
from app.providers.web import WebContentProvider
from app.schemas.api import (
    AgentRunResponse,
    CollectionDetailResponse,
    CollectionItemResponse,
    CollectionListResponse,
    CollectionPatchRequest,
    DemoSessionCreateRequest,
    DemoSessionResponse,
    ExtractionSummaryResponse,
    JsonMessageCreateRequest,
    MessageCreateRequest,
    MessageCreateResponse,
    PublicModelCallResponse,
    PublicToolRunResponse,
    SourceSummaryResponse,
    UndoRequest,
    UndoResponse,
)
from nanobot_core.providers import ModelProvider

_SESSION_PATH = r"^ses_[a-f0-9]{32}$"
_COLLECTION_PATH = r"^col_[a-f0-9]{32}$"
_TRACE_PATH = r"^trc_[A-Za-z0-9_-]{32}$"

api_router = APIRouter(prefix="/api/v1")

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
TextProvider = Annotated[ModelProvider, Depends(get_text_provider)]
Pricing = Annotated[ConfiguredPricingPolicy, Depends(get_pricing)]
Locks = Annotated[IdempotencyLockRegistry, Depends(get_idempotency_locks)]
AgentTimeout = Annotated[float, Depends(get_agent_timeout_seconds)]
WebProvider = Annotated[WebContentProvider | None, Depends(get_web_provider)]
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
    session: DbSession,
    payload: Annotated[DemoSessionCreateRequest | None, Body()] = None,
) -> DemoSessionResponse:
    del payload
    created = await DemoSessionService(session=session).create()
    return DemoSessionResponse(
        session_id=created.id,
        channel=created.channel.value,
        status=created.status.value,
        created_at=created.created_at,
    )


@api_router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageCreateResponse,
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
    provider: TextProvider,
    web_provider: WebProvider,
    storage: PrivateStorage,
    pricing: Pricing,
    locks: Locks,
    timeout_seconds: AgentTimeout,
) -> MessageCreateResponse:
    idempotency_key, collection_input = await _parse_collection_input(request)
    settings: Settings = request.app.state.settings
    result = await TextCollectionWorkflow(
        session=session,
        provider=provider,
        pricing=pricing,
        locks=locks,
        timeout_seconds=timeout_seconds,
        web_provider=web_provider,
        storage=storage,
        storage_config=settings.storage_provider_settings(),
    ).submit_input(
        user_id=user_id,
        session_id=session_id,
        idempotency_key=idempotency_key,
        input=collection_input,
    )
    extraction = result.extraction_result
    saved = result.auto_save_result
    plaintext_token = None
    if saved is not None and saved.undo_token is not None:
        plaintext_token = saved.undo_token.get_secret_value()
    return MessageCreateResponse(
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
        source_parse_status=(None if result.source is None else result.source.parse_status),
        recovery_actions=result.recovery_actions,
        error_code=result.error_code,
        undo_token=plaintext_token,
        undo_expires_at=None if saved is None else saved.undo_expires_at,
        replayed=result.replayed,
    )


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


@api_router.get("/collections", response_model=CollectionListResponse)
async def list_collections(
    session: DbSession,
    user_id: CurrentUserId,
    city_hint: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    city_pending: Annotated[bool | None, Query()] = None,
    district: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    kind: Annotated[CollectionKind | None, Query()] = None,
    status: Annotated[CollectionStatus | None, Query()] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = False,
    sort: Annotated[CollectionSort, Query()] = CollectionSort.CREATED_DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionListResponse:
    result = await CollectionQueryService(session).list(
        user_id=user_id,
        criteria=CollectionListCriteria(
            city_hint=city_hint,
            city_pending=city_pending,
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

"""Strict request and deliberately allowlisted response contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.domain.collections import (
    CandidateField,
    CollectionItem,
    CollectionItemPatch,
    CollectionKind,
    CollectionStatus,
    ExtractionOutcome,
    ExtractionReasonCode,
    IdempotencyKey,
    MessageContentType,
    Source,
    SourceParseStatus,
    SourceType,
    Uncertainty,
    UndoOutcome,
    UnsupportedReason,
)
from app.domain.places import PlaceCandidateSnapshot, PlaceTarget
from app.domain.runs import AgentRunStatus, ToolRunStatus
from nanobot_core.providers import FinishReason, TokenUsage


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DemoSessionCreateRequest(ApiModel):
    pass


class DemoSessionResponse(ApiModel):
    session_id: str
    channel: str
    status: str
    created_at: datetime
    expires_at: datetime
    csrf_token: str = Field(repr=False)
    resumed: bool


class WebSessionRevokedResponse(ApiModel):
    status: Literal["revoked"] = "revoked"


class MessageCreateRequest(ApiModel):
    idempotency_key: IdempotencyKey = Field(repr=False)
    content: str = Field(min_length=1, max_length=20_000, repr=False)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content cannot be blank")
        return value


class TextMessageCreateRequest(ApiModel):
    type: Literal["text"]
    idempotency_key: IdempotencyKey = Field(repr=False)
    text: str = Field(min_length=1, max_length=20_000, repr=False)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text cannot be blank")
        return value


class UrlMessageCreateRequest(ApiModel):
    type: Literal["url"]
    idempotency_key: IdempotencyKey = Field(repr=False)
    url: str = Field(min_length=1, max_length=2048, repr=False)


JsonMessageCreateRequest = Annotated[
    TextMessageCreateRequest | UrlMessageCreateRequest,
    Field(discriminator="type"),
]


class ExtractionSummaryResponse(ApiModel):
    outcome: ExtractionOutcome
    reason_code: ExtractionReasonCode | None = None
    unsupported_reason: UnsupportedReason | None = None
    missing_fields: tuple[CandidateField, ...] = ()
    recovery_suggestions: tuple[str, ...] = ()


class CollectionItemResponse(ApiModel):
    id: str
    kind: CollectionKind
    title: str
    city_hint: str | None
    city_pending: bool
    district: str | None
    address: str | None
    business_district: str | None
    landmark: str | None
    metro_station: str | None
    event_start_date: date | None
    event_end_date: date | None
    event_start_at: datetime | None
    event_end_at: datetime | None
    event_start_clue: str | None
    event_end_clue: str | None
    price_amount: Decimal | None
    price_currency: str | None
    tags: tuple[str, ...]
    missing_fields: tuple[CandidateField, ...]
    uncertainties: tuple[Uncertainty, ...]
    place_target: PlaceTarget | None
    place_candidate_snapshot: PlaceCandidateSnapshot | None
    status: CollectionStatus
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, item: CollectionItem) -> CollectionItemResponse:
        return cls(
            id=item.id,
            kind=item.kind,
            title=item.title,
            city_hint=item.city_hint,
            city_pending=item.city_hint is None,
            district=item.district,
            address=item.address,
            business_district=item.business_district,
            landmark=item.landmark,
            metro_station=item.metro_station,
            event_start_date=item.event_start_date,
            event_end_date=item.event_end_date,
            event_start_at=item.event_start_at,
            event_end_at=item.event_end_at,
            event_start_clue=item.event_start_clue,
            event_end_clue=item.event_end_clue,
            price_amount=item.price_amount,
            price_currency=item.price_currency,
            tags=item.tags,
            missing_fields=item.missing_fields,
            uncertainties=item.uncertainties,
            place_target=item.place_target,
            place_candidate_snapshot=item.place_candidate_snapshot,
            status=item.status,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class MessageCreateResponse(ApiModel):
    message_id: str
    trace_id: str
    input_type: MessageContentType
    run_status: AgentRunStatus
    extraction: ExtractionSummaryResponse | None
    collections: tuple[CollectionItemResponse, ...]
    source_id: str | None = None
    source_type: SourceType | None = None
    source_parse_status: SourceParseStatus | None = None
    recovery_actions: tuple[str, ...] = ()
    error_code: str | None = None
    undo_token: str | None = Field(default=None, repr=False)
    undo_expires_at: datetime | None = None
    replayed: bool


class ContentImportAcceptedResponse(ApiModel):
    message_id: str
    trace_id: str
    input_type: MessageContentType
    run_status: AgentRunStatus
    events_url: str
    result_url: str
    replayed: bool


class ContentImportToolStepResponse(ApiModel):
    tool_name: str
    stage: str
    status: ToolRunStatus
    source: str
    duration_ms: int | None
    error_code: str | None


class ContentImportResultResponse(ApiModel):
    message_id: str
    trace_id: str
    input_type: MessageContentType
    run_status: AgentRunStatus
    extraction: ExtractionSummaryResponse | None
    collections: tuple[CollectionItemResponse, ...]
    source_id: str | None = None
    source_type: SourceType | None = None
    source_parse_status: SourceParseStatus | None = None
    recovery_actions: tuple[str, ...] = ()
    error_code: str | None = None
    tool_steps: tuple[ContentImportToolStepResponse, ...] = ()


class ConversationMessageResponse(ApiModel):
    message_id: str
    input_type: MessageContentType
    content: str = Field(repr=False)
    trace_id: str
    run_status: AgentRunStatus
    events_url: str
    result_url: str
    created_at: datetime


class ConversationResponse(ApiModel):
    messages: tuple[ConversationMessageResponse, ...]


class CollectionListResponse(ApiModel):
    items: tuple[CollectionItemResponse, ...]
    page: int
    page_size: int
    total: int


class SourceSummaryResponse(ApiModel):
    id: str
    type: SourceType
    parse_status: SourceParseStatus
    created_at: datetime

    @classmethod
    def from_domain(cls, source: Source) -> SourceSummaryResponse:
        return cls(
            id=source.id,
            type=source.type,
            parse_status=source.parse_status,
            created_at=source.created_at,
        )


class CollectionDetailResponse(ApiModel):
    item: CollectionItemResponse
    sources: tuple[SourceSummaryResponse, ...]


class CollectionPatchRequest(ApiModel):
    expected_version: int = Field(ge=1)
    changes: CollectionItemPatch


class UndoRequest(ApiModel):
    undo_token: SecretStr = Field(min_length=1, max_length=256, repr=False)


class UndoResponse(ApiModel):
    outcome: UndoOutcome
    collection_item_ids: tuple[str, ...]


class PublicModelCallResponse(ApiModel):
    sequence: int
    status: str
    model_name: str | None
    usage: TokenUsage | None
    latency_ms: int
    finish_reason: FinishReason | None
    error_code: str | None
    estimated_cost: Decimal | None
    cost_currency: str | None
    cost_estimation_source: str
    cost_unknown_reason: str | None


class PublicToolRunResponse(ApiModel):
    sequence: int
    tool_name: str
    input_summary: str
    status: ToolRunStatus
    output_summary: str | None
    latency_ms: int | None
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None


class AgentRunResponse(ApiModel):
    trace_id: str
    session_id: str | None
    intent: str
    workflow: str
    status: AgentRunStatus
    model_names: tuple[str, ...]
    model_calls: tuple[PublicModelCallResponse, ...]
    usage: TokenUsage
    estimated_cost: Decimal | None
    cost_currency: str | None
    cost_estimation_source: str
    cost_unknown_reason: str | None
    duration_ms: int | None
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tool_runs: tuple[PublicToolRunResponse, ...]


class ErrorResponse(ApiModel):
    error_code: str
    message: str
    trace_id: str | None = None
    issues: tuple[dict[str, str], ...] = ()
    recovery_actions: tuple[str, ...] = ()

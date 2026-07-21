"""Validated, provider-independent entities for M0-2A text collections."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.collections.statuses import (
    CollectionStatus,
    ensure_persistable_collection_status,
)
from app.domain.identifiers import (
    generate_collection_item_id,
    generate_message_id,
    generate_session_id,
    generate_source_id,
    generate_user_id,
    validate_collection_item_id,
    validate_message_id,
    validate_session_id,
    validate_source_id,
    validate_trace_id,
    validate_user_id,
)
from app.domain.time import require_aware_utc

_SAFE_PLATFORM = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SAFE_FILE_KEY = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_SAFE_MEDIA_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+/-]{0,126}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class UserMode(StrEnum):
    REAL = "real"
    DEMO = "demo"


class SupportedCity(StrEnum):
    SHENZHEN = "shenzhen"


class SupportedTimezone(StrEnum):
    ASIA_SHANGHAI = "Asia/Shanghai"


class SessionChannel(StrEnum):
    WEB = "web"
    DEMO = "demo"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageContentType(StrEnum):
    TEXT = "text"
    URL = "url"
    IMAGE = "image"


class SourceType(StrEnum):
    TEXT = "text"
    URL = "url"
    IMAGE = "image"


class SourceParseStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"


class CollectionKind(StrEnum):
    PLACE = "place"
    EVENT = "event"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceMetadata(DomainModel):
    """Allowlisted metadata only; headers, cookies, bodies, and credentials have no field."""

    media_type: str | None = None
    byte_size: int | None = Field(default=None, ge=0, le=20_000_000)
    content_sha256: str | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str | None) -> str | None:
        if value is not None and _SAFE_MEDIA_TYPE.fullmatch(value) is None:
            raise ValueError("media_type must be a safe IANA-style value")
        return value

    @field_validator("content_sha256")
    @classmethod
    def validate_hash(cls, value: str | None) -> str | None:
        if value is not None and _SHA256.fullmatch(value) is None:
            raise ValueError("content_sha256 must be 64 lowercase hexadecimal characters")
        return value

class User(DomainModel):
    id: str = Field(default_factory=generate_user_id)
    mode: UserMode
    city: SupportedCity = SupportedCity.SHENZHEN
    timezone: SupportedTimezone = SupportedTimezone.ASIA_SHANGHAI
    created_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _required_domain_utc(value)


class Session(DomainModel):
    id: str = Field(default_factory=generate_session_id)
    user_id: str
    channel: SessionChannel
    status: SessionStatus = SessionStatus.ACTIVE
    summary: str | None = Field(default=None, max_length=2000)
    created_at: datetime
    updated_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_session_id(value)

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("summary cannot be blank")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return _required_domain_utc(value)

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")
        return self


class Message(DomainModel):
    id: str = Field(default_factory=generate_message_id)
    session_id: str
    role: MessageRole
    content_type: MessageContentType
    content: str = Field(min_length=1, max_length=20_000, repr=False)
    trace_id: str | None = None
    created_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_message_id(value)

    @field_validator("session_id")
    @classmethod
    def validate_session(cls, value: str) -> str:
        return validate_session_id(value)

    @field_validator("trace_id")
    @classmethod
    def validate_optional_trace(cls, value: str | None) -> str | None:
        return None if value is None else validate_trace_id(value)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content cannot be blank")
        return value

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _required_domain_utc(value)


class Source(DomainModel):
    id: str = Field(default_factory=generate_source_id)
    user_id: str
    type: SourceType
    url: str | None = Field(default=None, max_length=2048)
    file_key: str | None = Field(default=None, max_length=128)
    platform: str | None = Field(default=None, max_length=64)
    parse_status: SourceParseStatus = SourceParseStatus.PENDING
    fetched_at: datetime | None = None
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)
    created_at: datetime
    updated_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_source_id(value)

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError("url must be an HTTP(S) URL without embedded credentials")
        return value

    @field_validator("file_key")
    @classmethod
    def validate_file_key(cls, value: str | None) -> str | None:
        if value is not None and _SAFE_FILE_KEY.fullmatch(value) is None:
            raise ValueError("file_key must be an opaque storage key")
        return value

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str | None) -> str | None:
        if value is not None and _SAFE_PLATFORM.fullmatch(value) is None:
            raise ValueError("platform must be a stable lowercase identifier")
        return value

    @field_validator("fetched_at")
    @classmethod
    def normalize_fetched_at(cls, value: datetime | None) -> datetime | None:
        return _domain_utc(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return _required_domain_utc(value)

    @model_validator(mode="after")
    def validate_type_fields(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")
        if self.type is SourceType.TEXT and (self.url is not None or self.file_key is not None):
            raise ValueError("text sources cannot carry URL or file storage pointers")
        if self.type is SourceType.URL and (self.url is None or self.file_key is not None):
            raise ValueError("URL sources require url and cannot carry file_key")
        if self.type is SourceType.IMAGE and (self.file_key is None or self.url is not None):
            raise ValueError("image sources require file_key and cannot carry url")
        return self


class CollectionItem(DomainModel):
    id: str = Field(default_factory=generate_collection_item_id)
    user_id: str
    kind: CollectionKind
    title: str = Field(min_length=1, max_length=200)
    city: SupportedCity = SupportedCity.SHENZHEN
    district: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=500)
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    price_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    price_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    status: CollectionStatus
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_collection_item_id(value)

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title cannot be blank")
        return normalized

    @field_validator("district", "address")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("optional text fields cannot be blank")
        return value

    @field_validator("event_start_at", "event_end_at")
    @classmethod
    def normalize_optional_times(cls, value: datetime | None) -> datetime | None:
        return _domain_utc(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return _required_domain_utc(value)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for tag in value:
            clean = tag.strip()
            if not clean or len(clean) > 64:
                raise ValueError("tags must contain nonblank values up to 64 characters")
            key = clean.casefold()
            if key in seen:
                raise ValueError("tags must be unique")
            seen.add(key)
            normalized.append(clean)
        return tuple(normalized)

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        ensure_persistable_collection_status(self.status)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")
        if self.event_start_at is not None and self.event_end_at is not None:
            if self.event_end_at <= self.event_start_at:
                raise ValueError("event_end_at must be after event_start_at")
        if self.kind is CollectionKind.PLACE and (
            self.event_start_at is not None or self.event_end_at is not None
        ):
            raise ValueError("Place items cannot carry Event schedule fields")
        if (self.price_amount is None) is not (self.price_currency is None):
            raise ValueError("price amount and currency must be provided together")
        return self


class CollectionSource(DomainModel):
    user_id: str
    collection_item_id: str
    source_id: str
    created_at: datetime

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("collection_item_id")
    @classmethod
    def validate_collection(cls, value: str) -> str:
        return validate_collection_item_id(value)

    @field_validator("source_id")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return validate_source_id(value)

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _required_domain_utc(value)


def _domain_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return require_aware_utc(value)


def _required_domain_utc(value: datetime) -> datetime:
    normalized = _domain_utc(value)
    assert normalized is not None
    return normalized

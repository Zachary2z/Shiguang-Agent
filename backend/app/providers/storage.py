"""The single provider-neutral private file storage capability boundary."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.time import require_aware_utc
from app.storage_policy import SUPPORTED_STORAGE_CONTENT_TYPES

_SAFE_FILE_KEY = re.compile(r"^[A-Za-z0-9_-]{32,128}$", flags=re.ASCII)


def validate_storage_file_key(value: str) -> str:
    """Reject path syntax and non-ASCII ambiguity at the provider boundary."""

    if not isinstance(value, str) or _SAFE_FILE_KEY.fullmatch(value) is None:
        raise StorageProviderError(code=StorageProviderErrorCode.INVALID_FILE_KEY)
    return value


class RetentionPolicy(StrEnum):
    """Stable lifecycle classes; expiration remains explicit metadata."""

    ORIGINAL_SCREENSHOT = "original_screenshot_30_days"
    DEMO_SESSION = "demo_session_max_24_hours"
    USER_CONTROLLED = "user_controlled"


class PrivateAccessMethod(StrEnum):
    """Local M0 storage has no safe public URL until an authenticated route exists."""

    APPLICATION_DOWNLOAD_ROUTE_REQUIRED = "application_download_route_required"
    EXPIRED = "expired"


class StorageModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class PrivateFileMetadata(StorageModel):
    """Provider-neutral lifecycle metadata; deliberately contains no filesystem path."""

    file_key: str
    created_at: datetime
    byte_size: int = Field(ge=1)
    content_type: str
    retention_policy: RetentionPolicy
    expires_at: datetime | None = None
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("file_key")
    @classmethod
    def validate_file_key(cls, value: str) -> str:
        try:
            return validate_storage_file_key(value)
        except StorageProviderError:
            raise ValueError("file_key must be an opaque storage key") from None

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        if value not in SUPPORTED_STORAGE_CONTENT_TYPES:
            raise ValueError("content_type must be a supported private file type")
        return value

    @field_validator("expires_at")
    @classmethod
    def normalize_expires_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @model_validator(mode="after")
    def validate_expiration(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        return self


class PrivateFileAccess(StorageModel):
    """Controlled-access descriptor that never pretends a local public URL exists."""

    file: PrivateFileMetadata
    method: PrivateAccessMethod


class PrivateFileDeleteResult(StorageModel):
    """Idempotent delete result: false means the key was already absent."""

    file_key: str
    deleted: bool

    @field_validator("file_key")
    @classmethod
    def validate_file_key(cls, value: str) -> str:
        try:
            return validate_storage_file_key(value)
        except StorageProviderError:
            raise ValueError("file_key must be an opaque storage key") from None


class StorageProviderErrorCode(StrEnum):
    INVALID_REQUEST = "STORAGE_INVALID_REQUEST"
    INVALID_FILE_KEY = "STORAGE_INVALID_FILE_KEY"
    CONTENT_TYPE_NOT_ALLOWED = "STORAGE_CONTENT_TYPE_NOT_ALLOWED"
    CONTENT_SIGNATURE_MISMATCH = "STORAGE_CONTENT_SIGNATURE_MISMATCH"
    FILE_EMPTY = "STORAGE_FILE_EMPTY"
    FILE_TOO_LARGE = "STORAGE_FILE_TOO_LARGE"
    NOT_FOUND = "STORAGE_FILE_NOT_FOUND"
    CORRUPT_OBJECT = "STORAGE_CORRUPT_OBJECT"
    WRITE_FAILED = "STORAGE_WRITE_FAILED"
    DELETE_FAILED = "STORAGE_DELETE_FAILED"


_ERROR_SUMMARIES = {
    StorageProviderErrorCode.INVALID_REQUEST: "The private file request is invalid.",
    StorageProviderErrorCode.INVALID_FILE_KEY: "The private file key is invalid.",
    StorageProviderErrorCode.CONTENT_TYPE_NOT_ALLOWED: "The private file type is not allowed.",
    StorageProviderErrorCode.CONTENT_SIGNATURE_MISMATCH: (
        "The private file content does not match its declared type."
    ),
    StorageProviderErrorCode.FILE_EMPTY: "The private file is empty.",
    StorageProviderErrorCode.FILE_TOO_LARGE: "The private file exceeds the size limit.",
    StorageProviderErrorCode.NOT_FOUND: "The private file was not found.",
    StorageProviderErrorCode.CORRUPT_OBJECT: "The private file is unavailable.",
    StorageProviderErrorCode.WRITE_FAILED: "The private file could not be stored.",
    StorageProviderErrorCode.DELETE_FAILED: "The private file could not be deleted.",
}


class StorageProviderError(Exception):
    """A fixed public-safe failure that retains no file, filename, or path data."""

    def __init__(self, *, code: StorageProviderErrorCode) -> None:
        if not isinstance(code, StorageProviderErrorCode):
            raise TypeError("code must be a StorageProviderErrorCode")
        summary = _ERROR_SUMMARIES[code]
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.retryable = code in {
            StorageProviderErrorCode.WRITE_FAILED,
            StorageProviderErrorCode.DELETE_FAILED,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "summary": self.summary,
            "retryable": self.retryable,
        }


class StorageProvider(ABC):
    """Store streams privately and expose only opaque controlled-access identifiers."""

    @abstractmethod
    async def put_private(
        self,
        file: AsyncIterable[bytes],
        *,
        content_type: str,
        retention_policy: RetentionPolicy,
        expires_at: datetime | None = None,
        original_filename: str | None = None,
    ) -> PrivateFileMetadata:
        """Stream one private object without trusting or persisting its original filename."""

    @abstractmethod
    async def get_private_access(self, file_key: str) -> PrivateFileAccess:
        """Return controlled access metadata, never a local path or fabricated URL."""

    @abstractmethod
    async def delete(self, file_key: str) -> PrivateFileDeleteResult:
        """Delete an object; an already absent valid key is a successful no-op."""

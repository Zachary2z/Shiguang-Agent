"""The single domain boundary for browser sessions and future channel identities."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.identifiers import validate_user_id
from app.domain.identity.security import validate_secret_hash
from app.domain.time import require_aware_utc


class IdentityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class PrincipalMode(StrEnum):
    REAL = "real"
    DEMO = "demo"


class BrowserSession(IdentityModel):
    """Durable server-side browser credential state; plaintext secrets have no field."""

    id: str = Field(pattern=r"^wbs_[a-f0-9]{32}$")
    user_id: str = Field(repr=False)
    token_hash: str = Field(repr=False)
    csrf_token_hash: str = Field(repr=False)
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("token_hash", "csrf_token_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return validate_secret_hash(value)

    @field_validator("created_at", "expires_at", "revoked_at")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @model_validator(mode="after")
    def validate_lifetime(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if self.revoked_at is not None and self.revoked_at < self.created_at:
            raise ValueError("revoked_at cannot be before created_at")
        return self

    def is_active_at(self, now: datetime) -> bool:
        timestamp = require_aware_utc(now)
        return self.revoked_at is None and timestamp < self.expires_at


class CurrentPrincipal(IdentityModel):
    """Verified request identity. It is intentionally absent from public DTOs."""

    web_session_id: str = Field(pattern=r"^wbs_[a-f0-9]{32}$", repr=False)
    user_id: str = Field(repr=False)
    mode: PrincipalMode
    expires_at: datetime = Field(repr=False)

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime) -> datetime:
        return require_aware_utc(value)


class WebSessionRepository(Protocol):
    async def add(self, browser_session: BrowserSession) -> BrowserSession: ...

    async def get_by_token_hash(self, token_hash: str) -> BrowserSession | None: ...

    async def replace_credentials(
        self,
        *,
        session_id: str,
        token_hash: str,
        csrf_token_hash: str,
    ) -> BrowserSession | None: ...

    async def revoke(
        self,
        *,
        session_id: str,
        revoked_at: datetime,
    ) -> BrowserSession | None: ...


class ChannelIdentity(IdentityModel):
    """Provider-neutral channel subject; provider-specific fields remain outside the domain."""

    channel: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    subject: str = Field(min_length=1, max_length=255, repr=False)


class ChannelIdentityRepository(Protocol):
    """Reserved for M2-2; M1-1 has no persistent consumer and therefore no table."""

    async def resolve_user_id(self, identity: ChannelIdentity) -> str | None: ...

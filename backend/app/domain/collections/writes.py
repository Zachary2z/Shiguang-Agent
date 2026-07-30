"""M0-2C contracts for reversible, version-protected collection writes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from app.domain.collections.candidate_metadata import (
    CandidateField,
    Uncertainty,
    default_cny_for_known_price,
    validate_cny_price_pair,
)
from app.domain.collections.entities import CollectionItem
from app.domain.collections.extraction import EventCandidate, PlaceCandidate
from app.domain.collections.statuses import CollectionStatus
from app.domain.identifiers import (
    generate_collection_write_operation_id,
    validate_collection_write_operation_id,
    validate_source_id,
    validate_user_id,
)
from app.domain.time import require_aware_utc

IDEMPOTENCY_KEY_MIN_LENGTH = 1
IDEMPOTENCY_KEY_MAX_LENGTH = 128
IDEMPOTENCY_KEY_PATTERN_TEXT = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
IdempotencyKey = Annotated[
    str,
    Field(
        min_length=IDEMPOTENCY_KEY_MIN_LENGTH,
        max_length=IDEMPOTENCY_KEY_MAX_LENGTH,
        pattern=IDEMPOTENCY_KEY_PATTERN_TEXT,
        strict=True,
    ),
]
IDEMPOTENCY_KEY_ADAPTER: TypeAdapter[str] = TypeAdapter(IdempotencyKey)
IDEMPOTENCY_KEY_JSON_SCHEMA = IDEMPOTENCY_KEY_ADAPTER.json_schema()
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def validate_idempotency_key(value: str) -> str:
    """Apply the one idempotency-key contract at every transport boundary."""

    try:
        return IDEMPOTENCY_KEY_ADAPTER.validate_python(value)
    except ValidationError:
        raise ValueError("idempotency_key must use safe visible characters") from None


class IdempotencyConflictError(RuntimeError):
    """A key or source was already used for a different normalized request."""

    def __init__(self) -> None:
        super().__init__("idempotency key or source conflicts with an existing request")


class VersionConflictError(RuntimeError):
    """The caller attempted to overwrite a newer collection version."""

    def __init__(self) -> None:
        super().__init__("collection version conflict")


class CollectionWriteOperation(BaseModel):
    """Safe operation metadata; the Undo token hash is infrastructure-private."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(default_factory=generate_collection_write_operation_id)
    user_id: str
    source_id: str
    idempotency_key: IdempotencyKey = Field(repr=False)
    request_fingerprint: str = Field(min_length=64, max_length=64, repr=False)
    undo_expires_at: datetime
    undone_at: datetime | None = None
    created_at: datetime

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_collection_write_operation_id(value)

    @field_validator("user_id")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        return validate_user_id(value)

    @field_validator("source_id")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return validate_source_id(value)

    @field_validator("request_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("request_fingerprint must be a lowercase SHA-256 digest")
        return value

    @field_validator("undo_expires_at", "undone_at", "created_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware_utc(value)

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.undo_expires_at <= self.created_at:
            raise ValueError("undo_expires_at must be after created_at")
        if self.undone_at is not None and self.undone_at < self.created_at:
            raise ValueError("undone_at cannot be before created_at")
        return self


class CollectionItemPatch(BaseModel):
    """Allowlisted editable fields; model_fields_set distinguishes omission from clearing."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    title: str | None = None
    city_hint: str | None = None
    district: str | None = None
    address: str | None = None
    business_district: str | None = None
    landmark: str | None = None
    metro_station: str | None = None
    event_start_date: date | None = Field(default=None, strict=False)
    event_end_date: date | None = Field(default=None, strict=False)
    event_start_at: datetime | None = Field(default=None, strict=False)
    event_end_at: datetime | None = Field(default=None, strict=False)
    event_start_clue: str | None = None
    event_end_clue: str | None = None
    price_amount: Decimal | None = None
    price_currency: str | None = None
    tags: tuple[str, ...] | None = None
    missing_fields: tuple[CandidateField, ...] | None = None
    uncertainties: tuple[Uncertainty, ...] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_price_update(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = default_cny_for_known_price(value)
        if "price_currency" in normalized and "price_amount" not in normalized:
            raise ValueError("price updates must provide price_amount")
        if "price_amount" in normalized and normalized["price_amount"] is None:
            normalized["price_currency"] = None
        return normalized

    @model_validator(mode="after")
    def reject_null_required_values(self) -> Self:
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        if "tags" in self.model_fields_set and self.tags is None:
            raise ValueError("tags cannot be null")
        if "missing_fields" in self.model_fields_set and self.missing_fields is None:
            raise ValueError("missing_fields cannot be null")
        if "uncertainties" in self.model_fields_set and self.uncertainties is None:
            raise ValueError("uncertainties cannot be null")
        validate_cny_price_pair(self.price_amount, self.price_currency)
        return self

    def updates(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class AutoSaveResult(BaseModel):
    """Persisted items plus a one-time secret returned only by the creating call."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_id: str | None
    items: tuple[CollectionItem, ...] = ()
    undo_token: SecretStr | None = Field(default=None, repr=False)
    undo_expires_at: datetime | None = None
    replayed: bool = False


class UndoOutcome(StrEnum):
    UNDONE = "undone"
    ALREADY_UNDONE = "already_undone"
    NOT_AVAILABLE = "not_available"


class UndoResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    outcome: UndoOutcome
    collection_item_ids: tuple[str, ...] = ()


def status_for_extraction_candidate(
    candidate: PlaceCandidate | EventCandidate,
) -> CollectionStatus:
    """Map an extraction candidate without pretending M0-3 POI resolution exists."""

    if isinstance(candidate, PlaceCandidate):
        return CollectionStatus.PENDING_DETAILS
    return CollectionStatus.PENDING_DETAILS

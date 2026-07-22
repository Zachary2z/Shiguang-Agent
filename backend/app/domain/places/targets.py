"""Unified confirmed and unresolved Place target contracts for M0-3D."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Self
from unicodedata import category, normalize

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.identifiers import (
    validate_collection_item_id,
    validate_source_id,
    validate_user_id,
)
from app.domain.places.contracts import CoordinateSystem, Poi
from app.domain.places.matching import (
    MatchConfidence,
    MatchEvidence,
    MatchStatus,
    PlaceMatchCandidate,
    PlaceMatchResult,
)
from app.domain.time import require_aware_utc

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NAMESPACE = re.compile(r"^[a-z][a-z0-9._:-]{0,63}$")


class PlaceTargetContract(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class PlaceScope(StrEnum):
    EXACT = "exact"
    ANY_BRANCH = "any_branch"


class PlaceConfirmationSource(StrEnum):
    AUTO_UNIQUE_MATCH = "auto_unique_match"
    USER_SELECTION = "user_selection"


class BrandIdentityConfirmationSource(StrEnum):
    PROVIDER = "provider"
    CURATED = "curated"
    USER_CONFIRMED = "user_confirmed"


def normalize_brand_name(value: str) -> str:
    """Normalize display text for search/display only, never as brand identity proof."""

    normalized = normalize("NFKC", value).casefold()
    result = "".join(
        character
        for character in normalized
        if not character.isspace() and not category(character).startswith(("P", "S", "C"))
    )
    if not result:
        raise ValueError("brand name must contain visible letters or numbers")
    return result


class ConfirmedBrandIdentity(PlaceTargetContract):
    """A stable identity supplied by a confirmed namespace, never inferred from a name."""

    namespace: str = Field(min_length=1, max_length=64)
    stable_id: str = Field(min_length=1, max_length=128, repr=False)
    display_name: str = Field(min_length=1, max_length=200)
    normalized_name: str = Field(min_length=1, max_length=200)
    identity_confirmed_by: BrandIdentityConfirmationSource
    identity_confirmed_at: datetime

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        if _NAMESPACE.fullmatch(value) is None:
            raise ValueError("brand identity namespace is invalid")
        return value

    @field_validator("stable_id")
    @classmethod
    def validate_stable_id(cls, value: str) -> str:
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("brand stable identity is invalid")
        return value

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("brand display name cannot be blank")
        return cleaned

    @field_validator("identity_confirmed_at")
    @classmethod
    def normalize_confirmation_time(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @model_validator(mode="after")
    def require_matching_normalized_name(self) -> Self:
        if self.normalized_name != normalize_brand_name(self.display_name):
            raise ValueError("normalized brand name does not match display name")
        return self

    @property
    def identity(self) -> tuple[str, str]:
        return (self.namespace, self.stable_id)


class PlaceCandidateSnapshot(PlaceTargetContract):
    """A refreshable M0-3C result captured at a specific query time."""

    result: PlaceMatchResult
    queried_at: datetime

    @field_validator("queried_at")
    @classmethod
    def normalize_queried_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @property
    def candidates(self) -> tuple[PlaceMatchCandidate, ...]:
        return self.result.candidates

    @property
    def fingerprint(self) -> str:
        """Stable token proving which persisted candidate snapshot a user saw."""

        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class PlaceTarget(PlaceTargetContract):
    """One confirmed concrete POI or one confirmed flexible brand identity."""

    scope: PlaceScope
    poi: Poi | None = None
    brand_identity: ConfirmedBrandIdentity | None = None
    match_status: MatchStatus
    confidence: MatchConfidence | None = None
    confirmed_by: PlaceConfirmationSource
    confirmed_at: datetime
    evidence_summary: tuple[MatchEvidence, ...] = Field(default_factory=tuple, max_length=20)

    @field_validator("confirmed_at")
    @classmethod
    def normalize_confirmed_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)

    @model_validator(mode="after")
    def validate_target_shape(self) -> Self:
        if self.scope is PlaceScope.EXACT:
            if self.poi is None or self.brand_identity is not None:
                raise ValueError("exact targets require exactly one confirmed POI")
            if self.poi.coordinate.coordinate_system is not CoordinateSystem.GCJ_02:
                raise ValueError("exact targets require GCJ-02 coordinates")
            if self.match_status is not MatchStatus.MATCHED or self.confidence is None:
                raise ValueError("exact targets require a matched status and confidence")
            if self.confidence is MatchConfidence.LOW:
                raise ValueError("low-confidence candidates cannot become exact targets")
            if not self.evidence_summary:
                raise ValueError("exact targets require a matching evidence summary")
        else:
            if self.brand_identity is None or self.poi is not None:
                raise ValueError("any-branch targets require one stable brand identity")
            if self.confirmed_by is not PlaceConfirmationSource.USER_SELECTION:
                raise ValueError("any-branch targets require explicit user selection")
        return self


class PlaceSelectionOperation(PlaceTargetContract):
    """Durable idempotency record for one explicit selection transaction."""

    user_id: str
    idempotency_key: str = Field(min_length=1, max_length=128, repr=False)
    collection_item_id: str
    source_id: str
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)
    result_item_ids: tuple[str, ...] = Field(min_length=1)
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

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("idempotency key is invalid")
        return value

    @field_validator("result_item_ids")
    @classmethod
    def validate_result_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        validated = tuple(validate_collection_item_id(item) for item in value)
        if len(set(validated)) != len(validated):
            raise ValueError("selection result items must be unique")
        return validated

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return require_aware_utc(value)


class ResolvedPlaceTargetKind(StrEnum):
    EXACT = "exact"
    ANY_BRANCH = "any_branch"
    UNCONFIRMED = "unconfirmed"


class ResolvedPlaceTarget(PlaceTargetContract):
    kind: ResolvedPlaceTargetKind
    poi: Poi | None = None
    brand_identity: ConfirmedBrandIdentity | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> Self:
        if self.kind is ResolvedPlaceTargetKind.EXACT and (
            self.poi is None or self.brand_identity is not None
        ):
            raise ValueError("exact resolution requires one POI")
        if self.kind is ResolvedPlaceTargetKind.ANY_BRANCH and (
            self.brand_identity is None or self.poi is not None
        ):
            raise ValueError("any-branch resolution requires one brand identity")
        if self.kind is ResolvedPlaceTargetKind.UNCONFIRMED and (
            self.poi is not None or self.brand_identity is not None
        ):
            raise ValueError("unconfirmed resolution cannot carry a usable target")
        return self


def resolve_place_target(
    target: PlaceTarget | None,
    *,
    collection_status: str,
) -> ResolvedPlaceTarget:
    """Expose a stable planning boundary without doing any planning or branch lookup."""

    if collection_status != "active" or target is None:
        return ResolvedPlaceTarget(kind=ResolvedPlaceTargetKind.UNCONFIRMED)
    if target.scope is PlaceScope.EXACT:
        assert target.poi is not None
        return ResolvedPlaceTarget(
            kind=ResolvedPlaceTargetKind.EXACT,
            poi=target.poi.model_copy(deep=True),
        )
    assert target.brand_identity is not None
    return ResolvedPlaceTarget(
        kind=ResolvedPlaceTargetKind.ANY_BRANCH,
        brand_identity=target.brand_identity.model_copy(deep=True),
    )


def exact_target_from_candidate(
    candidate: PlaceMatchCandidate,
    *,
    confirmed_by: PlaceConfirmationSource,
    confirmed_at: datetime,
) -> PlaceTarget:
    """Promote only an already-filtered M0-3C candidate to a confirmed POI target."""

    if candidate.has_hard_conflict:
        raise ValueError("hard-conflict candidates cannot become exact targets")
    if candidate.confidence is MatchConfidence.LOW:
        raise ValueError("low-confidence candidates cannot become exact targets")
    poi = Poi(
        provider=candidate.provider,
        poi_id=candidate.poi_id,
        name=candidate.name,
        branch_name=candidate.branch_name,
        city_code=candidate.city_code,
        district=candidate.district,
        business_area=candidate.business_area,
        address=candidate.address,
        coordinate=candidate.coordinate.model_copy(deep=True),
        poi_type=candidate.poi_type,
    )
    return PlaceTarget(
        scope=PlaceScope.EXACT,
        poi=poi,
        match_status=MatchStatus.MATCHED,
        confidence=candidate.confidence,
        confirmed_by=confirmed_by,
        confirmed_at=confirmed_at,
        evidence_summary=tuple(item.model_copy(deep=True) for item in candidate.evidence),
    )

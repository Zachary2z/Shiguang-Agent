"""Transactional M0-2C auto-save, patch, logical delete, and Undo workflow."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast
from unicodedata import normalize

from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.place_matching import PlaceMatchingService
from app.application.place_targets import PlaceTargetSelectionService
from app.domain.collections import (
    EVENT_TEMPORAL_FIELDS,
    AutoSaveResult,
    CandidateField,
    CollectionItem,
    CollectionItemPatch,
    CollectionKind,
    CollectionStatus,
    CollectionWriteOperation,
    EventCandidate,
    ExtractionOutcome,
    ExtractionResult,
    IdempotencyConflictError,
    PlaceCandidate,
    PlanCity,
    ResourceNotFoundError,
    Source,
    Uncertainty,
    UndoOutcome,
    UndoResult,
    VersionConflictError,
    event_schedule_is_confirmed,
    status_for_extraction_candidate,
)
from app.domain.collections.writes import validate_idempotency_key
from app.domain.identifiers import validate_collection_item_id, validate_user_id
from app.domain.places import (
    CityScope,
    PlaceMatchRequest,
    PlaceScope,
    PlaceTarget,
    resolve_city_hint,
)
from app.domain.time import require_aware_utc, utc_now
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.providers.map import MapProviderError

DEFAULT_UNDO_TTL = timedelta(minutes=10)
MAX_UNDO_TTL = timedelta(hours=24)
LOCATION_CLUE_FIELDS = frozenset(
    {
        "title",
        "city_hint",
        "district",
        "address",
        "business_district",
        "landmark",
        "metro_station",
    }
)


class CollectionWriteService:
    """The single application entry point for collection mutations in M0-2C."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        now: Callable[[], datetime] = utc_now,
        token_factory: Callable[[], str] | None = None,
        undo_ttl: timedelta = DEFAULT_UNDO_TTL,
    ) -> None:
        if undo_ttl <= timedelta(0) or undo_ttl > MAX_UNDO_TTL:
            raise ValueError("undo_ttl must be greater than zero and at most 24 hours")
        self._session = session
        self._repository = SqlAlchemyCollectionRepository(session)
        self._now_provider = now
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._undo_ttl = undo_ttl

    async def auto_save(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        source: Source,
        extraction_result: ExtractionResult,
        place_matching: PlaceMatchingService | None = None,
    ) -> AutoSaveResult:
        owner = validate_user_id(user_id)
        if source.user_id != owner:
            raise ValueError("user_id must match Source.user_id")
        idempotency_key = validate_idempotency_key(idempotency_key)
        if extraction_result.outcome is not ExtractionOutcome.CANDIDATES:
            return AutoSaveResult(source_id=None)

        fingerprint = self._request_fingerprint(source, extraction_result)
        try:
            saved = await self._create_or_replay(
                owner=owner,
                idempotency_key=idempotency_key,
                source=source,
                extraction_result=extraction_result,
                fingerprint=fingerprint,
            )
        except IntegrityError as exc:
            await self._session.rollback()
            replay = await self._replay_after_unique_conflict(
                owner=owner,
                idempotency_key=idempotency_key,
                source_id=source.id,
                fingerprint=fingerprint,
            )
            if replay is None:
                raise exc
            saved = replay
        if place_matching is None or saved.replayed:
            return saved
        await self._session.rollback()
        resolved_items = []
        for item in saved.items:
            try:
                resolved_items.append(
                    await self.continue_location_confirmation(
                        owner=owner,
                        item=item,
                        place_matching=place_matching,
                    )
                )
            except asyncio.CancelledError:
                raise
            except MapProviderError:
                resolved_items.append(item)
        unique_items = tuple({item.id: item for item in resolved_items}.values())
        return saved.model_copy(update={"items": unique_items})

    async def patch(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        expected_version: int,
        patch: CollectionItemPatch,
        place_matching: PlaceMatchingService | None = None,
    ) -> CollectionItem:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        now = self._now()
        source_id: str | None = None
        async with self._session.begin():
            current = await self._repository.get_collection_item(
                user_id=owner,
                collection_item_id=identifier,
            )
            if current is None:
                raise ResourceNotFoundError
            location_identity_changed = self._location_identity_changed(
                current=current,
                patch=patch,
            )
            values = current.model_dump(mode="python")
            values.update(patch.updates())
            self._preserve_equivalent_location_clues(
                current=current,
                values=values,
                patch=patch,
            )
            self._recalculate_candidate_metadata(values, patch=patch)
            self._preserve_unconfirmed_event_time_metadata(
                current=current,
                values=values,
                patch=patch,
            )
            invalidate_resolution = location_identity_changed and (
                current.place_target is not None
                or current.place_candidate_snapshot is not None
                or current.status is not CollectionStatus.PENDING_DETAILS
            )
            if location_identity_changed:
                values.update(
                    status=CollectionStatus.PENDING_DETAILS,
                    place_target=None,
                    place_candidate_snapshot=None,
                )
            values["updated_at"] = now
            desired = CollectionItem.model_validate(values)
            if location_identity_changed and place_matching is not None:
                links = await self._repository.list_collection_sources(
                    user_id=owner,
                    collection_item_id=identifier,
                )
                source_id = links[0].source_id if links else None
                updated = (
                    desired
                    if source_id is not None
                    else await self._repository.apply_place_resolution(
                        user_id=owner,
                        item=desired,
                        expected_version=expected_version,
                    )
                )
            elif invalidate_resolution:
                updated = await self._repository.apply_place_resolution(
                    user_id=owner,
                    item=desired,
                    expected_version=expected_version,
                )
            else:
                updated = await self._repository.update_collection_item(
                    user_id=owner,
                    item=desired,
                    expected_version=expected_version,
                )
            target_status = self._event_status_after_confirmation(updated)
            if source_id is None and target_status is not updated.status:
                updated = await self._repository.transition_collection_status(
                    user_id=owner,
                    collection_item_id=identifier,
                    target=target_status,
                    updated_at=now,
                )
        if not location_identity_changed:
            return updated
        if source_id is None or place_matching is None:
            return updated
        has_city_hint, city_code = resolve_city_hint(desired.city_hint)
        if has_city_hint and city_code is None:
            async with self._session.begin():
                return await self._repository.apply_place_resolution(
                    user_id=owner,
                    item=desired,
                    expected_version=expected_version,
                )
        match_result = await place_matching.match(
            PlaceMatchRequest(
                candidate=self._place_candidate_from_item(desired),
                city=CityScope(city_code=city_code or PlanCity.SHENZHEN.value),
                search_district=desired.district,
            )
        )
        return await PlaceTargetSelectionService(
            session=self._session
        ).record_candidates_after_patch(
            user_id=owner,
            original_item=current,
            desired_item=desired,
            source_id=source_id,
            match_result=match_result,
            queried_at=self._now(),
            expected_version=expected_version,
        )

    async def continue_location_confirmation(
        self,
        *,
        owner: str,
        item: CollectionItem,
        place_matching: PlaceMatchingService | None,
    ) -> CollectionItem:
        if (
            item.kind not in {CollectionKind.PLACE, CollectionKind.EVENT}
            or item.place_target is not None
            or item.status
            not in {
                CollectionStatus.PENDING_DETAILS,
                CollectionStatus.PENDING_SELECTION,
            }
        ):
            return item
        has_city_hint, city_code = resolve_city_hint(item.city_hint)
        if has_city_hint and city_code is None:
            return item
        if place_matching is None:
            return item
        links = await self._repository.list_collection_sources(
            user_id=owner,
            collection_item_id=item.id,
        )
        if not links:
            return item
        candidate = self._place_candidate_from_item(item)
        try:
            match_result = await place_matching.match(
                PlaceMatchRequest(
                    candidate=candidate,
                    city=CityScope(
                        city_code=city_code or PlanCity.SHENZHEN.value,
                    ),
                    search_district=item.district,
                )
            )
        except asyncio.CancelledError:
            await asyncio.shield(self._session.rollback())
            raise
        except Exception:
            await self._session.rollback()
            raise
        await self._session.rollback()
        return await PlaceTargetSelectionService(session=self._session).record_candidates(
            user_id=owner,
            collection_item_id=item.id,
            source_id=links[0].source_id,
            match_result=match_result,
            queried_at=self._now(),
            expected_version=item.version,
        )

    @classmethod
    def _location_identity_changed(
        cls,
        *,
        current: CollectionItem,
        patch: CollectionItemPatch,
    ) -> bool:
        updates = patch.updates()
        return any(
            not cls._equivalent_location_clue(
                field=field,
                current=getattr(current, field),
                updated=updates[field],
            )
            for field in LOCATION_CLUE_FIELDS.intersection(patch.model_fields_set)
        )

    @classmethod
    def _preserve_equivalent_location_clues(
        cls,
        *,
        current: CollectionItem,
        values: dict[str, object],
        patch: CollectionItemPatch,
    ) -> None:
        for field in LOCATION_CLUE_FIELDS.intersection(patch.model_fields_set):
            if cls._equivalent_location_clue(
                field=field,
                current=getattr(current, field),
                updated=values[field],
            ):
                values[field] = getattr(current, field)

    @staticmethod
    def _equivalent_location_clue(
        *,
        field: str,
        current: object,
        updated: object,
    ) -> bool:
        if current is None or updated is None:
            return current is updated
        if not isinstance(current, str) or not isinstance(updated, str):
            return current == updated
        if field == "city_hint":
            _, current_city = resolve_city_hint(current)
            _, updated_city = resolve_city_hint(updated)
            if current_city is not None and updated_city is not None:
                return current_city == updated_city
        normalized_current = " ".join(normalize("NFKC", current).casefold().split())
        normalized_updated = " ".join(normalize("NFKC", updated).casefold().split())
        return normalized_current == normalized_updated

    @staticmethod
    def _place_candidate_from_item(item: CollectionItem) -> PlaceCandidate:
        candidate_address = (
            None if item.kind is CollectionKind.EVENT else item.address
        )
        present = {
            CandidateField.CITY_HINT: item.city_hint is not None,
            CandidateField.DISTRICT: item.district is not None,
            CandidateField.ADDRESS: candidate_address is not None,
            CandidateField.BUSINESS_DISTRICT: item.business_district is not None,
            CandidateField.LANDMARK: item.landmark is not None,
            CandidateField.METRO_STATION: item.metro_station is not None,
            CandidateField.PRICE: item.price_amount is not None,
            CandidateField.TAGS: bool(item.tags),
        }
        uncertain_fields = {entry.field for entry in item.uncertainties}
        missing = tuple(
            field
            for field, is_present in present.items()
            if not is_present and field not in uncertain_fields
        )
        return PlaceCandidate(
            title=(
                item.address or item.landmark or item.title
                if item.kind is CollectionKind.EVENT
                else item.title
            ),
            city_hint=item.city_hint,
            district=item.district,
            # Event.address is the existing venue-name slot used to start the POI
            # query; it is not reliable evidence of the provider's street address.
            address=candidate_address,
            business_district=item.business_district,
            landmark=item.landmark,
            metro_station=item.metro_station,
            price_amount=item.price_amount,
            price_currency=item.price_currency,
            tags=item.tags,
            missing_fields=missing,
            uncertainties=tuple(
                entry for entry in item.uncertainties if entry.field in present
            ),
        )

    @staticmethod
    def _recalculate_candidate_metadata(
        values: dict[str, object],
        *,
        patch: CollectionItemPatch,
    ) -> None:
        field_by_patch_name = {
            "city_hint": CandidateField.CITY_HINT,
            "district": CandidateField.DISTRICT,
            "address": CandidateField.ADDRESS,
            "business_district": CandidateField.BUSINESS_DISTRICT,
            "landmark": CandidateField.LANDMARK,
            "metro_station": CandidateField.METRO_STATION,
            "event_start_date": CandidateField.EVENT_START_DATE,
            "event_end_date": CandidateField.EVENT_END_DATE,
            "event_start_at": CandidateField.EVENT_START_AT,
            "event_end_at": CandidateField.EVENT_END_AT,
            "price_amount": CandidateField.PRICE,
            "tags": CandidateField.TAGS,
        }
        touched = {
            field_by_patch_name[name]
            for name in patch.model_fields_set
            if name in field_by_patch_name
        }
        if not touched:
            return
        missing = [
            CandidateField(field)
            for field in cast(tuple[CandidateField | str, ...], values.get("missing_fields", ()))
        ]
        uncertainties = [
            Uncertainty.model_validate(entry)
            for entry in cast(
                tuple[Uncertainty | dict[str, object], ...],
                values.get("uncertainties", ()),
            )
        ]
        for name, field in field_by_patch_name.items():
            if field not in touched:
                continue
            value = values.get(name)
            is_present = bool(value) if field is CandidateField.TAGS else value is not None
            missing = [existing for existing in missing if existing is not field]
            uncertainties = [
                existing for existing in uncertainties if existing.field is not field
            ]
            if not is_present:
                missing.append(field)
        if (
            values.get("event_start_date") is not None
            and values.get("event_end_date") is not None
            and values.get("event_start_at") is None
            and values.get("event_end_at") is None
        ):
            missing = [
                field
                for field in missing
                if field
                not in {CandidateField.EVENT_START_AT, CandidateField.EVENT_END_AT}
            ]
        values["missing_fields"] = tuple(dict.fromkeys(missing))
        values["uncertainties"] = tuple(uncertainties)

    @staticmethod
    def _preserve_unconfirmed_event_time_metadata(
        *,
        current: CollectionItem,
        values: dict[str, object],
        patch: CollectionItemPatch,
    ) -> None:
        if current.kind is not CollectionKind.EVENT:
            return
        touched = {
            field
            for field in EVENT_TEMPORAL_FIELDS
            if field.value in patch.model_fields_set
        }
        existing = {
            uncertainty.field: uncertainty
            for uncertainty in current.uncertainties
            if uncertainty.field in EVENT_TEMPORAL_FIELDS
        }
        uncertainties: list[Uncertainty] = []
        for raw in cast(
            tuple[Uncertainty | dict[str, object], ...],
            values.get("uncertainties", ()),
        ):
            uncertainty = Uncertainty.model_validate(raw)
            if uncertainty.field not in existing or uncertainty.field in touched:
                uncertainties.append(uncertainty)
        uncertainties.extend(
            uncertainty
            for field, uncertainty in existing.items()
            if field not in touched
        )
        values["uncertainties"] = tuple(uncertainties)

    @staticmethod
    def _event_status_after_confirmation(item: CollectionItem) -> CollectionStatus:
        if (
            item.kind is not CollectionKind.EVENT
            or item.status
            not in {CollectionStatus.ACTIVE, CollectionStatus.PENDING_DETAILS}
            or not isinstance(item.place_target, PlaceTarget)
            or item.place_target.scope is not PlaceScope.EXACT
        ):
            return item.status
        if event_schedule_is_confirmed(
            event_start_date=item.event_start_date,
            event_end_date=item.event_end_date,
            event_start_at=item.event_start_at,
            event_end_at=item.event_end_at,
            uncertainties=item.uncertainties,
        ):
            return CollectionStatus.ACTIVE
        return CollectionStatus.PENDING_DETAILS

    async def delete(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        expected_version: int | None = None,
    ) -> CollectionItem:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        async with self._session.begin():
            return await self._repository.delete_collection_item(
                user_id=owner,
                collection_item_id=identifier,
                updated_at=self._now(),
                expected_version=expected_version,
            )

    async def undo(self, *, user_id: str, undo_token: str) -> UndoResult:
        return await self._undo(
            user_id=user_id,
            undo_token=undo_token,
            required_collection_item_id=None,
        )

    async def restore(
        self,
        *,
        user_id: str,
        collection_item_id: str,
    ) -> CollectionItem:
        """Restore the exact pre-delete status through the existing write boundary."""

        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        async with self._session.begin():
            return await self._repository.restore_collection_item(
                user_id=owner,
                collection_item_id=identifier,
                updated_at=self._now(),
            )

    async def undo_collection_item(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        undo_token: str,
    ) -> UndoResult:
        """Undo only when the token's operation group contains the path item."""

        identifier = validate_collection_item_id(collection_item_id)
        return await self._undo(
            user_id=user_id,
            undo_token=undo_token,
            required_collection_item_id=identifier,
        )

    async def get_idempotent_result(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> AutoSaveResult | None:
        """Return a prior safe result without reissuing its one-time Undo token."""

        owner = validate_user_id(user_id)
        idempotency_key = validate_idempotency_key(idempotency_key)
        operation = await self._repository.get_write_operation_by_idempotency_key(
            user_id=owner,
            idempotency_key=idempotency_key,
        )
        if operation is None:
            return None
        items = await self._repository.list_write_operation_items(
            user_id=owner,
            operation_id=operation.id,
        )
        return AutoSaveResult(
            source_id=operation.source_id,
            items=tuple(items),
            undo_expires_at=operation.undo_expires_at,
            replayed=True,
        )

    async def _undo(
        self,
        *,
        user_id: str,
        undo_token: str,
        required_collection_item_id: str | None,
    ) -> UndoResult:
        owner = validate_user_id(user_id)
        if not isinstance(undo_token, str) or not undo_token:
            return UndoResult(outcome=UndoOutcome.NOT_AVAILABLE)
        token_hash = self._token_hash(undo_token)
        now = self._now()
        async with self._session.begin():
            operation = await self._repository.get_write_operation_by_undo_hash(
                user_id=owner,
                undo_token_hash=token_hash,
            )
            if operation is None or now >= operation.undo_expires_at:
                return UndoResult(outcome=UndoOutcome.NOT_AVAILABLE)
            items = await self._repository.list_write_operation_items(
                user_id=owner,
                operation_id=operation.id,
            )
            item_ids = tuple(item.id for item in items)
            if (
                required_collection_item_id is not None
                and required_collection_item_id not in item_ids
            ):
                return UndoResult(outcome=UndoOutcome.NOT_AVAILABLE)
            claimed = await self._repository.claim_write_operation_undo(
                user_id=owner,
                undo_token_hash=token_hash,
                claimed_at=now,
            )
            if not claimed:
                operation = await self._repository.get_write_operation_by_undo_hash(
                    user_id=owner,
                    undo_token_hash=token_hash,
                )
                if operation is None:
                    return UndoResult(outcome=UndoOutcome.NOT_AVAILABLE)
                if operation.undone_at is None:
                    raise VersionConflictError
                return UndoResult(
                    outcome=UndoOutcome.ALREADY_UNDONE,
                    collection_item_ids=item_ids,
                )
            for item in items:
                await self._repository.delete_collection_item(
                    user_id=owner,
                    collection_item_id=item.id,
                    updated_at=now,
                    expected_version=item.version,
                )
            return UndoResult(
                outcome=UndoOutcome.UNDONE,
                collection_item_ids=item_ids,
            )

    async def _create_or_replay(
        self,
        *,
        owner: str,
        idempotency_key: str,
        source: Source,
        extraction_result: ExtractionResult,
        fingerprint: str,
    ) -> AutoSaveResult:
        async with self._session.begin():
            existing = await self._find_existing_operation(
                owner=owner,
                idempotency_key=idempotency_key,
                source_id=source.id,
            )
            if existing is not None:
                return await self._replay(owner, existing, fingerprint)

            stored_source = await self._repository.get_source(
                user_id=owner,
                source_id=source.id,
            )
            if stored_source is None:
                await self._repository.add_source(user_id=owner, source=source)
            elif stored_source != source:
                raise IdempotencyConflictError

            now = self._now()
            plaintext_token = self._new_token()
            operation = CollectionWriteOperation(
                user_id=owner,
                source_id=source.id,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                undo_expires_at=now + self._undo_ttl,
                created_at=now,
            )
            await self._repository.add_write_operation(
                user_id=owner,
                operation=operation,
                undo_token_hash=self._token_hash(plaintext_token),
            )

            items: list[CollectionItem] = []
            for sequence, candidate in enumerate(extraction_result.candidates, start=1):
                item = self._item_from_candidate(owner, candidate, now)
                stored_item = await self._repository.add_collection_item(
                    user_id=owner,
                    item=item,
                )
                await self._repository.add_collection_source(
                    user_id=owner,
                    collection_item_id=stored_item.id,
                    source_id=source.id,
                    created_at=now,
                )
                await self._repository.add_write_operation_item(
                    user_id=owner,
                    operation_id=operation.id,
                    collection_item_id=stored_item.id,
                    sequence=sequence,
                    created_at=now,
                )
                items.append(stored_item)

            return AutoSaveResult(
                source_id=source.id,
                items=tuple(items),
                undo_token=SecretStr(plaintext_token),
                undo_expires_at=operation.undo_expires_at,
            )

    async def _replay_after_unique_conflict(
        self,
        *,
        owner: str,
        idempotency_key: str,
        source_id: str,
        fingerprint: str,
    ) -> AutoSaveResult | None:
        async with self._session.begin():
            operation = await self._find_existing_operation(
                owner=owner,
                idempotency_key=idempotency_key,
                source_id=source_id,
            )
            if operation is None:
                return None
            return await self._replay(owner, operation, fingerprint)

    async def _find_existing_operation(
        self,
        *,
        owner: str,
        idempotency_key: str,
        source_id: str,
    ) -> CollectionWriteOperation | None:
        by_key = await self._repository.get_write_operation_by_idempotency_key(
            user_id=owner,
            idempotency_key=idempotency_key,
        )
        by_source = await self._repository.get_write_operation_by_source(
            user_id=owner,
            source_id=source_id,
        )
        if by_key is not None and by_source is not None and by_key.id != by_source.id:
            raise IdempotencyConflictError
        return by_key or by_source

    async def _replay(
        self,
        owner: str,
        operation: CollectionWriteOperation,
        fingerprint: str,
    ) -> AutoSaveResult:
        if operation.request_fingerprint != fingerprint:
            raise IdempotencyConflictError
        items = await self._repository.list_write_operation_items(
            user_id=owner,
            operation_id=operation.id,
        )
        return AutoSaveResult(
            source_id=operation.source_id,
            items=tuple(items),
            undo_expires_at=operation.undo_expires_at,
            replayed=True,
        )

    @staticmethod
    def _item_from_candidate(
        owner: str,
        candidate: PlaceCandidate | EventCandidate,
        now: datetime,
    ) -> CollectionItem:
        timestamp = require_aware_utc(now)
        event_start_date = None
        event_end_date = None
        event_start_at = None
        event_end_at = None
        event_start_clue = None
        event_end_clue = None
        if isinstance(candidate, EventCandidate):
            event_start_date = candidate.event_start_date
            event_end_date = candidate.event_end_date
            event_start_at = candidate.event_start_at
            event_end_at = candidate.event_end_at
            event_start_clue = candidate.event_start_clue
            event_end_clue = candidate.event_end_clue
        return CollectionItem(
            user_id=owner,
            kind=CollectionKind(candidate.kind),
            title=candidate.title,
            city_hint=candidate.city_hint,
            district=candidate.district,
            address=candidate.address,
            business_district=candidate.business_district,
            landmark=candidate.landmark,
            metro_station=candidate.metro_station,
            event_start_date=event_start_date,
            event_end_date=event_end_date,
            event_start_at=event_start_at,
            event_end_at=event_end_at,
            event_start_clue=event_start_clue,
            event_end_clue=event_end_clue,
            price_amount=candidate.price_amount,
            price_currency=candidate.price_currency,
            tags=candidate.tags,
            missing_fields=candidate.missing_fields,
            uncertainties=candidate.uncertainties,
            status=status_for_extraction_candidate(candidate),
            created_at=timestamp,
            updated_at=timestamp,
        )

    @staticmethod
    def _request_fingerprint(source: Source, result: ExtractionResult) -> str:
        normalized = json.dumps(
            {
                "source": source.model_dump(mode="json"),
                "extraction_result": result.model_dump(mode="json"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _new_token(self) -> str:
        token = self._token_factory()
        if (
            not isinstance(token, str)
            or len(token) < 32
            or len(token) > 256
            or any(character.isspace() for character in token)
        ):
            raise ValueError("token_factory must return an opaque token")
        return token

    def _now(self) -> datetime:
        return require_aware_utc(self._now_provider())

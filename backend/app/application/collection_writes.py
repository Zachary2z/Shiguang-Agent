"""Transactional M0-2C auto-save, patch, logical delete, and Undo workflow."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import (
    AutoSaveResult,
    CollectionItem,
    CollectionItemPatch,
    CollectionKind,
    CollectionWriteOperation,
    EventCandidate,
    ExtractionOutcome,
    ExtractionResult,
    IdempotencyConflictError,
    PlaceCandidate,
    ResourceNotFoundError,
    Source,
    UndoOutcome,
    UndoResult,
    VersionConflictError,
    status_for_extraction_candidate,
)
from app.domain.collections.writes import validate_idempotency_key
from app.domain.identifiers import validate_collection_item_id, validate_user_id
from app.domain.time import require_aware_utc, utc_now
from app.infrastructure.repositories import SqlAlchemyCollectionRepository

DEFAULT_UNDO_TTL = timedelta(minutes=10)
MAX_UNDO_TTL = timedelta(hours=24)


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
    ) -> AutoSaveResult:
        owner = validate_user_id(user_id)
        if source.user_id != owner:
            raise ValueError("user_id must match Source.user_id")
        idempotency_key = validate_idempotency_key(idempotency_key)
        if extraction_result.outcome is not ExtractionOutcome.CANDIDATES:
            return AutoSaveResult(source_id=None)

        fingerprint = self._request_fingerprint(source, extraction_result)
        try:
            return await self._create_or_replay(
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
            if replay is not None:
                return replay
            raise exc

    async def patch(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        expected_version: int,
        patch: CollectionItemPatch,
    ) -> CollectionItem:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        now = self._now()
        async with self._session.begin():
            current = await self._repository.get_collection_item(
                user_id=owner,
                collection_item_id=identifier,
            )
            if current is None:
                raise ResourceNotFoundError
            values = current.model_dump(mode="python")
            values.update(patch.updates())
            values["updated_at"] = now
            desired = CollectionItem.model_validate(values)
            return await self._repository.update_collection_item(
                user_id=owner,
                item=desired,
                expected_version=expected_version,
            )

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

"""Transactional M0-3D orchestration for candidate and flexible-brand choices."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import (
    CandidateField,
    CollectionItem,
    CollectionKind,
    CollectionStatus,
    IdempotencyConflictError,
    ResourceNotFoundError,
    VersionConflictError,
    event_schedule_is_confirmed,
)
from app.domain.identifiers import (
    validate_collection_item_id,
    validate_source_id,
    validate_user_id,
)
from app.domain.places import (
    ConfirmedBrandIdentity,
    MatchConfidence,
    MatchStatus,
    PlaceCandidateSnapshot,
    PlaceConfirmationSource,
    PlaceMatchCandidate,
    PlaceMatchResult,
    PlaceScope,
    PlaceSelection,
    PlaceSelectionKind,
    PlaceSelectionOperation,
    PlaceTarget,
    exact_target_from_candidate,
    validate_place_selection,
)
from app.domain.time import require_aware_utc
from app.infrastructure.repositories import SqlAlchemyCollectionRepository


@dataclass(frozen=True, slots=True)
class PlaceSelectionResult:
    items: tuple[CollectionItem, ...]
    replayed: bool = False


class PlaceTargetSelectionService:
    """The sole write workflow for M0-3D target selection and candidate refresh."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session
        self._repository = SqlAlchemyCollectionRepository(session)

    async def record_candidates(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        source_id: str,
        match_result: PlaceMatchResult,
        queried_at: datetime,
        expected_version: int,
    ) -> CollectionItem:
        """Persist one match decision, promoting only a legal unique match."""

        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        source = validate_source_id(source_id)
        snapshot = PlaceCandidateSnapshot(
            result=match_result.model_copy(deep=True),
            queried_at=require_aware_utc(queried_at),
        )
        auto_candidate = self._unique_auto_match_candidate(snapshot)
        async with self._session.begin():
            item = await self._require_pending_location(owner, identifier)
            await self._require_linked_source(owner, identifier, source)
            target_status = (
                CollectionStatus.PENDING_SELECTION
                if snapshot.candidates
                and (
                    item.kind is CollectionKind.EVENT
                    or snapshot.result.status is MatchStatus.AMBIGUOUS
                )
                else CollectionStatus.PENDING_DETAILS
            )
            if auto_candidate is not None and item.kind is CollectionKind.PLACE:
                existing = await self._repository.find_exact_place_item(
                    user_id=owner,
                    provider=auto_candidate.provider,
                    poi_id=auto_candidate.poi_id,
                )
                if existing is not None:
                    await self._preserve_all_sources(
                        user_id=owner,
                        original_item_id=item.id,
                        target_item_id=existing.id,
                    )
                    await self._repository.delete_collection_item(
                        user_id=owner,
                        collection_item_id=item.id,
                        updated_at=snapshot.queried_at,
                        expected_version=expected_version,
                    )
                    return existing
                target = exact_target_from_candidate(
                    auto_candidate,
                    confirmed_by=PlaceConfirmationSource.AUTO_UNIQUE_MATCH,
                    confirmed_at=snapshot.queried_at,
                )
                desired = self._updated_item(
                    item,
                    status=CollectionStatus.ACTIVE,
                    target=target,
                    snapshot=snapshot,
                    now=snapshot.queried_at,
                    title=self._official_title(auto_candidate),
                    district=auto_candidate.district,
                    address=auto_candidate.address,
                    business_district=auto_candidate.business_area,
                )
                return await self._repository.apply_place_resolution(
                    user_id=owner,
                    item=desired,
                    expected_version=expected_version,
                )
            desired = self._updated_item(
                item,
                status=target_status,
                target=None,
                snapshot=snapshot,
                now=snapshot.queried_at,
            )
            return await self._repository.apply_place_resolution(
                user_id=owner,
                item=desired,
                expected_version=expected_version,
            )

    async def apply_selection(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        source_id: str | None = None,
        selections: tuple[PlaceSelection, ...],
        queried_at: datetime | None,
        snapshot_fingerprint: str,
        idempotency_key: str,
        expected_version: int,
        brand_identity: ConfirmedBrandIdentity | None = None,
    ) -> PlaceSelectionResult:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        source = await self._resolve_selection_source(
            owner=owner,
            collection_item_id=identifier,
            source_id=source_id,
        )
        if queried_at is None:
            async with self._session.begin():
                replay_operation = (
                    await self._repository.get_place_selection_operation(
                        user_id=owner,
                        idempotency_key=idempotency_key,
                    )
                )
            if replay_operation is None:
                raise ResourceNotFoundError
            expected_queried_at = replay_operation.created_at
        else:
            expected_queried_at = require_aware_utc(queried_at)
        expected_snapshot_fingerprint = self._validate_snapshot_fingerprint(
            snapshot_fingerprint
        )
        choices = self._validated_choices(selections)
        self._validate_choice_group(choices, brand_identity)
        fingerprint = self._fingerprint(
            collection_item_id=identifier,
            source_id=source,
            snapshot_fingerprint=expected_snapshot_fingerprint,
            queried_at=expected_queried_at,
            choices=choices,
            brand_identity=brand_identity,
        )

        for attempt in range(2):
            try:
                return await self._apply_once(
                    owner=owner,
                    collection_item_id=identifier,
                    source_id=source,
                    expected_snapshot_fingerprint=expected_snapshot_fingerprint,
                    expected_queried_at=expected_queried_at,
                    choices=choices,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                    expected_version=expected_version,
                    brand_identity=brand_identity,
                )
            except IntegrityError:
                await self._session.rollback()
                replay = await self._replay(
                    owner=owner,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                )
                if replay is not None:
                    return replay
                if attempt:
                    raise
            except VersionConflictError:
                await self._session.rollback()
                replay = await self._replay(
                    owner=owner,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                )
                if replay is not None:
                    return replay
                raise
        raise AssertionError("unreachable selection retry state")

    async def _apply_once(
        self,
        *,
        owner: str,
        collection_item_id: str,
        source_id: str,
        expected_snapshot_fingerprint: str,
        expected_queried_at: datetime,
        choices: tuple[PlaceSelection, ...],
        idempotency_key: str,
        fingerprint: str,
        expected_version: int,
        brand_identity: ConfirmedBrandIdentity | None,
    ) -> PlaceSelectionResult:
        async with self._session.begin():
            existing_operation = await self._repository.get_place_selection_operation(
                user_id=owner,
                idempotency_key=idempotency_key,
            )
            if existing_operation is not None:
                return await self._operation_result(owner, existing_operation, fingerprint)

            item = await self._repository.get_collection_item(
                user_id=owner,
                collection_item_id=collection_item_id,
            )
            if item is None:
                raise ResourceNotFoundError
            await self._require_linked_source(owner, collection_item_id, source_id)
            snapshot = self._persisted_selection_snapshot(
                item,
                expected_fingerprint=expected_snapshot_fingerprint,
                expected_queried_at=expected_queried_at,
            )
            choices = tuple(
                validate_place_selection(snapshot.result, choice) for choice in choices
            )
            if item.kind is CollectionKind.EVENT and (
                len(choices) != 1
                or choices[0].kind
                not in {
                    PlaceSelectionKind.CANDIDATE,
                    PlaceSelectionKind.NONE_OF_ABOVE,
                }
                or brand_identity is not None
            ):
                raise ValueError(
                    "Event locations require one exact candidate or none-of-above"
                )
            now = snapshot.queried_at

            if item.status is CollectionStatus.ACTIVE:
                items = self._active_selection_result(
                    item,
                    choices=choices,
                    brand_identity=brand_identity,
                )
            elif choices[0].kind is PlaceSelectionKind.NONE_OF_ABOVE:
                items = await self._choose_none(
                    owner=owner,
                    item=item,
                    snapshot=snapshot,
                    expected_version=expected_version,
                )
            elif choices[0].kind is PlaceSelectionKind.ANY_BRANCH:
                assert brand_identity is not None
                items = await self._choose_any_branch(
                    owner=owner,
                    item=item,
                    snapshot=snapshot,
                    expected_version=expected_version,
                    brand=brand_identity,
                )
            else:
                items = await self._choose_exact(
                    owner=owner,
                    item=item,
                    snapshot=snapshot,
                    choices=choices,
                    expected_version=expected_version,
                )

            operation = PlaceSelectionOperation(
                user_id=owner,
                idempotency_key=idempotency_key,
                collection_item_id=collection_item_id,
                source_id=source_id,
                request_fingerprint=fingerprint,
                result_item_ids=tuple(result.id for result in items),
                created_at=now,
            )
            await self._repository.add_place_selection_operation(
                user_id=owner,
                operation=operation,
            )
            return PlaceSelectionResult(items=items)

    async def _choose_none(
        self,
        *,
        owner: str,
        item: CollectionItem,
        snapshot: PlaceCandidateSnapshot,
        expected_version: int,
    ) -> tuple[CollectionItem, ...]:
        if item.status is not CollectionStatus.PENDING_SELECTION:
            raise VersionConflictError
        desired = self._updated_item(
            item,
            status=CollectionStatus.PENDING_DETAILS,
            target=None,
            snapshot=(
                None
                if item.kind is CollectionKind.EVENT
                else snapshot
            ),
            now=snapshot.queried_at,
        )
        stored = await self._repository.apply_place_resolution(
            user_id=owner,
            item=desired,
            expected_version=expected_version,
        )
        return (stored,)

    async def _choose_any_branch(
        self,
        *,
        owner: str,
        item: CollectionItem,
        snapshot: PlaceCandidateSnapshot,
        expected_version: int,
        brand: ConfirmedBrandIdentity,
    ) -> tuple[CollectionItem, ...]:
        existing = await self._repository.find_any_branch_item(
            user_id=owner,
            brand=brand,
        )
        if existing is not None:
            await self._preserve_all_sources(
                user_id=owner,
                original_item_id=item.id,
                target_item_id=existing.id,
            )
            if existing.id != item.id and item.status is not CollectionStatus.DELETED:
                await self._repository.delete_collection_item(
                    user_id=owner,
                    collection_item_id=item.id,
                    updated_at=snapshot.queried_at,
                    expected_version=(
                        expected_version
                        if item.status is CollectionStatus.PENDING_SELECTION
                        else None
                    ),
                )
            return (existing,)
        if item.status is not CollectionStatus.PENDING_SELECTION:
            raise VersionConflictError
        top = snapshot.candidates[0]
        target = PlaceTarget(
            scope=PlaceScope.ANY_BRANCH,
            brand_identity=brand.model_copy(deep=True),
            match_status=snapshot.result.status,
            confidence=top.confidence,
            confirmed_by=PlaceConfirmationSource.USER_SELECTION,
            confirmed_at=snapshot.queried_at,
            evidence_summary=tuple(evidence.model_copy(deep=True) for evidence in top.evidence),
        )
        desired = self._updated_item(
            item,
            status=CollectionStatus.ACTIVE,
            target=target,
            snapshot=snapshot,
            now=snapshot.queried_at,
            title=brand.display_name,
        )
        stored = await self._repository.apply_place_resolution(
            user_id=owner,
            item=desired,
            expected_version=expected_version,
        )
        return (stored,)

    async def _choose_exact(
        self,
        *,
        owner: str,
        item: CollectionItem,
        snapshot: PlaceCandidateSnapshot,
        choices: tuple[PlaceSelection, ...],
        expected_version: int,
    ) -> tuple[CollectionItem, ...]:
        candidates = tuple(self._candidate(snapshot, choice) for choice in choices)
        if item.kind is CollectionKind.EVENT:
            if item.status is not CollectionStatus.PENDING_SELECTION:
                raise VersionConflictError
            candidate = candidates[0]
            target = exact_target_from_candidate(
                candidate,
                confirmed_by=PlaceConfirmationSource.USER_SELECTION,
                confirmed_at=snapshot.queried_at,
            )
            desired = self._updated_item(
                item,
                status=(
                    CollectionStatus.ACTIVE
                    if event_schedule_is_confirmed(
                        event_start_date=item.event_start_date,
                        event_end_date=item.event_end_date,
                        event_start_at=item.event_start_at,
                        event_end_at=item.event_end_at,
                        uncertainties=item.uncertainties,
                    )
                    else CollectionStatus.PENDING_DETAILS
                ),
                target=target,
                snapshot=snapshot,
                now=snapshot.queried_at,
                district=candidate.district,
                address=candidate.address,
                business_district=candidate.business_area,
            )
            return (
                await self._repository.apply_place_resolution(
                    user_id=owner,
                    item=desired,
                    expected_version=expected_version,
                ),
            )
        results: list[CollectionItem] = []
        original_used = False
        write_operation = await self._repository.get_write_operation_for_item(
            user_id=owner,
            collection_item_id=item.id,
        )
        for candidate in candidates:
            existing = await self._repository.find_exact_place_item(
                user_id=owner,
                provider=candidate.provider,
                poi_id=candidate.poi_id,
            )
            if existing is not None:
                await self._preserve_all_sources(
                    user_id=owner,
                    original_item_id=item.id,
                    target_item_id=existing.id,
                )
                results.append(existing)
                original_used = original_used or existing.id == item.id
                continue

            target = exact_target_from_candidate(
                candidate,
                confirmed_by=PlaceConfirmationSource.USER_SELECTION,
                confirmed_at=snapshot.queried_at,
            )
            if not original_used and item.status is CollectionStatus.PENDING_SELECTION:
                desired = self._updated_item(
                    item,
                    status=CollectionStatus.ACTIVE,
                    target=target,
                    snapshot=snapshot,
                    now=snapshot.queried_at,
                    title=self._official_title(candidate),
                    district=candidate.district,
                    address=candidate.address,
                    business_district=candidate.business_area,
                )
                stored = await self._repository.apply_place_resolution(
                    user_id=owner,
                    item=desired,
                    expected_version=expected_version,
                )
                original_used = True
            else:
                stored = await self._repository.add_collection_item(
                    user_id=owner,
                    item=self._new_exact_item(item, candidate, target, snapshot),
                )
                await self._preserve_all_sources(
                    user_id=owner,
                    original_item_id=item.id,
                    target_item_id=stored.id,
                )
                if write_operation is not None:
                    await self._repository.append_write_operation_item(
                        user_id=owner,
                        operation_id=write_operation.id,
                        collection_item_id=stored.id,
                        created_at=snapshot.queried_at,
                    )
            results.append(stored)

        if not original_used and item.status is not CollectionStatus.DELETED:
            await self._repository.delete_collection_item(
                user_id=owner,
                collection_item_id=item.id,
                updated_at=snapshot.queried_at,
                expected_version=(
                    expected_version if item.status is CollectionStatus.PENDING_SELECTION else None
                ),
            )
        return tuple(results)

    async def _replay(
        self,
        *,
        owner: str,
        idempotency_key: str,
        fingerprint: str,
    ) -> PlaceSelectionResult | None:
        async with self._session.begin():
            operation = await self._repository.get_place_selection_operation(
                user_id=owner,
                idempotency_key=idempotency_key,
            )
            if operation is None:
                return None
            return await self._operation_result(owner, operation, fingerprint)

    async def _operation_result(
        self,
        owner: str,
        operation: PlaceSelectionOperation,
        fingerprint: str,
    ) -> PlaceSelectionResult:
        if operation.request_fingerprint != fingerprint:
            raise IdempotencyConflictError
        items: list[CollectionItem] = []
        for identifier in operation.result_item_ids:
            item = await self._repository.get_collection_item(
                user_id=owner,
                collection_item_id=identifier,
            )
            if item is None:
                raise ResourceNotFoundError
            items.append(item)
        return PlaceSelectionResult(items=tuple(items), replayed=True)

    async def _require_pending_location(
        self,
        owner: str,
        identifier: str,
    ) -> CollectionItem:
        item = await self._repository.get_collection_item(
            user_id=owner,
            collection_item_id=identifier,
        )
        if item is None:
            raise ResourceNotFoundError
        if item.place_target is not None or item.status not in {
            CollectionStatus.PENDING_DETAILS,
            CollectionStatus.PENDING_SELECTION,
        }:
            raise VersionConflictError
        return item

    async def _require_linked_source(
        self,
        owner: str,
        collection_item_id: str,
        source_id: str,
    ) -> None:
        if await self._repository.get_source(user_id=owner, source_id=source_id) is None:
            raise ResourceNotFoundError
        links = await self._repository.list_collection_sources(
            user_id=owner,
            collection_item_id=collection_item_id,
        )
        if source_id not in {link.source_id for link in links}:
            raise ResourceNotFoundError

    async def _resolve_selection_source(
        self,
        *,
        owner: str,
        collection_item_id: str,
        source_id: str | None,
    ) -> str:
        if source_id is not None:
            return validate_source_id(source_id)
        links = await self._repository.list_collection_sources(
            user_id=owner,
            collection_item_id=collection_item_id,
        )
        if not links:
            raise ResourceNotFoundError
        source = links[0].source_id
        # The selection service owns the following write transaction.
        await self._session.rollback()
        return source

    async def _preserve_all_sources(
        self,
        *,
        user_id: str,
        original_item_id: str,
        target_item_id: str,
    ) -> None:
        if original_item_id == target_item_id:
            return
        links = await self._repository.list_collection_sources(
            user_id=user_id,
            collection_item_id=original_item_id,
        )
        for link in links:
            await self._repository.ensure_collection_source(
                user_id=user_id,
                collection_item_id=target_item_id,
                source_id=link.source_id,
                created_at=link.created_at,
            )

    @staticmethod
    def _validated_choices(
        choices: tuple[PlaceSelection, ...],
    ) -> tuple[PlaceSelection, ...]:
        if not choices:
            raise ValueError("at least one explicit Place selection is required")
        validated = tuple(choice.model_copy(deep=True) for choice in choices)
        identities = tuple(
            (choice.provider, choice.poi_id)
            for choice in validated
            if choice.kind is PlaceSelectionKind.CANDIDATE
        )
        if len(set(identities)) != len(identities):
            raise ValueError("specific Place selections must be unique")
        return validated

    @staticmethod
    def _unique_auto_match_candidate(
        snapshot: PlaceCandidateSnapshot,
    ) -> PlaceMatchCandidate | None:
        result = snapshot.result
        if result.status is not MatchStatus.MATCHED:
            return None
        if len(result.candidates) != 1:
            raise ValueError("matched result must contain exactly one automatic candidate")
        candidate = result.candidates[0]
        if candidate.confidence is not MatchConfidence.HIGH:
            raise ValueError("matched result requires one high-confidence candidate")
        if candidate.has_hard_conflict:
            raise ValueError("matched result cannot contain a hard-conflict candidate")
        return candidate

    @staticmethod
    def _validate_snapshot_fingerprint(value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("candidate snapshot fingerprint is invalid")
        return value

    @staticmethod
    def _persisted_selection_snapshot(
        item: CollectionItem,
        *,
        expected_fingerprint: str,
        expected_queried_at: datetime,
    ) -> PlaceCandidateSnapshot:
        snapshot = item.place_candidate_snapshot
        if (
            item.status not in {CollectionStatus.PENDING_SELECTION, CollectionStatus.ACTIVE}
            or (item.status is CollectionStatus.PENDING_SELECTION) is not (
                item.place_target is None
            )
            or not isinstance(snapshot, PlaceCandidateSnapshot)
        ):
            raise VersionConflictError
        if (
            snapshot.queried_at != expected_queried_at
            or snapshot.fingerprint != expected_fingerprint
        ):
            raise ValueError("candidate snapshot does not match persisted state")
        return snapshot

    @staticmethod
    def _active_selection_result(
        item: CollectionItem,
        *,
        choices: tuple[PlaceSelection, ...],
        brand_identity: ConfirmedBrandIdentity | None,
    ) -> tuple[CollectionItem, ...]:
        target = item.place_target
        if not isinstance(target, PlaceTarget) or len(choices) != 1:
            raise VersionConflictError
        choice = choices[0]
        if target.scope is PlaceScope.EXACT:
            if (
                choice.kind is not PlaceSelectionKind.CANDIDATE
                or target.poi is None
                or (choice.provider, choice.poi_id)
                != (target.poi.provider, target.poi.poi_id)
            ):
                raise VersionConflictError
        elif (
            choice.kind is not PlaceSelectionKind.ANY_BRANCH
            or brand_identity is None
            or target.brand_identity is None
            or brand_identity.identity != target.brand_identity.identity
        ):
            raise VersionConflictError
        return (item,)

    @staticmethod
    def _validate_choice_group(
        choices: tuple[PlaceSelection, ...],
        brand: ConfirmedBrandIdentity | None,
    ) -> None:
        kinds = {choice.kind for choice in choices}
        if len(kinds) != 1:
            raise ValueError("specific, any-branch, and none choices cannot be mixed")
        kind = choices[0].kind
        if kind is not PlaceSelectionKind.CANDIDATE and len(choices) != 1:
            raise ValueError("non-candidate choices must be singular")
        if (kind is PlaceSelectionKind.ANY_BRANCH) is not (brand is not None):
            raise ValueError("only any-branch selection accepts a confirmed brand identity")

    @staticmethod
    def _candidate(
        snapshot: PlaceCandidateSnapshot,
        choice: PlaceSelection,
    ) -> PlaceMatchCandidate:
        for candidate in snapshot.candidates:
            if candidate.identity == (choice.provider, choice.poi_id):
                return candidate
        raise ValueError("selected POI is not in the current candidate snapshot")

    @staticmethod
    def _updated_item(
        item: CollectionItem,
        *,
        status: CollectionStatus,
        target: PlaceTarget | None,
        snapshot: PlaceCandidateSnapshot | None,
        now: datetime,
        title: str | None = None,
        district: str | None = None,
        address: str | None = None,
        business_district: str | None = None,
    ) -> CollectionItem:
        values = item.model_dump(mode="python")
        values.update(
            status=status,
            place_target=target,
            place_candidate_snapshot=snapshot,
            updated_at=now,
            uncertainties=item.uncertainties,
        )
        for field, value in (
            ("title", title),
            ("district", district),
            ("address", address),
            ("business_district", business_district),
        ):
            if value is not None:
                values[field] = value
        PlaceTargetSelectionService._clear_resolved_candidate_metadata(
            values,
            district=district,
            address=address,
            business_district=business_district,
        )
        return CollectionItem.model_validate(values)

    @classmethod
    def _new_exact_item(
        cls,
        original: CollectionItem,
        candidate: PlaceMatchCandidate,
        target: PlaceTarget,
        snapshot: PlaceCandidateSnapshot,
    ) -> CollectionItem:
        values = original.model_dump(mode="python")
        values.pop("id")
        values.update(
            title=cls._official_title(candidate),
            district=candidate.district,
            address=candidate.address,
            business_district=candidate.business_area,
            status=CollectionStatus.ACTIVE,
            version=1,
            place_target=target,
            place_candidate_snapshot=snapshot,
            created_at=snapshot.queried_at,
            updated_at=snapshot.queried_at,
            uncertainties=original.uncertainties,
        )
        cls._clear_resolved_candidate_metadata(
            values,
            district=candidate.district,
            address=candidate.address,
            business_district=candidate.business_area,
        )
        return CollectionItem.model_validate(values)

    @staticmethod
    def _clear_resolved_candidate_metadata(
        values: dict[str, Any],
        *,
        district: str | None,
        address: str | None,
        business_district: str | None,
    ) -> None:
        resolved = {CandidateField.CITY_HINT}
        resolved.update(
            {
            field
            for field, value in (
                (CandidateField.DISTRICT, district),
                (CandidateField.ADDRESS, address),
                (CandidateField.BUSINESS_DISTRICT, business_district),
            )
            if value is not None
            }
        )
        values["missing_fields"] = tuple(
            field for field in values.get("missing_fields", ()) if field not in resolved
        )
        values["uncertainties"] = tuple(
            uncertainty
            for uncertainty in values.get("uncertainties", ())
            if uncertainty.field not in resolved
        )

    @staticmethod
    def _official_title(candidate: PlaceMatchCandidate) -> str:
        if candidate.branch_name and candidate.branch_name not in candidate.name:
            return f"{candidate.name}（{candidate.branch_name}）"
        return candidate.name

    @staticmethod
    def _fingerprint(
        *,
        collection_item_id: str,
        source_id: str,
        snapshot_fingerprint: str,
        queried_at: datetime,
        choices: tuple[PlaceSelection, ...],
        brand_identity: ConfirmedBrandIdentity | None,
    ) -> str:
        payload = json.dumps(
            {
                "collection_item_id": collection_item_id,
                "source_id": source_id,
                "snapshot_fingerprint": snapshot_fingerprint,
                "queried_at": queried_at.isoformat(),
                "choices": [choice.model_dump(mode="json") for choice in choices],
                "brand_identity": (
                    None if brand_identity is None else brand_identity.model_dump(mode="json")
                ),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

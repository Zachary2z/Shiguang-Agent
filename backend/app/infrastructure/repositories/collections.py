"""User-scoped SQLAlchemy adapter for the M0-2A collection repository."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import (
    DEFAULT_COLLECTION_STATUSES,
    DELETABLE_COLLECTION_STATUSES,
    CandidateField,
    CollectionDataIntegrityError,
    CollectionItem,
    CollectionKind,
    CollectionSource,
    CollectionStatus,
    CollectionWriteOperation,
    Message,
    MessageContentType,
    MessageRole,
    PlanCity,
    ResourceNotFoundError,
    Session,
    SessionChannel,
    SessionStatus,
    Source,
    SourceMetadata,
    SourceParseStatus,
    SourceType,
    SupportedTimezone,
    Uncertainty,
    User,
    UserMode,
    VersionConflictError,
    ensure_collection_transition,
    ensure_persistable_collection_status,
)
from app.domain.identifiers import (
    validate_collection_item_id,
    validate_collection_write_operation_id,
    validate_message_id,
    validate_session_id,
    validate_source_id,
    validate_user_id,
)
from app.domain.places import (
    ConfirmedBrandIdentity,
    PlaceCandidateSnapshot,
    PlaceScope,
    PlaceSelectionOperation,
    PlaceTarget,
    PoiProvider,
)
from app.domain.time import as_utc, require_aware_utc, required_utc
from app.infrastructure.db.dml import execute_dml_rowcount
from app.infrastructure.db.models import (
    CollectionItemModel,
    CollectionSourceModel,
    CollectionWriteOperationItemModel,
    CollectionWriteOperationModel,
    MessageModel,
    PlaceSelectionOperationModel,
    SessionModel,
    SourceModel,
    UserModel,
)


class SqlAlchemyCollectionRepository:
    """Persist collection aggregate entities without exposing unscoped ID lookups."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_user(self, *, user_id: str, user: User) -> User:
        owner = validate_user_id(user_id)
        if owner != user.id:
            raise ValueError("user_id must match User.id")
        row = UserModel(
            id=user.id,
            mode=user.mode.value,
            default_plan_city=user.default_plan_city.value,
            timezone=user.timezone.value,
            created_at=user.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._user(row)

    async def get_user(self, *, user_id: str) -> User | None:
        owner = validate_user_id(user_id)
        row = await self._session.scalar(select(UserModel).where(UserModel.id == owner))
        return None if row is None else self._user(row)

    async def add_session(self, *, user_id: str, session: Session) -> Session:
        owner = validate_user_id(user_id)
        if owner != session.user_id:
            raise ValueError("user_id must match Session.user_id")
        await self._require_user(owner)
        row = SessionModel(
            id=session.id,
            user_id=owner,
            channel=session.channel.value,
            status=session.status.value,
            summary=session.summary,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._session_entity(row)

    async def get_session(self, *, user_id: str, session_id: str) -> Session | None:
        owner = validate_user_id(user_id)
        identifier = validate_session_id(session_id)
        row = await self._session.scalar(
            select(SessionModel).where(
                SessionModel.id == identifier,
                SessionModel.user_id == owner,
            )
        )
        return None if row is None else self._session_entity(row)

    async def list_sessions(self, *, user_id: str) -> list[Session]:
        owner = validate_user_id(user_id)
        rows = (
            await self._session.scalars(
                select(SessionModel)
                .where(SessionModel.user_id == owner)
                .order_by(SessionModel.updated_at, SessionModel.id)
            )
        ).all()
        return [self._session_entity(row) for row in rows]

    async def add_message(self, *, user_id: str, message: Message) -> Message:
        owner = validate_user_id(user_id)
        if not isinstance(message.role, MessageRole):
            raise ValueError("persisted Message role must be user or assistant")
        await self._require_session(owner, message.session_id)
        row = MessageModel(
            id=message.id,
            session_id=message.session_id,
            role=message.role.value,
            content_type=message.content_type.value,
            content=message.content,
            trace_id=message.trace_id,
            created_at=message.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._message(row)

    async def get_message(self, *, user_id: str, message_id: str) -> Message | None:
        owner = validate_user_id(user_id)
        identifier = validate_message_id(message_id)
        row = await self._session.scalar(
            select(MessageModel)
            .join(SessionModel, MessageModel.session_id == SessionModel.id)
            .where(MessageModel.id == identifier, SessionModel.user_id == owner)
        )
        return None if row is None else self._message(row)

    async def list_messages(self, *, user_id: str, session_id: str) -> list[Message]:
        owner = validate_user_id(user_id)
        identifier = validate_session_id(session_id)
        rows = (
            await self._session.scalars(
                select(MessageModel)
                .join(SessionModel, MessageModel.session_id == SessionModel.id)
                .where(
                    MessageModel.session_id == identifier,
                    SessionModel.user_id == owner,
                )
                .order_by(MessageModel.created_at, MessageModel.id)
            )
        ).all()
        return [self._message(row) for row in rows]

    async def delete_message(self, *, user_id: str, message_id: str) -> bool:
        owner = validate_user_id(user_id)
        identifier = validate_message_id(message_id)
        rowcount = await execute_dml_rowcount(
            self._session,
            delete(MessageModel).where(
                MessageModel.id == identifier,
                MessageModel.session_id.in_(
                    select(SessionModel.id).where(SessionModel.user_id == owner)
                ),
            ),
        )
        return rowcount == 1

    async def add_source(self, *, user_id: str, source: Source) -> Source:
        owner = validate_user_id(user_id)
        if owner != source.user_id:
            raise ValueError("user_id must match Source.user_id")
        await self._require_user(owner)
        row = SourceModel(
            id=source.id,
            user_id=owner,
            type=source.type.value,
            url=source.url,
            file_key=source.file_key,
            platform=source.platform,
            parse_status=source.parse_status.value,
            fetched_at=source.fetched_at,
            metadata_json=source.metadata.model_dump(mode="json", exclude_none=True),
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._source(row)

    async def get_source(self, *, user_id: str, source_id: str) -> Source | None:
        owner = validate_user_id(user_id)
        identifier = validate_source_id(source_id)
        row = await self._session.scalar(
            select(SourceModel).where(
                SourceModel.id == identifier,
                SourceModel.user_id == owner,
            )
        )
        return None if row is None else self._source(row)

    async def list_sources(self, *, user_id: str) -> list[Source]:
        owner = validate_user_id(user_id)
        rows = (
            await self._session.scalars(
                select(SourceModel)
                .where(SourceModel.user_id == owner)
                .order_by(SourceModel.created_at, SourceModel.id)
            )
        ).all()
        return [self._source(row) for row in rows]

    async def delete_source(self, *, user_id: str, source_id: str) -> bool:
        owner = validate_user_id(user_id)
        identifier = validate_source_id(source_id)
        rowcount = await execute_dml_rowcount(
            self._session,
            delete(SourceModel).where(
                SourceModel.id == identifier,
                SourceModel.user_id == owner,
                ~SourceModel.id.in_(
                    select(CollectionSourceModel.source_id).where(
                        CollectionSourceModel.user_id == owner
                    )
                ),
            ),
        )
        return rowcount == 1

    async def update_source_parse_status(
        self,
        *,
        user_id: str,
        source_id: str,
        parse_status: SourceParseStatus,
        updated_at: datetime,
    ) -> Source:
        owner = validate_user_id(user_id)
        identifier = validate_source_id(source_id)
        timestamp = require_aware_utc(updated_at)
        row = await self._session.scalar(
            select(SourceModel).where(
                SourceModel.id == identifier,
                SourceModel.user_id == owner,
            )
        )
        if row is None:
            raise ResourceNotFoundError
        row.parse_status = parse_status.value
        row.updated_at = timestamp
        await self._session.flush()
        return self._source(row)

    async def update_source(
        self,
        *,
        user_id: str,
        source: Source,
    ) -> Source:
        """Update one owned Source while keeping its input identity immutable."""

        owner = validate_user_id(user_id)
        if source.user_id != owner:
            raise ValueError("user_id must match Source.user_id")
        row = await self._session.scalar(
            select(SourceModel).where(
                SourceModel.id == source.id,
                SourceModel.user_id == owner,
            )
        )
        if row is None:
            raise ResourceNotFoundError
        if (
            row.type != source.type.value
            or row.url != source.url
            or row.file_key != source.file_key
        ):
            raise ValueError("Source input identity cannot be changed")
        row.platform = source.platform
        row.parse_status = source.parse_status.value
        row.fetched_at = source.fetched_at
        row.metadata_json = source.metadata.model_dump(mode="json", exclude_none=True)
        row.updated_at = source.updated_at
        await self._session.flush()
        return self._source(row)

    async def add_collection_item(
        self,
        *,
        user_id: str,
        item: CollectionItem,
    ) -> CollectionItem:
        owner = validate_user_id(user_id)
        if owner != item.user_id:
            raise ValueError("user_id must match CollectionItem.user_id")
        ensure_persistable_collection_status(item.status)
        await self._require_user(owner)
        row = CollectionItemModel(
            id=item.id,
            user_id=owner,
            kind=item.kind.value,
            title=item.title,
            city_hint=item.city_hint,
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
            tags_json=list(item.tags),
            missing_fields_json=[field.value for field in item.missing_fields],
            uncertainties_json=[
                uncertainty.model_dump(mode="json") for uncertainty in item.uncertainties
            ],
            **self._place_storage_values(item),
            status=item.status.value,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._collection_item(row)

    async def get_collection_item(
        self,
        *,
        user_id: str,
        collection_item_id: str,
    ) -> CollectionItem | None:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        row = await self._session.scalar(
            select(CollectionItemModel).where(
                CollectionItemModel.id == identifier,
                CollectionItemModel.user_id == owner,
            )
        )
        return None if row is None else self._collection_item(row)

    async def list_collection_items(
        self,
        *,
        user_id: str,
        include_inactive: bool = False,
    ) -> list[CollectionItem]:
        owner = validate_user_id(user_id)
        statement = select(CollectionItemModel).where(CollectionItemModel.user_id == owner)
        if not include_inactive:
            statement = statement.where(
                CollectionItemModel.status.in_(
                    sorted(status.value for status in DEFAULT_COLLECTION_STATUSES)
                )
            )
        rows = (
            await self._session.scalars(
                statement.order_by(CollectionItemModel.created_at, CollectionItemModel.id)
            )
        ).all()
        return [self._collection_item(row) for row in rows]

    async def transition_collection_status(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        target: CollectionStatus,
        updated_at: datetime,
    ) -> CollectionItem:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        timestamp = require_aware_utc(updated_at)
        ensure_persistable_collection_status(target)
        row = await self._session.scalar(
            select(CollectionItemModel).where(
                CollectionItemModel.id == identifier,
                CollectionItemModel.user_id == owner,
            )
        )
        if row is None:
            raise ResourceNotFoundError
        current = CollectionStatus(row.status)
        ensure_collection_transition(current, target)
        if (
            row.kind == CollectionKind.PLACE.value
            and current is CollectionStatus.PENDING_SELECTION
            and target is CollectionStatus.ACTIVE
            and row.place_scope is None
        ):
            raise ValueError("pending Place selection requires a confirmed target")
        if current is not target:
            row.status = target.value
            row.version += 1
            row.updated_at = timestamp
            await self._session.flush()
        return self._collection_item(row)

    async def update_collection_item(
        self,
        *,
        user_id: str,
        item: CollectionItem,
        expected_version: int,
    ) -> CollectionItem:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(item.id)
        if expected_version < 1 or isinstance(expected_version, bool):
            raise ValueError("expected_version must be a positive integer")
        row = await self._require_collection_item(owner, identifier)
        current = self._collection_item(row)
        if row.version != expected_version:
            raise VersionConflictError
        if (
            item.user_id != owner
            or item.kind is not current.kind
            or item.status is not current.status
            or item.version != current.version
            or item.created_at != current.created_at
            or item.place_target != current.place_target
            or item.place_candidate_snapshot != current.place_candidate_snapshot
        ):
            raise ValueError("immutable CollectionItem fields cannot be changed")
        if self._editable_values(item) == self._editable_values(current):
            return current

        rowcount = await execute_dml_rowcount(
            self._session,
            update(CollectionItemModel)
            .where(
                CollectionItemModel.id == identifier,
                CollectionItemModel.user_id == owner,
                CollectionItemModel.version == expected_version,
            )
            .values(
                **self._editable_storage_values(item),
                version=expected_version + 1,
                updated_at=item.updated_at,
            )
        )
        if rowcount != 1:
            raise VersionConflictError
        updated = await self._require_collection_item(owner, identifier)
        return self._collection_item(updated)

    async def apply_place_resolution(
        self,
        *,
        user_id: str,
        item: CollectionItem,
        expected_version: int,
    ) -> CollectionItem:
        """CAS one existing Place into its selected target or recovery state."""

        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(item.id)
        if expected_version < 1 or isinstance(expected_version, bool):
            raise ValueError("expected_version must be a positive integer")
        current_row = await self._require_collection_item(owner, identifier)
        current = self._collection_item(current_row)
        if current.version != expected_version:
            raise VersionConflictError
        if (
            current.kind is not CollectionKind.PLACE
            or item.user_id != owner
            or item.kind is not current.kind
            or item.id != current.id
            or item.version != current.version
            or item.created_at != current.created_at
        ):
            raise ValueError("Place resolution cannot change aggregate identity")
        ensure_collection_transition(current.status, item.status)
        rowcount = await execute_dml_rowcount(
            self._session,
            update(CollectionItemModel)
            .where(
                CollectionItemModel.id == identifier,
                CollectionItemModel.user_id == owner,
                CollectionItemModel.version == expected_version,
            )
            .values(
                **self._editable_storage_values(item),
                **self._place_storage_values(item),
                status=item.status.value,
                version=expected_version + 1,
                updated_at=item.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        if rowcount != 1:
            raise VersionConflictError
        return self._collection_item(await self._refresh_collection_item(owner, identifier))

    async def find_exact_place_item(
        self,
        *,
        user_id: str,
        provider: PoiProvider,
        poi_id: str,
    ) -> CollectionItem | None:
        owner = validate_user_id(user_id)
        row = await self._session.scalar(
            select(CollectionItemModel).where(
                CollectionItemModel.user_id == owner,
                CollectionItemModel.place_scope == PlaceScope.EXACT.value,
                CollectionItemModel.poi_provider == provider.value,
                CollectionItemModel.poi_id == poi_id,
                CollectionItemModel.status != CollectionStatus.DELETED.value,
            )
        )
        return None if row is None else self._collection_item(row)

    async def find_any_branch_item(
        self,
        *,
        user_id: str,
        brand: ConfirmedBrandIdentity,
    ) -> CollectionItem | None:
        owner = validate_user_id(user_id)
        row = await self._session.scalar(
            select(CollectionItemModel).where(
                CollectionItemModel.user_id == owner,
                CollectionItemModel.place_scope == PlaceScope.ANY_BRANCH.value,
                CollectionItemModel.brand_namespace == brand.namespace,
                CollectionItemModel.brand_id == brand.stable_id,
                CollectionItemModel.status != CollectionStatus.DELETED.value,
            )
        )
        return None if row is None else self._collection_item(row)

    async def delete_collection_item(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        updated_at: datetime,
        expected_version: int | None = None,
    ) -> CollectionItem:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        timestamp = require_aware_utc(updated_at)
        if expected_version is not None and (
            expected_version < 1 or isinstance(expected_version, bool)
        ):
            raise ValueError("expected_version must be a positive integer")
        conditions = [
            CollectionItemModel.id == identifier,
            CollectionItemModel.user_id == owner,
            CollectionItemModel.status.in_(
                sorted(status.value for status in DELETABLE_COLLECTION_STATUSES)
            ),
        ]
        if expected_version is not None:
            conditions.append(CollectionItemModel.version == expected_version)
        rowcount = await execute_dml_rowcount(
            self._session,
            update(CollectionItemModel)
            .where(*conditions)
            .values(
                deleted_from_status=CollectionItemModel.status,
                status=CollectionStatus.DELETED.value,
                version=CollectionItemModel.version + 1,
                updated_at=timestamp,
            )
            .execution_options(synchronize_session=False)
        )
        updated = await self._refresh_collection_item(owner, identifier)
        if rowcount == 1:
            return self._collection_item(updated)
        current = CollectionStatus(updated.status)
        if current is CollectionStatus.DELETED:
            return self._collection_item(updated)
        if expected_version is not None and updated.version != expected_version:
            raise VersionConflictError
        ensure_collection_transition(current, CollectionStatus.DELETED)
        raise VersionConflictError

    async def restore_collection_item(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        updated_at: datetime,
    ) -> CollectionItem:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        timestamp = require_aware_utc(updated_at)
        rowcount = await execute_dml_rowcount(
            self._session,
            update(CollectionItemModel)
            .where(
                CollectionItemModel.id == identifier,
                CollectionItemModel.user_id == owner,
                CollectionItemModel.status == CollectionStatus.DELETED.value,
                CollectionItemModel.deleted_from_status.is_not(None),
            )
            .values(
                status=CollectionItemModel.deleted_from_status,
                deleted_from_status=None,
                version=CollectionItemModel.version + 1,
                updated_at=timestamp,
            )
            .execution_options(synchronize_session=False)
        )
        updated = await self._refresh_collection_item(owner, identifier)
        if rowcount == 1 or CollectionStatus(updated.status) is not CollectionStatus.DELETED:
            return self._collection_item(updated)
        raise ResourceNotFoundError

    async def add_collection_source(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        source_id: str,
        created_at: datetime,
    ) -> CollectionSource:
        owner = validate_user_id(user_id)
        item_identifier = validate_collection_item_id(collection_item_id)
        source_identifier = validate_source_id(source_id)
        timestamp = require_aware_utc(created_at)
        await self._require_collection_item(owner, item_identifier)
        await self._require_source(owner, source_identifier)
        row = CollectionSourceModel(
            user_id=owner,
            collection_item_id=item_identifier,
            source_id=source_identifier,
            created_at=timestamp,
        )
        self._session.add(row)
        await self._session.flush()
        return self._collection_source(row)

    async def ensure_collection_source(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        source_id: str,
        created_at: datetime,
    ) -> CollectionSource:
        owner = validate_user_id(user_id)
        item_identifier = validate_collection_item_id(collection_item_id)
        source_identifier = validate_source_id(source_id)
        existing = await self._session.scalar(
            select(CollectionSourceModel).where(
                CollectionSourceModel.user_id == owner,
                CollectionSourceModel.collection_item_id == item_identifier,
                CollectionSourceModel.source_id == source_identifier,
            )
        )
        if existing is not None:
            return self._collection_source(existing)
        return await self.add_collection_source(
            user_id=owner,
            collection_item_id=item_identifier,
            source_id=source_identifier,
            created_at=created_at,
        )

    async def list_collection_sources(
        self,
        *,
        user_id: str,
        collection_item_id: str,
    ) -> list[CollectionSource]:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        rows = (
            await self._session.scalars(
                select(CollectionSourceModel)
                .where(
                    CollectionSourceModel.user_id == owner,
                    CollectionSourceModel.collection_item_id == identifier,
                )
                .order_by(CollectionSourceModel.created_at, CollectionSourceModel.source_id)
            )
        ).all()
        return [self._collection_source(row) for row in rows]

    async def add_write_operation(
        self,
        *,
        user_id: str,
        operation: CollectionWriteOperation,
        undo_token_hash: str,
    ) -> CollectionWriteOperation:
        owner = validate_user_id(user_id)
        if owner != operation.user_id:
            raise ValueError("user_id must match CollectionWriteOperation.user_id")
        if len(undo_token_hash) != 64 or any(
            character not in "0123456789abcdef" for character in undo_token_hash
        ):
            raise ValueError("undo_token_hash must be a lowercase SHA-256 digest")
        await self._require_source(owner, operation.source_id)
        row = CollectionWriteOperationModel(
            id=operation.id,
            user_id=owner,
            source_id=operation.source_id,
            idempotency_key=operation.idempotency_key,
            request_fingerprint=operation.request_fingerprint,
            undo_token_hash=undo_token_hash,
            undo_expires_at=operation.undo_expires_at,
            undone_at=operation.undone_at,
            created_at=operation.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._write_operation(row)

    async def get_write_operation_by_idempotency_key(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> CollectionWriteOperation | None:
        owner = validate_user_id(user_id)
        row = await self._session.scalar(
            select(CollectionWriteOperationModel).where(
                CollectionWriteOperationModel.user_id == owner,
                CollectionWriteOperationModel.idempotency_key == idempotency_key,
            )
        )
        return None if row is None else self._write_operation(row)

    async def get_write_operation_by_source(
        self,
        *,
        user_id: str,
        source_id: str,
    ) -> CollectionWriteOperation | None:
        owner = validate_user_id(user_id)
        identifier = validate_source_id(source_id)
        row = await self._session.scalar(
            select(CollectionWriteOperationModel).where(
                CollectionWriteOperationModel.user_id == owner,
                CollectionWriteOperationModel.source_id == identifier,
            )
        )
        return None if row is None else self._write_operation(row)

    async def get_write_operation_by_undo_hash(
        self,
        *,
        user_id: str,
        undo_token_hash: str,
    ) -> CollectionWriteOperation | None:
        owner = validate_user_id(user_id)
        row = await self._session.scalar(
            select(CollectionWriteOperationModel)
            .where(
                CollectionWriteOperationModel.user_id == owner,
                CollectionWriteOperationModel.undo_token_hash == undo_token_hash,
            )
            .execution_options(populate_existing=True)
        )
        return None if row is None else self._write_operation(row)

    async def add_write_operation_item(
        self,
        *,
        user_id: str,
        operation_id: str,
        collection_item_id: str,
        sequence: int,
        created_at: datetime,
    ) -> None:
        owner = validate_user_id(user_id)
        operation_identifier = validate_collection_write_operation_id(operation_id)
        item_identifier = validate_collection_item_id(collection_item_id)
        timestamp = require_aware_utc(created_at)
        if sequence < 1 or isinstance(sequence, bool):
            raise ValueError("operation item sequence must be a positive integer")
        await self._require_write_operation(owner, operation_identifier)
        await self._require_collection_item(owner, item_identifier)
        self._session.add(
            CollectionWriteOperationItemModel(
                operation_id=operation_identifier,
                collection_item_id=item_identifier,
                user_id=owner,
                sequence=sequence,
                created_at=timestamp,
            )
        )
        await self._session.flush()

    async def list_write_operation_items(
        self,
        *,
        user_id: str,
        operation_id: str,
    ) -> list[CollectionItem]:
        owner = validate_user_id(user_id)
        identifier = validate_collection_write_operation_id(operation_id)
        rows = (
            await self._session.scalars(
                select(CollectionItemModel)
                .join(
                    CollectionWriteOperationItemModel,
                    CollectionWriteOperationItemModel.collection_item_id == CollectionItemModel.id,
                )
                .where(
                    CollectionWriteOperationItemModel.operation_id == identifier,
                    CollectionWriteOperationItemModel.user_id == owner,
                    CollectionItemModel.user_id == owner,
                )
                .order_by(
                    CollectionWriteOperationItemModel.sequence,
                )
            )
        ).all()
        return [self._collection_item(row) for row in rows]

    async def claim_write_operation_undo(
        self,
        *,
        user_id: str,
        undo_token_hash: str,
        claimed_at: datetime,
    ) -> bool:
        owner = validate_user_id(user_id)
        if len(undo_token_hash) != 64 or any(
            character not in "0123456789abcdef" for character in undo_token_hash
        ):
            raise ValueError("undo_token_hash must be a lowercase SHA-256 digest")
        timestamp = require_aware_utc(claimed_at)
        rowcount = await execute_dml_rowcount(
            self._session,
            update(CollectionWriteOperationModel)
            .where(
                CollectionWriteOperationModel.user_id == owner,
                CollectionWriteOperationModel.undo_token_hash == undo_token_hash,
                CollectionWriteOperationModel.undone_at.is_(None),
                CollectionWriteOperationModel.undo_expires_at > timestamp,
            )
            .values(undone_at=timestamp)
            .execution_options(synchronize_session=False)
        )
        return rowcount == 1

    async def add_place_selection_operation(
        self,
        *,
        user_id: str,
        operation: PlaceSelectionOperation,
    ) -> PlaceSelectionOperation:
        owner = validate_user_id(user_id)
        if operation.user_id != owner:
            raise ValueError("user_id must match PlaceSelectionOperation.user_id")
        await self._require_collection_item(owner, operation.collection_item_id)
        await self._require_source(owner, operation.source_id)
        row = PlaceSelectionOperationModel(
            user_id=owner,
            idempotency_key=operation.idempotency_key,
            collection_item_id=operation.collection_item_id,
            source_id=operation.source_id,
            request_fingerprint=operation.request_fingerprint,
            result_item_ids_json=list(operation.result_item_ids),
            created_at=operation.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._place_selection_operation(row)

    async def get_place_selection_operation(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> PlaceSelectionOperation | None:
        owner = validate_user_id(user_id)
        row = await self._session.scalar(
            select(PlaceSelectionOperationModel)
            .where(
                PlaceSelectionOperationModel.user_id == owner,
                PlaceSelectionOperationModel.idempotency_key == idempotency_key,
            )
            .execution_options(populate_existing=True)
        )
        return None if row is None else self._place_selection_operation(row)

    async def get_write_operation_for_item(
        self,
        *,
        user_id: str,
        collection_item_id: str,
    ) -> CollectionWriteOperation | None:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        row = await self._session.scalar(
            select(CollectionWriteOperationModel)
            .join(
                CollectionWriteOperationItemModel,
                CollectionWriteOperationItemModel.operation_id == CollectionWriteOperationModel.id,
            )
            .where(
                CollectionWriteOperationItemModel.collection_item_id == identifier,
                CollectionWriteOperationItemModel.user_id == owner,
                CollectionWriteOperationModel.user_id == owner,
            )
        )
        return None if row is None else self._write_operation(row)

    async def append_write_operation_item(
        self,
        *,
        user_id: str,
        operation_id: str,
        collection_item_id: str,
        created_at: datetime,
    ) -> None:
        owner = validate_user_id(user_id)
        identifier = validate_collection_write_operation_id(operation_id)
        current_max = await self._session.scalar(
            select(func.max(CollectionWriteOperationItemModel.sequence)).where(
                CollectionWriteOperationItemModel.operation_id == identifier,
                CollectionWriteOperationItemModel.user_id == owner,
            )
        )
        await self.add_write_operation_item(
            user_id=owner,
            operation_id=identifier,
            collection_item_id=collection_item_id,
            sequence=(current_max or 0) + 1,
            created_at=created_at,
        )

    async def _require_user(self, user_id: str) -> UserModel:
        row = await self._session.scalar(select(UserModel).where(UserModel.id == user_id))
        if row is None:
            raise ResourceNotFoundError
        return row

    async def _require_session(self, user_id: str, session_id: str) -> SessionModel:
        row = await self._session.scalar(
            select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.user_id == user_id,
            )
        )
        if row is None:
            raise ResourceNotFoundError
        return row

    async def _require_source(self, user_id: str, source_id: str) -> SourceModel:
        row = await self._session.scalar(
            select(SourceModel).where(
                SourceModel.id == source_id,
                SourceModel.user_id == user_id,
            )
        )
        if row is None:
            raise ResourceNotFoundError
        return row

    async def _require_collection_item(
        self,
        user_id: str,
        collection_item_id: str,
    ) -> CollectionItemModel:
        row = await self._session.scalar(
            select(CollectionItemModel).where(
                CollectionItemModel.id == collection_item_id,
                CollectionItemModel.user_id == user_id,
            )
        )
        if row is None:
            raise ResourceNotFoundError
        return row

    async def _refresh_collection_item(
        self,
        user_id: str,
        collection_item_id: str,
    ) -> CollectionItemModel:
        row = await self._session.scalar(
            select(CollectionItemModel)
            .where(
                CollectionItemModel.id == collection_item_id,
                CollectionItemModel.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ResourceNotFoundError
        return row

    async def _require_write_operation(
        self,
        user_id: str,
        operation_id: str,
    ) -> CollectionWriteOperationModel:
        row = await self._session.scalar(
            select(CollectionWriteOperationModel).where(
                CollectionWriteOperationModel.id == operation_id,
                CollectionWriteOperationModel.user_id == user_id,
            )
        )
        if row is None:
            raise ResourceNotFoundError
        return row

    @staticmethod
    def _user(row: UserModel) -> User:
        return User(
            id=row.id,
            mode=UserMode(row.mode),
            default_plan_city=PlanCity(row.default_plan_city),
            timezone=SupportedTimezone(row.timezone),
            created_at=required_utc(row.created_at),
        )

    @staticmethod
    def _session_entity(row: SessionModel) -> Session:
        return Session(
            id=row.id,
            user_id=row.user_id,
            channel=SessionChannel(row.channel),
            status=SessionStatus(row.status),
            summary=row.summary,
            created_at=required_utc(row.created_at),
            updated_at=required_utc(row.updated_at),
        )

    @staticmethod
    def _message(row: MessageModel) -> Message:
        return Message(
            id=row.id,
            session_id=row.session_id,
            role=MessageRole(row.role),
            content_type=MessageContentType(row.content_type),
            content=row.content,
            trace_id=row.trace_id,
            created_at=required_utc(row.created_at),
        )

    @staticmethod
    def _source(row: SourceModel) -> Source:
        return Source(
            id=row.id,
            user_id=row.user_id,
            type=SourceType(row.type),
            url=row.url,
            file_key=row.file_key,
            platform=row.platform,
            parse_status=SourceParseStatus(row.parse_status),
            fetched_at=as_utc(row.fetched_at),
            metadata=SourceMetadata.model_validate_json(json.dumps(row.metadata_json)),
            created_at=required_utc(row.created_at),
            updated_at=required_utc(row.updated_at),
        )

    @staticmethod
    def _collection_item(row: CollectionItemModel) -> CollectionItem:
        target: PlaceTarget | None = None
        snapshot: PlaceCandidateSnapshot | None = None
        invalid_place_json = False
        try:
            target = (
                None
                if row.place_target_json is None
                else PlaceTarget.model_validate_json(json.dumps(row.place_target_json))
            )
            snapshot = (
                None
                if row.place_candidate_snapshot_json is None
                else PlaceCandidateSnapshot.model_validate_json(
                    json.dumps(row.place_candidate_snapshot_json)
                )
            )
        except (KeyError, TypeError, ValueError):
            invalid_place_json = True
        if invalid_place_json:
            raise CollectionDataIntegrityError
        SqlAlchemyCollectionRepository._validate_place_storage_consistency(
            row,
            target=target,
            snapshot=snapshot,
        )
        return CollectionItem(
            id=row.id,
            user_id=row.user_id,
            kind=CollectionKind(row.kind),
            title=row.title,
            city_hint=row.city_hint,
            district=row.district,
            address=row.address,
            business_district=row.business_district,
            landmark=row.landmark,
            metro_station=row.metro_station,
            event_start_date=row.event_start_date,
            event_end_date=row.event_end_date,
            event_start_at=as_utc(row.event_start_at),
            event_end_at=as_utc(row.event_end_at),
            event_start_clue=row.event_start_clue,
            event_end_clue=row.event_end_clue,
            price_amount=row.price_amount,
            price_currency=row.price_currency,
            tags=tuple(row.tags_json),
            missing_fields=tuple(CandidateField(value) for value in row.missing_fields_json),
            uncertainties=tuple(
                Uncertainty(
                    field=CandidateField(value["field"]),
                    reason=value["reason"],
                )
                for value in row.uncertainties_json
            ),
            place_target=target,
            place_candidate_snapshot=snapshot,
            status=CollectionStatus(row.status),
            version=row.version,
            created_at=required_utc(row.created_at),
            updated_at=required_utc(row.updated_at),
        )

    @staticmethod
    def _validate_place_storage_consistency(
        row: CollectionItemModel,
        *,
        target: PlaceTarget | None,
        snapshot: PlaceCandidateSnapshot | None,
    ) -> None:
        if target is None:
            if any(
                value is not None
                for value in (
                    row.place_scope,
                    row.poi_provider,
                    row.poi_id,
                    row.poi_city_code,
                    row.poi_latitude,
                    row.poi_longitude,
                    row.poi_coordinate_system,
                    row.brand_namespace,
                    row.brand_id,
                    row.place_match_status,
                    row.place_confirmed_by,
                    row.place_confirmed_at,
                )
            ):
                raise CollectionDataIntegrityError
        else:
            confirmed_at = row.place_confirmed_at
            if (
                row.place_scope != target.scope.value
                or row.place_match_status != target.match_status.value
                or row.place_confirmed_by != target.confirmed_by.value
                or confirmed_at is None
                or required_utc(confirmed_at) != target.confirmed_at
            ):
                raise CollectionDataIntegrityError
            if target.scope is PlaceScope.EXACT:
                assert target.poi is not None
                poi = target.poi
                if (
                    row.poi_provider != poi.provider.value
                    or row.poi_id != poi.poi_id
                    or row.poi_city_code != poi.city_code
                    or row.poi_latitude != poi.coordinate.latitude
                    or row.poi_longitude != poi.coordinate.longitude
                    or row.poi_coordinate_system != poi.coordinate.coordinate_system.value
                    or row.brand_namespace is not None
                    or row.brand_id is not None
                ):
                    raise CollectionDataIntegrityError
            else:
                assert target.brand_identity is not None
                brand = target.brand_identity
                if (
                    row.brand_namespace != brand.namespace
                    or row.brand_id != brand.stable_id
                    or any(
                        value is not None
                        for value in (
                            row.poi_provider,
                            row.poi_id,
                            row.poi_city_code,
                            row.poi_latitude,
                            row.poi_longitude,
                            row.poi_coordinate_system,
                        )
                    )
                ):
                    raise CollectionDataIntegrityError

        if snapshot is None:
            if row.candidate_count != 0 or row.candidates_queried_at is not None:
                raise CollectionDataIntegrityError
        else:
            queried_at = row.candidates_queried_at
            if (
                row.candidate_count != len(snapshot.candidates)
                or queried_at is None
                or required_utc(queried_at) != snapshot.queried_at
            ):
                raise CollectionDataIntegrityError

    @staticmethod
    def _collection_source(row: CollectionSourceModel) -> CollectionSource:
        return CollectionSource(
            user_id=row.user_id,
            collection_item_id=row.collection_item_id,
            source_id=row.source_id,
            created_at=required_utc(row.created_at),
        )

    @staticmethod
    def _write_operation(
        row: CollectionWriteOperationModel,
    ) -> CollectionWriteOperation:
        return CollectionWriteOperation(
            id=row.id,
            user_id=row.user_id,
            source_id=row.source_id,
            idempotency_key=row.idempotency_key,
            request_fingerprint=row.request_fingerprint,
            undo_expires_at=required_utc(row.undo_expires_at),
            undone_at=as_utc(row.undone_at),
            created_at=required_utc(row.created_at),
        )

    @staticmethod
    def _place_selection_operation(
        row: PlaceSelectionOperationModel,
    ) -> PlaceSelectionOperation:
        return PlaceSelectionOperation(
            user_id=row.user_id,
            idempotency_key=row.idempotency_key,
            collection_item_id=row.collection_item_id,
            source_id=row.source_id,
            request_fingerprint=row.request_fingerprint,
            result_item_ids=tuple(row.result_item_ids_json),
            created_at=required_utc(row.created_at),
        )

    @staticmethod
    def _editable_values(item: CollectionItem) -> tuple[object, ...]:
        return (
            item.title,
            item.city_hint,
            item.district,
            item.address,
            item.business_district,
            item.landmark,
            item.metro_station,
            item.event_start_date,
            item.event_end_date,
            item.event_start_at,
            item.event_end_at,
            item.event_start_clue,
            item.event_end_clue,
            item.price_amount,
            item.price_currency,
            item.tags,
            item.missing_fields,
            item.uncertainties,
        )

    @staticmethod
    def _editable_storage_values(item: CollectionItem) -> dict[str, object]:
        return {
            "title": item.title,
            "city_hint": item.city_hint,
            "district": item.district,
            "address": item.address,
            "business_district": item.business_district,
            "landmark": item.landmark,
            "metro_station": item.metro_station,
            "event_start_date": item.event_start_date,
            "event_end_date": item.event_end_date,
            "event_start_at": item.event_start_at,
            "event_end_at": item.event_end_at,
            "event_start_clue": item.event_start_clue,
            "event_end_clue": item.event_end_clue,
            "price_amount": item.price_amount,
            "price_currency": item.price_currency,
            "tags_json": list(item.tags),
            "missing_fields_json": [field.value for field in item.missing_fields],
            "uncertainties_json": [
                uncertainty.model_dump(mode="json") for uncertainty in item.uncertainties
            ],
        }

    @staticmethod
    def _place_storage_values(item: CollectionItem) -> dict[str, object]:
        target = item.place_target
        snapshot = item.place_candidate_snapshot
        values: dict[str, object] = {
            "place_scope": None,
            "place_target_json": None,
            "poi_provider": None,
            "poi_id": None,
            "poi_city_code": None,
            "poi_latitude": None,
            "poi_longitude": None,
            "poi_coordinate_system": None,
            "brand_namespace": None,
            "brand_id": None,
            "place_match_status": None,
            "place_confirmed_by": None,
            "place_confirmed_at": None,
            "place_candidate_snapshot_json": None,
            "candidate_count": 0,
            "candidates_queried_at": None,
        }
        if target is not None:
            values.update(
                place_scope=target.scope.value,
                place_target_json=target.model_dump(mode="json"),
                place_match_status=target.match_status.value,
                place_confirmed_by=target.confirmed_by.value,
                place_confirmed_at=target.confirmed_at,
            )
            if target.scope is PlaceScope.EXACT:
                assert target.poi is not None
                values.update(
                    poi_provider=target.poi.provider.value,
                    poi_id=target.poi.poi_id,
                    poi_city_code=target.poi.city_code,
                    poi_latitude=target.poi.coordinate.latitude,
                    poi_longitude=target.poi.coordinate.longitude,
                    poi_coordinate_system=target.poi.coordinate.coordinate_system.value,
                )
            else:
                assert target.brand_identity is not None
                values.update(
                    brand_namespace=target.brand_identity.namespace,
                    brand_id=target.brand_identity.stable_id,
                )
        if snapshot is not None:
            values.update(
                place_candidate_snapshot_json=snapshot.model_dump(mode="json"),
                candidate_count=len(snapshot.candidates),
                candidates_queried_at=snapshot.queried_at,
            )
        return values

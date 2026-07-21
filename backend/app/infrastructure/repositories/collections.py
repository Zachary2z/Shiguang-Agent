"""User-scoped SQLAlchemy adapter for the M0-2A collection repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import (
    DEFAULT_COLLECTION_STATUSES,
    CollectionItem,
    CollectionKind,
    CollectionSource,
    CollectionStatus,
    Message,
    MessageContentType,
    MessageRole,
    ResourceNotFoundError,
    Session,
    SessionChannel,
    SessionStatus,
    Source,
    SourceMetadata,
    SourceParseStatus,
    SourceType,
    SupportedCity,
    SupportedTimezone,
    User,
    UserMode,
    ensure_collection_transition,
    ensure_persistable_collection_status,
)
from app.domain.identifiers import (
    validate_collection_item_id,
    validate_message_id,
    validate_session_id,
    validate_source_id,
    validate_user_id,
)
from app.domain.time import as_utc, require_aware_utc, required_utc
from app.infrastructure.db.models import (
    CollectionItemModel,
    CollectionSourceModel,
    MessageModel,
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
            city=user.city.value,
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
            city=item.city.value,
            district=item.district,
            address=item.address,
            event_start_at=item.event_start_at,
            event_end_at=item.event_end_at,
            price_amount=item.price_amount,
            price_currency=item.price_currency,
            tags_json=list(item.tags),
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
        if current is not target:
            row.status = target.value
            row.version += 1
            row.updated_at = timestamp
            await self._session.flush()
        return self._collection_item(row)

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

    @staticmethod
    def _user(row: UserModel) -> User:
        return User(
            id=row.id,
            mode=UserMode(row.mode),
            city=SupportedCity(row.city),
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
            metadata=SourceMetadata.model_validate(row.metadata_json),
            created_at=required_utc(row.created_at),
            updated_at=required_utc(row.updated_at),
        )

    @staticmethod
    def _collection_item(row: CollectionItemModel) -> CollectionItem:
        return CollectionItem(
            id=row.id,
            user_id=row.user_id,
            kind=CollectionKind(row.kind),
            title=row.title,
            city=SupportedCity(row.city),
            district=row.district,
            address=row.address,
            event_start_at=as_utc(row.event_start_at),
            event_end_at=as_utc(row.event_end_at),
            price_amount=row.price_amount,
            price_currency=row.price_currency,
            tags=tuple(row.tags_json),
            status=CollectionStatus(row.status),
            version=row.version,
            created_at=required_utc(row.created_at),
            updated_at=required_utc(row.updated_at),
        )

    @staticmethod
    def _collection_source(row: CollectionSourceModel) -> CollectionSource:
        return CollectionSource(
            user_id=row.user_id,
            collection_item_id=row.collection_item_id,
            source_id=row.source_id,
            created_at=required_utc(row.created_at),
        )

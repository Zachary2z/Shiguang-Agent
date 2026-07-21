"""Infrastructure-independent M0-2A repository contract."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.collections.entities import (
    CollectionItem,
    CollectionSource,
    Message,
    Session,
    Source,
    SourceParseStatus,
    User,
)
from app.domain.collections.statuses import CollectionStatus


class ResourceNotFoundError(LookupError):
    """Uniform safe result for missing and cross-user resources."""

    def __init__(self) -> None:
        super().__init__("resource not found")


class CollectionRepository(Protocol):
    """Every public query and write requires an explicit owner user_id."""

    async def add_user(self, *, user_id: str, user: User) -> User: ...

    async def get_user(self, *, user_id: str) -> User | None: ...

    async def add_session(self, *, user_id: str, session: Session) -> Session: ...

    async def get_session(self, *, user_id: str, session_id: str) -> Session | None: ...

    async def list_sessions(self, *, user_id: str) -> list[Session]: ...

    async def add_message(self, *, user_id: str, message: Message) -> Message: ...

    async def get_message(self, *, user_id: str, message_id: str) -> Message | None: ...

    async def list_messages(self, *, user_id: str, session_id: str) -> list[Message]: ...

    async def add_source(self, *, user_id: str, source: Source) -> Source: ...

    async def get_source(self, *, user_id: str, source_id: str) -> Source | None: ...

    async def list_sources(self, *, user_id: str) -> list[Source]: ...

    async def update_source_parse_status(
        self,
        *,
        user_id: str,
        source_id: str,
        parse_status: SourceParseStatus,
        updated_at: datetime,
    ) -> Source: ...

    async def add_collection_item(
        self,
        *,
        user_id: str,
        item: CollectionItem,
    ) -> CollectionItem: ...

    async def get_collection_item(
        self,
        *,
        user_id: str,
        collection_item_id: str,
    ) -> CollectionItem | None: ...

    async def list_collection_items(
        self,
        *,
        user_id: str,
        include_inactive: bool = False,
    ) -> list[CollectionItem]: ...

    async def transition_collection_status(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        target: CollectionStatus,
        updated_at: datetime,
    ) -> CollectionItem: ...

    async def add_collection_source(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        source_id: str,
        created_at: datetime,
    ) -> CollectionSource: ...

    async def list_collection_sources(
        self,
        *,
        user_id: str,
        collection_item_id: str,
    ) -> list[CollectionSource]: ...

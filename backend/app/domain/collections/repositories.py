"""Infrastructure-independent M0-2A repository contract."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

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
from app.domain.collections.types import CollectionKind
from app.domain.collections.writes import CollectionWriteOperation

if TYPE_CHECKING:
    from app.domain.places.contracts import PoiProvider
    from app.domain.places.targets import (
        ConfirmedBrandIdentity,
        PlaceSelectionOperation,
    )


class ResourceNotFoundError(LookupError):
    """Uniform safe result for missing and cross-user resources."""

    def __init__(self) -> None:
        super().__init__("resource not found")


class CollectionDataIntegrityError(RuntimeError):
    """Fixed safe failure for contradictory persisted collection representations."""

    def __init__(self) -> None:
        super().__init__("collection data integrity violation")


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

    async def delete_message(self, *, user_id: str, message_id: str) -> bool: ...

    async def add_source(self, *, user_id: str, source: Source) -> Source: ...

    async def get_source(self, *, user_id: str, source_id: str) -> Source | None: ...

    async def list_sources(self, *, user_id: str) -> list[Source]: ...

    async def delete_source(self, *, user_id: str, source_id: str) -> bool: ...

    async def update_source_parse_status(
        self,
        *,
        user_id: str,
        source_id: str,
        parse_status: SourceParseStatus,
        updated_at: datetime,
    ) -> Source: ...

    async def update_source(
        self,
        *,
        user_id: str,
        source: Source,
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

    async def query_collection_items(
        self,
        *,
        user_id: str,
        search: str | None,
        city_hint: str | None,
        city_code: str | None,
        city_code_not: str | None,
        include_flexible_brands: bool,
        exclude_flexible_brands: bool,
        city_pending: bool | None,
        formal_city_pending: bool | None,
        district: str | None,
        kind: CollectionKind | None,
        status: CollectionStatus | None,
        tags: tuple[str, ...],
        include_inactive: bool,
        sort_field: str,
        descending: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[CollectionItem], int]: ...

    async def transition_collection_status(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        target: CollectionStatus,
        updated_at: datetime,
    ) -> CollectionItem: ...

    async def update_collection_item(
        self,
        *,
        user_id: str,
        item: CollectionItem,
        expected_version: int,
    ) -> CollectionItem: ...

    async def delete_collection_item(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        updated_at: datetime,
        expected_version: int | None = None,
    ) -> CollectionItem: ...

    async def restore_collection_item(
        self,
        *,
        user_id: str,
        collection_item_id: str,
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

    async def add_write_operation(
        self,
        *,
        user_id: str,
        operation: CollectionWriteOperation,
        undo_token_hash: str,
    ) -> CollectionWriteOperation: ...

    async def get_write_operation_by_idempotency_key(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> CollectionWriteOperation | None: ...

    async def get_write_operation_by_source(
        self,
        *,
        user_id: str,
        source_id: str,
    ) -> CollectionWriteOperation | None: ...

    async def get_write_operation_by_undo_hash(
        self,
        *,
        user_id: str,
        undo_token_hash: str,
    ) -> CollectionWriteOperation | None: ...

    async def add_write_operation_item(
        self,
        *,
        user_id: str,
        operation_id: str,
        collection_item_id: str,
        sequence: int,
        created_at: datetime,
    ) -> None: ...

    async def list_write_operation_items(
        self,
        *,
        user_id: str,
        operation_id: str,
    ) -> list[CollectionItem]: ...

    async def claim_write_operation_undo(
        self,
        *,
        user_id: str,
        undo_token_hash: str,
        claimed_at: datetime,
    ) -> bool: ...

    async def apply_place_resolution(
        self,
        *,
        user_id: str,
        item: CollectionItem,
        expected_version: int,
    ) -> CollectionItem: ...

    async def find_exact_place_item(
        self, *, user_id: str, provider: PoiProvider, poi_id: str
    ) -> CollectionItem | None: ...

    async def find_any_branch_item(
        self, *, user_id: str, brand: ConfirmedBrandIdentity
    ) -> CollectionItem | None: ...

    async def ensure_collection_source(
        self,
        *,
        user_id: str,
        collection_item_id: str,
        source_id: str,
        created_at: datetime,
    ) -> CollectionSource: ...

    async def add_place_selection_operation(
        self, *, user_id: str, operation: PlaceSelectionOperation
    ) -> PlaceSelectionOperation: ...

    async def get_place_selection_operation(
        self, *, user_id: str, idempotency_key: str
    ) -> PlaceSelectionOperation | None: ...

    async def get_write_operation_for_item(
        self, *, user_id: str, collection_item_id: str
    ) -> CollectionWriteOperation | None: ...

    async def append_write_operation_item(
        self,
        *,
        user_id: str,
        operation_id: str,
        collection_item_id: str,
        created_at: datetime,
    ) -> None: ...

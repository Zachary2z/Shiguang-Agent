"""Read-only application queries for M0 collection HTTP endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import (
    CollectionItem,
    CollectionKind,
    CollectionStatus,
    ResourceNotFoundError,
    Source,
)
from app.domain.identifiers import validate_collection_item_id, validate_user_id
from app.infrastructure.repositories import SqlAlchemyCollectionRepository


class CollectionSort(StrEnum):
    CREATED_ASC = "created_at"
    CREATED_DESC = "-created_at"
    UPDATED_ASC = "updated_at"
    UPDATED_DESC = "-updated_at"


class CollectionCityGroup(StrEnum):
    SHENZHEN = "shenzhen"
    OTHER = "other"
    PENDING = "pending"


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionListCriteria:
    search: str | None = None
    city_hint: str | None = None
    city_code: str | None = None
    city_group: CollectionCityGroup | None = None
    city_pending: bool | None = None
    formal_city_pending: bool | None = None
    district: str | None = None
    kind: CollectionKind | None = None
    status: CollectionStatus | None = None
    tags: tuple[str, ...] = ()
    include_inactive: bool = False
    sort: CollectionSort = CollectionSort.CREATED_DESC
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionPage:
    items: tuple[CollectionItem, ...]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionDetail:
    item: CollectionItem
    sources: tuple[Source, ...]


def collection_formal_city_code(item: CollectionItem) -> str | None:
    """Return formal persisted city evidence without trusting free-text hints."""

    target = item.place_target
    if target is None:
        return None
    if target.poi is not None:
        return str(target.poi.city_code)
    return None


class CollectionQueryService:
    """Apply stable filtering and pagination outside the HTTP route layer."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = SqlAlchemyCollectionRepository(session)

    async def list(
        self,
        *,
        user_id: str,
        criteria: CollectionListCriteria,
    ) -> CollectionPage:
        owner = validate_user_id(user_id)
        if criteria.page < 1 or criteria.page_size < 1 or criteria.page_size > 100:
            raise ValueError("page must be positive and page_size must be from 1 to 100")
        if criteria.city_code is not None and criteria.city_group is not None:
            raise ValueError("city_code and city_group cannot be combined")
        search = None if criteria.search is None else " ".join(criteria.search.split())
        if search == "":
            search = None
        items, total = await self._repository.query_collection_items(
            user_id=owner,
            search=search,
            city_hint=criteria.city_hint,
            city_code=(
                "shenzhen"
                if criteria.city_group is CollectionCityGroup.SHENZHEN
                else criteria.city_code
            ),
            city_code_not=(
                "shenzhen"
                if criteria.city_group is CollectionCityGroup.OTHER
                else None
            ),
            include_flexible_brands=(
                criteria.city_group is CollectionCityGroup.SHENZHEN
            ),
            exclude_flexible_brands=(
                criteria.city_group
                in {CollectionCityGroup.OTHER, CollectionCityGroup.PENDING}
            ),
            city_pending=criteria.city_pending,
            formal_city_pending=(
                True
                if criteria.city_group is CollectionCityGroup.PENDING
                else criteria.formal_city_pending
            ),
            district=criteria.district,
            kind=criteria.kind,
            status=criteria.status,
            tags=criteria.tags,
            include_inactive=criteria.include_inactive,
            sort_field=(
                "created_at"
                if criteria.sort
                in {CollectionSort.CREATED_ASC, CollectionSort.CREATED_DESC}
                else "updated_at"
            ),
            descending=criteria.sort
            in {CollectionSort.CREATED_DESC, CollectionSort.UPDATED_DESC},
            offset=(criteria.page - 1) * criteria.page_size,
            limit=criteria.page_size,
        )
        return CollectionPage(
            items=tuple(items),
            page=criteria.page,
            page_size=criteria.page_size,
            total=total,
        )

    async def get_detail(
        self,
        *,
        user_id: str,
        collection_item_id: str,
    ) -> CollectionDetail:
        owner = validate_user_id(user_id)
        identifier = validate_collection_item_id(collection_item_id)
        item = await self._repository.get_collection_item(
            user_id=owner,
            collection_item_id=identifier,
        )
        if item is None:
            raise ResourceNotFoundError
        links = await self._repository.list_collection_sources(
            user_id=owner,
            collection_item_id=identifier,
        )
        sources: list[Source] = []
        for link in links:
            source = await self._repository.get_source(
                user_id=owner,
                source_id=link.source_id,
            )
            if source is not None:
                sources.append(source)
        return CollectionDetail(item=item, sources=tuple(sources))

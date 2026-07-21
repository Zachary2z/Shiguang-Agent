"""Read-only application queries for M0 collection HTTP endpoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionListCriteria:
    city_hint: str | None = None
    city_pending: bool | None = None
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
        items = await self._repository.list_collection_items(
            user_id=owner,
            include_inactive=criteria.include_inactive or criteria.status is not None,
        )
        filtered = [item for item in items if self._matches(item, criteria)]
        filtered.sort(key=self._sort_key(criteria.sort), reverse=self._reverse(criteria.sort))
        start = (criteria.page - 1) * criteria.page_size
        return CollectionPage(
            items=tuple(filtered[start : start + criteria.page_size]),
            page=criteria.page,
            page_size=criteria.page_size,
            total=len(filtered),
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

    @staticmethod
    def _matches(item: CollectionItem, criteria: CollectionListCriteria) -> bool:
        if criteria.city_hint is not None and item.city_hint != criteria.city_hint:
            return False
        if criteria.city_pending is True and item.city_hint is not None:
            return False
        if criteria.city_pending is False and item.city_hint is None:
            return False
        if criteria.district is not None and item.district != criteria.district:
            return False
        if criteria.kind is not None and item.kind is not criteria.kind:
            return False
        if criteria.status is not None and item.status is not criteria.status:
            return False
        item_tags = {tag.casefold() for tag in item.tags}
        return all(tag.casefold() in item_tags for tag in criteria.tags)

    @staticmethod
    def _sort_key(
        sort: CollectionSort,
    ) -> Callable[[CollectionItem], tuple[datetime, str]]:
        if sort in {CollectionSort.CREATED_ASC, CollectionSort.CREATED_DESC}:
            return lambda item: (item.created_at, item.id)
        return lambda item: (item.updated_at, item.id)

    @staticmethod
    def _reverse(sort: CollectionSort) -> bool:
        return sort in {CollectionSort.CREATED_DESC, CollectionSort.UPDATED_DESC}

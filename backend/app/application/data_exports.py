"""Private, allowlisted JSON export for one authenticated user."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.memories import MemoryConfirmationStatus
from app.domain.time import utc_now
from app.infrastructure.repositories import (
    SqlAlchemyCollectionRepository,
    SqlAlchemyMemoryRepository,
    SqlAlchemyPlanRepository,
)


class UserDataExportService:
    async def build(self, *, session: AsyncSession, user_id: str) -> bytes:
        collections = await SqlAlchemyCollectionRepository(
            session
        ).list_collection_items(user_id=user_id, include_inactive=True)
        plans = await SqlAlchemyPlanRepository(session).list_latest(user_id=user_id)
        memories = await SqlAlchemyMemoryRepository(session).list(user_id=user_id)
        payload = {
            "format_version": 1,
            "exported_at": utc_now().isoformat(),
            "collections": [
                {
                    "id": item.id,
                    "kind": item.kind.value,
                    "title": item.title,
                    "city_hint": item.city_hint,
                    "district": item.district,
                    "address": item.address,
                    "tags": list(item.tags),
                    "status": item.status.value,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in collections
            ],
            "plans": [
                {
                    "id": plan.id,
                    "version": plan.version,
                    "status": plan.status.value,
                    "constraints": {
                        "city_code": plan.constraints.city_code.value,
                        "start_at": plan.constraints.start_at.isoformat(),
                        "end_at": plan.constraints.end_at.isoformat(),
                        "area": (
                            None
                            if plan.constraints.area is None
                            else plan.constraints.area.model_dump(mode="json")
                        ),
                        "budget": (
                            None
                            if plan.constraints.budget is None
                            else str(plan.constraints.budget)
                        ),
                        "pace": plan.constraints.pace.value,
                        "include": list(plan.constraints.include),
                        "exclude": list(plan.constraints.exclude),
                        "collection_only": plan.constraints.collection_only,
                        "selected_collection_item_ids": list(
                            plan.constraints.selected_collection_item_ids
                        ),
                        "required_collection_item_ids": list(
                            plan.constraints.required_collection_item_ids
                        ),
                    },
                    "created_at": plan.created_at.isoformat(),
                    "updated_at": plan.updated_at.isoformat(),
                }
                for plan in plans
            ],
            "memories": [
                {
                    "id": memory.id,
                    "type": memory.type.value,
                    "content": memory.content,
                    "value": memory.value,
                    "source": {
                        "type": memory.source.type.value,
                        "summary": memory.source.summary,
                    },
                    "confirmation_status": memory.confirmation_status.value,
                    "expires_at": (
                        None if memory.expires_at is None else memory.expires_at.isoformat()
                    ),
                    "disabled": memory.disabled_at is not None,
                    "created_at": memory.created_at.isoformat(),
                    "updated_at": memory.updated_at.isoformat(),
                    "last_used_at": (
                        None
                        if memory.last_used_at is None
                        else memory.last_used_at.isoformat()
                    ),
                }
                for memory in memories
                if memory.confirmation_status is MemoryConfirmationStatus.CONFIRMED
            ],
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


__all__ = ["UserDataExportService"]

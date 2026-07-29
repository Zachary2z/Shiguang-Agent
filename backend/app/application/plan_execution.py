"""Single execution boundary for confirmed-plan calendar, navigation, and feedback."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import CollectionStatus, IdempotencyConflictError
from app.domain.identifiers import generate_feedback_id
from app.domain.places import CityScope, NavigationRequest
from app.domain.plans import (
    PlanCompletionStatus,
    PlanExecutionItem,
    PlanExecutionNotAllowedError,
    PlanFeedback,
    PlanFeedbackSelectionError,
    PlanItem,
    PlanItemExecutionStatus,
    PreferenceSuggestion,
)
from app.domain.time import as_utc, utc_now
from app.infrastructure.db.models import (
    CollectionItemModel,
    CollectionVisitSourceModel,
    CollectionVisitStateModel,
    PlanFeedbackAuditModel,
    PlanFeedbackStateModel,
    PlanItemModel,
    PlanModel,
)
from app.infrastructure.repositories import (
    SqlAlchemyMemoryRepository,
    SqlAlchemyPlanRepository,
    plan_request_fingerprint,
)
from app.providers.map import MapProvider

_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class FeedbackSubmission:
    feedback: PlanFeedback
    replayed: bool


def _stored_time(value: datetime) -> datetime:
    normalized = as_utc(value)
    assert normalized is not None
    return normalized


def _parse_item(row: PlanItemModel) -> PlanItem:
    return PlanItem.model_validate_json(
        json.dumps(row.snapshot_json, ensure_ascii=False, separators=(",", ":"))
    )


async def _require_execution_plan(
    session: AsyncSession, *, user_id: str, plan_id: str
) -> PlanModel:
    # Keep the existing repository gate as the public source of confirmation semantics.
    repository = SqlAlchemyPlanRepository(session)
    await repository.require_confirmed_for_execution(
        user_id=user_id, plan_id=plan_id
    )
    row = await session.scalar(
        select(PlanModel)
        .where(PlanModel.id == plan_id, PlanModel.user_id == user_id)
        .with_for_update()
    )
    if row is None:
        raise PlanExecutionNotAllowedError
    return row


async def _main_rows(
    session: AsyncSession, *, user_id: str, plan_id: str
) -> tuple[PlanItemModel, ...]:
    rows = (
        await session.scalars(
            select(PlanItemModel)
            .where(
                PlanItemModel.plan_id == plan_id,
                PlanItemModel.user_id == user_id,
                PlanItemModel.option_index == 0,
            )
            .order_by(PlanItemModel.item_index, PlanItemModel.id)
        )
    ).all()
    return tuple(rows)


class PlanCalendarService:
    """Generate one deterministic RFC 5545 event for a confirmed plan."""

    async def generate(
        self, *, session: AsyncSession, user_id: str, plan_id: str
    ) -> bytes:
        row = await _require_execution_plan(session, user_id=user_id, plan_id=plan_id)
        items = tuple(_parse_item(item) for item in await _main_rows(
            session, user_id=user_id, plan_id=plan_id
        ))
        if not items:
            raise PlanExecutionNotAllowedError
        constraints = json.loads(json.dumps(row.constraints_json))
        start = datetime.fromisoformat(str(constraints["start_at"])).astimezone(_SHANGHAI)
        end = datetime.fromisoformat(str(constraints["end_at"])).astimezone(_SHANGHAI)
        known_addresses = tuple(
            dict.fromkeys(
                item.source.concrete_poi.address
                for item in items
                if item.source.concrete_poi is not None
                and item.source.concrete_poi.address
            )
        )
        description = "\n".join(
            f"{item.start_at.astimezone(_SHANGHAI):%H:%M}–"
            f"{item.end_at.astimezone(_SHANGHAI):%H:%M} {item.title}"
            + (
                ""
                if item.source.concrete_poi is None
                else f"｜{item.source.concrete_poi.address}"
            )
            for item in items
        )
        stamp = _stored_time(row.confirmed_at or row.updated_at)
        lines = (
            "BEGIN:VCALENDAR",
            "PRODID:-//Shiguang//Confirmed Plan//CN",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTIMEZONE",
            "TZID:Asia/Shanghai",
            "BEGIN:STANDARD",
            "DTSTART:19700101T000000",
            "TZOFFSETFROM:+0800",
            "TZOFFSETTO:+0800",
            "TZNAME:CST",
            "END:STANDARD",
            "END:VTIMEZONE",
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(plan_id)}@shiguang.local",
            f"DTSTAMP:{stamp:%Y%m%dT%H%M%SZ}",
            f"DTSTART;TZID=Asia/Shanghai:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID=Asia/Shanghai:{end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{_ics_escape('拾光计划｜' + ' → '.join(item.title for item in items))}",
            f"DESCRIPTION:{_ics_escape(description)}",
            f"LOCATION:{_ics_escape('；'.join(known_addresses))}",
            "END:VEVENT",
            "END:VCALENDAR",
        )
        return ("\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n").encode()


class PlanNavigationService:
    """Build safe local navigation URIs through the existing MapProvider."""

    async def list_entries(
        self,
        *,
        session: AsyncSession,
        user_id: str,
        plan_id: str,
        map_provider: MapProvider,
    ) -> tuple[PlanExecutionItem, ...]:
        await _require_execution_plan(session, user_id=user_id, plan_id=plan_id)
        result: list[PlanExecutionItem] = []
        for row in await _main_rows(session, user_id=user_id, plan_id=plan_id):
            item = _parse_item(row)
            poi = item.source.concrete_poi
            uri = None
            if poi is not None:
                uri = (
                    await map_provider.build_navigation_uri(
                        NavigationRequest(
                            city=CityScope(city_code=poi.city_code),
                            poi_id=poi.poi_id,
                            coordinate=poi.coordinate,
                        )
                    )
                ).uri
            result.append(
                PlanExecutionItem(
                    id=row.id,
                    title=item.title,
                    start_at=item.start_at,
                    end_at=item.end_at,
                    address=None if poi is None else poi.address,
                    collection_item_ids=item.source.collection_item_ids,
                    is_external=item.source.kind.value == "external_place",
                    status=PlanItemExecutionStatus(row.execution_status),
                    navigation_uri=uri,
                )
            )
        return tuple(result)


class PlanFeedbackService:
    """Atomically submit or correct one plan's explicit completion feedback."""

    async def submit(
        self,
        *,
        session: AsyncSession,
        user_id: str,
        plan_id: str,
        completion_status: PlanCompletionStatus,
        visited_plan_item_ids: tuple[str, ...],
        reason: str | None,
        client_idempotency_key: str,
        expected_revision: int | None,
        preference_candidate: PreferenceSuggestion | None = None,
    ) -> FeedbackSubmission:
        key = _scoped_feedback_key(user_id, client_idempotency_key)
        fingerprint = plan_request_fingerprint(
            {
                "plan_id": plan_id,
                "completion_status": completion_status.value,
                "visited_plan_item_ids": sorted(visited_plan_item_ids),
                "reason": reason,
                "preference_candidate": (
                    None
                    if preference_candidate is None
                    else preference_candidate.model_dump(mode="json")
                ),
                "expected_revision": expected_revision,
            }
        )
        replay = await _feedback_replay(
            session=session,
            user_id=user_id,
            key=key,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        stored_candidate = preference_candidate
        if (
            preference_candidate is not None
            and await SqlAlchemyMemoryRepository(
                session
            ).suggestion_payload_was_rejected(
                user_id=user_id,
                payload=preference_candidate.model_dump(mode="json"),
            )
        ):
            stored_candidate = None

        plan = await _require_execution_plan(session, user_id=user_id, plan_id=plan_id)
        # The Plan row lock is the cross-process serialization boundary. A competing
        # request may have committed while this transaction waited, so replay must be
        # checked again before optimistic revision comparison.
        replay = await _feedback_replay(
            session=session,
            user_id=user_id,
            key=key,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        item_rows = await _main_rows(session, user_id=user_id, plan_id=plan_id)
        if not item_rows:
            raise PlanExecutionNotAllowedError
        allowed = {item.id for item in item_rows}
        requested = set(visited_plan_item_ids)
        if not requested.issubset(allowed):
            raise PlanFeedbackSelectionError(
                "feedback contains a plan item outside this plan"
            )
        if completion_status is PlanCompletionStatus.COMPLETED:
            requested = allowed
        elif completion_status is PlanCompletionStatus.PARTIALLY_COMPLETED:
            if not requested or requested == allowed:
                raise PlanFeedbackSelectionError(
                    "partial completion requires some but not all plan items"
                )
        elif requested:
            raise PlanFeedbackSelectionError(
                "not completed cannot include visited plan items"
            )

        state = await session.scalar(
            select(PlanFeedbackStateModel)
            .where(
                PlanFeedbackStateModel.plan_id == plan_id,
                PlanFeedbackStateModel.user_id == user_id,
            )
            .with_for_update()
        )
        actual_revision = None if state is None else state.revision
        if expected_revision != actual_revision:
            from app.domain.plans import PlanVersionConflictError

            raise PlanVersionConflictError
        revision = 1 if state is None else state.revision + 1
        feedback_id = generate_feedback_id()
        now = utc_now()
        audit = PlanFeedbackAuditModel(
            id=feedback_id,
            plan_id=plan_id,
            user_id=user_id,
            revision=revision,
            completion_status=completion_status.value,
            reason=reason,
            visited_plan_item_ids_json=sorted(requested),
            preference_suggestion_json=(
                None
                if stored_candidate is None
                else stored_candidate.model_dump(mode="json")
            ),
            idempotency_key=key,
            request_fingerprint=fingerprint,
            corrects_feedback_id=None if state is None else state.current_feedback_id,
            created_at=now,
        )
        session.add(audit)
        if state is None:
            session.add(
                PlanFeedbackStateModel(
                    plan_id=plan_id,
                    user_id=user_id,
                    current_feedback_id=feedback_id,
                    revision=revision,
                    completion_status=completion_status.value,
                    reason=reason,
                    preference_suggestion_json=(
                        None
                        if stored_candidate is None
                        else stored_candidate.model_dump(mode="json")
                    ),
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            state.current_feedback_id = feedback_id
            state.revision = revision
            state.completion_status = completion_status.value
            state.reason = reason
            state.preference_suggestion_json = (
                None
                if stored_candidate is None
                else stored_candidate.model_dump(mode="json")
            )
            state.updated_at = now
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            replay = await _feedback_replay(
                session=session,
                user_id=user_id,
                key=key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                return replay
            from app.domain.plans import PlanVersionConflictError

            raise PlanVersionConflictError from None

        old_collection_ids = set(
            (
                await session.scalars(
                    select(CollectionVisitSourceModel.collection_item_id)
                    .join(
                        PlanItemModel,
                        PlanItemModel.id == CollectionVisitSourceModel.plan_item_id,
                    )
                    .where(
                        CollectionVisitSourceModel.user_id == user_id,
                        PlanItemModel.plan_id == plan_id,
                    )
                )
            ).all()
        )
        await session.execute(
            delete(CollectionVisitSourceModel).where(
                CollectionVisitSourceModel.user_id == user_id,
                CollectionVisitSourceModel.plan_item_id.in_(allowed),
            )
        )
        selected_rows = [row for row in item_rows if row.id in requested]
        new_collection_ids: set[str] = set()
        for row in selected_rows:
            item = _parse_item(row)
            for collection_id in item.source.collection_item_ids:
                collection = await session.scalar(
                    select(CollectionItemModel).where(
                        CollectionItemModel.id == collection_id,
                        CollectionItemModel.user_id == user_id,
                    )
                )
                if collection is None:
                    continue
                new_collection_ids.add(collection_id)
                baseline = await session.get(CollectionVisitStateModel, collection_id)
                if baseline is None:
                    session.add(
                        CollectionVisitStateModel(
                            collection_item_id=collection_id,
                            user_id=user_id,
                            baseline_visited=(
                                collection.status == CollectionStatus.VISITED.value
                            ),
                            created_at=now,
                        )
                    )
                session.add(
                    CollectionVisitSourceModel(
                        plan_item_id=row.id,
                        collection_item_id=collection_id,
                        user_id=user_id,
                        feedback_id=feedback_id,
                        created_at=now,
                    )
                )
        await session.flush()
        await self._recompute_collections(
            session=session,
            user_id=user_id,
            collection_ids=old_collection_ids | new_collection_ids,
            now=now,
        )
        await session.execute(
            update(PlanItemModel)
            .where(
                PlanItemModel.plan_id == plan_id,
                PlanItemModel.user_id == user_id,
                PlanItemModel.option_index == 0,
            )
            .values(execution_status=PlanItemExecutionStatus.NOT_VISITED.value)
        )
        if requested:
            await session.execute(
                update(PlanItemModel)
                .where(
                    PlanItemModel.plan_id == plan_id,
                    PlanItemModel.user_id == user_id,
                    PlanItemModel.id.in_(requested),
                )
                .values(execution_status=PlanItemExecutionStatus.VISITED.value)
            )
        plan.status = completion_status.value
        plan.updated_at = now
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            replay = await _feedback_replay(
                session=session,
                user_id=user_id,
                key=key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                return replay
            raise
        return FeedbackSubmission(feedback=_audit_domain(audit), replayed=False)

    async def current(
        self, *, session: AsyncSession, user_id: str, plan_id: str
    ) -> PlanFeedback | None:
        await _require_execution_plan(session, user_id=user_id, plan_id=plan_id)
        state = await session.scalar(
            select(PlanFeedbackStateModel).where(
                PlanFeedbackStateModel.plan_id == plan_id,
                PlanFeedbackStateModel.user_id == user_id,
            )
        )
        if state is None:
            return None
        audit = await session.scalar(
            select(PlanFeedbackAuditModel).where(
                PlanFeedbackAuditModel.id == state.current_feedback_id,
                PlanFeedbackAuditModel.user_id == user_id,
            )
        )
        return None if audit is None else _audit_domain(audit)

    @staticmethod
    async def _recompute_collections(
        *,
        session: AsyncSession,
        user_id: str,
        collection_ids: set[str],
        now: datetime,
    ) -> None:
        for collection_id in collection_ids:
            collection = await session.scalar(
                select(CollectionItemModel)
                .where(
                    CollectionItemModel.id == collection_id,
                    CollectionItemModel.user_id == user_id,
                )
                .with_for_update()
            )
            baseline = await session.scalar(
                select(CollectionVisitStateModel).where(
                    CollectionVisitStateModel.collection_item_id == collection_id,
                    CollectionVisitStateModel.user_id == user_id,
                )
            )
            if collection is None or baseline is None:
                continue
            active_sources = await session.scalar(
                select(func.count())
                .select_from(CollectionVisitSourceModel)
                .where(
                    CollectionVisitSourceModel.collection_item_id == collection_id,
                    CollectionVisitSourceModel.user_id == user_id,
                )
            )
            target = (
                CollectionStatus.VISITED.value
                if baseline.baseline_visited or bool(active_sources)
                else CollectionStatus.ACTIVE.value
            )
            if collection.status in {
                CollectionStatus.ACTIVE.value,
                CollectionStatus.VISITED.value,
            } and collection.status != target:
                collection.status = target
                collection.version += 1
                collection.updated_at = now


def _scoped_feedback_key(user_id: str, client_key: str) -> str:
    if not client_key or len(client_key) > 128:
        raise ValueError("idempotency key is invalid")
    return "feedback." + hashlib.sha256(f"{user_id}\0{client_key}".encode()).hexdigest()


async def _feedback_replay(
    *,
    session: AsyncSession,
    user_id: str,
    key: str,
    fingerprint: str,
) -> FeedbackSubmission | None:
    audit = await session.scalar(
        select(PlanFeedbackAuditModel).where(
            PlanFeedbackAuditModel.user_id == user_id,
            PlanFeedbackAuditModel.idempotency_key == key,
        )
    )
    if audit is None:
        return None
    if audit.request_fingerprint != fingerprint:
        raise IdempotencyConflictError
    return FeedbackSubmission(feedback=_audit_domain(audit), replayed=True)


def _audit_domain(row: PlanFeedbackAuditModel) -> PlanFeedback:
    return PlanFeedback(
        id=row.id,
        plan_id=row.plan_id,
        revision=row.revision,
        completion_status=PlanCompletionStatus(row.completion_status),
        reason=row.reason,
        visited_plan_item_ids=tuple(row.visited_plan_item_ids_json),
        preference_suggestion=(
            None
            if row.preference_suggestion_json is None
            else PreferenceSuggestion.model_validate_json(
                json.dumps(row.preference_suggestion_json)
            )
        ),
        created_at=_stored_time(row.created_at),
    )


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _fold_ics_line(value: str) -> str:
    chunks: list[str] = []
    current = ""
    limit = 75
    for char in value:
        candidate = current + char
        if len(candidate.encode("utf-8")) > limit and current:
            chunks.append(current)
            current = char
            limit = 74
        else:
            current = candidate
    chunks.append(current)
    return "\r\n ".join(chunks)


__all__ = [
    "FeedbackSubmission",
    "PlanCalendarService",
    "PlanFeedbackService",
    "PlanNavigationService",
]

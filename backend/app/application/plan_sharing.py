"""Single service for hashed plan shares and one public redacted snapshot."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime

from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import IdempotencyConflictError, ResourceNotFoundError
from app.domain.identifiers import generate_share_link_id
from app.domain.places import CityScope, NavigationRequest
from app.domain.plans import (
    PlanDraftOutcome,
    PlanItemSourceKind,
    PlanStatus,
    PlanVersion,
)
from app.domain.sharing import (
    OwnerShareStatus,
    PublicShareStatus,
    ShareContract,
    SharedPlanItem,
    SharedPlanSnapshot,
    generate_share_token,
    hash_share_token,
    share_expiry_for,
)
from app.domain.time import as_utc, require_aware_utc, utc_now
from app.infrastructure.db.models import PlanModel, PlanShareLinkModel
from app.infrastructure.repositories import (
    SqlAlchemyPlanRepository,
    plan_request_fingerprint,
)
from app.providers.map import MapProvider, MapProviderError


class OwnerPlanShareView(ShareContract):
    status: OwnerShareStatus
    created_at: datetime | None = None
    expires_at: datetime | None = None
    share_url: str | None = Field(default=None, repr=False)
    created: bool = False


class PublicPlanShareView(ShareContract):
    status: PublicShareStatus
    plan: SharedPlanSnapshot | None = None


@dataclass(frozen=True)
class _OwnedPlanContext:
    requested: PlanVersion
    root: PlanModel


@dataclass(frozen=True)
class _ShareContext:
    requested: PlanVersion
    confirmed: PlanVersion


def _stored_time(value: datetime) -> datetime:
    normalized = as_utc(value)
    assert normalized is not None
    return normalized


def _scoped_share_key(user_id: str, client_key: str) -> str:
    digest = hashlib.sha256(f"{user_id}\0{client_key}".encode()).hexdigest()
    return f"share.{digest}"


class PlanShareService:
    """Own share lifecycle, token rules, and the only redaction entrypoint."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        map_provider: MapProvider | None = None,
    ) -> None:
        self._session = session
        self._plans = SqlAlchemyPlanRepository(session)
        self._map_provider = map_provider

    async def status(
        self,
        *,
        user_id: str,
        plan_id: str,
        now: datetime | None = None,
    ) -> OwnerPlanShareView:
        timestamp = require_aware_utc(now or utc_now())
        context = await self._require_owned_root(
            user_id=user_id,
            plan_id=plan_id,
            lock=False,
        )
        row = await self._current_row(
            user_id=user_id,
            root_plan_id=context.root.id,
        )
        if row is None or row.revoked_at is not None:
            return OwnerPlanShareView(status=OwnerShareStatus.INACTIVE)
        expiry = _stored_time(row.expires_at)
        status = (
            OwnerShareStatus.EXPIRED
            if timestamp >= expiry
            else OwnerShareStatus.ACTIVE
        )
        return OwnerPlanShareView(
            status=status,
            created_at=_stored_time(row.created_at),
            expires_at=expiry,
        )

    async def create(
        self,
        *,
        user_id: str,
        plan_id: str,
        regenerate: bool,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OwnerPlanShareView:
        timestamp = require_aware_utc(now or utc_now())
        operation = "regenerate" if regenerate else "create"
        stored_key = _scoped_share_key(user_id, idempotency_key)
        fingerprint = plan_request_fingerprint(
            {"operation": operation, "plan_id": plan_id}
        )
        replay = await self._idempotent_replay(
            user_id=user_id,
            idempotency_key=stored_key,
            request_fingerprint=fingerprint,
            now=timestamp,
        )
        if replay is not None:
            return replay
        context = await self._require_shareable_plan(
            user_id=user_id,
            plan_id=plan_id,
            lock=True,
        )
        root_plan_id = context.requested.root_plan_id
        replay = await self._idempotent_replay(
            user_id=user_id,
            idempotency_key=stored_key,
            request_fingerprint=fingerprint,
            now=timestamp,
        )
        if replay is not None:
            return replay
        expiry = share_expiry_for(context.confirmed.constraints.end_at)
        if timestamp >= expiry:
            return OwnerPlanShareView(
                status=OwnerShareStatus.EXPIRED,
                expires_at=expiry,
            )

        current = await self._current_row(
            user_id=user_id,
            root_plan_id=root_plan_id,
        )
        if (
            current is not None
            and current.revoked_at is None
            and not regenerate
            and timestamp < expiry
        ):
            return OwnerPlanShareView(
                status=OwnerShareStatus.ACTIVE,
                created_at=_stored_time(current.created_at),
                expires_at=expiry,
            )
        if current is not None and current.revoked_at is None:
            current.revoked_at = timestamp

        token = generate_share_token()
        row = PlanShareLinkModel(
            id=generate_share_link_id(),
            plan_id=root_plan_id,
            user_id=user_id,
            token_hash=hash_share_token(token),
            idempotency_key=stored_key,
            request_fingerprint=fingerprint,
            operation=operation,
            created_at=timestamp,
            expires_at=expiry,
            revoked_at=None,
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            replay = await self._idempotent_replay(
                user_id=user_id,
                idempotency_key=stored_key,
                request_fingerprint=fingerprint,
                now=timestamp,
            )
            if replay is not None:
                return replay
            # PostgreSQL serializes on the root Plan row; this fallback preserves
            # SQLite compatibility for a different-key create race.
            current_replay = await self._current_row(
                user_id=user_id,
                root_plan_id=root_plan_id,
            )
            if current_replay is None or current_replay.revoked_at is not None:
                raise
            return OwnerPlanShareView(
                status=OwnerShareStatus.ACTIVE,
                created_at=_stored_time(current_replay.created_at),
                expires_at=share_expiry_for(context.confirmed.constraints.end_at),
            )
        return OwnerPlanShareView(
            status=OwnerShareStatus.ACTIVE,
            created_at=timestamp,
            expires_at=expiry,
            share_url=f"/share#{token}",
            created=True,
        )

    async def revoke(
        self,
        *,
        user_id: str,
        plan_id: str,
        now: datetime | None = None,
    ) -> OwnerPlanShareView:
        timestamp = require_aware_utc(now or utc_now())
        context = await self._require_owned_root(
            user_id=user_id,
            plan_id=plan_id,
            lock=True,
        )
        await self._session.execute(
            update(PlanShareLinkModel)
            .where(
                PlanShareLinkModel.plan_id == context.root.id,
                PlanShareLinkModel.user_id == user_id,
                PlanShareLinkModel.revoked_at.is_(None),
            )
            .values(revoked_at=timestamp)
        )
        await self._session.commit()
        return OwnerPlanShareView(status=OwnerShareStatus.INACTIVE)

    async def read_public(
        self,
        *,
        token: str,
        now: datetime | None = None,
    ) -> PublicPlanShareView:
        timestamp = require_aware_utc(now or utc_now())
        digest = hash_share_token(token)
        row = await self._session.scalar(
            select(PlanShareLinkModel).where(
                PlanShareLinkModel.token_hash == digest
            )
        )
        stored_digest = row.token_hash if row is not None else ("0" * 64)
        digest_matches = hmac.compare_digest(stored_digest, digest)
        if row is None or not digest_matches or row.revoked_at is not None:
            return PublicPlanShareView(status=PublicShareStatus.UNAVAILABLE)
        expiry = _stored_time(row.expires_at)
        if timestamp >= expiry:
            return PublicPlanShareView(status=PublicShareStatus.UNAVAILABLE)

        root = await self._session.scalar(
            select(PlanModel)
            .where(
                PlanModel.user_id == row.user_id,
                PlanModel.id == row.plan_id,
            )
        )
        if root is not None and root.status == PlanStatus.CANCELLED.value:
            return PublicPlanShareView(status=PublicShareStatus.CANCELLED)

        confirmed = await self._plans.latest_confirmed(
            user_id=row.user_id,
            root_plan_id=row.plan_id,
        )
        if confirmed is None:
            return PublicPlanShareView(status=PublicShareStatus.UNAVAILABLE)
        snapshot = await self._build_snapshot(confirmed, expires_at=expiry)
        return PublicPlanShareView(
            status=PublicShareStatus.ACTIVE,
            plan=snapshot,
        )

    async def sync_expiry_after_confirmation(self, plan: PlanVersion) -> None:
        """Keep the stored audit expiry aligned when a new version is confirmed."""

        latest = await self._plans.latest_confirmed(
            user_id=plan.user_id,
            root_plan_id=plan.root_plan_id,
        )
        if latest is None:
            return
        await self._session.execute(
            update(PlanShareLinkModel)
            .where(
                PlanShareLinkModel.plan_id == plan.root_plan_id,
                PlanShareLinkModel.user_id == plan.user_id,
                PlanShareLinkModel.revoked_at.is_(None),
            )
            .values(expires_at=share_expiry_for(latest.constraints.end_at))
        )

    async def preview(
        self,
        *,
        user_id: str,
        plan_id: str,
    ) -> SharedPlanSnapshot:
        """Build the exact redacted owner preview without creating a share."""

        context = await self._require_shareable_plan(
            user_id=user_id,
            plan_id=plan_id,
            lock=False,
        )
        expiry = share_expiry_for(context.confirmed.constraints.end_at)
        return await self._build_snapshot(context.confirmed, expires_at=expiry)

    async def _idempotent_replay(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        now: datetime,
    ) -> OwnerPlanShareView | None:
        operation = await self._session.scalar(
            select(PlanShareLinkModel).where(
                PlanShareLinkModel.user_id == user_id,
                PlanShareLinkModel.idempotency_key == idempotency_key,
            )
        )
        if operation is None:
            return None
        if operation.request_fingerprint != request_fingerprint:
            raise IdempotencyConflictError
        current = await self._current_row(
            user_id=user_id,
            root_plan_id=operation.plan_id,
        )
        if current is None:
            return OwnerPlanShareView(status=OwnerShareStatus.INACTIVE)
        expiry = _stored_time(current.expires_at)
        return OwnerPlanShareView(
            status=(
                OwnerShareStatus.EXPIRED
                if now >= expiry
                else OwnerShareStatus.ACTIVE
            ),
            created_at=_stored_time(current.created_at),
            expires_at=expiry,
        )

    async def _require_shareable_plan(
        self,
        *,
        user_id: str,
        plan_id: str,
        lock: bool,
    ) -> _ShareContext:
        owned = await self._require_owned_root(
            user_id=user_id,
            plan_id=plan_id,
            lock=lock,
        )
        confirmed = await self._plans.latest_confirmed(
            user_id=user_id,
            root_plan_id=owned.requested.root_plan_id,
        )
        if confirmed is None:
            from app.domain.plans import PlanExecutionNotAllowedError

            raise PlanExecutionNotAllowedError
        return _ShareContext(requested=owned.requested, confirmed=confirmed)

    async def _require_owned_root(
        self,
        *,
        user_id: str,
        plan_id: str,
        lock: bool,
    ) -> _OwnedPlanContext:
        """Validate ownership and resolve the root without requiring confirmation."""

        requested = await self._plans.require(user_id=user_id, plan_id=plan_id)
        statement = select(PlanModel).where(
            PlanModel.id == requested.root_plan_id,
            PlanModel.user_id == user_id,
        )
        if lock:
            statement = statement.with_for_update()
        root = await self._session.scalar(statement)
        if root is None:
            raise ResourceNotFoundError
        return _OwnedPlanContext(requested=requested, root=root)

    async def _current_row(
        self,
        *,
        user_id: str,
        root_plan_id: str,
    ) -> PlanShareLinkModel | None:
        row: PlanShareLinkModel | None = await self._session.scalar(
            select(PlanShareLinkModel)
            .where(
                PlanShareLinkModel.plan_id == root_plan_id,
                PlanShareLinkModel.user_id == user_id,
                PlanShareLinkModel.revoked_at.is_(None),
            )
            .order_by(PlanShareLinkModel.created_at.desc())
        )
        return row

    async def _build_snapshot(
        self,
        plan: PlanVersion,
        *,
        expires_at: datetime,
    ) -> SharedPlanSnapshot:
        if (
            plan.draft is None
            or plan.draft.outcome is not PlanDraftOutcome.GENERATED
            or not plan.draft.options
        ):
            from app.domain.plans import PlanExecutionNotAllowedError

            raise PlanExecutionNotAllowedError
        option = plan.draft.options[0]
        shared_items: list[SharedPlanItem] = []
        for index, item in enumerate(option.items):
            poi = item.source.concrete_poi
            map_url: str | None = None
            if poi is not None and self._map_provider is not None:
                try:
                    map_url = (
                        await self._map_provider.build_navigation_uri(
                            NavigationRequest(
                                city=CityScope(city_code=poi.city_code),
                                poi_id=poi.poi_id,
                                coordinate=poi.coordinate,
                            )
                        )
                    ).uri
                except MapProviderError:
                    map_url = None
            buffer_after = (
                option.switch_buffer_seconds or 0
                if index < len(option.items) - 1
                else option.end_buffer_seconds
            )
            shared_items.append(
                SharedPlanItem(
                    title=item.title,
                    start_at=item.start_at,
                    end_at=item.end_at,
                    public_address=None if poi is None else poi.address,
                    visit_duration_seconds=item.visit_duration_seconds,
                    transport_mode=item.inbound_route.transport_mode,
                    travel_duration_seconds=item.inbound_route.duration_seconds,
                    travel_distance_meters=item.inbound_route.distance_meters,
                    buffer_after_seconds=buffer_after,
                    price_amount=item.price_amount,
                    price_currency=item.price_currency,
                    source_label=(
                        item.source.source_label or "高德公开地点"
                        if item.source.kind is PlanItemSourceKind.EXTERNAL_PLACE
                        else "计划地点"
                    ),
                    risks=item.risks,
                    queried_at=item.source.poi_queried_at,
                    map_url=map_url,
                )
            )
        confirmed_at = plan.confirmed_at
        assert confirmed_at is not None
        return SharedPlanSnapshot(
            version=plan.version,
            confirmed_at=confirmed_at,
            updated_at=plan.updated_at,
            start_at=plan.constraints.start_at,
            end_at=plan.constraints.end_at,
            origin_label=_public_origin_label(plan),
            items=tuple(shared_items),
            total_cost_amount=option.total_cost_amount,
            total_cost_currency=option.total_cost_currency,
            risks=option.risks,
            weather_status=(
                None if plan.draft.weather_status is None else plan.draft.weather_status.value
            ),
            weather_source=plan.draft.weather_source,
            weather_queried_at=plan.draft.weather_queried_at,
            weather_summary=plan.draft.weather_summary,
            expires_at=expires_at,
        )


def _public_origin_label(plan: PlanVersion) -> str:
    area = plan.constraints.area
    if area is not None:
        if area.districts:
            return " · ".join(area.districts)
    # Free-form area labels can contain a home, school, or workplace address.
    # Only the structured administrative district crosses the public boundary.
    return "深圳市内出发"


__all__ = [
    "OwnerPlanShareView",
    "PlanShareService",
    "PublicPlanShareView",
]

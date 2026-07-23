"""The single M0-5D orchestration path for an explicit external Place gap."""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.application.place_matching import PlaceMatchingService
from app.application.plan_drafts import PlanDraftService
from app.domain.places import (
    Coordinate,
    MatchStatus,
    PlaceMatchRequest,
    RouteRequest,
    RouteResult,
    TransportMode,
    poi_from_match_candidate,
)
from app.domain.plans import PlanConstraints
from app.domain.plans.drafts import (
    ExternalDraftCandidate,
    PlanDraftFactSnapshot,
    PlanDraftOutcome,
    PlanDraftResult,
    PlanItemSourceKind,
    PlanRouteLeg,
)
from app.domain.plans.retrieval import (
    StructuredCollectionResult,
    external_poi_scope_reasons,
)
from app.domain.plans.supplement import (
    RECOVERY_SUMMARIES,
    ExternalApprovalDecision,
    ExternalPlaceApprovalDecision,
    ExternalPlaceApprovalRequirement,
    ExternalPlaceSupplementResult,
    ExternalRecoveryCode,
    ExternalSupplementOutcome,
    RequiredGapKind,
    RequiredPlanGap,
)
from app.domain.runs import AgentRunStatus
from app.providers.map import MapProvider, MapProviderError, MapProviderErrorCode

_MAP_RECOVERY_CODES: dict[MapProviderErrorCode, ExternalRecoveryCode] = {
    MapProviderErrorCode.TIMEOUT: ExternalRecoveryCode.MAP_TIMEOUT,
    MapProviderErrorCode.RATE_LIMITED: ExternalRecoveryCode.MAP_RATE_LIMITED,
    MapProviderErrorCode.INVALID_RESPONSE: ExternalRecoveryCode.MAP_INVALID_RESPONSE,
    MapProviderErrorCode.AUTHENTICATION_FAILED: ExternalRecoveryCode.MAP_UNAVAILABLE,
    MapProviderErrorCode.INVALID_REQUEST: ExternalRecoveryCode.MAP_UNAVAILABLE,
    MapProviderErrorCode.POI_NOT_FOUND: ExternalRecoveryCode.PLACE_NOT_FOUND,
    MapProviderErrorCode.UNAVAILABLE: ExternalRecoveryCode.MAP_UNAVAILABLE,
}


class ExternalPlaceSupplementService:
    """Compose existing matching, map, and draft services without persistent state."""

    def __init__(
        self,
        *,
        map_provider: MapProvider,
        place_matching: PlaceMatchingService,
        plan_drafts: PlanDraftService,
    ) -> None:
        self._map_provider = map_provider
        self._place_matching = place_matching
        self._plan_drafts = plan_drafts

    async def generate(
        self,
        *,
        constraints: PlanConstraints,
        collections: StructuredCollectionResult,
        facts: PlanDraftFactSnapshot,
        required_gap: RequiredPlanGap | None,
        approval_decision: ExternalPlaceApprovalDecision | None,
        queried_at: datetime,
    ) -> ExternalPlaceSupplementResult:
        base_draft = self._plan_drafts.generate(
            constraints=constraints,
            collections=collections,
            facts=facts,
        )
        if required_gap is None:
            return self._draft_or_recovery(base_draft)
        if constraints.collection_only:
            if base_draft.outcome is PlanDraftOutcome.GENERATED:
                return self._draft(base_draft)
            return self._recovery(ExternalRecoveryCode.COLLECTION_ONLY)
        if required_gap.kind is RequiredGapKind.EVENT:
            return self._recovery(
                ExternalRecoveryCode.EVENT_NOT_SEARCHABLE,
                draft=(
                    base_draft
                    if base_draft.outcome is PlanDraftOutcome.GENERATED
                    else None
                ),
            )

        has_collection_core = base_draft.outcome is PlanDraftOutcome.GENERATED
        requirement = ExternalPlaceApprovalRequirement.for_gap(required_gap)
        if not has_collection_core and (
            approval_decision is None
            or approval_decision.approval_id != requirement.approval_id
        ):
            return ExternalPlaceSupplementResult(
                outcome=ExternalSupplementOutcome.WAITING_APPROVAL,
                run_status=AgentRunStatus.WAITING_USER,
                approval=requirement,
            )
        if (
            approval_decision is not None
            and approval_decision.approval_id == requirement.approval_id
            and approval_decision.decision is ExternalApprovalDecision.REJECTED
        ):
            if has_collection_core:
                return self._draft(base_draft)
            return self._recovery(ExternalRecoveryCode.ADD_COLLECTIONS)

        assert required_gap.place_candidate is not None
        try:
            match = await self._place_matching.match(
                PlaceMatchRequest(
                    candidate=required_gap.place_candidate.model_copy(deep=True),
                    city=constraints.city_scope,
                    search_district=self._single_district(constraints),
                    search_location=(
                        None
                        if constraints.origin is None
                        else constraints.origin.model_copy(deep=True)
                    ),
                )
            )
        except asyncio.CancelledError:
            raise
        except MapProviderError as exc:
            return self._recovery(_MAP_RECOVERY_CODES[exc.code], draft=self._base(base_draft))

        existing_pois = {
            decision.poi_identity
            for decision in collections.included
            if decision.poi_identity is not None
        }
        candidates = tuple(
            item
            for item in match.candidates
            if item.identity not in existing_pois
            and not external_poi_scope_reasons(
                poi_from_match_candidate(item),
                constraints,
            )
        )[:3]
        if match.status is MatchStatus.NOT_FOUND or not candidates:
            return self._recovery(
                ExternalRecoveryCode.PLACE_NOT_FOUND,
                draft=self._base(base_draft),
            )
        if match.status is not MatchStatus.MATCHED or len(candidates) != 1:
            return ExternalPlaceSupplementResult(
                outcome=ExternalSupplementOutcome.NEEDS_SELECTION,
                run_status=AgentRunStatus.SUCCEEDED,
                draft=self._base(base_draft),
                candidates=candidates,
                recovery_code=ExternalRecoveryCode.PLACE_AMBIGUOUS,
                recovery_summary=RECOVERY_SUMMARIES[
                    ExternalRecoveryCode.PLACE_AMBIGUOUS
                ],
            )

        poi = poi_from_match_candidate(candidates[0])
        route_origin, from_ids = self._route_origin(base_draft, constraints)
        if route_origin is None:
            return self._recovery(
                ExternalRecoveryCode.ROUTE_FACTS_MISSING,
                draft=self._base(base_draft),
            )
        mode = (
            constraints.transport_modes[0]
            if constraints.transport_modes
            else TransportMode.TRANSIT
        )
        route_request = RouteRequest(
            city=constraints.city_scope,
            origin=route_origin,
            destination=poi.coordinate,
            mode=mode,
        )
        try:
            raw_route = await self._map_provider.route(route_request)
            route = RouteResult(
                city_code=raw_route.city_code,
                origin=raw_route.origin,
                destination=raw_route.destination,
                mode=raw_route.mode,
                distance_meters=raw_route.distance_meters,
                duration_seconds=raw_route.duration_seconds,
            )
            if (
                route.city_code != constraints.city_code.value
                or route.origin != route_request.origin
                or route.destination != route_request.destination
                or route.mode is not route_request.mode
            ):
                raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
        except asyncio.CancelledError:
            raise
        except MapProviderError as exc:
            return self._recovery(_MAP_RECOVERY_CODES[exc.code], draft=self._base(base_draft))
        except Exception:
            return self._recovery(
                ExternalRecoveryCode.MAP_INVALID_RESPONSE,
                draft=self._base(base_draft),
            )

        external = ExternalDraftCandidate(
            poi=poi,
            queried_at=queried_at,
            supplement_reason=required_gap.supplement_reason,
            visit_duration_seconds=required_gap.visit_duration_seconds,
            price_amount=required_gap.place_candidate.price_amount,
            price_currency=required_gap.place_candidate.price_currency,
            inbound_route=PlanRouteLeg(
                from_collection_item_ids=from_ids,
                to_external_provider=poi.provider,
                to_external_poi_id=poi.poi_id,
                duration_seconds=route.duration_seconds,
                distance_meters=route.distance_meters,
                transport_mode=route.mode,
            ),
        )
        draft = self._plan_drafts.generate(
            constraints=constraints,
            collections=collections,
            facts=facts,
            external_candidate=external,
        )
        external_added = (
            draft.outcome is PlanDraftOutcome.GENERATED
            and any(
                item.source.kind is PlanItemSourceKind.EXTERNAL_PLACE
                for item in draft.options[0].items
            )
        )
        if not external_added:
            return self._recovery(
                ExternalRecoveryCode.NO_EXECUTABLE_DRAFT,
                draft=self._base(base_draft),
            )
        validation = self._plan_drafts.validate(
            draft=draft,
            constraints=constraints,
            collections=collections,
            facts=facts,
            external_candidate=external,
        )
        if not validation.is_valid:
            return self._recovery(
                ExternalRecoveryCode.NO_EXECUTABLE_DRAFT,
                draft=self._base(base_draft),
            )
        return self._draft(draft)

    @staticmethod
    def _single_district(constraints: PlanConstraints) -> str | None:
        if constraints.area is None or len(constraints.area.districts) != 1:
            return None
        return constraints.area.districts[0]

    @staticmethod
    def _route_origin(
        base_draft: PlanDraftResult,
        constraints: PlanConstraints,
    ) -> tuple[Coordinate | None, tuple[str, ...]]:
        if base_draft.outcome is PlanDraftOutcome.GENERATED:
            core = base_draft.options[0].items[0]
            if (
                core.source.kind is PlanItemSourceKind.COLLECTION_DERIVED
                and core.source.concrete_poi is not None
            ):
                return (
                    core.source.concrete_poi.coordinate.model_copy(deep=True),
                    core.source.collection_item_ids,
                )
            return (None, ())
        if constraints.origin is not None:
            return (constraints.origin.model_copy(deep=True), ())
        return (None, ())

    @staticmethod
    def _base(draft: PlanDraftResult) -> PlanDraftResult | None:
        return draft if draft.outcome is PlanDraftOutcome.GENERATED else None

    def _draft_or_recovery(self, draft: PlanDraftResult) -> ExternalPlaceSupplementResult:
        if draft.outcome is PlanDraftOutcome.GENERATED:
            return self._draft(draft)
        return self._recovery(ExternalRecoveryCode.NO_EXECUTABLE_DRAFT)

    @staticmethod
    def _draft(draft: PlanDraftResult) -> ExternalPlaceSupplementResult:
        return ExternalPlaceSupplementResult(
            outcome=ExternalSupplementOutcome.DRAFT,
            run_status=AgentRunStatus.SUCCEEDED,
            draft=draft,
        )

    @staticmethod
    def _recovery(
        code: ExternalRecoveryCode,
        *,
        draft: PlanDraftResult | None = None,
    ) -> ExternalPlaceSupplementResult:
        return ExternalPlaceSupplementResult(
            outcome=ExternalSupplementOutcome.RECOVERY_REQUIRED,
            run_status=AgentRunStatus.SUCCEEDED,
            draft=draft,
            recovery_code=code,
            recovery_summary=RECOVERY_SUMMARIES[code],
        )

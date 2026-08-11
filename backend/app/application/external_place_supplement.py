"""The sole read-only Amap boundary for one explicit external Place gap."""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.application.place_matching import PlaceMatchingService
from app.domain.places import MatchStatus, PlaceMatchRequest, poi_from_match_candidate
from app.domain.plans import PlanConstraints
from app.domain.plans.retrieval import StructuredCollectionResult, external_poi_scope_reasons
from app.domain.plans.supplement import (
    RECOVERY_SUMMARIES,
    ExternalApprovalDecision,
    ExternalPlaceApprovalDecision,
    ExternalPlaceApprovalRequirement,
    ExternalPlaceCandidate,
    ExternalPlaceSupplementResult,
    ExternalRecoveryCode,
    ExternalSupplementOutcome,
    RequiredGapKind,
    RequiredPlanGap,
)
from app.domain.runs import AgentRunStatus
from app.providers.map import MapProviderError, MapProviderErrorCode

_MAP_RECOVERY_CODES = {
    MapProviderErrorCode.TIMEOUT: ExternalRecoveryCode.MAP_TIMEOUT,
    MapProviderErrorCode.RATE_LIMITED: ExternalRecoveryCode.MAP_RATE_LIMITED,
    MapProviderErrorCode.INVALID_RESPONSE: ExternalRecoveryCode.MAP_INVALID_RESPONSE,
    MapProviderErrorCode.AUTHENTICATION_FAILED: ExternalRecoveryCode.MAP_UNAVAILABLE,
    MapProviderErrorCode.INVALID_REQUEST: ExternalRecoveryCode.MAP_UNAVAILABLE,
    MapProviderErrorCode.POI_NOT_FOUND: ExternalRecoveryCode.PLACE_NOT_FOUND,
    MapProviderErrorCode.UNAVAILABLE: ExternalRecoveryCode.MAP_UNAVAILABLE,
}


class ExternalPlaceSupplementService:
    """Authorize and search one explicit gap; never schedule or persist plans."""

    def __init__(self, *, place_matching: PlaceMatchingService) -> None:
        self._place_matching = place_matching

    async def generate(
        self,
        *,
        constraints: PlanConstraints,
        collections: StructuredCollectionResult,
        required_gap: RequiredPlanGap,
        approval_decision: ExternalPlaceApprovalDecision | None,
        queried_at: datetime,
    ) -> ExternalPlaceSupplementResult:
        if constraints.collection_only:
            return self._recovery(ExternalRecoveryCode.COLLECTION_ONLY)
        if required_gap.kind is RequiredGapKind.EVENT:
            return self._recovery(ExternalRecoveryCode.EVENT_NOT_SEARCHABLE)

        requirement = ExternalPlaceApprovalRequirement.for_gap(required_gap)
        if not collections.included and (
            approval_decision is None or approval_decision.approval_id != requirement.approval_id
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
            return self._recovery(ExternalRecoveryCode.ADD_COLLECTIONS)

        assert required_gap.place_candidate is not None
        try:
            match = await self._place_matching.match(
                PlaceMatchRequest(
                    candidate=required_gap.place_candidate.model_copy(deep=True),
                    city=constraints.city_scope,
                    search_district=self._single_district(constraints),
                    search_location=constraints.origin,
                )
            )
        except asyncio.CancelledError:
            raise
        except MapProviderError as exc:
            return self._recovery(_MAP_RECOVERY_CODES[exc.code])

        existing = {
            decision.poi_identity
            for decision in collections.included
            if decision.poi_identity is not None
        }
        eligible = tuple(
            candidate
            for candidate in match.candidates
            if candidate.identity not in existing
            and not external_poi_scope_reasons(poi_from_match_candidate(candidate), constraints)
        )[:3]
        if match.status is not MatchStatus.MATCHED or not eligible:
            if eligible:
                return ExternalPlaceSupplementResult(
                    outcome=ExternalSupplementOutcome.NEEDS_SELECTION,
                    run_status=AgentRunStatus.SUCCEEDED,
                    candidates=eligible,
                    recovery_code=ExternalRecoveryCode.PLACE_AMBIGUOUS,
                    recovery_summary=RECOVERY_SUMMARIES[ExternalRecoveryCode.PLACE_AMBIGUOUS],
                )
            return self._recovery(ExternalRecoveryCode.PLACE_NOT_FOUND)
        selected = match.candidates[0]
        if selected not in eligible:
            return self._recovery(ExternalRecoveryCode.PLACE_NOT_FOUND)
        return ExternalPlaceSupplementResult(
            outcome=ExternalSupplementOutcome.CANDIDATE,
            run_status=AgentRunStatus.SUCCEEDED,
            candidate=ExternalPlaceCandidate(
                poi=poi_from_match_candidate(selected),
                queried_at=queried_at,
                supplement_reason=required_gap.supplement_reason,
                price_amount=required_gap.place_candidate.price_amount,
                price_currency=required_gap.place_candidate.price_currency,
            ),
        )

    @staticmethod
    def _single_district(constraints: PlanConstraints) -> str | None:
        if constraints.area is None or len(constraints.area.districts) != 1:
            return None
        return constraints.area.districts[0]

    @staticmethod
    def _recovery(code: ExternalRecoveryCode) -> ExternalPlaceSupplementResult:
        return ExternalPlaceSupplementResult(
            outcome=ExternalSupplementOutcome.RECOVERY_REQUIRED,
            run_status=AgentRunStatus.SUCCEEDED,
            recovery_code=code,
            recovery_summary=RECOVERY_SUMMARIES[code],
        )

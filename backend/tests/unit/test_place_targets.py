"""M0-3D unified Place target and planning-boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.places import (
    BrandIdentityConfirmationSource,
    ConfirmedBrandIdentity,
    EvidenceField,
    EvidenceOutcome,
    EvidenceReason,
    MatchConfidence,
    MatchEvidence,
    MatchStatus,
    PlaceCandidateSnapshot,
    PlaceConfirmationSource,
    PlaceMatchCandidate,
    PlaceMatchResult,
    PlaceScope,
    PlaceTarget,
    ResolvedPlaceTargetKind,
    exact_target_from_candidate,
    normalize_brand_name,
    resolve_place_target,
)
from tests.fixtures.place_matching import M_STAND_COASTAL, M_STAND_MIXC

NOW = datetime(2026, 7, 22, 4, 0, tzinfo=UTC)


def _evidence() -> tuple[MatchEvidence, ...]:
    return tuple(
        MatchEvidence(
            field=field,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.SOURCE_MISSING,
            score_delta=0.0,
        )
        for field in EvidenceField
    )


def _candidate(index: int = 0) -> PlaceMatchCandidate:
    poi = (M_STAND_COASTAL, M_STAND_MIXC)[index]
    return PlaceMatchCandidate(
        provider=poi.provider,
        poi_id=poi.poi_id,
        city_code=poi.city_code,
        coordinate=poi.coordinate,
        name=poi.name,
        branch_name=poi.branch_name,
        district=poi.district,
        business_area=poi.business_area,
        address=poi.address,
        poi_type=poi.poi_type,
        provider_rank=index + 1,
        rank=index + 1,
        score=70.0 - index,
        confidence=MatchConfidence.MEDIUM,
        evidence=_evidence(),
    )


def _brand(*, stable_id: str = "brand_mstand_cn") -> ConfirmedBrandIdentity:
    return ConfirmedBrandIdentity(
        namespace="curated_brand",
        stable_id=stable_id,
        display_name="M Stand 咖啡",
        normalized_name=normalize_brand_name("M Stand 咖啡"),
        identity_confirmed_by=BrandIdentityConfirmationSource.CURATED,
        identity_confirmed_at=NOW,
    )


def test_exact_target_requires_one_valid_confirmed_gcj02_poi() -> None:
    candidate = _candidate()
    target = exact_target_from_candidate(
        candidate,
        confirmed_by=PlaceConfirmationSource.USER_SELECTION,
        confirmed_at=NOW,
    )

    assert target.scope is PlaceScope.EXACT
    assert target.poi is not None
    assert target.poi.poi_id == candidate.poi_id
    assert target.poi.city_code == "shenzhen"
    assert target.match_status is MatchStatus.MATCHED
    assert target.confirmed_at == NOW
    with pytest.raises(ValidationError, match="exact targets require exactly one"):
        PlaceTarget(
            scope=PlaceScope.EXACT,
            match_status=MatchStatus.MATCHED,
            confidence=MatchConfidence.HIGH,
            confirmed_by=PlaceConfirmationSource.USER_SELECTION,
            confirmed_at=NOW,
            evidence_summary=_evidence(),
        )


def test_low_confidence_user_choice_is_allowed_but_hard_conflict_is_not() -> None:
    low_confidence = _candidate().model_copy(update={"confidence": MatchConfidence.LOW})
    conflict_evidence = _evidence()[0].model_copy(
        update={
            "outcome": EvidenceOutcome.CONFLICT,
            "reason": EvidenceReason.CONFLICT,
            "score_delta": -100.0,
            "hard_conflict": True,
        }
    )
    hard_conflict = _candidate().model_copy(
        update={"evidence": (conflict_evidence, *_evidence()[1:])}
    )

    target = exact_target_from_candidate(
        low_confidence,
        confirmed_by=PlaceConfirmationSource.USER_SELECTION,
        confirmed_at=NOW,
    )
    assert target.confidence is MatchConfidence.LOW
    with pytest.raises(ValueError, match="hard-conflict"):
        exact_target_from_candidate(
            hard_conflict,
            confirmed_by=PlaceConfirmationSource.USER_SELECTION,
            confirmed_at=NOW,
        )


def test_any_branch_requires_stable_identity_and_explicit_user_choice() -> None:
    brand = _brand()
    target = PlaceTarget(
        scope=PlaceScope.ANY_BRANCH,
        brand_identity=brand,
        match_status=MatchStatus.AMBIGUOUS,
        confidence=MatchConfidence.MEDIUM,
        confirmed_by=PlaceConfirmationSource.USER_SELECTION,
        confirmed_at=NOW,
    )
    assert target.brand_identity == brand

    with pytest.raises(ValidationError, match="stable brand identity"):
        PlaceTarget(
            scope=PlaceScope.ANY_BRANCH,
            match_status=MatchStatus.AMBIGUOUS,
            confirmed_by=PlaceConfirmationSource.USER_SELECTION,
            confirmed_at=NOW,
        )
    with pytest.raises(ValidationError, match="explicit user selection"):
        PlaceTarget(
            scope=PlaceScope.ANY_BRANCH,
            brand_identity=brand,
            match_status=MatchStatus.AMBIGUOUS,
            confirmed_by=PlaceConfirmationSource.AUTO_UNIQUE_MATCH,
            confirmed_at=NOW,
        )


def test_brand_name_normalization_never_merges_distinct_stable_identities() -> None:
    first = _brand(stable_id="brand_mstand_cn")
    second = _brand(stable_id="brand_mstand_other")
    assert first.normalized_name == second.normalized_name
    assert first.identity != second.identity
    with pytest.raises(ValidationError, match="normalized brand name"):
        ConfirmedBrandIdentity(
            namespace="curated_brand",
            stable_id="brand_bad",
            display_name="M Stand 咖啡",
            normalized_name="starbucks",
            identity_confirmed_by=BrandIdentityConfirmationSource.CURATED,
            identity_confirmed_at=NOW,
        )


def test_snapshot_preserves_queried_at_and_inputs_are_not_mutated() -> None:
    result = PlaceMatchResult(
        status=MatchStatus.AMBIGUOUS,
        candidates=(_candidate(), _candidate(1)),
    )
    original = result.model_dump(mode="python")
    first = PlaceCandidateSnapshot(result=result, queried_at=NOW)
    second = PlaceCandidateSnapshot(result=result, queried_at=NOW)

    assert first == second
    assert len(first.candidates) == 2
    assert first.queried_at == NOW
    assert result.model_dump(mode="python") == original


def test_target_resolution_blocks_pending_and_distinguishes_exact_and_any_branch() -> None:
    exact = exact_target_from_candidate(
        _candidate(),
        confirmed_by=PlaceConfirmationSource.USER_SELECTION,
        confirmed_at=NOW,
    )
    any_branch = PlaceTarget(
        scope=PlaceScope.ANY_BRANCH,
        brand_identity=_brand(),
        match_status=MatchStatus.AMBIGUOUS,
        confidence=MatchConfidence.MEDIUM,
        confirmed_by=PlaceConfirmationSource.USER_SELECTION,
        confirmed_at=NOW,
    )

    assert resolve_place_target(None, collection_status="pending_selection").kind is (
        ResolvedPlaceTargetKind.UNCONFIRMED
    )
    assert resolve_place_target(exact, collection_status="pending_selection").kind is (
        ResolvedPlaceTargetKind.UNCONFIRMED
    )
    assert resolve_place_target(exact, collection_status="active").kind is (
        ResolvedPlaceTargetKind.EXACT
    )
    assert resolve_place_target(any_branch, collection_status="active").kind is (
        ResolvedPlaceTargetKind.ANY_BRANCH
    )

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.domain.places import (
    EvidenceField,
    EvidenceOutcome,
    MatchEvidence,
    MatchStatus,
    PlaceMatchCandidate,
    PlaceMatchRequest,
    Poi,
    PoiType,
    classify_place_matches,
    score_place_candidate,
)
from tests.fixtures.place_matching import (
    M_STAND_COASTAL,
    M_STAND_MIXC,
    SHENZHEN,
    place_candidate,
    poi,
)

POLICY = Settings(_env_file=None, app_env="test").place_matching_policy()  # type: ignore[call-arg]


def _venue_pois() -> tuple[Poi, ...]:
    values = (
        ("venue", "深圳市当代艺术与城市规划馆", PoiType.MUSEUM),
        ("parking", "深圳市当代艺术与城市规划馆地下停车场", PoiType.TRANSIT),
        ("entrance", "深圳市当代艺术与城市规划馆地下停车场(入口)", PoiType.TRANSIT),
    )
    return tuple(
        poi(
            poi_id=poi_id,
            name=name,
            district="福田区",
            address="福中路184号(少年宫地铁站步行500米)",
            poi_type=poi_type,
        )
        for poi_id, name, poi_type in values
    )


def _score(
    title: str,
    address: str | None,
    candidates: tuple[Poi, ...] | None = None,
) -> tuple[PlaceMatchCandidate, ...]:
    request = PlaceMatchRequest(
        candidate=place_candidate(
            title=title,
            city_hint="深圳",
            district="福田区",
            address=address,
        ),
        city=SHENZHEN,
        source_context=SecretStr(f"请收藏{title}，地址是{address or '未提供'}。"),
    )
    return tuple(
        score_place_candidate(
            request=request,
            poi=candidate,
            provider_rank=rank,
            policy=POLICY,
        )
        for rank, candidate in enumerate(candidates or _venue_pois(), start=1)
    )


def _evidence(candidate: PlaceMatchCandidate, field: EvidenceField) -> MatchEvidence:
    return next(item for item in candidate.evidence if item.field is field)


def test_administrative_name_address_core_and_subfacility_evidence_select_venue() -> None:
    scored = _score("深圳当代艺术与城市规划馆", "福田区福中路184号")
    result = classify_place_matches(scored, policy=POLICY)

    assert result.status is MatchStatus.MATCHED
    assert result.candidates[0].poi_id == "venue"
    assert _evidence(scored[0], EvidenceField.NAME).outcome is EvidenceOutcome.MATCH
    assert _evidence(scored[0], EvidenceField.ADDRESS).outcome is EvidenceOutcome.MATCH
    assert all(
        _evidence(candidate, EvidenceField.BRANCH_NAME).outcome
        is EvidenceOutcome.CONFLICT
        for candidate in scored[1:]
    )
    assert scored[0].score - max(item.score for item in scored[1:]) >= POLICY.minimum_score_gap


@pytest.mark.parametrize("address", ["福华路184号", "福中路185号"])
def test_different_road_or_street_number_remains_an_address_conflict(address: str) -> None:
    scored = _score("深圳当代艺术与城市规划馆", address)

    assert _evidence(scored[0], EvidenceField.ADDRESS).outcome is EvidenceOutcome.CONFLICT


def test_explicit_parking_input_matches_parking_instead_of_parent_or_entrance() -> None:
    scored = _score("深圳当代艺术与城市规划馆地下停车场", "福中路184号")
    result = classify_place_matches(scored, policy=POLICY)

    assert result.status is MatchStatus.MATCHED
    assert result.candidates[0].poi_id == "parking"


def test_chain_branches_and_name_only_evidence_remain_unconfirmed() -> None:
    chain_request = PlaceMatchRequest(
        candidate=place_candidate(title="M Stand咖啡", tags=("咖啡",)),
        city=SHENZHEN,
    )
    chain_scores = tuple(
        score_place_candidate(
            request=chain_request,
            poi=candidate,
            provider_rank=rank,
            policy=POLICY,
        )
        for rank, candidate in enumerate((M_STAND_COASTAL, M_STAND_MIXC), start=1)
    )
    weak = _score(
        "同名空间",
        None,
        (poi(poi_id="provider-first", name="同名空间"),),
    )
    same_name_request = PlaceMatchRequest(
        candidate=place_candidate(
            title="同名书店",
            district="南山区",
            address="文心五路海岸城",
        ),
        city=SHENZHEN,
    )
    same_name_scores = tuple(
        score_place_candidate(
            request=same_name_request,
            poi=candidate,
            provider_rank=rank,
            policy=POLICY,
        )
        for rank, candidate in enumerate(
            (
                poi(
                    poi_id="futian",
                    name="同名书店",
                    district="福田区",
                    address="福田区福华路",
                ),
                poi(
                    poi_id="nanshan",
                    name="同名书店",
                    district="南山区",
                    address="南山区文心五路海岸城",
                ),
            ),
            start=1,
        )
    )

    assert classify_place_matches(chain_scores, policy=POLICY).status is MatchStatus.AMBIGUOUS
    assert classify_place_matches(same_name_scores, policy=POLICY).status is MatchStatus.AMBIGUOUS
    assert classify_place_matches(weak, policy=POLICY).status is MatchStatus.NEEDS_CONTEXT


def test_provider_rank_and_default_thresholds_do_not_auto_confirm_equal_candidates() -> None:
    same_name = (
        poi(poi_id="provider-first", name="同名空间", district="福田区"),
        poi(poi_id="provider-second", name="同名空间", district="福田区"),
    )
    result = classify_place_matches(
        _score("同名空间", "福中路184号", same_name),
        policy=POLICY,
    )

    assert POLICY.unique_match_score == 75
    assert POLICY.minimum_score_gap == 12
    assert result.status is MatchStatus.AMBIGUOUS
    assert result.candidates[0].poi_id == "provider-first"

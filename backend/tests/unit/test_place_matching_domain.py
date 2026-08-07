from __future__ import annotations

from math import inf, nan

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.domain.collections import CandidateField, CollectionKind, EventCandidate
from app.domain.places import (
    EvidenceField,
    EvidenceOutcome,
    EvidenceReason,
    MatchConfidence,
    MatchEvidence,
    MatchStatus,
    PlaceMatchCandidate,
    PlaceMatchingPolicy,
    PlaceMatchRequest,
    PlaceMatchResult,
    PlaceSelection,
    PlaceSelectionKind,
    PoiProvider,
    PoiType,
    classify_place_matches,
    score_place_candidate,
    validate_place_selection,
)
from tests.fixtures.place_matching import (
    GUANGZHOU,
    M_STAND_COASTAL,
    M_STAND_MIXC,
    SHENZHEN,
    SHENZHEN_MOCAUP,
    STARBUCKS_COCO,
    STARBUCKS_ONE_AVENUE,
    place_candidate,
    poi,
)

POLICY = Settings(_env_file=None, app_env="test").place_matching_policy()


def _request(
    *,
    candidate_title: str = "深圳当代艺术与城市规划馆",
    source_context: str | None = None,
    **candidate_fields: object,
) -> PlaceMatchRequest:
    candidate = place_candidate(title=candidate_title, **candidate_fields)  # type: ignore[arg-type]
    return PlaceMatchRequest(
        candidate=candidate,
        city=SHENZHEN,
        source_context=source_context,
    )


def _evidence(*, hard_conflict: bool = False) -> tuple[MatchEvidence, ...]:
    return tuple(
        MatchEvidence(
            field=field,
            outcome=(
                EvidenceOutcome.CONFLICT
                if hard_conflict and field is EvidenceField.CITY
                else EvidenceOutcome.MISSING
            ),
            reason=(
                EvidenceReason.OUTSIDE_SEARCH_SCOPE
                if hard_conflict and field is EvidenceField.CITY
                else EvidenceReason.SOURCE_MISSING
            ),
            score_delta=0.0,
            hard_conflict=hard_conflict and field is EvidenceField.CITY,
        )
        for field in EvidenceField
    )


def _scored(
    score: float,
    *,
    poi_id: str,
    provider_rank: int = 1,
    hard_conflict: bool = False,
) -> PlaceMatchCandidate:
    return PlaceMatchCandidate(
        provider=PoiProvider.AMAP,
        poi_id=poi_id,
        city_code="shenzhen",
        coordinate=SHENZHEN_MOCAUP.coordinate,
        name="测试地点",
        address="测试公开地址",
        poi_type=PoiType.OTHER,
        provider_rank=provider_rank,
        rank=1,
        score=score,
        confidence=MatchConfidence.LOW if hard_conflict else MatchConfidence.HIGH,
        evidence=_evidence(hard_conflict=hard_conflict),
    )


def _policy(**updates: float) -> PlaceMatchingPolicy:
    values = POLICY.model_dump()
    values.update(updates)
    return PlaceMatchingPolicy.model_validate(values)


def _by_field(candidate: PlaceMatchCandidate) -> dict[EvidenceField, MatchEvidence]:
    return {item.field: item for item in candidate.evidence}


def test_shenzhen_mocaup_is_a_unique_high_confidence_match() -> None:
    request = _request(
        district="福田区",
        address="福中路184号",
        business_district="市民中心",
        landmark="深圳市民中心",
        metro_station="少年宫地铁站",
        tags=("博物馆", "室内"),
        source_context=(
            "深圳当代艺术与城市规划馆在福中路184号，靠近深圳市民中心和"
            "少年宫地铁站，博物馆电话0755-12345678。"
        ),
    )
    scored = score_place_candidate(
        request=request,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )
    result = classify_place_matches((scored,), policy=POLICY)

    assert result.status is MatchStatus.MATCHED
    assert result.candidates[0].confidence is MatchConfidence.HIGH
    assert result.candidates[0].score >= POLICY.unique_match_score
    assert result.candidates[0].identity == (PoiProvider.AMAP, "sz_mocaup")
    assert result.candidates[0].city_code == "shenzhen"
    assert result.candidates[0].coordinate.coordinate_system.value == "gcj_02"


@pytest.mark.parametrize(
    ("title", "pois"),
    [
        ("M Stand咖啡", (M_STAND_COASTAL, M_STAND_MIXC)),
        (
            "星巴克咖啡",
            (
                poi(
                    poi_id="starbucks_a",
                    name="星巴克咖啡",
                    branch_name="COCO Park店",
                    poi_type=PoiType.CAFE,
                ),
                poi(
                    poi_id="starbucks_b",
                    name="星巴克咖啡",
                    branch_name="卓悦中心店",
                    poi_type=PoiType.CAFE,
                ),
            ),
        ),
    ],
)
def test_two_multi_branch_chains_remain_ambiguous(
    title: str,
    pois: tuple[object, ...],
) -> None:
    request = _request(
        candidate_title=title,
        tags=("咖啡",),
        source_context=f"想收藏{title}",
    )
    scored = tuple(
        score_place_candidate(
            request=request,
            poi=candidate_poi,  # type: ignore[arg-type]
            provider_rank=rank,
            policy=POLICY,
        )
        for rank, candidate_poi in enumerate(pois, start=1)
    )

    result = classify_place_matches(scored, policy=POLICY)

    assert result.status is MatchStatus.AMBIGUOUS
    assert all(candidate.confidence is MatchConfidence.MEDIUM for candidate in result.candidates)


def test_same_name_in_different_areas_prefers_the_supported_area() -> None:
    request = _request(
        candidate_title="同名书店",
        district="南山区",
        business_district="海岸城",
        address="文心五路海岸城",
        landmark="海岸城",
        tags=("书店",),
        source_context="南山区海岸城文心五路的同名书店",
    )
    nanshan = poi(
        poi_id="book_nanshan",
        name="同名书店",
        district="南山区",
        business_area="海岸城",
        address="南山区文心五路海岸城",
    )
    futian = poi(
        poi_id="book_futian",
        name="同名书店",
        district="福田区",
        business_area="中心区",
        address="福田区福华路",
    )
    scored = tuple(
        score_place_candidate(request=request, poi=item, provider_rank=rank, policy=POLICY)
        for rank, item in enumerate((futian, nanshan), start=1)
    )

    result = classify_place_matches(scored, policy=POLICY)

    assert result.status is MatchStatus.AMBIGUOUS
    assert result.candidates[0].poi_id == "book_nanshan"
    assert result.candidates[0].provider_rank == 2
    assert len(result.candidates) == 2
    assert all(not candidate.has_hard_conflict for candidate in result.candidates)


def test_matching_name_with_district_conflict_needs_context() -> None:
    request = _request(candidate_title="同名书店", district="南山区")
    conflict = poi(
        poi_id="book_wrong_district",
        name="同名书店",
        district="福田区",
    )
    scored = score_place_candidate(
        request=request,
        poi=conflict,
        provider_rank=1,
        policy=POLICY,
    )

    result = classify_place_matches((scored,), policy=POLICY)

    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert tuple(candidate.poi_id for candidate in result.candidates) == (
        "book_wrong_district",
    )
    district = _by_field(scored)[EvidenceField.DISTRICT]
    assert district.outcome is EvidenceOutcome.CONFLICT
    assert district.hard_conflict is False


def test_name_and_branch_fields_produce_match_and_conflict_evidence() -> None:
    supported_request = _request(
        candidate_title="M Stand咖啡万象天地店",
        source_context="M Stand万象天地店",
    )
    unsupported_request = _request(
        candidate_title="完全不同的地点海岸城店",
        source_context="完全不同的地点海岸城店",
    )

    supported = score_place_candidate(
        request=supported_request,
        poi=M_STAND_MIXC,
        provider_rank=1,
        policy=POLICY,
    )
    unsupported = score_place_candidate(
        request=unsupported_request,
        poi=M_STAND_MIXC,
        provider_rank=1,
        policy=POLICY,
    )

    assert _by_field(supported)[EvidenceField.NAME].outcome in {
        EvidenceOutcome.MATCH,
        EvidenceOutcome.PARTIAL_MATCH,
    }
    assert _by_field(supported)[EvidenceField.BRANCH_NAME].outcome is EvidenceOutcome.MATCH
    assert _by_field(unsupported)[EvidenceField.NAME].outcome is EvidenceOutcome.CONFLICT
    branch = _by_field(unsupported)[EvidenceField.BRANCH_NAME]
    assert branch.outcome is EvidenceOutcome.CONFLICT
    assert branch.hard_conflict is False


@pytest.mark.parametrize(
    ("title", "candidate_poi"),
    [
        ("M Stand咖啡店", M_STAND_COASTAL),
        (
            "诚品书店",
            poi(
                poi_id="eslite_coastal",
                name="诚品书店",
                branch_name="海岸城店",
            ),
        ),
        (
            "海底捞餐厅",
            poi(
                poi_id="haidilao_houhai",
                name="海底捞",
                branch_name="后海店",
                poi_type=PoiType.RESTAURANT,
            ),
        ),
    ],
)
def test_generic_business_names_are_not_specific_branch_conflicts(
    title: str,
    candidate_poi: object,
) -> None:
    scored = score_place_candidate(
        request=_request(candidate_title=title, source_context=f"想收藏{title}"),
        poi=candidate_poi,  # type: ignore[arg-type]
        provider_rank=1,
        policy=POLICY,
    )

    branch = _by_field(scored)[EvidenceField.BRANCH_NAME]
    assert branch.outcome is EvidenceOutcome.MISSING
    assert branch.hard_conflict is False


@pytest.mark.parametrize(
    ("generic_title", "specific_title", "expected_id", "other_id", "pois"),
    [
        (
            "M Stand咖啡店",
            "M Stand咖啡海岸城店",
            "mstand_coastal",
            "mstand_mixc",
            (M_STAND_COASTAL, M_STAND_MIXC),
        ),
        (
            "星巴克咖啡店",
            "星巴克COCO Park店",
            "starbucks_coco",
            "starbucks_one_avenue",
            (STARBUCKS_COCO, STARBUCKS_ONE_AVENUE),
        ),
    ],
)
def test_two_chains_distinguish_generic_correct_and_wrong_branch_names(
    generic_title: str,
    specific_title: str,
    expected_id: str,
    other_id: str,
    pois: tuple[object, ...],
) -> None:
    generic_request = _request(
        candidate_title=generic_title,
        tags=("咖啡",),
        source_context=f"想收藏{generic_title}",
    )
    generic_scores = tuple(
        score_place_candidate(
            request=generic_request,
            poi=candidate_poi,  # type: ignore[arg-type]
            provider_rank=rank,
            policy=POLICY,
        )
        for rank, candidate_poi in enumerate(pois, start=1)
    )

    generic_result = classify_place_matches(generic_scores, policy=POLICY)

    assert generic_result.status is MatchStatus.AMBIGUOUS
    assert len(generic_result.candidates) == 2
    assert all(
        _by_field(candidate)[EvidenceField.BRANCH_NAME].outcome
        is EvidenceOutcome.MISSING
        for candidate in generic_scores
    )

    specific_request = _request(
        candidate_title=specific_title,
        tags=("咖啡",),
        source_context=f"想收藏{specific_title}",
    )
    specific_scores = tuple(
        score_place_candidate(
            request=specific_request,
            poi=candidate_poi,  # type: ignore[arg-type]
            provider_rank=rank,
            policy=POLICY,
        )
        for rank, candidate_poi in enumerate(pois, start=1)
    )
    by_id = {candidate.poi_id: candidate for candidate in specific_scores}
    specific_result = classify_place_matches(specific_scores, policy=POLICY)

    assert _by_field(by_id[expected_id])[EvidenceField.BRANCH_NAME].outcome is EvidenceOutcome.MATCH
    wrong_branch = _by_field(by_id[other_id])[EvidenceField.BRANCH_NAME]
    assert wrong_branch.outcome is EvidenceOutcome.CONFLICT
    assert wrong_branch.hard_conflict is False
    assert specific_result.status is MatchStatus.AMBIGUOUS
    assert tuple(candidate.poi_id for candidate in specific_result.candidates) == (
        expected_id,
        other_id,
    )


@pytest.mark.parametrize(
    ("field", "positive", "negative"),
    [
        (EvidenceField.BUSINESS_AREA, "市民中心", "东门"),
        (EvidenceField.ADDRESS, "福中路184号", "建设路1号"),
        (EvidenceField.LANDMARK, "深圳市民中心", "世界之窗"),
        (EvidenceField.METRO_STATION, "少年宫地铁站", "老街地铁站"),
    ],
)
def test_structured_text_evidence_has_positive_and_negative_outcomes(
    field: EvidenceField,
    positive: str,
    negative: str,
) -> None:
    key = {
        EvidenceField.BUSINESS_AREA: "business_district",
        EvidenceField.ADDRESS: "address",
        EvidenceField.LANDMARK: "landmark",
        EvidenceField.METRO_STATION: "metro_station",
    }[field]
    positive_request = _request(**{key: positive})
    negative_request = _request(**{key: negative})

    positive_score = score_place_candidate(
        request=positive_request,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )
    negative_score = score_place_candidate(
        request=negative_request,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )

    assert _by_field(positive_score)[field].outcome in {
        EvidenceOutcome.MATCH,
        EvidenceOutcome.PARTIAL_MATCH,
    }
    assert _by_field(negative_score)[field].outcome is EvidenceOutcome.CONFLICT
    assert positive_score.score > negative_score.score


def test_phone_and_type_supply_positive_and_negative_evidence() -> None:
    positive = _request(
        tags=("博物馆",),
        source_context="博物馆联系电话 0755-12345678",
    )
    negative = _request(
        tags=("咖啡",),
        source_context="咖啡店联系电话 0755-87654321",
    )
    positive_score = score_place_candidate(
        request=positive,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )
    negative_score = score_place_candidate(
        request=negative,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )

    assert _by_field(positive_score)[EvidenceField.PHONE].outcome is EvidenceOutcome.MATCH
    assert _by_field(positive_score)[EvidenceField.POI_TYPE].outcome is EvidenceOutcome.MATCH
    assert _by_field(negative_score)[EvidenceField.PHONE].outcome is EvidenceOutcome.CONFLICT
    assert _by_field(negative_score)[EvidenceField.PHONE].hard_conflict is False
    assert _by_field(negative_score)[EvidenceField.POI_TYPE].outcome is EvidenceOutcome.CONFLICT


def test_name_only_single_result_needs_context() -> None:
    request = _request(candidate_title="M Stand咖啡")
    scored = score_place_candidate(
        request=request,
        poi=M_STAND_COASTAL,
        provider_rank=1,
        policy=POLICY,
    )

    result = classify_place_matches((scored,), policy=POLICY)

    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert result.candidates[0].score < POLICY.unique_match_score


def test_provider_rank_never_overrides_stronger_evidence() -> None:
    request = _request(
        candidate_title="M Stand咖啡万象天地店",
        district="南山区",
        business_district="高新园",
        address="深南大道万象天地",
        landmark="万象天地",
        metro_station="高新园地铁站",
        tags=("咖啡",),
        source_context=(
            "M Stand万象天地店在高新园地铁站，深南大道万象天地咖啡店，"
            "电话0755-11112222"
        ),
    )
    first = score_place_candidate(
        request=request,
        poi=M_STAND_COASTAL,
        provider_rank=1,
        policy=POLICY,
    )
    supported_second = M_STAND_MIXC.model_copy(
        update={
            "address": "深南大道万象天地 高新园地铁站",
            "phone": "0755-11112222",
        },
        deep=True,
    )
    second = score_place_candidate(
        request=request,
        poi=supported_second,
        provider_rank=2,
        policy=POLICY,
    )

    result = classify_place_matches((first, second), policy=POLICY)

    second_evidence = _by_field(second)
    assert second_evidence[EvidenceField.NAME].outcome is not EvidenceOutcome.MATCH
    assert second_evidence[EvidenceField.ADDRESS].outcome is not EvidenceOutcome.MATCH
    assert result.status is MatchStatus.MATCHED
    assert result.candidates[0].poi_id == "mstand_mixc"
    assert result.candidates[0].provider_rank == 2


def test_at_most_three_candidates_are_returned() -> None:
    candidates = tuple(
        _scored(60.0 - index, poi_id=f"poi_{index}", provider_rank=index)
        for index in range(1, 6)
    )

    result = classify_place_matches(candidates, policy=POLICY)

    assert result.status is MatchStatus.AMBIGUOUS
    assert tuple(item.poi_id for item in result.candidates) == ("poi_1", "poi_2", "poi_3")


def test_duplicate_provider_identity_is_rejected() -> None:
    duplicate = (_scored(60.0, poi_id="same"), _scored(50.0, poi_id="same", provider_rank=2))

    with pytest.raises(ValueError, match="duplicate"):
        classify_place_matches(duplicate, policy=POLICY)


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (0.0, MatchStatus.MATCHED),
        (-0.001, MatchStatus.NEEDS_CONTEXT),
        (0.001, MatchStatus.MATCHED),
    ],
)
def test_unique_score_threshold_boundaries(offset: float, expected: MatchStatus) -> None:
    candidate = _scored(POLICY.unique_match_score + offset, poi_id="threshold")

    result = classify_place_matches((candidate,), policy=POLICY)

    assert result.status is expected


@pytest.mark.parametrize(
    ("gap_offset", "expected"),
    [
        (0.0, MatchStatus.MATCHED),
        (-0.001, MatchStatus.AMBIGUOUS),
        (0.001, MatchStatus.MATCHED),
    ],
)
def test_minimum_score_gap_boundaries(gap_offset: float, expected: MatchStatus) -> None:
    top_score = 80.0
    second_score = top_score - POLICY.minimum_score_gap - gap_offset
    candidates = (
        _scored(top_score, poi_id="top", provider_rank=2),
        _scored(second_score, poi_id="second", provider_rank=1),
    )

    result = classify_place_matches(candidates, policy=POLICY)

    assert result.status is expected


def test_equal_scores_use_provider_rank_as_a_stable_tie_breaker_only() -> None:
    candidates = (
        _scored(60.0, poi_id="third", provider_rank=3),
        _scored(60.0, poi_id="first", provider_rank=1),
        _scored(60.0, poi_id="second", provider_rank=2),
    )

    first = classify_place_matches(candidates, policy=POLICY)
    second = classify_place_matches(tuple(reversed(candidates)), policy=POLICY)

    assert first == second
    assert first.status is MatchStatus.AMBIGUOUS
    assert tuple(item.poi_id for item in first.candidates) == ("first", "second", "third")


@pytest.mark.parametrize(
    "field",
    ["unique_match_score", "minimum_score_gap", "candidate_score"],
)
def test_direct_policy_construction_rejects_zero_safety_thresholds(field: str) -> None:
    values = POLICY.model_dump()
    values[field] = 0.0

    with pytest.raises(ValidationError):
        PlaceMatchingPolicy.model_validate(values)


def test_model_construct_cannot_bypass_zero_threshold_safety() -> None:
    unsafe = PlaceMatchingPolicy.model_construct(
        unique_match_score=0.0,
        minimum_score_gap=0.0,
        candidate_score=0.0,
        partial_match_factor=POLICY.partial_match_factor,
        weights=POLICY.weights,
    )
    equal = (
        _scored(0.0, poi_id="first", provider_rank=1),
        _scored(0.0, poi_id="second", provider_rank=2),
    )

    with pytest.raises(ValueError, match="policy thresholds"):
        classify_place_matches(equal, policy=unsafe)
    with pytest.raises(ValueError, match="policy thresholds"):
        score_place_candidate(
            request=_request(),
            poi=SHENZHEN_MOCAUP,
            provider_rank=1,
            policy=unsafe,
        )


def test_city_mismatch_is_a_hard_conflict_and_cannot_match() -> None:
    request = PlaceMatchRequest(candidate=place_candidate(title="广州塔"), city=SHENZHEN)
    guangzhou_poi = poi(
        poi_id="canton_tower",
        name="广州塔",
        city_code="guangzhou",
        poi_type=PoiType.ATTRACTION,
    )

    scored = score_place_candidate(
        request=request,
        poi=guangzhou_poi,
        provider_rank=1,
        policy=POLICY,
    )
    result = classify_place_matches((scored,), policy=POLICY)

    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert result.candidates == ()
    city = _by_field(scored)[EvidenceField.CITY]
    assert city.outcome is EvidenceOutcome.CONFLICT
    assert city.hard_conflict is True


def test_explicit_city_hint_conflicting_with_search_scope_cannot_auto_match() -> None:
    request = _request(
        candidate_title="深圳当代艺术与城市规划馆",
        city_hint="广州",
        district="福田区",
        address="福中路184号",
        business_district="市民中心",
        landmark="深圳市民中心",
        metro_station="少年宫地铁站",
        tags=("博物馆",),
        source_context="福中路184号的深圳当代艺术与城市规划馆，博物馆电话0755-12345678",
    )
    scored = score_place_candidate(
        request=request,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )

    result = classify_place_matches((scored,), policy=POLICY)

    assert scored.score >= POLICY.unique_match_score
    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert result.candidates == ()
    city = _by_field(scored)[EvidenceField.CITY]
    assert city.reason is EvidenceReason.CITY_HINT_CONFLICT
    assert city.hard_conflict is True


@pytest.mark.parametrize("city_hint", ["上海", "北京", "未知城市文本"])
def test_unresolved_non_empty_city_hint_blocks_automatic_matching(city_hint: str) -> None:
    request = _request(
        city_hint=city_hint,
        district="福田区",
        address="福中路184号",
        business_district="市民中心",
        landmark="深圳市民中心",
        metro_station="少年宫地铁站",
        tags=("博物馆",),
        source_context="福中路184号的深圳当代艺术与城市规划馆，电话0755-12345678",
    )
    scored = score_place_candidate(
        request=request,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )

    result = classify_place_matches((scored,), policy=POLICY)

    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert result.candidates == ()
    city = _by_field(scored)[EvidenceField.CITY]
    assert city.reason is EvidenceReason.CITY_HINT_UNRESOLVED
    assert city.hard_conflict is True


@pytest.mark.parametrize(
    ("city_hint", "city", "city_code", "district"),
    [
        ("深圳", SHENZHEN, "shenzhen", "福田区"),
        ("深圳市", SHENZHEN, "shenzhen", "福田区"),
        ("shenzhen", SHENZHEN, "shenzhen", "福田区"),
        ("广州", GUANGZHOU, "guangzhou", "越秀区"),
        ("广州市", GUANGZHOU, "guangzhou", "越秀区"),
        ("canton", GUANGZHOU, "guangzhou", "越秀区"),
    ],
)
def test_supported_city_aliases_match_the_correct_explicit_scope(
    city_hint: str,
    city: object,
    city_code: str,
    district: str,
) -> None:
    candidate_poi = poi(
        poi_id=f"museum_{city_code}",
        name="城市博物馆",
        city_code=city_code,
        district=district,
        business_area="中心区",
        address=f"{district}中心路1号 地标广场 中心地铁站",
        poi_type=PoiType.MUSEUM,
        phone="020-12345678" if city_code == "guangzhou" else "0755-12345678",
    )
    request = PlaceMatchRequest(
        candidate=place_candidate(
            title="城市博物馆",
            city_hint=city_hint,
            district=district,
            address=f"{district}中心路1号",
            business_district="中心区",
            landmark="地标广场",
            metro_station="中心地铁站",
            tags=("博物馆",),
        ),
        city=city,  # type: ignore[arg-type]
        source_context="城市博物馆在中心路1号，电话020-12345678"
        if city_code == "guangzhou"
        else "城市博物馆在中心路1号，电话0755-12345678",
    )
    scored = score_place_candidate(
        request=request,
        poi=candidate_poi,
        provider_rank=1,
        policy=POLICY,
    )

    result = classify_place_matches((scored,), policy=POLICY)

    assert result.status is MatchStatus.MATCHED
    assert _by_field(scored)[EvidenceField.CITY].reason is EvidenceReason.WITHIN_SEARCH_SCOPE


def test_supported_city_alias_conflicting_with_scope_is_hidden() -> None:
    request = PlaceMatchRequest(
        candidate=place_candidate(title="城市博物馆", city_hint="深圳市"),
        city=GUANGZHOU,
    )
    scored = score_place_candidate(
        request=request,
        poi=poi(
            poi_id="museum_guangzhou",
            name="城市博物馆",
            city_code="guangzhou",
        ),
        provider_rank=1,
        policy=POLICY,
    )

    result = classify_place_matches((scored,), policy=POLICY)

    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert result.candidates == ()
    assert _by_field(scored)[EvidenceField.CITY].reason is EvidenceReason.CITY_HINT_CONFLICT


def test_search_scope_is_not_positive_city_evidence() -> None:
    request = _request(candidate_title="深圳当代艺术与城市规划馆")
    scored = score_place_candidate(
        request=request,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )

    city = _by_field(scored)[EvidenceField.CITY]
    assert request.candidate.city_hint is None
    assert city.reason is EvidenceReason.WITHIN_SEARCH_SCOPE
    assert city.score_delta == 0
    assert scored.city_code == SHENZHEN_MOCAUP.city_code
    assert "search_scope_city" not in scored.model_dump()


def test_event_candidates_are_rejected_before_scoring() -> None:
    event = EventCandidate(
        kind=CollectionKind.EVENT,
        title="周末设计展",
        missing_fields=tuple(CandidateField),
    )
    request = PlaceMatchRequest(candidate=event, city=GUANGZHOU)

    with pytest.raises(TypeError, match="Event candidates"):
        score_place_candidate(
            request=request,
            poi=SHENZHEN_MOCAUP,
            provider_rank=1,
            policy=POLICY,
        )


def test_user_can_select_the_second_current_candidate() -> None:
    result = classify_place_matches(
        (
            _scored(60.0, poi_id="first", provider_rank=1),
            _scored(59.0, poi_id="second", provider_rank=2),
        ),
        policy=POLICY,
    )
    selection = PlaceSelection(
        kind=PlaceSelectionKind.CANDIDATE,
        provider=PoiProvider.AMAP,
        poi_id="second",
    )

    validated = validate_place_selection(result, selection)

    assert validated == selection
    assert validated is not selection


@pytest.mark.parametrize(
    "kind",
    [PlaceSelectionKind.NONE_OF_ABOVE, PlaceSelectionKind.ANY_BRANCH],
)
def test_non_candidate_choices_require_an_explicit_user_selection(
    kind: PlaceSelectionKind,
) -> None:
    result = classify_place_matches(
        (_scored(50.0, poi_id="candidate"),),
        policy=POLICY,
    )
    selection = PlaceSelection(kind=kind)

    assert validate_place_selection(result, selection).kind is kind
    assert all(not hasattr(candidate, "place_scope") for candidate in result.candidates)


def test_invalid_or_non_current_selection_is_rejected() -> None:
    result = classify_place_matches(
        (_scored(50.0, poi_id="current"),),
        policy=POLICY,
    )
    outsider = PlaceSelection(
        kind=PlaceSelectionKind.CANDIDATE,
        provider=PoiProvider.AMAP,
        poi_id="outsider",
    )

    with pytest.raises(ValueError, match="current candidates"):
        validate_place_selection(result, outsider)
    with pytest.raises(ValidationError):
        PlaceSelection(kind=PlaceSelectionKind.CANDIDATE)
    with pytest.raises(ValidationError):
        PlaceSelection(
            kind=PlaceSelectionKind.NONE_OF_ABOVE,
            provider=PoiProvider.AMAP,
            poi_id="current",
        )


@pytest.mark.parametrize(
    ("score", "hard_conflict", "visible"),
    [
        (0.0, False, True),
        (POLICY.candidate_score - 0.001, False, True),
        (POLICY.candidate_score, False, True),
        (POLICY.candidate_score + 0.001, False, True),
        (POLICY.candidate_score + 20.0, True, False),
    ],
)
def test_all_conflict_free_candidates_are_public_without_lowering_auto_thresholds(
    score: float,
    hard_conflict: bool,
    visible: bool,
) -> None:
    candidate = _scored(
        score,
        poi_id="quality_boundary",
        hard_conflict=hard_conflict,
    )

    result = classify_place_matches((candidate,), policy=POLICY)

    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert (len(result.candidates) == 1) is visible


def test_multiple_safe_low_score_candidates_remain_selectable() -> None:
    result = classify_place_matches(
        (
            _scored(0.0, poi_id="zero"),
            _scored(POLICY.candidate_score - 0.001, poi_id="low", provider_rank=2),
            _scored(90.0, poi_id="conflict", provider_rank=3, hard_conflict=True),
        ),
        policy=POLICY,
    )

    assert result.status is MatchStatus.AMBIGUOUS
    assert tuple(candidate.poi_id for candidate in result.candidates) == ("low", "zero")


def test_result_contract_only_allows_empty_candidates_for_safe_empty_outcomes() -> None:
    assert PlaceMatchResult(status=MatchStatus.NEEDS_CONTEXT).candidates == ()
    assert PlaceMatchResult(status=MatchStatus.NOT_FOUND).candidates == ()

    with pytest.raises(ValidationError, match="require candidates"):
        PlaceMatchResult(status=MatchStatus.MATCHED)
    with pytest.raises(ValidationError, match="require candidates"):
        PlaceMatchResult(status=MatchStatus.AMBIGUOUS)
    with pytest.raises(ValidationError, match="hard conflicts"):
        PlaceMatchResult(
            status=MatchStatus.NEEDS_CONTEXT,
            candidates=(
                _scored(90.0, poi_id="conflict", hard_conflict=True),
            ),
        )


def test_safe_low_quality_candidate_is_selectable_but_hard_conflict_is_hidden() -> None:
    result = classify_place_matches(
        (
            _scored(0.0, poi_id="zero"),
            _scored(90.0, poi_id="conflict", provider_rank=2, hard_conflict=True),
        ),
        policy=POLICY,
    )

    selected = validate_place_selection(
        result,
        PlaceSelection(
            kind=PlaceSelectionKind.CANDIDATE,
            provider=PoiProvider.AMAP,
            poi_id="zero",
        ),
    )
    assert selected.poi_id == "zero"
    with pytest.raises(ValueError, match="not a unique member"):
        validate_place_selection(
            result,
            PlaceSelection(
                kind=PlaceSelectionKind.CANDIDATE,
                provider=PoiProvider.AMAP,
                poi_id="conflict",
            ),
        )


def test_evidence_accepts_missing_optional_fields_and_normalizes_input_order() -> None:
    complete = _scored(50.0, poi_id="evidence")
    by_field = _by_field(complete)
    payload = complete.model_dump()
    payload["evidence"] = (
        by_field[EvidenceField.CITY],
        by_field[EvidenceField.NAME],
    )
    candidate = PlaceMatchCandidate.model_validate(payload)

    assert tuple(item.field for item in candidate.evidence) == (
        EvidenceField.NAME,
        EvidenceField.CITY,
    )
    with pytest.raises(ValidationError, match="unique"):
        PlaceMatchCandidate.model_validate(
            {
                **complete.model_dump(),
                "evidence": (
                    by_field[EvidenceField.NAME],
                    by_field[EvidenceField.NAME],
                    by_field[EvidenceField.CITY],
                ),
            }
        )


@pytest.mark.parametrize(
    "field_value",
    [nan, inf, -inf, -0.001, 100.001],
)
def test_illegal_scores_and_thresholds_are_rejected(field_value: float) -> None:
    with pytest.raises(ValidationError):
        _scored(field_value, poi_id="invalid")
    with pytest.raises(ValidationError):
        _policy(unique_match_score=field_value)


def test_input_objects_are_not_modified() -> None:
    request = _request(
        district="福田区",
        source_context="private context 0755-12345678",
    )
    before_request = request.model_copy(deep=True)
    before_poi = SHENZHEN_MOCAUP.model_copy(deep=True)

    score_place_candidate(
        request=request,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )

    assert request == before_request
    assert SHENZHEN_MOCAUP == before_poi


def test_private_context_and_phone_are_not_retained_in_results_or_repr() -> None:
    secret = "PRIVATE_CONTEXT_FAKE_KEY_123 0755-12345678"
    request = _request(source_context=secret)
    scored = score_place_candidate(
        request=request,
        poi=SHENZHEN_MOCAUP,
        provider_rank=1,
        policy=POLICY,
    )
    result = classify_place_matches((scored,), policy=POLICY)

    serialized = result.model_dump_json()
    assert secret not in repr(request)
    assert secret not in serialized
    assert "075512345678" not in serialized
    assert "phone" not in scored.model_dump()
    assert isinstance(request.source_context, SecretStr)

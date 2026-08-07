from __future__ import annotations

import pytest

from app.application import PlaceMatchingService
from app.config import Settings
from app.domain.places import (
    MatchStatus,
    PlaceMatchRequest,
    PoiSearchResult,
    PoiType,
    SearchPoiRequest,
)
from app.providers import StubMapProvider
from tests.fixtures.place_matching import SHENZHEN, place_candidate, poi


@pytest.mark.asyncio
async def test_explicit_venue_searches_once_and_selects_the_parent_poi() -> None:
    request = PlaceMatchRequest(
        candidate=place_candidate(
            title="深圳当代艺术与城市规划馆",
            city_hint="深圳",
            district="福田区",
            address="福田区福中路184号",
        ),
        city=SHENZHEN,
    )
    calls: list[object] = []

    async def record_call(value: object) -> None:
        calls.append(value)

    search = SearchPoiRequest(
        query=request.candidate.title,
        city=SHENZHEN,
        district="福田区",
    )
    candidates = tuple(
        poi(
            poi_id=poi_id,
            name=name,
            district="福田区",
            address="福中路184号(少年宫地铁站步行500米)",
            poi_type=poi_type,
        )
        for poi_id, name, poi_type in (
            ("venue", "深圳市当代艺术与城市规划馆", PoiType.MUSEUM),
            (
                "toilet",
                "深圳市当代艺术馆与城市规划馆无障碍卫生间",
                PoiType.OTHER,
            ),
            (
                "wall",
                "深圳市当代艺术与城市规划馆-西门几何外墙（打卡点）",
                PoiType.ATTRACTION,
            ),
        )
    )
    service = PlaceMatchingService(
        map_provider=StubMapProvider(
            search_results={
                search: PoiSearchResult(city_code="shenzhen", pois=candidates),
            },
            call_hook=record_call,
        ),
        policy=Settings(_env_file=None, app_env="test").place_matching_policy(),  # type: ignore[call-arg]
    )

    result = await service.match(request)

    assert calls == [search]
    assert result.status is MatchStatus.MATCHED
    assert result.candidates[0].poi_id == "venue"

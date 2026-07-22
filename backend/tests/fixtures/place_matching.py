"""Hand-written, provider-neutral M0-3C place matching fixtures."""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.collections import CandidateField, CollectionKind, PlaceCandidate
from app.domain.places import (
    CityScope,
    Coordinate,
    CoordinateSystem,
    Poi,
    PoiProvider,
    PoiSearchResult,
    PoiType,
    SearchPoiRequest,
)
from app.providers import StubMapProvider

SHENZHEN = CityScope(city_code="shenzhen")
GUANGZHOU = CityScope(city_code="guangzhou")


def place_candidate(
    *,
    title: str,
    city_hint: str | None = None,
    district: str | None = None,
    address: str | None = None,
    business_district: str | None = None,
    landmark: str | None = None,
    metro_station: str | None = None,
    tags: tuple[str, ...] = (),
) -> PlaceCandidate:
    values = {
        CandidateField.CITY_HINT: city_hint,
        CandidateField.DISTRICT: district,
        CandidateField.ADDRESS: address,
        CandidateField.BUSINESS_DISTRICT: business_district,
        CandidateField.LANDMARK: landmark,
        CandidateField.METRO_STATION: metro_station,
        CandidateField.TAGS: tags or None,
    }
    missing = tuple(field for field, value in values.items() if value is None)
    return PlaceCandidate(
        kind=CollectionKind.PLACE,
        title=title,
        city_hint=city_hint,
        district=district,
        address=address,
        business_district=business_district,
        landmark=landmark,
        metro_station=metro_station,
        tags=tags,
        missing_fields=(*missing, CandidateField.PRICE),
    )


def poi(
    *,
    poi_id: str,
    name: str,
    city_code: str = "shenzhen",
    branch_name: str | None = None,
    district: str | None = None,
    business_area: str | None = None,
    address: str = "测试公开地址",
    poi_type: PoiType = PoiType.OTHER,
    phone: str | None = None,
    latitude: float = 22.543096,
    longitude: float = 114.057865,
) -> Poi:
    return Poi(
        provider=PoiProvider.AMAP,
        poi_id=poi_id,
        name=name,
        branch_name=branch_name,
        city_code=city_code,
        district=district,
        business_area=business_area,
        address=address,
        coordinate=Coordinate(
            latitude=latitude,
            longitude=longitude,
            coordinate_system=CoordinateSystem.GCJ_02,
        ),
        poi_type=poi_type,
        phone=phone,
    )


SHENZHEN_MOCAUP = poi(
    poi_id="sz_mocaup",
    name="深圳当代艺术与城市规划馆",
    district="福田区",
    business_area="市民中心",
    address="福田区福中路184号 深圳市民中心附近 少年宫地铁站",
    poi_type=PoiType.MUSEUM,
    phone="0755-12345678",
)

M_STAND_COASTAL = poi(
    poi_id="mstand_coastal",
    name="M Stand咖啡",
    branch_name="海岸城店",
    district="南山区",
    business_area="后海",
    address="文心五路海岸城购物中心",
    poi_type=PoiType.CAFE,
)
M_STAND_MIXC = poi(
    poi_id="mstand_mixc",
    name="M Stand咖啡",
    branch_name="万象天地店",
    district="南山区",
    business_area="高新园",
    address="深南大道万象天地",
    poi_type=PoiType.CAFE,
)
STARBUCKS_COCO = poi(
    poi_id="starbucks_coco",
    name="星巴克",
    branch_name="COCO Park店",
    district="福田区",
    business_area="会展中心",
    address="福华三路COCO Park",
    poi_type=PoiType.CAFE,
)
STARBUCKS_ONE_AVENUE = poi(
    poi_id="starbucks_one_avenue",
    name="星巴克",
    branch_name="卓悦中心店",
    district="福田区",
    business_area="岗厦",
    address="福华一路卓悦中心",
    poi_type=PoiType.CAFE,
)


def stub_for_searches(
    values: Mapping[tuple[str, str], tuple[Poi, ...]],
) -> StubMapProvider:
    search_results = {
        SearchPoiRequest(query=query, city=CityScope(city_code=city_code)): PoiSearchResult(
            city_code=city_code,
            pois=pois,
        )
        for (city_code, query), pois in values.items()
    }
    return StubMapProvider(search_results=search_results)

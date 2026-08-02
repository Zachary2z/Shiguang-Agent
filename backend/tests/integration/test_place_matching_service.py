from __future__ import annotations

import asyncio
import socket
from collections.abc import Callable
from pathlib import Path

import pytest

from app.application import PlaceMatchingService
from app.config import Settings
from app.domain.collections import CandidateField, CollectionKind, EventCandidate
from app.domain.places import (
    CityScope,
    Coordinate,
    CoordinateSystem,
    GetPoiRequest,
    GetPoiResult,
    MatchStatus,
    PlaceMatchRequest,
    PoiSearchResult,
    PoiType,
    SearchPoiRequest,
)
from app.providers import MapProviderError, MapProviderErrorCode, StubMapProvider
from tests.fixtures.place_matching import (
    GUANGZHOU,
    M_STAND_COASTAL,
    M_STAND_MIXC,
    SHENZHEN,
    SHENZHEN_MOCAUP,
    place_candidate,
    poi,
)

POLICY = Settings(_env_file=None, app_env="test").place_matching_policy()


def _service(provider: StubMapProvider) -> PlaceMatchingService:
    return PlaceMatchingService(map_provider=provider, policy=POLICY)


def _directory_entries(path: Path) -> tuple[Path, ...]:
    return tuple(path.iterdir())


def _request(
    *,
    title: str,
    city: CityScope = SHENZHEN,
    source_context: str | None = None,
    **candidate_fields: object,
) -> PlaceMatchRequest:
    return PlaceMatchRequest(
        candidate=place_candidate(title=title, **candidate_fields),  # type: ignore[arg-type]
        city=city,
        source_context=source_context,
    )


def _unique_request() -> PlaceMatchRequest:
    return _request(
        title="深圳当代艺术与城市规划馆",
        district="福田区",
        address="福中路184号",
        business_district="市民中心",
        landmark="深圳市民中心",
        metro_station="少年宫地铁站",
        tags=("博物馆",),
        source_context=(
            "深圳当代艺术与城市规划馆位于福田区福中路184号，靠近深圳市民中心"
            "和少年宫地铁站，博物馆电话0755-12345678。"
        ),
    )


def _provider_for_request(
    request: PlaceMatchRequest,
    result: PoiSearchResult,
    *,
    call_hook: Callable[[object], object] | None = None,
) -> StubMapProvider:
    search_request = SearchPoiRequest(
        query=request.candidate.title,
        city=request.city,
        district=request.candidate.district,
    )
    return StubMapProvider(
        search_results={search_request: result},
        call_hook=call_hook,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_service_returns_unique_high_confidence_match() -> None:
    request = _unique_request()
    provider = _provider_for_request(
        request,
        PoiSearchResult(city_code="shenzhen", pois=(SHENZHEN_MOCAUP,)),
    )

    result = await _service(provider).match(request)

    assert result.status is MatchStatus.MATCHED
    assert len(result.candidates) == 1
    assert result.candidates[0].provider.value == "amap"
    assert result.candidates[0].poi_id == "sz_mocaup"
    assert result.candidates[0].city_code == "shenzhen"
    assert result.candidates[0].coordinate.coordinate_system is CoordinateSystem.GCJ_02


@pytest.mark.asyncio
async def test_official_amap_link_resolves_exact_identity_without_search() -> None:
    request = GetPoiRequest(poi_id=SHENZHEN_MOCAUP.poi_id)
    calls: list[object] = []

    async def record_call(value: object) -> None:
        calls.append(value)

    provider = StubMapProvider(
        poi_results={request: GetPoiResult(poi=SHENZHEN_MOCAUP)},
        call_hook=record_call,  # type: ignore[arg-type]
    )

    result = await _service(provider).match_official_amap_link(
        f"https://www.amap.com/place/{SHENZHEN_MOCAUP.poi_id}",
    )

    assert result.status is MatchStatus.MATCHED
    assert tuple(candidate.poi_id for candidate in result.candidates) == (
        SHENZHEN_MOCAUP.poi_id,
    )
    assert calls == [request]


@pytest.mark.asyncio
async def test_official_amap_link_propagates_get_poi_cancellation() -> None:
    async def cancel(_: object) -> None:
        raise asyncio.CancelledError("cancel official POI resolution")

    provider = StubMapProvider(call_hook=cancel)  # type: ignore[arg-type]

    with pytest.raises(asyncio.CancelledError, match="cancel official"):
        await _service(provider).match_official_amap_link(
            "https://www.amap.com/place/B0SZ000001",
        )


@pytest.mark.asyncio
async def test_official_amap_link_rejects_unsupported_city_without_relabeling() -> None:
    unsupported = SHENZHEN_MOCAUP.model_copy(update={"city_code": "shanghai"})
    request = GetPoiRequest(poi_id=unsupported.poi_id)
    provider = StubMapProvider(
        poi_results={request: GetPoiResult(poi=unsupported)},
    )

    with pytest.raises(MapProviderError) as exc_info:
        await _service(provider).match_official_amap_link(
            f"https://www.amap.com/place/{unsupported.poi_id}"
        )

    assert exc_info.value.code is MapProviderErrorCode.UNSUPPORTED_CITY
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_exact_name_district_and_public_address_meet_default_reliability() -> None:
    request = _request(
        title="深圳当代艺术与城市规划馆",
        city_hint="深圳",
        district="福田区",
        address="福中路184号",
    )
    provider = _provider_for_request(
        request,
        PoiSearchResult(
            city_code="shenzhen",
            pois=(
                poi(
                    poi_id="exact_public_address",
                    name="深圳当代艺术与城市规划馆",
                    district="福田区",
                    address="福中路184号",
                    poi_type=PoiType.MUSEUM,
                ),
            ),
        ),
    )

    result = await _service(provider).match(request)

    assert result.status is MatchStatus.MATCHED
    assert len(result.candidates) == 1
    assert result.candidates[0].score >= POLICY.unique_match_score


@pytest.mark.asyncio
async def test_name_and_city_start_search_without_auto_confirming_weak_evidence() -> None:
    calls: list[object] = []

    async def record_call(request: object) -> None:
        calls.append(request)

    request = _request(
        title="深圳莲花山公园",
        city_hint="深圳",
    )
    park = poi(
        poi_id="lianhuashan",
        name="深圳莲花山公园",
        poi_type=PoiType.PARK,
    )
    provider = _provider_for_request(
        request,
        PoiSearchResult(city_code="shenzhen", pois=(park,)),
        call_hook=record_call,
    )

    result = await _service(provider).match(request)

    assert len(calls) == 1
    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert tuple(candidate.poi_id for candidate in result.candidates) == ("lianhuashan",)


@pytest.mark.asyncio
async def test_empty_provider_result_becomes_not_found() -> None:
    request = _request(title="地图未收录地点")

    result = await _service(StubMapProvider()).match(request)

    assert result.status is MatchStatus.NOT_FOUND
    assert result.candidates == ()


@pytest.mark.asyncio
async def test_close_chain_candidates_are_ambiguous() -> None:
    request = _request(
        title="M Stand咖啡",
        tags=("咖啡",),
        source_context="想收藏M Stand咖啡",
    )
    provider = _provider_for_request(
        request,
        PoiSearchResult(
            city_code="shenzhen",
            pois=(M_STAND_COASTAL, M_STAND_MIXC),
        ),
    )

    result = await _service(provider).match(request)

    assert result.status is MatchStatus.AMBIGUOUS
    assert tuple(candidate.provider_rank for candidate in result.candidates) == (1, 2)


@pytest.mark.asyncio
async def test_generic_chain_business_name_remains_a_selectable_ambiguity() -> None:
    request = _request(
        title="M Stand咖啡店",
        tags=("咖啡",),
        source_context="想收藏M Stand咖啡店",
    )
    provider = _provider_for_request(
        request,
        PoiSearchResult(
            city_code="shenzhen",
            pois=(M_STAND_COASTAL, M_STAND_MIXC),
        ),
    )

    result = await _service(provider).match(request)

    assert result.status is MatchStatus.AMBIGUOUS
    assert tuple(candidate.poi_id for candidate in result.candidates) == (
        "mstand_coastal",
        "mstand_mixc",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("city_hint", ["上海", "北京", "未知城市文本"])
async def test_unresolved_city_hint_cannot_bind_search_scope_poi(city_hint: str) -> None:
    original = _unique_request()
    request = original.model_copy(
        update={
            "candidate": original.candidate.model_copy(update={"city_hint": city_hint})
        },
        deep=True,
    )
    provider = _provider_for_request(
        request,
        PoiSearchResult(city_code="shenzhen", pois=(SHENZHEN_MOCAUP,)),
    )

    result = await _service(provider).match(request)

    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert result.candidates == ()


@pytest.mark.asyncio
async def test_provider_pois_without_reliable_candidates_become_empty_needs_context() -> None:
    request = _request(title="完全不同的名称")
    provider = _provider_for_request(
        request,
        PoiSearchResult(city_code="shenzhen", pois=(SHENZHEN_MOCAUP,)),
    )

    result = await _service(provider).match(request)

    assert result.status is MatchStatus.NEEDS_CONTEXT
    assert result.candidates == ()


@pytest.mark.asyncio
async def test_service_never_returns_more_than_three_candidates() -> None:
    request = _request(title="连锁咖啡", tags=("咖啡",), source_context="连锁咖啡")
    pois = tuple(
        poi(
            poi_id=f"chain_{index}",
            name="连锁咖啡",
            branch_name=f"第{index}店",
            poi_type=PoiType.CAFE,
        )
        for index in range(1, 7)
    )
    provider = _provider_for_request(
        request,
        PoiSearchResult(city_code="shenzhen", pois=pois),
    )

    result = await _service(provider).match(request)

    assert len(result.candidates) == 3
    assert tuple(item.rank for item in result.candidates) == (1, 2, 3)


@pytest.mark.asyncio
async def test_event_candidate_never_calls_map_provider() -> None:
    calls = 0

    async def count_call(_: object) -> None:
        nonlocal calls
        calls += 1

    event = EventCandidate(
        kind=CollectionKind.EVENT,
        title="广州设计展",
        missing_fields=tuple(CandidateField),
    )
    request = PlaceMatchRequest(candidate=event, city=GUANGZHOU)
    service = _service(StubMapProvider(call_hook=count_call))

    with pytest.raises(TypeError, match="Event candidates"):
        await service.match(request)
    assert calls == 0


class _RaisingSearchProvider(StubMapProvider):
    def __init__(self, error: MapProviderError) -> None:
        super().__init__()
        self.error = error

    async def search_poi(self, request: SearchPoiRequest) -> PoiSearchResult:
        del request
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize("code", tuple(MapProviderErrorCode))
async def test_all_safe_map_provider_errors_propagate_unchanged(
    code: MapProviderErrorCode,
) -> None:
    error = MapProviderError(code=code)
    service = _service(_RaisingSearchProvider(error))

    with pytest.raises(MapProviderError) as raised:
        await service.match(_request(title="测试地点"))

    assert raised.value is error
    assert raised.value.code is code


class _FixedResultProvider(StubMapProvider):
    def __init__(self, result: object) -> None:
        super().__init__()
        self.result = result

    async def search_poi(self, request: SearchPoiRequest) -> PoiSearchResult:
        del request
        return self.result  # type: ignore[return-value]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_result",
    [
        PoiSearchResult(
            city_code="guangzhou",
            pois=(
                poi(
                    poi_id="wrong_city",
                    name="测试地点",
                    city_code="guangzhou",
                ),
            ),
        ),
        PoiSearchResult.model_construct(
            city_code="shenzhen",
            pois=(SHENZHEN_MOCAUP, SHENZHEN_MOCAUP),
        ),
        PoiSearchResult.model_construct(
            city_code="shenzhen",
            pois=({"raw": "RAW_SUPPLIER_PAYLOAD_FAKE_SECRET"},),
        ),
        PoiSearchResult(
            city_code="shenzhen",
            pois=(
                SHENZHEN_MOCAUP.model_copy(
                    update={
                        "coordinate": Coordinate(
                            latitude=22.54,
                            longitude=114.05,
                            coordinate_system=CoordinateSystem.WGS_84,
                        )
                    }
                ),
            ),
        ),
        {"raw_provider_response": "RAW_SUPPLIER_PAYLOAD_FAKE_SECRET"},
    ],
)
async def test_invalid_provider_results_are_rejected_with_a_fixed_safe_error(
    invalid_result: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service(_FixedResultProvider(invalid_result))

    with pytest.raises(MapProviderError) as raised:
        await service.match(
            _request(
                title="测试地点",
                source_context="PRIVATE_SOURCE_CONTEXT_FAKE_SECRET",
            )
        )

    assert raised.value.code is MapProviderErrorCode.INVALID_RESPONSE
    public = str(raised.value) + repr(raised.value) + str(raised.value.to_public_dict())
    assert "RAW_SUPPLIER_PAYLOAD_FAKE_SECRET" not in public
    assert "PRIVATE_SOURCE_CONTEXT_FAKE_SECRET" not in public
    assert "FAKE_SECRET" not in caplog.text


@pytest.mark.asyncio
async def test_shenzhen_and_guangzhou_sequential_and_concurrent_calls_do_not_leak_city() -> None:
    shenzhen_poi = poi(
        poi_id="city_museum_sz",
        name="城市博物馆",
        city_code="shenzhen",
        district="福田区",
        poi_type=PoiType.MUSEUM,
    )
    guangzhou_poi = poi(
        poi_id="city_museum_gz",
        name="城市博物馆",
        city_code="guangzhou",
        district="越秀区",
        poi_type=PoiType.MUSEUM,
    )
    shenzhen_request = _request(title="城市博物馆", city=SHENZHEN, tags=("博物馆",))
    guangzhou_request = _request(title="城市博物馆", city=GUANGZHOU, tags=("博物馆",))
    provider = StubMapProvider(
        search_results={
            SearchPoiRequest(query="城市博物馆", city=SHENZHEN): PoiSearchResult(
                city_code="shenzhen",
                pois=(shenzhen_poi,),
            ),
            SearchPoiRequest(query="城市博物馆", city=GUANGZHOU): PoiSearchResult(
                city_code="guangzhou",
                pois=(guangzhou_poi,),
            ),
        }
    )
    service = _service(provider)

    sequential = (
        await service.match(shenzhen_request),
        await service.match(guangzhou_request),
        await service.match(shenzhen_request),
    )
    concurrent = await asyncio.gather(
        *(
            service.match(shenzhen_request if index % 2 == 0 else guangzhou_request)
            for index in range(40)
        )
    )

    assert [result.candidates[0].city_code for result in sequential] == [
        "shenzhen",
        "guangzhou",
        "shenzhen",
    ]
    assert all(
        result.candidates[0].city_code == ("shenzhen" if index % 2 == 0 else "guangzhou")
        for index, result in enumerate(concurrent)
    )


@pytest.mark.asyncio
async def test_repeated_calls_are_equal_and_inputs_remain_unchanged() -> None:
    request = _unique_request()
    request_before = request.model_copy(deep=True)
    poi_before = SHENZHEN_MOCAUP.model_copy(deep=True)
    service = _service(
        _provider_for_request(
            request,
            PoiSearchResult(city_code="shenzhen", pois=(SHENZHEN_MOCAUP,)),
        )
    )

    first = await service.match(request)
    second = await service.match(request)

    assert first == second
    assert first is not second
    assert request == request_before
    assert SHENZHEN_MOCAUP == poi_before


@pytest.mark.asyncio
async def test_cancellation_propagates_from_active_provider_call() -> None:
    started = asyncio.Event()

    async def wait_forever(_: object) -> None:
        started.set()
        await asyncio.Event().wait()

    request = _request(title="取消测试")
    service = _service(
        _provider_for_request(
            request,
            PoiSearchResult(city_code="shenzhen", pois=(SHENZHEN_MOCAUP,)),
            call_hook=wait_forever,
        )
    )
    task = asyncio.create_task(service.match(request))
    await started.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_offline_service_has_no_database_file_message_or_network_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def blocked(*_: object, **__: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    before = _directory_entries(tmp_path)
    request = _unique_request()
    service = _service(
        _provider_for_request(
            request,
            PoiSearchResult(city_code="shenzhen", pois=(SHENZHEN_MOCAUP,)),
        )
    )

    result = await service.match(request)

    assert result.status is MatchStatus.MATCHED
    assert _directory_entries(tmp_path) == before

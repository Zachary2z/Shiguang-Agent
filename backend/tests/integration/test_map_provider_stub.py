"""State isolation, cancellation, injection, and safety tests for the map stub."""

from __future__ import annotations

import asyncio
import logging

import pytest

from app.domain.places import CityScope, NavigationRequest, PoiSearchResult, SearchPoiRequest
from app.providers import MapProviderError, MapProviderErrorCode, StubMapProvider
from tests.fixtures.maps import (
    GZ_NAVIGATION,
    GZ_UNIQUE_SEARCH,
    SZ_NAVIGATION,
    SZ_UNIQUE_SEARCH,
    TIMEOUT_SEARCH,
    make_stub_map_provider,
)

FAKE_SECRET = "fake-map-secret-must-not-leak"
FAKE_RAW_RESPONSE = "fake-provider-raw-response-must-not-leak"


@pytest.mark.asyncio
async def test_same_input_is_stable_and_returns_independent_snapshots() -> None:
    provider = make_stub_map_provider()

    first = await provider.search_poi(SZ_UNIQUE_SEARCH)
    second = await provider.search_poi(SZ_UNIQUE_SEARCH)

    assert first == second
    assert first is not second
    assert first.pois[0] is not second.pois[0]


@pytest.mark.parametrize("navigation_request", [SZ_NAVIGATION, GZ_NAVIGATION])
@pytest.mark.asyncio
async def test_stub_generated_navigation_uri_is_valid_stable_and_input_safe(
    navigation_request: NavigationRequest,
) -> None:
    request_before = navigation_request.model_dump()
    provider = StubMapProvider()

    first = await provider.build_navigation_uri(navigation_request)
    second = await provider.build_navigation_uri(navigation_request)

    assert navigation_request.model_dump() == request_before
    assert first == second
    assert first is not second
    assert first.uri.startswith("geo:")


@pytest.mark.asyncio
async def test_stub_does_not_modify_request_or_caller_fixture_mapping() -> None:
    request = SearchPoiRequest(query="no configured result", city=CityScope(city_code="shenzhen"))
    request_before = request.model_dump()
    fixtures: dict[SearchPoiRequest, PoiSearchResult] = {}
    provider = StubMapProvider(search_results=fixtures)

    result = await provider.search_poi(request)
    fixtures[SZ_UNIQUE_SEARCH] = PoiSearchResult(city_code="shenzhen")

    assert request.model_dump() == request_before
    assert result.pois == ()
    assert (await provider.search_poi(SZ_UNIQUE_SEARCH)).pois == ()


@pytest.mark.asyncio
async def test_sequential_interleaved_and_concurrent_cities_never_cross_contaminate() -> None:
    provider = make_stub_map_provider()

    sequential = [
        await provider.search_poi(SZ_UNIQUE_SEARCH),
        await provider.search_poi(GZ_UNIQUE_SEARCH),
        await provider.search_poi(SZ_UNIQUE_SEARCH),
        await provider.search_poi(GZ_UNIQUE_SEARCH),
    ]
    concurrent = await asyncio.gather(
        *(provider.search_poi(request) for request in (SZ_UNIQUE_SEARCH, GZ_UNIQUE_SEARCH) * 20)
    )

    assert [item.city_code for item in sequential] == [
        "shenzhen",
        "guangzhou",
        "shenzhen",
        "guangzhou",
    ]
    assert [item.city_code for item in concurrent] == [
        city for _ in range(20) for city in ("shenzhen", "guangzhou")
    ]
    assert all(poi.city_code == result.city_code for result in concurrent for poi in result.pois)


@pytest.mark.asyncio
async def test_cancelled_error_propagates_without_becoming_provider_failure() -> None:
    entered = asyncio.Event()
    wait_forever = asyncio.Event()

    async def cancellable_hook(request: object) -> None:
        del request
        entered.set()
        await wait_forever.wait()

    provider = StubMapProvider(call_hook=cancellable_hook)
    task = asyncio.create_task(provider.search_poi(SZ_UNIQUE_SEARCH))
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_hook_failure_is_reduced_to_fixed_safe_error() -> None:
    async def unsafe_hook(request: object) -> None:
        del request
        raise RuntimeError(f"{FAKE_SECRET} {FAKE_RAW_RESPONSE}")

    provider = StubMapProvider(call_hook=unsafe_hook)
    with pytest.raises(MapProviderError) as error:
        await provider.search_poi(SZ_UNIQUE_SEARCH)

    assert error.value.code is MapProviderErrorCode.UNAVAILABLE
    assert error.value.__context__ is None
    public_text = str(error.value.to_public_dict()) + repr(error.value)
    assert FAKE_SECRET not in public_text
    assert FAKE_RAW_RESPONSE not in public_text


@pytest.mark.asyncio
async def test_timeout_error_repr_public_data_and_logs_are_secret_free(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_request = SearchPoiRequest(
        query=FAKE_SECRET,
        city=CityScope(city_code="shenzhen"),
    )
    provider = StubMapProvider(timeout_requests=(secret_request, TIMEOUT_SEARCH))

    with caplog.at_level(logging.INFO), pytest.raises(MapProviderError) as error:
        await provider.search_poi(secret_request)
        logging.getLogger("test").info("unreachable")

    public_text = repr(secret_request) + repr(error.value) + str(error.value.to_public_dict())
    assert FAKE_SECRET not in public_text
    assert FAKE_RAW_RESPONSE not in public_text
    assert FAKE_SECRET not in caplog.text
    assert FAKE_RAW_RESPONSE not in caplog.text


@pytest.mark.asyncio
async def test_city_words_in_query_never_override_the_explicit_scope() -> None:
    provider = make_stub_map_provider()
    request = SearchPoiRequest(
        query="广州 广东省博物馆",
        city=CityScope(city_code="shenzhen"),
    )

    result = await provider.search_poi(request)

    assert result.city_code == "shenzhen"
    assert result.pois == ()

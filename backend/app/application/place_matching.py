"""The single application workflow that orchestrates provider-neutral POI matching."""

from __future__ import annotations

from app.domain.collections.extraction import PlaceCandidate
from app.domain.places.contracts import (
    Coordinate,
    CoordinateSystem,
    Poi,
    PoiSearchResult,
    SearchPoiRequest,
)
from app.domain.places.matching import (
    PlaceMatchingPolicy,
    PlaceMatchRequest,
    PlaceMatchResult,
    classify_place_matches,
    score_place_candidate,
)
from app.providers.map import MapProvider, MapProviderError, MapProviderErrorCode


class PlaceMatchingService:
    """Search once through the injected MapProvider, then apply pure domain rules."""

    def __init__(self, *, map_provider: MapProvider, policy: PlaceMatchingPolicy) -> None:
        self._map_provider = map_provider
        self._policy = policy.model_copy(deep=True)

    async def match(self, request: PlaceMatchRequest) -> PlaceMatchResult:
        """Match one Place candidate within the explicit request-local city scope."""

        if not isinstance(request.candidate, PlaceCandidate):
            raise TypeError("Event candidates cannot enter POI matching")

        provider_result = await self._map_provider.search_poi(
            SearchPoiRequest(
                query=request.candidate.title,
                city=request.city.model_copy(deep=True),
                district=request.search_district or request.candidate.district,
                location=(
                    None
                    if request.search_location is None
                    else request.search_location.model_copy(deep=True)
                ),
            )
        )
        search_result = self._validated_provider_result(
            request=request,
            result=provider_result,
        )
        scored = tuple(
            score_place_candidate(
                request=request,
                poi=poi,
                provider_rank=provider_rank,
                policy=self._policy,
            )
            for provider_rank, poi in enumerate(search_result.pois, start=1)
        )
        return classify_place_matches(scored, policy=self._policy)

    @staticmethod
    def _validated_provider_result(
        *,
        request: PlaceMatchRequest,
        result: object,
    ) -> PoiSearchResult:
        validated: PoiSearchResult | None = None
        if isinstance(result, PoiSearchResult):
            try:
                # Rebuild from the public internal fields so even a test double that used
                # ``model_construct`` cannot bypass validation or retain extra payloads.
                pois = tuple(
                    Poi(
                        provider=poi.provider,
                        poi_id=poi.poi_id,
                        name=poi.name,
                        branch_name=poi.branch_name,
                        city_code=poi.city_code,
                        district=poi.district,
                        business_area=poi.business_area,
                        address=poi.address,
                        coordinate=Coordinate(
                            latitude=poi.coordinate.latitude,
                            longitude=poi.coordinate.longitude,
                            coordinate_system=poi.coordinate.coordinate_system,
                        ),
                        poi_type=poi.poi_type,
                        phone=poi.phone,
                        opening_hours_summary=poi.opening_hours_summary,
                    )
                    for poi in result.pois
                )
                validated = PoiSearchResult(city_code=result.city_code, pois=pois)
            except Exception:
                validated = None
        if validated is None:
            raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
        identities = tuple((poi.provider, poi.poi_id) for poi in validated.pois)
        invalid = (
            validated.city_code != request.city.city_code
            or len(set(identities)) != len(identities)
            or any(
                poi.city_code != request.city.city_code
                or poi.coordinate.coordinate_system is not CoordinateSystem.GCJ_02
                for poi in validated.pois
            )
        )
        if invalid:
            raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
        return validated

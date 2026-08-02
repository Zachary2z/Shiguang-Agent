"""The single application workflow that orchestrates provider-neutral POI matching."""

from __future__ import annotations

from app.domain.collections.extraction import PlaceCandidate
from app.domain.places.contracts import (
    Coordinate,
    CoordinateSystem,
    GetPoiRequest,
    GetPoiResult,
    Poi,
    PoiProvider,
    PoiSearchResult,
    SearchPoiRequest,
)
from app.domain.places.links import inspect_amap_official_link
from app.domain.places.matching import (
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
    classify_place_matches,
    resolve_city_hint,
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

    async def match_official_amap_link(
        self,
        url: str,
    ) -> PlaceMatchResult:
        """Resolve one explicit official identity through the same MapProvider boundary."""

        link = inspect_amap_official_link(url)
        if not link.is_official or link.poi_id is None:
            raise MapProviderError(code=MapProviderErrorCode.INVALID_REQUEST)
        result = await self._map_provider.get_poi(
            GetPoiRequest(poi_id=link.poi_id)
        )
        poi = self._validated_provider_poi(
            result=result,
            poi_id=link.poi_id,
        )
        evidence = (
            MatchEvidence(
                field=EvidenceField.NAME,
                outcome=EvidenceOutcome.MISSING,
                reason=EvidenceReason.SOURCE_MISSING,
                score_delta=0.0,
            ),
            MatchEvidence(
                field=EvidenceField.CITY,
                outcome=EvidenceOutcome.MATCH,
                reason=EvidenceReason.WITHIN_SEARCH_SCOPE,
                score_delta=0.0,
            ),
        )
        candidate = PlaceMatchCandidate(
            provider=poi.provider,
            poi_id=poi.poi_id,
            city_code=poi.city_code,
            coordinate=poi.coordinate.model_copy(deep=True),
            name=poi.name,
            branch_name=poi.branch_name,
            district=poi.district,
            business_area=poi.business_area,
            address=poi.address,
            poi_type=poi.poi_type,
            opening_hours_summary=poi.opening_hours_summary,
            provider_rank=1,
            rank=1,
            score=100.0,
            confidence=MatchConfidence.HIGH,
            evidence=evidence,
        )
        return PlaceMatchResult(status=MatchStatus.MATCHED, candidates=(candidate,))

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
                    PlaceMatchingService._copy_provider_poi(poi) for poi in result.pois
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

    @staticmethod
    def _validated_provider_poi(
        *,
        result: object,
        poi_id: str,
    ) -> Poi:
        validated: Poi | None = None
        if isinstance(result, GetPoiResult):
            try:
                validated = PlaceMatchingService._copy_provider_poi(result.poi)
            except Exception:
                validated = None
        if (
            validated is None
            or validated.provider is not PoiProvider.AMAP
            or validated.poi_id != poi_id
            or validated.coordinate.coordinate_system is not CoordinateSystem.GCJ_02
        ):
            raise MapProviderError(code=MapProviderErrorCode.INVALID_RESPONSE)
        _, supported_city = resolve_city_hint(validated.city_code)
        if supported_city != validated.city_code:
            raise MapProviderError(code=MapProviderErrorCode.UNSUPPORTED_CITY)
        return validated

    @staticmethod
    def _copy_provider_poi(source: Poi) -> Poi:
        """Rebuild one provider DTO through the sole public internal POI contract."""

        return Poi(
            provider=source.provider,
            poi_id=source.poi_id,
            name=source.name,
            branch_name=source.branch_name,
            city_code=source.city_code,
            district=source.district,
            business_area=source.business_area,
            address=source.address,
            coordinate=Coordinate(
                latitude=source.coordinate.latitude,
                longitude=source.coordinate.longitude,
                coordinate_system=source.coordinate.coordinate_system,
            ),
            poi_type=source.poi_type,
            phone=source.phone,
            opening_hours_summary=source.opening_hours_summary,
        )

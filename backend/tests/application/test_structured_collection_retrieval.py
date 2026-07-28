"""Offline M0-5B structured retrieval, hard-rule, and branch-resolution tests."""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config

from app.application import (
    PlaceMatchingService,
    PlanDraftService,
    StructuredCollectionRetrievalError,
    StructuredCollectionRetrievalService,
)
from app.application.map_plan_facts import (
    MAX_PLAN_FACT_CANDIDATES,
    MAX_PLAN_ROUTE_CALLS,
    MapPlanFactResolver,
)
from app.config import Settings
from app.domain.collections import (
    CollectionItem,
    CollectionKind,
    CollectionStatus,
    PlanCity,
    User,
    UserMode,
)
from app.domain.identifiers import generate_collection_item_id, generate_user_id
from app.domain.places import (
    BrandIdentityConfirmationSource,
    CityScope,
    ConfirmedBrandIdentity,
    Coordinate,
    CoordinateSystem,
    EvidenceField,
    EvidenceOutcome,
    EvidenceReason,
    MatchConfidence,
    MatchEvidence,
    MatchStatus,
    PlaceConfirmationSource,
    PlaceMatchingPolicy,
    PlaceScope,
    PlaceTarget,
    Poi,
    PoiProvider,
    PoiSearchResult,
    PoiType,
    RouteRequest,
    RouteResult,
    SearchPoiRequest,
    TransportMode,
    WeatherRequest,
    WeatherResult,
    normalize_brand_name,
)
from app.domain.plans import ActivityArea, PlanConstraints
from app.domain.plans.drafts import (
    DraftCandidateFacts,
    DraftRouteFacts,
    PlanDraftFactSnapshot,
    PlanDraftOutcome,
    PlanRiskCode,
)
from app.domain.plans.retrieval import (
    AvailabilityAssessment,
    CandidateOutcome,
    CandidateReasonCode,
    CollectionPlanningFacts,
    PlanningFactSnapshot,
    PoiPlanningFacts,
    RouteAssessment,
    WeatherAssessment,
)
from app.infrastructure.db import Database
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.providers import StubMapProvider
from app.providers.map import MapProviderErrorCode

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 23, 6, 0, tzinfo=UTC)
START = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
END = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
SHENZHEN_COORDINATE = Coordinate(
    latitude=22.541174,
    longitude=114.057701,
    coordinate_system=CoordinateSystem.GCJ_02,
)
ORIGIN = Coordinate(
    latitude=22.533100,
    longitude=113.930400,
    coordinate_system=CoordinateSystem.GCJ_02,
)
DEFAULT_AREA = ActivityArea(districts=("福田区",))


class ReadOnlyRepository:
    def __init__(self, items: list[CollectionItem]) -> None:
        self.items = copy.deepcopy(items)
        self.calls: list[tuple[str, bool]] = []

    async def list_collection_items(
        self,
        *,
        user_id: str,
        include_inactive: bool = False,
    ) -> list[CollectionItem]:
        self.calls.append((user_id, include_inactive))
        return copy.deepcopy([item for item in self.items if item.user_id == user_id])


def _evidence() -> tuple[MatchEvidence, ...]:
    return (
        MatchEvidence(
            field=EvidenceField.NAME,
            outcome=EvidenceOutcome.MATCH,
            reason=EvidenceReason.EXACT,
            score_delta=30,
        ),
    )


def _poi(
    poi_id: str,
    *,
    city_code: str = "shenzhen",
    district: str = "福田区",
    name: str = "测试地点",
    branch_name: str | None = None,
    poi_type: PoiType = PoiType.MUSEUM,
) -> Poi:
    return Poi(
        provider=PoiProvider.AMAP,
        poi_id=poi_id,
        name=name,
        branch_name=branch_name,
        city_code=city_code,
        district=district,
        business_area="市民中心",
        address="福中路1号",
        coordinate=SHENZHEN_COORDINATE,
        poi_type=poi_type,
    )


def _exact_target(poi: Poi) -> PlaceTarget:
    return PlaceTarget(
        scope=PlaceScope.EXACT,
        poi=poi,
        match_status=MatchStatus.MATCHED,
        confidence=MatchConfidence.HIGH,
        confirmed_by=PlaceConfirmationSource.USER_SELECTION,
        confirmed_at=NOW,
        evidence_summary=_evidence(),
    )


def _brand_target() -> PlaceTarget:
    brand = ConfirmedBrandIdentity(
        namespace="curated_brand",
        stable_id="brand_test_cafe",
        display_name="测试咖啡",
        normalized_name=normalize_brand_name("测试咖啡"),
        identity_confirmed_by=BrandIdentityConfirmationSource.CURATED,
        identity_confirmed_at=NOW,
    )
    return PlaceTarget(
        scope=PlaceScope.ANY_BRANCH,
        brand_identity=brand,
        match_status=MatchStatus.AMBIGUOUS,
        confirmed_by=PlaceConfirmationSource.USER_SELECTION,
        confirmed_at=NOW,
    )


def _place(
    user_id: str,
    *,
    title: str = "测试地点",
    poi: Poi | None = None,
    target: PlaceTarget | None = None,
    city_hint: str | None = "深圳",
    status: CollectionStatus = CollectionStatus.ACTIVE,
    tags: tuple[str, ...] = ("室内", "展览"),
    price: Decimal | None = Decimal("50"),
) -> CollectionItem:
    return CollectionItem(
        id=generate_collection_item_id(),
        user_id=user_id,
        kind=CollectionKind.PLACE,
        title=title,
        city_hint=city_hint,
        district=None if poi is None else poi.district,
        address=None if poi is None else poi.address,
        price_amount=price,
        price_currency=None if price is None else "CNY",
        tags=tags,
        place_target=target or (None if poi is None else _exact_target(poi)),
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _event(
    user_id: str,
    *,
    title: str = "周末设计展",
    start_at: datetime | None = START + timedelta(hours=1),
    end_at: datetime | None = START + timedelta(hours=3),
    start_date: date | None = None,
    end_date: date | None = None,
    status: CollectionStatus = CollectionStatus.ACTIVE,
    city_hint: str | None = "深圳",
    price: Decimal | None = Decimal("20"),
    target: PlaceTarget | None = None,
) -> CollectionItem:
    return CollectionItem(
        id=generate_collection_item_id(),
        user_id=user_id,
        kind=CollectionKind.EVENT,
        title=title,
        city_hint=city_hint,
        district="福田区",
        event_start_date=start_date,
        event_end_date=end_date,
        event_start_at=start_at,
        event_end_at=end_at,
        price_amount=price,
        price_currency=None if price is None else "CNY",
        tags=("室内", "展览"),
        place_target=target,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _constraints(
    *,
    budget: Decimal | None = None,
    area: ActivityArea | None = DEFAULT_AREA,
    origin: Coordinate | None = None,
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> PlanConstraints:
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=START,
        end_at=END,
        area=area,
        origin=origin,
        budget=budget,
        include=include,
        exclude=exclude,
        created_at=NOW,
        expires_at=END + timedelta(days=1),
    )


def _known_poi_facts(poi: Poi, *, duration: int = 600) -> PoiPlanningFacts:
    return PoiPlanningFacts(
        provider=poi.provider,
        poi_id=poi.poi_id,
        route=RouteAssessment.REACHABLE,
        route_duration_seconds=duration,
        route_distance_meters=800,
        weather=WeatherAssessment.COMPATIBLE,
        availability=AvailabilityAssessment.AVAILABLE,
    )


def _known_event_facts(
    item: CollectionItem,
    *,
    route: RouteAssessment = RouteAssessment.REACHABLE,
    duration: int | None = 900,
) -> CollectionPlanningFacts:
    return CollectionPlanningFacts(
        collection_item_id=item.id,
        formal_city=_constraints().city_scope,
        location_confirmed=True,
        coordinate=SHENZHEN_COORDINATE,
        route=route,
        route_duration_seconds=duration,
        weather=WeatherAssessment.COMPATIBLE,
        availability=AvailabilityAssessment.AVAILABLE,
    )


def _draft_facts(
    *,
    collection_item_ids: tuple[str, ...],
    route_duration_seconds: int,
    route_distance_meters: int,
) -> PlanDraftFactSnapshot:
    return PlanDraftFactSnapshot(
        candidates=(
            DraftCandidateFacts(
                collection_item_ids=collection_item_ids,
                visit_duration_seconds=60 * 60,
            ),
        ),
        routes=(
            DraftRouteFacts(
                to_collection_item_ids=collection_item_ids,
                duration_seconds=route_duration_seconds,
                distance_meters=route_distance_meters,
                transport_mode=TransportMode.TRANSIT,
            ),
        ),
    )


def _service(
    items: list[CollectionItem],
    *,
    provider: StubMapProvider | None = None,
) -> tuple[StructuredCollectionRetrievalService, ReadOnlyRepository]:
    repository = ReadOnlyRepository(items)
    matching = PlaceMatchingService(
        map_provider=provider or StubMapProvider(),
        policy=Settings(_env_file=None, app_env="test").place_matching_policy(),
    )
    return (
        StructuredCollectionRetrievalService(
            repository=repository,  # type: ignore[arg-type]
            place_matching=matching,
        ),
        repository,
    )


@pytest.fixture
def retrieval_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> str:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'retrieval.db'}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_url


@pytest.mark.asyncio
async def test_current_user_place_and_live_event_are_included_without_writes() -> None:
    user_id, other_user_id = generate_user_id(), generate_user_id()
    place_poi = _poi("poi_shenzhen_museum")
    place = _place(user_id, poi=place_poi)
    event = _event(user_id)
    other = _place(other_user_id, poi=_poi("poi_private_other"), title="其他用户秘密")
    service, repository = _service([place, event, other])
    before = copy.deepcopy(repository.items)

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(
            collections=(_known_event_facts(event),),
            pois=(_known_poi_facts(place_poi),),
        ),
        now=NOW,
    )

    assert {decision.collection_item_ids for decision in result.included} == {
        (place.id,),
        (event.id,),
    }
    assert all(other.id not in decision.collection_item_ids for decision in result.decisions)
    assert "其他用户秘密" not in repr(result)
    assert repository.calls == [(user_id, True)]
    assert repository.items == before


@pytest.mark.asyncio
async def test_sql_repository_retrieval_is_user_scoped_and_read_only(
    retrieval_database: str,
) -> None:
    database = Database(retrieval_database)
    user_id, other_user_id = generate_user_id(), generate_user_id()
    poi = _poi("poi_database")
    own_item = _place(user_id, poi=poi)
    other_item = _place(other_user_id, poi=_poi("poi_database_other"))
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(
            user_id=user_id,
            user=User(id=user_id, mode=UserMode.REAL, created_at=NOW),
        )
        await repository.add_user(
            user_id=other_user_id,
            user=User(id=other_user_id, mode=UserMode.REAL, created_at=NOW),
        )
        await repository.add_collection_item(user_id=user_id, item=own_item)
        await repository.add_collection_item(user_id=other_user_id, item=other_item)
        await session.commit()

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        service = StructuredCollectionRetrievalService(
            repository=repository,
            place_matching=PlaceMatchingService(
                map_provider=StubMapProvider(),
                policy=PlaceMatchingPolicy(
                    unique_match_score=30,
                    minimum_score_gap=5,
                    candidate_score=20,
                ),
            ),
        )
        result = await service.retrieve(
            user_id=user_id,
            constraints=_constraints(),
            facts=PlanningFactSnapshot(pois=(_known_poi_facts(poi),)),
            now=NOW,
        )

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        own_after = await repository.list_collection_items(
            user_id=user_id,
            include_inactive=True,
        )
        other_after = await repository.list_collection_items(
            user_id=other_user_id,
            include_inactive=True,
        )
    await database.close()

    assert result.included[0].collection_item_ids == (own_item.id,)
    assert own_after == [own_item]
    assert other_after == [other_item]
    assert other_item.id not in str(result.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_repository_failure_and_owner_violation_are_fixed_and_do_not_leak() -> None:
    user_id, other_user_id = generate_user_id(), generate_user_id()
    private_item = _place(other_user_id, title="private-origin-secret", poi=_poi("poi_private"))

    class BrokenRepository(ReadOnlyRepository):
        async def list_collection_items(
            self,
            *,
            user_id: str,
            include_inactive: bool = False,
        ) -> list[CollectionItem]:
            raise RuntimeError("provider-response api-key=private-origin-secret")

    for repository in (BrokenRepository([]), ReadOnlyRepository([private_item])):
        if type(repository) is ReadOnlyRepository:
            repository.items = [private_item]

            async def cross_owner(**_kwargs: object) -> list[CollectionItem]:
                return [private_item]

            repository.list_collection_items = cross_owner  # type: ignore[method-assign]
        service = StructuredCollectionRetrievalService(
            repository=repository,  # type: ignore[arg-type]
            place_matching=PlaceMatchingService(
                map_provider=StubMapProvider(),
                policy=PlaceMatchingPolicy(
                    unique_match_score=30,
                    minimum_score_gap=5,
                    candidate_score=20,
                ),
            ),
        )
        with pytest.raises(StructuredCollectionRetrievalError) as captured:
            await service.retrieve(
                user_id=user_id,
                constraints=_constraints(origin=ORIGIN),
                facts=PlanningFactSnapshot(),
                now=NOW,
            )
        error = captured.value
        assert error.to_dict() == {
            "code": "COLLECTION_RETRIEVAL_FAILED",
            "summary": "Collection retrieval failed.",
        }
        assert error.__cause__ is None
        assert error.__context__ is None
        assert "private-origin-secret" not in repr(error)


@pytest.mark.asyncio
async def test_constraints_expiry_boundary_stops_before_repository_and_map() -> None:
    user_id = generate_user_id()
    expiry = NOW + timedelta(hours=1)
    branch = _poi(
        "poi_expiry_branch",
        name="测试咖啡",
        branch_name="中心店",
        poi_type=PoiType.CAFE,
    )
    brand = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
        price=Decimal("35"),
    )
    constraints = _constraints(origin=ORIGIN).model_copy(
        update={"expires_at": expiry}
    )

    valid_service, valid_repository = _service(
        [brand],
        provider=_branch_provider((branch,), district="福田区"),
    )
    valid = await valid_service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=PlanningFactSnapshot(pois=(_known_poi_facts(branch),)),
        now=expiry - timedelta(microseconds=1),
    )
    assert valid.included
    assert valid_repository.calls == [(user_id, True)]

    map_calls: list[SearchPoiRequest] = []

    async def capture(request: Any) -> None:
        if isinstance(request, SearchPoiRequest):
            map_calls.append(request)

    for invalid_now in (expiry, expiry + timedelta(microseconds=1)):
        map_calls.clear()
        service, repository = _service(
            [brand],
            provider=_branch_provider((branch,), call_hook=capture),
        )
        with pytest.raises(StructuredCollectionRetrievalError) as error_info:
            await service.retrieve(
                user_id=user_id,
                constraints=constraints,
                facts=PlanningFactSnapshot(pois=(_known_poi_facts(branch),)),
                now=invalid_now,
            )

        error = error_info.value
        assert error.to_dict() == {
            "code": "PLAN_CONSTRAINTS_EXPIRED",
            "summary": "Plan constraints have expired.",
        }
        assert error.__cause__ is None
        assert error.__context__ is None
        assert str(ORIGIN.latitude) not in repr(error)
        assert repository.calls == []
        assert map_calls == []


@pytest.mark.asyncio
async def test_retrieval_now_requires_aware_time_before_any_io() -> None:
    user_id = generate_user_id()
    service, repository = _service([_place(user_id, poi=_poi("poi_naive_now"))])

    with pytest.raises(StructuredCollectionRetrievalError) as captured:
        await service.retrieve(
            user_id=user_id,
            constraints=_constraints(origin=ORIGIN),
            facts=PlanningFactSnapshot(),
            now=NOW.replace(tzinfo=None),
        )

    assert captured.value.to_dict() == {
        "code": "INVALID_RETRIEVAL_TIME",
        "summary": "Retrieval time is invalid.",
    }
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert repository.calls == []


@pytest.mark.asyncio
async def test_retrieval_preserves_repository_and_map_cancellation() -> None:
    user_id = generate_user_id()
    repository_cancelled = asyncio.CancelledError()

    class CancelledRepository(ReadOnlyRepository):
        async def list_collection_items(
            self,
            *,
            user_id: str,
            include_inactive: bool = False,
        ) -> list[CollectionItem]:
            raise repository_cancelled

    repository_service = StructuredCollectionRetrievalService(
        repository=CancelledRepository([]),  # type: ignore[arg-type]
        place_matching=PlaceMatchingService(
            map_provider=StubMapProvider(),
            policy=PlaceMatchingPolicy(
                unique_match_score=30,
                minimum_score_gap=5,
                candidate_score=20,
            ),
        ),
    )
    with pytest.raises(asyncio.CancelledError) as repository_error:
        await repository_service.retrieve(
            user_id=user_id,
            constraints=_constraints(),
            facts=PlanningFactSnapshot(),
            now=NOW,
        )
    assert repository_error.value is repository_cancelled

    map_cancelled = asyncio.CancelledError()

    async def cancel_map(_request: Any) -> None:
        raise map_cancelled

    brand = _place(user_id, title="测试咖啡", target=_brand_target())
    map_service, repository = _service(
        [brand],
        provider=_branch_provider((), call_hook=cancel_map),
    )
    with pytest.raises(asyncio.CancelledError) as map_error:
        await map_service.retrieve(
            user_id=user_id,
            constraints=_constraints(area=None, origin=ORIGIN),
            facts=PlanningFactSnapshot(),
            now=NOW,
        )
    assert map_error.value is map_cancelled
    assert repository.calls == [(user_id, True)]


@pytest.mark.asyncio
async def test_formal_city_controls_eligibility_and_city_hint_never_substitutes() -> None:
    user_id = generate_user_id()
    other_city = _place(
        user_id,
        poi=_poi("poi_guangzhou", city_code="guangzhou", district="天河区"),
        city_hint="深圳",
    )
    pending_city = _event(user_id, title="深圳标题但城市待确认", city_hint="深圳")
    other_city_event = _event(user_id, title="广州活动", city_hint="深圳")
    service, repository = _service([other_city, pending_city, other_city_event])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(area=ActivityArea(labels=("展览",))),
        facts=PlanningFactSnapshot(
            collections=(
                CollectionPlanningFacts(
                    collection_item_id=other_city_event.id,
                    formal_city=CityScope(city_code="guangzhou"),
                    location_confirmed=True,
                    route=RouteAssessment.REACHABLE,
                    route_duration_seconds=900,
                    weather=WeatherAssessment.COMPATIBLE,
                    availability=AvailabilityAssessment.AVAILABLE,
                ),
            ),
            pois=(_known_poi_facts(other_city.place_target.poi),),  # type: ignore[union-attr]
        ),
        now=NOW,
    )

    reasons = {
        decision.collection_item_ids[0]: decision.reason_codes
        for decision in result.decisions
    }
    assert CandidateReasonCode.CITY_MISMATCH in reasons[other_city.id]
    assert CandidateReasonCode.CITY_UNCONFIRMED in reasons[pending_city.id]
    assert CandidateReasonCode.LOCATION_UNCONFIRMED in reasons[pending_city.id]
    assert CandidateReasonCode.CITY_MISMATCH in reasons[other_city_event.id]
    assert repository.items[0].city_hint == "深圳"
    assert repository.items[1].city_hint == "深圳"
    assert repository.items[2].city_hint == "深圳"


@pytest.mark.asyncio
async def test_inactive_pending_deleted_and_unconfirmed_place_are_excluded() -> None:
    user_id = generate_user_id()
    statuses = (
        CollectionStatus.PENDING_SELECTION,
        CollectionStatus.PENDING_DETAILS,
        CollectionStatus.DELETED,
        CollectionStatus.ARCHIVED,
    )
    items = [_place(user_id, title=status.value, status=status) for status in statuses]
    items.append(_place(user_id, title="active without target"))
    service, _ = _service(items)

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )

    assert len(result.excluded) == len(statuses)
    assert all(
        CandidateReasonCode.STATUS_NOT_ACTIVE in decision.reason_codes
        for decision in result.excluded
    )
    active = next(item for item in result.decisions if item.title == "active without target")
    assert active.outcome is CandidateOutcome.VERIFICATION_REQUIRED
    assert CandidateReasonCode.LOCATION_UNCONFIRMED in active.reason_codes


@pytest.mark.asyncio
async def test_event_end_and_time_window_boundaries_are_deterministic() -> None:
    user_id = generate_user_id()
    ended = _event(user_id, title="ended", start_at=START - timedelta(hours=2), end_at=START)
    starts_at_end = _event(user_id, title="late", start_at=END, end_at=END + timedelta(hours=1))
    missing_time = _event(user_id, title="unknown", start_at=None, end_at=None)
    service, _ = _service([ended, starts_at_end, missing_time])
    facts = PlanningFactSnapshot(
        collections=tuple(_known_event_facts(item) for item in (ended, starts_at_end, missing_time))
    )

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=facts,
        now=NOW,
    )
    by_title = {item.title: item for item in result.decisions}

    assert CandidateReasonCode.EVENT_ENDED in by_title["ended"].reason_codes
    assert CandidateReasonCode.TIME_WINDOW_CONFLICT in by_title["late"].reason_codes
    assert by_title["unknown"].outcome is CandidateOutcome.VERIFICATION_REQUIRED
    assert CandidateReasonCode.EVENT_TIME_UNKNOWN in by_title["unknown"].reason_codes


@pytest.mark.asyncio
async def test_date_only_event_is_saved_but_never_treated_as_exact_plan_window() -> None:
    user_id = generate_user_id()
    date_only = _event(
        user_id,
        title="日期范围展览",
        start_at=None,
        end_at=None,
        start_date=date(2026, 7, 25),
        end_date=date(2026, 7, 31),
        status=CollectionStatus.PENDING_DETAILS,
    )
    service, _ = _service([date_only])
    facts = PlanningFactSnapshot(collections=(_known_event_facts(date_only),))

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=facts,
        now=NOW,
    )

    decision = result.decisions[0]
    assert decision.outcome is CandidateOutcome.EXCLUDED
    assert CandidateReasonCode.STATUS_NOT_ACTIVE in decision.reason_codes
    assert CandidateReasonCode.EVENT_TIME_UNKNOWN in decision.reason_codes
    assert result.included == ()


@pytest.mark.asyncio
async def test_district_area_tags_keywords_include_and_exclude_are_hard_rules() -> None:
    user_id = generate_user_id()
    poi = _poi("poi_keywords", district="南山区", name="安静咖啡馆", poi_type=PoiType.CAFE)
    item = _place(user_id, poi=poi, tags=("室内", "咖啡"))
    service, _ = _service([item])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(
            area=ActivityArea(districts=("福田区",), labels=("海边",)),
            include=("安静", "甜品"),
            exclude=("咖啡",),
        ),
        facts=PlanningFactSnapshot(pois=(_known_poi_facts(poi),)),
        now=NOW,
    )
    decision = result.decisions[0]

    assert decision.outcome is CandidateOutcome.EXCLUDED
    assert CandidateReasonCode.DISTRICT_MISMATCH in decision.reason_codes
    assert CandidateReasonCode.AREA_MISMATCH in decision.reason_codes
    assert CandidateReasonCode.INCLUDE_NOT_MATCHED in decision.reason_codes
    assert CandidateReasonCode.EXCLUDED_BY_USER in decision.reason_codes


@pytest.mark.asyncio
async def test_budget_null_does_not_filter_known_high_price_and_budget_still_excludes() -> None:
    user_id = generate_user_id()
    known_poi = _poi("poi_known")
    known = _place(user_id, title="known", poi=known_poi, price=Decimal("500"))
    service, repository = _service([known])
    before = copy.deepcopy(repository.items)
    facts = PlanningFactSnapshot(pois=(_known_poi_facts(known_poi),))

    no_budget = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=facts,
        now=NOW,
    )
    with_budget = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(budget=Decimal("100")),
        facts=facts,
        now=NOW,
    )

    assert no_budget.included[0].price_amount == Decimal("500")
    assert no_budget.included[0].price_currency == "CNY"
    assert with_budget.excluded[0].reason_codes == (CandidateReasonCode.BUDGET_EXCEEDED,)
    assert repository.items == before


@pytest.mark.asyncio
async def test_unknown_price_flows_from_retrieval_into_draft_by_budget_state() -> None:
    user_id = generate_user_id()
    poi = _poi("poi_price_unknown")
    item = _place(user_id, title="价格待确认地点", poi=poi, price=None)
    service, repository = _service([item])
    before = copy.deepcopy(repository.items)
    planning_facts = PlanningFactSnapshot(pois=(_known_poi_facts(poi),))
    no_budget_constraints = _constraints()
    budget_constraints = _constraints(budget=Decimal("100"))

    first = await service.retrieve(
        user_id=user_id,
        constraints=no_budget_constraints,
        facts=planning_facts,
        now=NOW,
    )
    repeated = await service.retrieve(
        user_id=user_id,
        constraints=no_budget_constraints,
        facts=planning_facts,
        now=NOW,
    )
    with_budget = await service.retrieve(
        user_id=user_id,
        constraints=budget_constraints,
        facts=planning_facts,
        now=NOW,
    )

    assert first == repeated
    assert len(first.included) == 1
    decision = first.included[0]
    assert decision.price_amount is None
    assert decision.price_currency is None
    assert decision.reason_codes == ()
    assert with_budget.verification_required[0].reason_codes == (
        CandidateReasonCode.PRICE_UNKNOWN,
    )
    blocked_draft = PlanDraftService().generate(
        constraints=budget_constraints,
        collections=with_budget,
        facts=PlanDraftFactSnapshot(),
    )
    assert blocked_draft.outcome is not PlanDraftOutcome.GENERATED
    assert blocked_draft.options == ()

    assert decision.route_duration_seconds is not None
    assert decision.route_distance_meters is not None
    draft_facts = _draft_facts(
        collection_item_ids=decision.collection_item_ids,
        route_duration_seconds=decision.route_duration_seconds,
        route_distance_meters=decision.route_distance_meters,
    )
    draft_service = PlanDraftService()
    draft = draft_service.generate(
        constraints=no_budget_constraints,
        collections=first,
        facts=draft_facts,
    )
    repeated_draft = draft_service.generate(
        constraints=no_budget_constraints,
        collections=repeated,
        facts=draft_facts,
    )

    assert draft == repeated_draft
    assert draft.outcome is PlanDraftOutcome.GENERATED
    plan_item = draft.options[0].items[0]
    assert plan_item.price_amount is None
    assert plan_item.price_currency is None
    assert plan_item.risk_codes == (PlanRiskCode.PRICE_UNKNOWN,)
    assert draft.options[0].total_cost_amount is None
    assert draft.options[0].total_cost_currency is None
    assert draft_service.validate(
        draft=draft,
        constraints=no_budget_constraints,
        collections=first,
        facts=draft_facts,
    ).is_valid
    assert repository.items == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "weather", "availability", "expected"),
    [
        (
            RouteAssessment.UNREACHABLE,
            WeatherAssessment.COMPATIBLE,
            AvailabilityAssessment.AVAILABLE,
            CandidateReasonCode.ROUTE_UNREACHABLE,
        ),
        (
            RouteAssessment.PROVIDER_FAILED,
            WeatherAssessment.COMPATIBLE,
            AvailabilityAssessment.AVAILABLE,
            CandidateReasonCode.ROUTE_PROVIDER_FAILED,
        ),
        (
            RouteAssessment.REACHABLE,
            WeatherAssessment.CONFLICT,
            AvailabilityAssessment.AVAILABLE,
            CandidateReasonCode.WEATHER_CONFLICT,
        ),
        (
            RouteAssessment.REACHABLE,
            WeatherAssessment.PROVIDER_FAILED,
            AvailabilityAssessment.AVAILABLE,
            CandidateReasonCode.WEATHER_PROVIDER_FAILED,
        ),
        (
            RouteAssessment.REACHABLE,
            WeatherAssessment.COMPATIBLE,
            AvailabilityAssessment.UNAVAILABLE,
            CandidateReasonCode.PLACE_UNAVAILABLE,
        ),
    ],
)
async def test_explicit_route_weather_and_availability_facts_never_fake_success(
    route: RouteAssessment,
    weather: WeatherAssessment,
    availability: AvailabilityAssessment,
    expected: CandidateReasonCode,
) -> None:
    user_id, poi = generate_user_id(), _poi("poi_dynamic")
    item = _place(user_id, poi=poi)
    service, _ = _service([item])
    facts = PoiPlanningFacts(
        provider=poi.provider,
        poi_id=poi.poi_id,
        route=route,
        route_duration_seconds=600 if route is RouteAssessment.REACHABLE else None,
        weather=weather,
        availability=availability,
    )

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(pois=(facts,)),
        now=NOW,
    )

    assert expected in result.decisions[0].reason_codes
    if expected in {
        CandidateReasonCode.ROUTE_PROVIDER_FAILED,
        CandidateReasonCode.WEATHER_PROVIDER_FAILED,
    }:
        assert result.decisions[0].outcome is CandidateOutcome.VERIFICATION_REQUIRED
    else:
        assert result.decisions[0].outcome is CandidateOutcome.EXCLUDED


@pytest.mark.asyncio
async def test_unknown_route_weather_and_opening_require_verification() -> None:
    user_id, poi = generate_user_id(), _poi("poi_unknown_facts")
    item = _place(user_id, poi=poi)
    service, _ = _service([item])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )

    decision = result.decisions[0]
    assert decision.outcome is CandidateOutcome.VERIFICATION_REQUIRED
    assert decision.reason_codes[-3:] == (
        CandidateReasonCode.ROUTE_UNKNOWN,
        CandidateReasonCode.WEATHER_UNKNOWN,
        CandidateReasonCode.AVAILABILITY_UNKNOWN,
    )


@pytest.mark.asyncio
async def test_reachable_route_must_still_fit_the_available_time_window() -> None:
    user_id, poi = generate_user_id(), _poi("poi_route_too_long")
    item = _place(user_id, poi=poi)
    service, _ = _service([item])
    facts = _known_poi_facts(poi).model_copy(
        update={"route_duration_seconds": int((END - START).total_seconds())}
    )

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(pois=(facts,)),
        now=NOW,
    )

    assert result.decisions[0].outcome is CandidateOutcome.EXCLUDED
    assert CandidateReasonCode.ROUTE_EXCEEDS_TIME_WINDOW in result.decisions[0].reason_codes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route_seconds", "expected_outcome"),
    [
        (1799, CandidateOutcome.INCLUDED),
        (1800, CandidateOutcome.EXCLUDED),
        (1801, CandidateOutcome.EXCLUDED),
    ],
)
async def test_event_route_must_arrive_strictly_before_event_end(
    route_seconds: int,
    expected_outcome: CandidateOutcome,
) -> None:
    user_id = generate_user_id()
    event = _event(
        user_id,
        start_at=START - timedelta(hours=1),
        end_at=START + timedelta(minutes=30),
    )
    service, _ = _service([event])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(
            collections=(_known_event_facts(event, duration=route_seconds),)
        ),
        now=NOW,
    )

    decision = result.decisions[0]
    assert decision.outcome is expected_outcome
    assert (
        CandidateReasonCode.ROUTE_EXCEEDS_TIME_WINDOW in decision.reason_codes
    ) is (expected_outcome is CandidateOutcome.EXCLUDED)


@pytest.mark.asyncio
async def test_started_event_remains_eligible_when_arrival_precedes_end() -> None:
    user_id = generate_user_id()
    event = _event(
        user_id,
        start_at=START - timedelta(hours=2),
        end_at=START + timedelta(minutes=20),
    )
    service, _ = _service([event])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(
            collections=(_known_event_facts(event, duration=600),)
        ),
        now=NOW,
    )

    assert result.decisions[0].outcome is CandidateOutcome.INCLUDED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "expected_reason", "expected_outcome"),
    [
        (
            RouteAssessment.UNREACHABLE,
            CandidateReasonCode.ROUTE_UNREACHABLE,
            CandidateOutcome.EXCLUDED,
        ),
        (
            RouteAssessment.UNKNOWN,
            CandidateReasonCode.ROUTE_UNKNOWN,
            CandidateOutcome.VERIFICATION_REQUIRED,
        ),
        (
            RouteAssessment.PROVIDER_FAILED,
            CandidateReasonCode.ROUTE_PROVIDER_FAILED,
            CandidateOutcome.VERIFICATION_REQUIRED,
        ),
    ],
)
async def test_event_non_reachable_route_states_keep_existing_semantics(
    route: RouteAssessment,
    expected_reason: CandidateReasonCode,
    expected_outcome: CandidateOutcome,
) -> None:
    user_id = generate_user_id()
    event = _event(user_id)
    service, _ = _service([event])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(
            collections=(_known_event_facts(event, route=route, duration=None),)
        ),
        now=NOW,
    )

    decision = result.decisions[0]
    assert decision.outcome is expected_outcome
    assert expected_reason in decision.reason_codes
    assert CandidateReasonCode.ROUTE_EXCEEDS_TIME_WINDOW not in decision.reason_codes


def _branch_provider(
    pois: tuple[Poi, ...],
    *,
    origin: Coordinate | None = None,
    district: str | None = None,
    timeout: bool = False,
    call_hook: Any = None,
) -> StubMapProvider:
    effective_origin = origin or ORIGIN
    request = SearchPoiRequest(
        query="测试咖啡",
        city=_constraints(area=None, origin=effective_origin).city_scope,
        district=district,
        location=effective_origin,
    )
    return StubMapProvider(
        search_results={request: PoiSearchResult(city_code="shenzhen", pois=pois)},
        timeout_requests=(request,) if timeout else (),
        call_hook=call_hook,
    )


def test_any_branch_tests_use_unchanged_production_matching_thresholds() -> None:
    policy = Settings(_env_file=None, app_env="test").place_matching_policy()

    assert policy.unique_match_score == 75
    assert policy.minimum_score_gap == 12
    assert policy.candidate_score == 35


@pytest.mark.asyncio
async def test_production_policy_needs_context_candidate_is_evaluated_and_included() -> None:
    user_id = generate_user_id()
    branch = _poi(
        "poi_default_policy_branch",
        name="测试咖啡",
        branch_name="福田店",
        poi_type=PoiType.CAFE,
    )
    brand = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
        price=Decimal("35"),
    )
    service, repository = _service([brand], provider=_branch_provider((branch,)))
    constraints = _constraints(area=None, origin=ORIGIN)
    facts = PlanningFactSnapshot(pois=(_known_poi_facts(branch),))
    before = copy.deepcopy(repository.items)

    first = await service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts,
        now=NOW,
    )
    second = await service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts,
        now=NOW,
    )

    assert first == second
    assert first.included[0].poi is not None
    assert first.included[0].poi.poi_id == branch.poi_id
    assert repository.items == before
    assert constraints == _constraints(area=None, origin=ORIGIN)
    assert facts == PlanningFactSnapshot(pois=(_known_poi_facts(branch),))


@pytest.mark.asyncio
async def test_any_branch_uses_city_area_route_and_origin_without_mutating_collection() -> None:
    user_id = generate_user_id()
    far = _poi("poi_branch_far", name="测试咖啡", branch_name="远店", poi_type=PoiType.CAFE)
    near = _poi("poi_branch_near", name="测试咖啡", branch_name="近店", poi_type=PoiType.CAFE)
    brand = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
        price=Decimal("35"),
    )
    calls: list[SearchPoiRequest] = []

    async def capture(request: Any) -> None:
        if isinstance(request, SearchPoiRequest):
            calls.append(request)

    provider = _branch_provider(
        (far, near),
        origin=ORIGIN,
        district="福田区",
        call_hook=capture,
    )
    service, repository = _service([brand], provider=provider)
    before = copy.deepcopy(repository.items)

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(origin=ORIGIN),
        facts=PlanningFactSnapshot(
            pois=(_known_poi_facts(far, duration=1200), _known_poi_facts(near, duration=300))
        ),
        now=NOW,
    )

    assert result.included[0].poi is not None
    assert result.included[0].poi.poi_id == near.poi_id
    assert calls[0].location == ORIGIN
    assert calls[0].district == "福田区"
    assert repository.items == before
    assert repository.items[0].place_target.scope is PlaceScope.ANY_BRANCH


@pytest.mark.asyncio
async def test_any_branch_ignores_stale_branch_location_clues_for_new_plan_scope() -> None:
    user_id = generate_user_id()
    branch = _poi(
        "poi_futian_branch",
        district="福田区",
        name="测试咖啡",
        branch_name="福田店",
        poi_type=PoiType.CAFE,
    )
    brand = _place(
        user_id,
        title="测试咖啡旧南山店描述",
        target=_brand_target(),
        tags=("咖啡",),
        price=Decimal("35"),
    ).model_copy(
        update={
            "district": "南山区",
            "address": "南山区旧分店地址",
            "business_district": "旧南山商圈",
            "landmark": "旧南山地标",
            "metro_station": "旧南山站",
        },
        deep=True,
    )
    provider_calls: list[SearchPoiRequest] = []

    async def capture(request: Any) -> None:
        if isinstance(request, SearchPoiRequest):
            provider_calls.append(request)

    service, repository = _service(
        [brand],
        provider=_branch_provider(
            (branch,),
            district="福田区",
            origin=ORIGIN,
            call_hook=capture,
        ),
    )
    before = copy.deepcopy(repository.items)

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(
            area=ActivityArea(districts=("福田区",)),
            origin=ORIGIN,
        ),
        facts=PlanningFactSnapshot(pois=(_known_poi_facts(branch),)),
        now=NOW,
    )

    assert result.included[0].poi is not None
    assert result.included[0].poi.poi_id == branch.poi_id
    assert provider_calls == [
        SearchPoiRequest(
            query="测试咖啡",
            city=_constraints().city_scope,
            district="福田区",
            location=ORIGIN,
        )
    ]
    assert repository.items == before
    assert repository.items[0].district == "南山区"
    assert repository.items[0].place_target == brand.place_target


@pytest.mark.asyncio
async def test_unresolved_any_branch_does_not_reuse_stale_location_fields() -> None:
    user_id = generate_user_id()
    weak = _poi("poi_unrelated", name="不相关地点", poi_type=PoiType.CAFE)
    brand = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
        price=Decimal("35"),
    ).model_copy(
        update={
            "district": "南山区",
            "address": "旧南山地址",
            "business_district": "旧南山商圈",
            "landmark": "旧南山地标",
            "metro_station": "旧南山站",
        },
        deep=True,
    )
    service, repository = _service(
        [brand],
        provider=_branch_provider((weak,), district="福田区"),
    )
    before = copy.deepcopy(repository.items)

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(
            area=ActivityArea(districts=("福田区",)),
            origin=ORIGIN,
            exclude=("旧南山地址",),
        ),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )

    decision = result.decisions[0]
    assert decision.outcome is CandidateOutcome.VERIFICATION_REQUIRED
    assert CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT in decision.reason_codes
    assert CandidateReasonCode.DISTRICT_MISMATCH not in decision.reason_codes
    assert CandidateReasonCode.EXCLUDED_BY_USER not in decision.reason_codes
    assert repository.items == before


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_rule", ["weather", "availability", "budget"])
async def test_resolved_any_branch_still_applies_candidate_hard_rules(
    failed_rule: str,
) -> None:
    user_id = generate_user_id()
    branch = _poi(
        f"poi_branch_{failed_rule}",
        name="测试咖啡",
        branch_name="福田店",
        poi_type=PoiType.CAFE,
    )
    brand = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
        price=Decimal("35"),
    )
    dynamic = _known_poi_facts(branch)
    if failed_rule == "weather":
        dynamic = dynamic.model_copy(update={"weather": WeatherAssessment.CONFLICT})
    elif failed_rule == "availability":
        dynamic = dynamic.model_copy(
            update={"availability": AvailabilityAssessment.UNAVAILABLE}
        )
    constraints = _constraints(
        area=None,
        origin=ORIGIN,
        budget=Decimal("20") if failed_rule == "budget" else None,
    )
    service, _ = _service([brand], provider=_branch_provider((branch,)))

    result = await service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=PlanningFactSnapshot(pois=(dynamic,)),
        now=NOW,
    )

    assert result.decisions[0].outcome is CandidateOutcome.EXCLUDED
    assert CandidateReasonCode.BRANCH_NO_HARD_CONSTRAINT_MATCH in (
        result.decisions[0].reason_codes
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pois", "timed_out", "expected"),
    [
        ((), False, CandidateReasonCode.BRANCH_NOT_FOUND),
        (
            (_poi("poi_weak", name="不相关地点"),),
            False,
            CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT,
        ),
        ((), True, CandidateReasonCode.BRANCH_PROVIDER_FAILED),
    ],
)
async def test_any_branch_failure_modes_have_stable_safe_reasons(
    pois: tuple[Poi, ...],
    timed_out: bool,
    expected: CandidateReasonCode,
) -> None:
    user_id = generate_user_id()
    brand = _place(user_id, title="测试咖啡", target=_brand_target(), price=Decimal("35"))
    service, _ = _service([brand], provider=_branch_provider(pois, timeout=timed_out))

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(area=None, origin=ORIGIN),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )

    assert expected in result.decisions[0].reason_codes
    public = result.model_dump(mode="json")
    assert "provider response" not in str(public).lower()
    assert "secret" not in str(public).lower()


@pytest.mark.asyncio
async def test_any_branch_with_only_unreachable_candidates_is_excluded() -> None:
    user_id = generate_user_id()
    branch = _poi(
        "poi_unreachable_branch",
        name="测试咖啡",
        branch_name="远店",
        poi_type=PoiType.CAFE,
    )
    brand = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
        price=Decimal("35"),
    )
    service, _ = _service([brand], provider=_branch_provider((branch,)))

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(area=None, origin=ORIGIN),
        facts=PlanningFactSnapshot(
            pois=(
                PoiPlanningFacts(
                    provider=branch.provider,
                    poi_id=branch.poi_id,
                    route=RouteAssessment.UNREACHABLE,
                    weather=WeatherAssessment.COMPATIBLE,
                    availability=AvailabilityAssessment.AVAILABLE,
                ),
            )
        ),
        now=NOW,
    )

    assert result.decisions[0].outcome is CandidateOutcome.EXCLUDED
    assert CandidateReasonCode.BRANCH_NO_HARD_CONSTRAINT_MATCH in (
        result.decisions[0].reason_codes
    )


@pytest.mark.asyncio
async def test_exact_and_any_branch_same_poi_are_deduplicated_with_both_sources() -> None:
    user_id = generate_user_id()
    poi = _poi(
        "poi_same_branch",
        name="测试咖啡",
        branch_name="中心店",
        poi_type=PoiType.CAFE,
    )
    exact = _place(
        user_id,
        title="测试咖啡中心店",
        poi=poi,
        tags=("咖啡",),
        price=Decimal("35"),
    )
    brand = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
        price=Decimal("35"),
    )
    service, _ = _service([exact, brand], provider=_branch_provider((poi,)))

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(area=None, origin=ORIGIN),
        facts=PlanningFactSnapshot(pois=(_known_poi_facts(poi),)),
        now=NOW,
    )

    assert len(result.included) == 1
    assert result.included[0].collection_item_ids == tuple(sorted((exact.id, brand.id)))
    assert result.included[0].any_branch_collection_item_ids == (brand.id,)
    assert result.included[0].poi is not None
    assert result.included[0].poi.poi_id == poi.poi_id


@pytest.mark.asyncio
async def test_repeated_calls_are_identical_do_not_modify_inputs_and_never_use_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, poi = generate_user_id(), _poi("poi_repeat")
    item = _place(user_id, poi=poi)
    service, repository = _service([item])
    constraints = _constraints()
    facts = PlanningFactSnapshot(pois=(_known_poi_facts(poi),))
    constraints_before = constraints.model_copy(deep=True)
    facts_before = facts.model_copy(deep=True)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    first = await service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts,
        now=NOW,
    )
    second = await service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts,
        now=NOW,
    )

    assert first == second
    assert constraints == constraints_before
    assert facts == facts_before
    assert repository.calls == [(user_id, True), (user_id, True)]


def test_fact_contracts_reject_contradictory_route_and_duplicate_identities() -> None:
    with pytest.raises(ValueError, match="only reachable"):
        PoiPlanningFacts(
            provider=PoiProvider.AMAP,
            poi_id="poi_bad",
            route=RouteAssessment.UNREACHABLE,
            route_duration_seconds=1,
        )
    with pytest.raises(ValueError, match="require a duration"):
        PoiPlanningFacts(
            provider=PoiProvider.AMAP,
            poi_id="poi_missing_duration",
            route=RouteAssessment.REACHABLE,
            route_distance_meters=1,
        )
    duplicate = PoiPlanningFacts(provider=PoiProvider.AMAP, poi_id="poi_duplicate")
    with pytest.raises(ValueError, match="must be unique"):
        PlanningFactSnapshot(pois=(duplicate, duplicate))


def test_provider_error_code_remains_safe_and_stable() -> None:
    assert MapProviderErrorCode.TIMEOUT.value == "MAP_PROVIDER_TIMEOUT"


def _map_fact_provider(
    *,
    constraints: PlanConstraints,
    search_pois: tuple[Poi, ...] = (),
    calls: list[object] | None = None,
) -> StubMapProvider:
    route_request = RouteRequest(
        city=constraints.city_scope,
        origin=constraints.origin or SHENZHEN_COORDINATE,
        destination=SHENZHEN_COORDINATE,
        mode=(
            constraints.transport_modes[0]
            if constraints.transport_modes
            else TransportMode.TRANSIT
        ),
    )
    weather_request = WeatherRequest(
        city=constraints.city_scope,
        on_date=constraints.start_at.date(),
    )
    search_results = {}
    if search_pois:
        search_request = SearchPoiRequest(
            query="测试咖啡",
            city=constraints.city_scope,
            district=constraints.area.districts[0] if constraints.area else None,
            location=constraints.origin,
        )
        search_results[search_request] = PoiSearchResult(
            city_code=constraints.city_code.value,
            pois=search_pois,
        )

    async def record(request: object) -> None:
        if calls is not None:
            calls.append(request)

    return StubMapProvider(
        search_results=search_results,
        route_results={
            route_request: RouteResult(
                city_code=constraints.city_code.value,
                origin=route_request.origin,
                destination=route_request.destination,
                mode=route_request.mode,
                distance_meters=800,
                duration_seconds=600,
            )
        },
        weather_results={
            weather_request: WeatherResult(
                city_code=constraints.city_code.value,
                on_date=constraints.start_at.date(),
                condition="晴",
                temperature_celsius=28,
            )
        },
        call_hook=record,
    )


async def _resolve_map_facts(
    *,
    database_url: str,
    user_id: str,
    items: tuple[CollectionItem, ...],
    constraints: PlanConstraints,
    provider: StubMapProvider,
):
    database = Database(database_url)
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(
            user_id=user_id,
            user=User(id=user_id, mode=UserMode.REAL, created_at=NOW),
        )
        for item in items:
            await repository.add_collection_item(user_id=user_id, item=item)
        await session.commit()
    async with database.session() as session:
        result = await MapPlanFactResolver(
            session=session,
            map_provider=provider,
            matching_policy=Settings(
                _env_file=None,
                app_env="test",
            ).place_matching_policy(),
        ).resolve(user_id=user_id, constraints=constraints)
    await database.close()
    return result


@pytest.mark.asyncio
async def test_map_fact_chain_includes_exact_event_with_precise_time_window(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    event = _event(
        user_id,
        target=_exact_target(_poi("poi_timed_event")),
    )
    constraints = _constraints(origin=ORIGIN)
    calls: list[object] = []

    result = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(event,),
        constraints=constraints,
        provider=_map_fact_provider(constraints=constraints, calls=calls),
    )

    assert result.retrieval.collections[0].collection_item_id == event.id
    assert result.draft.candidates[0].event_start_at == event.event_start_at
    assert result.draft.candidates[0].event_end_at == event.event_end_at
    assert sum(isinstance(call, RouteRequest) for call in calls) == 1


@pytest.mark.asyncio
async def test_map_fact_chain_conservatively_excludes_date_only_event_without_route(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    event = _event(
        user_id,
        start_at=None,
        end_at=None,
        start_date=START.date(),
        end_date=START.date(),
        target=_exact_target(_poi("poi_date_only_event")),
    )
    constraints = _constraints(origin=ORIGIN)
    calls: list[object] = []

    result = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(event,),
        constraints=constraints,
        provider=_map_fact_provider(constraints=constraints, calls=calls),
    )

    assert result.draft.candidates == ()
    assert not any(isinstance(call, RouteRequest) for call in calls)
    assert not any(isinstance(call, WeatherRequest) for call in calls)


@pytest.mark.asyncio
async def test_map_fact_chain_resolves_any_branch_to_one_fixed_poi(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    branch = _poi(
        "poi_resolved_branch",
        name="测试咖啡",
        branch_name="市民中心店",
        poi_type=PoiType.CAFE,
    )
    item = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
    )
    constraints = _constraints(origin=ORIGIN)
    calls: list[object] = []

    result = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(item,),
        constraints=constraints,
        provider=_map_fact_provider(
            constraints=constraints,
            search_pois=(branch,),
            calls=calls,
        ),
    )

    assert result.draft.candidates[0].collection_item_ids == (item.id,)
    assert [fact.poi_id for fact in result.retrieval.pois] == [branch.poi_id]
    assert sum(isinstance(call, SearchPoiRequest) for call in calls) == 1
    assert sum(isinstance(call, RouteRequest) for call in calls) == 1


@pytest.mark.asyncio
async def test_ineligible_collections_never_trigger_route_queries(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    items = (
        _place(user_id, poi=_poi("other_city", city_code="guangzhou")),
        _place(
            user_id,
            poi=_poi("inactive"),
            status=CollectionStatus.ARCHIVED,
        ),
        _place(
            user_id,
            poi=None,
            status=CollectionStatus.PENDING_DETAILS,
        ),
        _place(
            user_id,
            title="明确排除",
            poi=_poi("excluded"),
            tags=("商场",),
        ),
        _event(
            user_id,
            start_at=END + timedelta(hours=1),
            end_at=END + timedelta(hours=2),
            target=_exact_target(_poi("late_event")),
        ),
    )
    constraints = _constraints(origin=ORIGIN, exclude=("商场",))
    calls: list[object] = []

    result = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=items,
        constraints=constraints,
        provider=_map_fact_provider(constraints=constraints, calls=calls),
    )

    assert result.draft.candidates == ()
    assert not any(isinstance(call, RouteRequest) for call in calls)
    assert not any(isinstance(call, WeatherRequest) for call in calls)


@pytest.mark.asyncio
async def test_high_cardinality_map_fact_routes_are_bounded(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    items = tuple(
        _place(user_id, title=f"地点 {index}", poi=_poi(f"poi_{index:03d}"))
        for index in range(100)
    )
    constraints = _constraints(origin=ORIGIN)
    calls: list[object] = []

    result = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=items,
        constraints=constraints,
        provider=_map_fact_provider(constraints=constraints, calls=calls),
    )

    route_calls = sum(isinstance(call, RouteRequest) for call in calls)
    assert len(result.draft.candidates) == MAX_PLAN_FACT_CANDIDATES
    assert route_calls <= MAX_PLAN_ROUTE_CALLS

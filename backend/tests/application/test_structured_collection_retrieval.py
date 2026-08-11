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
    PlanDraftService as ProductionPlanDraftService,
)
from app.application import (
    StructuredCollectionRetrievalError,
    StructuredCollectionRetrievalService,
)
from app.application.map_plan_facts import (
    MAX_PLAN_ROUTE_CALLS,
    MapPlanFactResolver,
)
from app.application.memories import MemoryPlanningService, MemoryService
from app.application.plan_experience import (
    ExistingPlanServicesExecutor,
    PlanGenerationOutcome,
    plan_failure_code_for_retrieval,
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
from app.domain.identifiers import (
    generate_collection_item_id,
    generate_memory_id,
    generate_user_id,
)
from app.domain.memories import (
    Memory,
    MemorySource,
    MemorySourceType,
    MemoryType,
)
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
from app.domain.plans import (
    ActivityArea,
    ExternalRecoveryCode,
    PlanConstraints,
    PlanPace,
    PlanPaceSource,
)
from app.domain.plans.drafts import (
    DraftCandidateFacts,
    DraftRouteFacts,
    PlanDraftFactSnapshot,
    PlanDraftOutcome,
    PlanOptionProposal,
    PlanOptionRole,
    PlanProposalItem,
    PlanProposalSet,
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
    location_confirmed: bool = True,
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
        place_target=(
            target
            if target is not None or not location_confirmed
            else _exact_target(_poi("default_event_poi"))
        ),
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
    selected_collection_item_ids: tuple[str, ...] = (),
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
        collection_only=bool(selected_collection_item_ids),
        selected_collection_item_ids=selected_collection_item_ids,
        created_at=NOW,
        expires_at=END + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_selected_collection_items_are_the_only_retrieval_candidates() -> None:
    user_id = generate_user_id()
    selected = _place(user_id, title="选中的收藏", poi=_poi("selected"))
    unselected = _place(user_id, title="未选中的收藏", poi=_poi("unselected"))
    service = StructuredCollectionRetrievalService(
        repository=ReadOnlyRepository([unselected, selected])
    )

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(selected_collection_item_ids=(selected.id,)),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )

    assert [decision.collection_item_ids for decision in result.decisions] == [(selected.id,)]


@pytest.mark.asyncio
async def test_missing_or_other_user_selected_collection_is_rejected() -> None:
    user_id = generate_user_id()
    other = _place(generate_user_id(), poi=_poi("private"))
    service = StructuredCollectionRetrievalService(repository=ReadOnlyRepository([other]))

    with pytest.raises(StructuredCollectionRetrievalError):
        await service.retrieve(
            user_id=user_id,
            constraints=_constraints(selected_collection_item_ids=(other.id,)),
            facts=PlanningFactSnapshot(),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_deleted_selected_collection_is_not_replaced() -> None:
    user_id = generate_user_id()
    deleted = _place(
        user_id,
        title="已删除",
        poi=_poi("deleted"),
        status=CollectionStatus.DELETED,
    )
    available = _place(user_id, title="其他收藏", poi=_poi("available"))

    result = await StructuredCollectionRetrievalService(
        repository=ReadOnlyRepository([deleted, available])
    ).retrieve(
        user_id=user_id,
        constraints=_constraints(selected_collection_item_ids=(deleted.id,)),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )

    assert result.included == ()
    assert [decision.collection_item_ids for decision in result.decisions] == [(deleted.id,)]


@pytest.mark.asyncio
async def test_selected_collection_still_obeys_plan_hard_constraints() -> None:
    user_id = generate_user_id()
    selected = _place(user_id, poi=_poi("selected-hard-rule", district="福田区"))

    result = await StructuredCollectionRetrievalService(
        repository=ReadOnlyRepository([selected])
    ).retrieve(
        user_id=user_id,
        constraints=_constraints(
            area=ActivityArea(districts=("南山区",)),
            selected_collection_item_ids=(selected.id,),
        ),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )

    assert result.included == ()
    assert CandidateReasonCode.DISTRICT_MISMATCH in result.decisions[0].reason_codes


@pytest.mark.asyncio
async def test_selected_exact_collection_treats_area_label_as_preference() -> None:
    user_id = generate_user_id()
    museum_poi = _poi("museum-selected", name="深圳市当代艺术与城市规划馆").model_copy(
        update={"business_area": "莲花山", "address": "福中路184号"}
    )
    library_poi = _poi("library-selected", name="深圳图书馆中心馆").model_copy(
        update={"business_area": "莲花山", "address": "福中一路2001号"}
    )
    selected = (
        _place(user_id, title=museum_poi.name, poi=museum_poi),
        _place(user_id, title=library_poi.name, poi=library_poi),
    )
    constraints = _constraints(
        area=ActivityArea(districts=("福田区",), labels=("市民中心",)),
        selected_collection_item_ids=tuple(item.id for item in selected),
    )

    result = await StructuredCollectionRetrievalService(
        repository=ReadOnlyRepository(list(selected))
    ).retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=PlanningFactSnapshot(
            pois=tuple(_known_poi_facts(poi) for poi in (museum_poi, library_poi))
        ),
        now=NOW,
    )
    first, second = ((item.id,) for item in selected)
    draft = PlanDraftService().generate(
        constraints=constraints,
        collections=result,
        facts=PlanDraftFactSnapshot(
            candidates=tuple(
                DraftCandidateFacts(
                    collection_item_ids=(item.id,),
                )
                for item in selected
            ),
            routes=(
                DraftRouteFacts(
                    from_collection_item_ids=first,
                    to_collection_item_ids=second,
                    duration_seconds=600,
                    distance_meters=1_000,
                    transport_mode=TransportMode.TRANSIT,
                ),
                DraftRouteFacts(
                    from_collection_item_ids=second,
                    to_collection_item_ids=first,
                    duration_seconds=600,
                    distance_meters=1_000,
                    transport_mode=TransportMode.TRANSIT,
                ),
            ),
        ),
    )

    assert {item.title for item in result.included} == {item.title for item in selected}
    assert all(
        CandidateReasonCode.AREA_MISMATCH not in item.reason_codes for item in result.included
    )
    assert draft.outcome is PlanDraftOutcome.GENERATED
    assert {item.title for item in draft.options[0].items} == {item.title for item in selected}


def _pace_memory(value: PlanPace) -> Memory:
    return Memory(
        id=generate_memory_id(),
        type=MemoryType.PACE_PREFERENCE,
        content=f"默认使用{value.value}节奏",
        value=value.value,
        source=MemorySource(
            type=MemorySourceType.EXPLICIT_USER,
            summary="由你明确设置并授权保存",
        ),
        confidence=100,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )


@pytest.mark.parametrize("inactive_state", ["deleted", "disabled", "expired"])
def test_pace_default_is_recomputed_after_memory_becomes_inactive(
    inactive_state: str,
) -> None:
    current = NOW + timedelta(hours=2)
    inactive = _pace_memory(PlanPace.RELAXED)
    if inactive_state == "deleted":
        inactive = inactive.model_copy(update={"deleted_at": NOW + timedelta(hours=1)})
    elif inactive_state == "disabled":
        inactive = inactive.model_copy(update={"disabled_at": NOW + timedelta(hours=1)})
    else:
        inactive = inactive.model_copy(update={"expires_at": NOW + timedelta(hours=1)})
    stale = _constraints().model_copy(
        update={
            "pace": PlanPace.RELAXED,
            "pace_source": PlanPaceSource.MEMORY_DEFAULT,
        }
    )

    effective, usages = MemoryPlanningService.apply_pace_default(
        constraints=stale,
        memories=tuple(memory for memory in (inactive,) if memory.is_effective(current)),
    )

    assert effective.pace is PlanPace.BALANCED
    assert effective.pace_source is PlanPaceSource.SYSTEM_DEFAULT
    assert usages == {}


def test_pace_default_uses_only_latest_effective_memory_and_never_user_request() -> None:
    relaxed = _pace_memory(PlanPace.RELAXED)
    packed = _pace_memory(PlanPace.PACKED).model_copy(
        update={"created_at": NOW + timedelta(minutes=1), "updated_at": NOW + timedelta(minutes=1)}
    )
    system_default = _constraints().model_copy(
        update={"pace_source": PlanPaceSource.SYSTEM_DEFAULT}
    )

    effective, usages = MemoryPlanningService.apply_pace_default(
        constraints=system_default,
        memories=(relaxed, packed),
    )
    explicit = system_default.model_copy(
        update={
            "pace": PlanPace.RELAXED,
            "pace_source": PlanPaceSource.USER_REQUEST,
        }
    )
    preserved, explicit_usages = MemoryPlanningService.apply_pace_default(
        constraints=explicit,
        memories=(packed,),
    )
    balanced, balanced_usages = MemoryPlanningService.apply_pace_default(
        constraints=system_default,
        memories=(_pace_memory(PlanPace.BALANCED),),
    )

    assert effective.pace is PlanPace.PACKED
    assert effective.pace_source is PlanPaceSource.MEMORY_DEFAULT
    assert set(usages) == {packed.id}
    assert preserved == explicit
    assert explicit_usages == {}
    assert balanced.pace is PlanPace.BALANCED
    assert balanced.pace_source is PlanPaceSource.SYSTEM_DEFAULT
    assert balanced_usages == {}


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


def _known_branch_facts(
    item: CollectionItem,
    poi: Poi,
    *,
    dynamic: PoiPlanningFacts | None = None,
) -> CollectionPlanningFacts:
    provider_facts = dynamic or _known_poi_facts(poi)
    values = provider_facts.model_dump(exclude={"provider", "poi_id"})
    return CollectionPlanningFacts(
        collection_item_id=item.id,
        formal_city=_constraints().city_scope,
        location_confirmed=True,
        coordinate=poi.coordinate,
        resolved_poi=poi,
        **values,
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


class PlanDraftService(ProductionPlanDraftService):
    """Adapt legacy retrieval fixtures to the now-required model proposal input."""

    def generate(self, *, constraints, collections, facts, **kwargs):
        included = collections.included
        keys = {
            f"candidate_{index}": decision.collection_item_ids
            for index, decision in enumerate(included)
        }
        if included:
            all_items = tuple(
                PlanProposalItem(candidate_key=key, visit_duration_seconds=3600) for key in keys
            )
            proposals = PlanProposalSet(
                options=(
                    PlanOptionProposal(
                        role=PlanOptionRole.MAIN,
                        items=all_items,
                        reason="retrieval integration fixture",
                    ),
                    PlanOptionProposal(
                        role=PlanOptionRole.ALTERNATIVE,
                        items=(
                            PlanProposalItem(
                                candidate_key=next(iter(keys)),
                                visit_duration_seconds=2700,
                            ),
                        ),
                        reason="retrieval integration fixture alternative 1",
                    ),
                    PlanOptionProposal(
                        role=PlanOptionRole.ALTERNATIVE,
                        items=(
                            PlanProposalItem(
                                candidate_key=next(reversed(keys)),
                                visit_duration_seconds=4500,
                            ),
                        ),
                        reason="retrieval integration fixture alternative 2",
                    ),
                )
            )
        else:
            proposals = None
        self._fixture_proposals = proposals
        self._fixture_keys = keys
        return super().generate(
            constraints=constraints,
            collections=collections,
            facts=facts,
            proposals=proposals,
            candidate_keys=keys,
            **kwargs,
        )

    def validate(self, **kwargs):
        kwargs.setdefault("proposals", self._fixture_proposals)
        kwargs.setdefault("candidate_keys", self._fixture_keys)
        return super().validate(**kwargs)


def _service(
    items: list[CollectionItem],
    *,
    provider: StubMapProvider | None = None,
) -> tuple[StructuredCollectionRetrievalService, ReadOnlyRepository]:
    repository = ReadOnlyRepository(items)
    return (
        StructuredCollectionRetrievalService(
            repository=repository,  # type: ignore[arg-type]
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
async def test_active_exact_place_with_only_core_poi_facts_is_planning_retrievable() -> None:
    user_id = generate_user_id()
    poi = Poi(
        provider=PoiProvider.AMAP,
        poi_id="poi_core_only",
        name="核心事实地点",
        city_code="shenzhen",
        coordinate=SHENZHEN_COORDINATE,
        poi_type=PoiType.OTHER,
    )
    place = _place(user_id, poi=poi)
    service, _repository = _service([place])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(area=None, origin=ORIGIN),
        facts=PlanningFactSnapshot(pois=(_known_poi_facts(poi),)),
        now=NOW,
    )

    assert tuple(decision.collection_item_ids for decision in result.included) == ((place.id,),)


@pytest.mark.asyncio
async def test_only_effective_confirmed_memory_scores_matching_candidates() -> None:
    user_id = generate_user_id()
    indoor_poi = _poi("poi_memory_indoor", name="室内艺术馆")
    park_poi = _poi("poi_memory_park", name="城市公园", poi_type=PoiType.PARK)
    indoor = _place(user_id, poi=indoor_poi, tags=("室内", "艺术"))
    park = _place(user_id, poi=park_poi, tags=("户外", "散步"))
    service, _repository = _service([park, indoor])
    active = Memory(
        id=generate_memory_id(),
        type=MemoryType.POSITIVE_PREFERENCE,
        content="喜欢室内空间",
        value="室内",
        source=MemorySource(
            type=MemorySourceType.EXPLICIT_USER,
            summary="由你明确设置并授权保存",
        ),
        confidence=100,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )
    disabled = active.model_copy(
        update={
            "id": generate_memory_id(),
            "type": MemoryType.NEGATIVE_PREFERENCE,
            "disabled_at": NOW + timedelta(minutes=1),
        }
    )
    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(
            pois=(
                _known_poi_facts(indoor_poi),
                _known_poi_facts(park_poi),
            )
        ),
        now=NOW + timedelta(hours=1),
        memories=(active, disabled),
    )
    scores = {
        decision.collection_item_ids: (
            decision.preference_score,
            decision.applied_memory_ids,
        )
        for decision in result.included
    }
    assert scores[(indoor.id,)] == (1, (active.id,))
    assert scores[(park.id,)] == (0, ())


@pytest.mark.asyncio
async def test_thousand_matching_memories_use_one_bounded_stable_ranking_basis() -> None:
    user_id = generate_user_id()
    indoor_poi = _poi("poi_many_memories", name="室内艺术馆")
    park_poi = _poi("poi_many_memories_park", name="城市公园", poi_type=PoiType.PARK)
    indoor = _place(user_id, poi=indoor_poi)
    park = _place(user_id, poi=park_poi)
    service = StructuredCollectionRetrievalService(repository=ReadOnlyRepository([indoor, park]))
    memories = tuple(
        Memory(
            id=generate_memory_id(),
            type=MemoryType.POSITIVE_PREFERENCE,
            content=f"第 {index} 条室内偏好",
            value="室内",
            source=MemorySource(
                type=MemorySourceType.EXPLICIT_USER,
                summary="由你明确设置并授权保存",
            ),
            confidence=100,
            created_at=NOW,
            updated_at=NOW,
            version=1,
        )
        for index in range(1000)
    )

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(pois=(_known_poi_facts(indoor_poi), _known_poi_facts(park_poi))),
        now=NOW + timedelta(hours=1),
        memories=memories,
    )

    scores = {
        decision.collection_item_ids: (
            decision.preference_score,
            decision.applied_memory_ids,
        )
        for decision in result.included
    }
    assert scores[(indoor.id,)] == (1, ())
    assert all(-1 <= score <= 1 for score, _memory_ids in scores.values())
    assert all(len(memory_ids) <= 1 for _score, memory_ids in scores.values())


@pytest.mark.asyncio
async def test_negative_memory_stably_wins_conflicting_positive_memory() -> None:
    user_id = generate_user_id()
    indoor_poi = _poi("poi_memory_conflict", name="安静室内艺术馆")
    park_poi = _poi("poi_memory_conflict_park", name="城市公园", poi_type=PoiType.PARK)
    indoor = _place(user_id, poi=indoor_poi)
    park = _place(user_id, poi=park_poi)
    base = Memory(
        id="mem_00000000000000000000000000000001",
        type=MemoryType.POSITIVE_PREFERENCE,
        content="喜欢安静空间",
        value="安静",
        source=MemorySource(
            type=MemorySourceType.EXPLICIT_USER,
            summary="由你明确设置并授权保存",
        ),
        confidence=100,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )
    negative = base.model_copy(
        update={
            "id": "mem_00000000000000000000000000000002",
            "type": MemoryType.NEGATIVE_PREFERENCE,
            "content": "避开安静空间",
        }
    )
    result = await StructuredCollectionRetrievalService(
        repository=ReadOnlyRepository([indoor, park])
    ).retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(pois=(_known_poi_facts(indoor_poi), _known_poi_facts(park_poi))),
        now=NOW + timedelta(hours=1),
        memories=(base, negative),
    )
    scores = {
        decision.collection_item_ids: (
            decision.preference_score,
            decision.applied_memory_ids,
        )
        for decision in result.included
    }
    assert scores[(indoor.id,)] == (-1, (negative.id,))
    assert scores[(park.id,)] == (0, ())


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
    constraints = _constraints(origin=ORIGIN).model_copy(update={"expires_at": expiry})

    valid_service, valid_repository = _service(
        [brand],
        provider=_branch_provider((branch,), district="福田区"),
    )
    valid = await valid_service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=PlanningFactSnapshot(
            collections=(_known_branch_facts(brand, branch),),
            pois=(_known_poi_facts(branch),),
        ),
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
    )
    with pytest.raises(asyncio.CancelledError) as repository_error:
        await repository_service.retrieve(
            user_id=user_id,
            constraints=_constraints(),
            facts=PlanningFactSnapshot(),
            now=NOW,
        )
    assert repository_error.value is repository_cancelled

    brand = _place(user_id, title="测试咖啡", target=_brand_target())
    map_service, repository = _service([brand])
    result = await map_service.retrieve(
        user_id=user_id,
        constraints=_constraints(area=None, origin=ORIGIN),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )
    assert CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT in (result.decisions[0].reason_codes)
    assert repository.calls == [(user_id, True)]


@pytest.mark.asyncio
async def test_formal_city_controls_eligibility_and_city_hint_never_substitutes() -> None:
    user_id = generate_user_id()
    other_city = _place(
        user_id,
        poi=_poi("poi_guangzhou", city_code="guangzhou", district="天河区"),
        city_hint="深圳",
    )
    pending_city = _event(
        user_id,
        title="深圳标题但城市待确认",
        city_hint="深圳",
        location_confirmed=False,
    )
    other_city_event = _event(
        user_id,
        title="广州活动",
        city_hint="深圳",
        target=_exact_target(_poi("guangzhou_event", city_code="guangzhou", district="天河区")),
    )
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
        decision.collection_item_ids[0]: decision.reason_codes for decision in result.decisions
    }
    assert CandidateReasonCode.CITY_MISMATCH in reasons[other_city.id]
    assert CandidateReasonCode.CITY_UNCONFIRMED in reasons[pending_city.id]
    assert CandidateReasonCode.LOCATION_UNCONFIRMED in reasons[pending_city.id]
    assert CandidateReasonCode.CITY_MISMATCH in reasons[other_city_event.id]
    assert repository.items[0].city_hint == "深圳"
    assert repository.items[1].city_hint == "深圳"
    assert repository.items[2].city_hint == "深圳"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item_kind", "expected_code"),
    [
        ("none", "ADD_COLLECTIONS"),
        ("location", "LOCATION_UNCONFIRMED"),
        ("event_time", "EVENT_TIME_UNKNOWN"),
        ("other_city", "CITY_MISMATCH"),
        ("provider", "ROUTE_PROVIDER_FAILED"),
    ],
)
async def test_plan_failure_preserves_authoritative_retrieval_reason(
    item_kind: str,
    expected_code: str,
) -> None:
    user_id = generate_user_id()
    items: list[CollectionItem] = []
    facts = PlanningFactSnapshot()
    if item_kind == "location":
        items.append(_place(user_id, poi=None))
    elif item_kind == "event_time":
        items.append(
            _event(
                user_id,
                start_at=None,
                end_at=None,
                target=_exact_target(_poi("event_time")),
            )
        )
    elif item_kind == "other_city":
        poi = _poi("other_city_reason", city_code="guangzhou")
        items.append(_place(user_id, poi=poi))
        facts = PlanningFactSnapshot(pois=(_known_poi_facts(poi),))
    elif item_kind == "provider":
        poi = _poi("provider_reason")
        items.append(_place(user_id, poi=poi))
        facts = PlanningFactSnapshot(
            pois=(
                PoiPlanningFacts(
                    provider=poi.provider,
                    poi_id=poi.poi_id,
                    route=RouteAssessment.PROVIDER_FAILED,
                    weather=WeatherAssessment.COMPATIBLE,
                    availability=AvailabilityAssessment.AVAILABLE,
                ),
            )
        )

    service, _ = _service(items)
    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=facts,
        now=NOW,
    )

    assert (
        plan_failure_code_for_retrieval(
            recovery_code=ExternalRecoveryCode.NO_EXECUTABLE_DRAFT,
            collections=result,
        )
        == expected_code
    )


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
async def test_exact_event_target_stays_confirmed_while_time_is_pending() -> None:
    user_id = generate_user_id()
    event = _event(
        user_id,
        start_at=None,
        end_at=None,
        status=CollectionStatus.PENDING_DETAILS,
        target=_exact_target(_poi("pending_event_time")),
    )
    service, _ = _service([event])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=PlanningFactSnapshot(),
        now=NOW,
    )

    decision = result.decisions[0]
    assert CandidateReasonCode.EVENT_TIME_UNKNOWN in decision.reason_codes
    assert CandidateReasonCode.LOCATION_UNCONFIRMED not in decision.reason_codes
    assert CandidateReasonCode.CITY_UNCONFIRMED not in decision.reason_codes


@pytest.mark.asyncio
async def test_date_range_event_intersects_plan_date_without_exact_time() -> None:
    user_id = generate_user_id()
    date_only = _event(
        user_id,
        title="日期范围展览",
        start_at=None,
        end_at=None,
        start_date=date(2026, 7, 25),
        end_date=date(2026, 7, 31),
        status=CollectionStatus.ACTIVE,
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
    assert decision.outcome is CandidateOutcome.INCLUDED
    assert CandidateReasonCode.EVENT_TIME_UNKNOWN not in decision.reason_codes
    assert result.included == (decision,)


@pytest.mark.asyncio
async def test_date_range_event_outside_plan_date_is_conflict_or_ended() -> None:
    user_id = generate_user_id()
    future = _event(
        user_id,
        title="尚未开始",
        start_at=None,
        end_at=None,
        start_date=date(2026, 7, 26),
        end_date=date(2026, 7, 31),
    )
    ended = _event(
        user_id,
        title="已经结束",
        start_at=None,
        end_at=None,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 24),
    )
    service, _ = _service([future, ended])
    facts = PlanningFactSnapshot(
        collections=tuple(_known_event_facts(item) for item in (future, ended))
    )

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(),
        facts=facts,
        now=NOW,
    )
    by_title = {item.title: item for item in result.decisions}

    assert by_title["尚未开始"].reason_codes == (CandidateReasonCode.TIME_WINDOW_CONFLICT,)
    assert by_title["已经结束"].reason_codes == (CandidateReasonCode.EVENT_ENDED,)


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
    assert with_budget.included[0].reason_codes == (CandidateReasonCode.PRICE_UNKNOWN,)
    budget_draft = PlanDraftService().generate(
        constraints=budget_constraints,
        collections=with_budget,
        facts=_draft_facts(
            collection_item_ids=decision.collection_item_ids,
            route_duration_seconds=decision.route_duration_seconds,
            route_distance_meters=decision.route_distance_meters,
        ),
    )
    assert budget_draft.outcome is PlanDraftOutcome.GENERATED
    assert budget_draft.options[0].total_cost_amount is None
    assert budget_draft.options[0].risk_codes == (PlanRiskCode.BUDGET_UNVERIFIED,)

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
        CandidateReasonCode.WEATHER_CONFLICT,
        CandidateReasonCode.WEATHER_PROVIDER_FAILED,
    }:
        assert result.decisions[0].outcome is CandidateOutcome.INCLUDED
    else:
        assert result.decisions[0].outcome is CandidateOutcome.EXCLUDED


@pytest.mark.asyncio
async def test_unknown_route_weather_and_opening_are_non_blocking() -> None:
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
    assert decision.outcome is CandidateOutcome.INCLUDED
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
    assert (CandidateReasonCode.ROUTE_EXCEEDS_TIME_WINDOW in decision.reason_codes) is (
        expected_outcome is CandidateOutcome.EXCLUDED
    )


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
        facts=PlanningFactSnapshot(collections=(_known_event_facts(event, duration=600),)),
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
            CandidateOutcome.INCLUDED,
        ),
        (
            RouteAssessment.PROVIDER_FAILED,
            CandidateReasonCode.ROUTE_PROVIDER_FAILED,
            CandidateOutcome.EXCLUDED,
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
    facts = PlanningFactSnapshot(
        collections=(_known_branch_facts(brand, branch),),
        pois=(_known_poi_facts(branch),),
    )
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
    assert facts.collections[0].resolved_poi == branch


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
            collections=(
                _known_branch_facts(
                    brand,
                    near,
                    dynamic=_known_poi_facts(near, duration=300),
                ),
            ),
            pois=(_known_poi_facts(far, duration=1200), _known_poi_facts(near, duration=300)),
        ),
        now=NOW,
    )

    assert result.included[0].poi is not None
    assert result.included[0].poi.poi_id == near.poi_id
    assert calls == []
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
        facts=PlanningFactSnapshot(
            collections=(_known_branch_facts(brand, branch),),
            pois=(_known_poi_facts(branch),),
        ),
        now=NOW,
    )

    assert result.included[0].poi is not None
    assert result.included[0].poi.poi_id == branch.poi_id
    assert provider_calls == []
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
        dynamic = dynamic.model_copy(update={"availability": AvailabilityAssessment.UNAVAILABLE})
    constraints = _constraints(
        area=None,
        origin=ORIGIN,
        budget=Decimal("20") if failed_rule == "budget" else None,
    )
    service, _ = _service([brand], provider=_branch_provider((branch,)))

    result = await service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=PlanningFactSnapshot(
            collections=(_known_branch_facts(brand, branch, dynamic=dynamic),),
            pois=(dynamic,),
        ),
        now=NOW,
    )

    assert result.decisions[0].outcome is (
        CandidateOutcome.INCLUDED if failed_rule == "weather" else CandidateOutcome.EXCLUDED
    )
    expected_reason = {
        "weather": CandidateReasonCode.WEATHER_CONFLICT,
        "availability": CandidateReasonCode.PLACE_UNAVAILABLE,
        "budget": CandidateReasonCode.BUDGET_EXCEEDED,
    }[failed_rule]
    assert expected_reason in result.decisions[0].reason_codes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        CandidateReasonCode.BRANCH_NOT_FOUND,
        CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT,
        CandidateReasonCode.BRANCH_PROVIDER_FAILED,
    ],
)
async def test_any_branch_failure_modes_have_stable_safe_reasons(
    reason: CandidateReasonCode,
) -> None:
    user_id = generate_user_id()
    brand = _place(user_id, title="测试咖啡", target=_brand_target(), price=Decimal("35"))
    service, _ = _service([brand])

    result = await service.retrieve(
        user_id=user_id,
        constraints=_constraints(area=None, origin=ORIGIN),
        facts=PlanningFactSnapshot(
            collections=(
                CollectionPlanningFacts(
                    collection_item_id=brand.id,
                    branch_failure_reason=reason,
                ),
            )
        ),
        now=NOW,
    )

    assert reason in result.decisions[0].reason_codes
    assert not (
        {
            CandidateReasonCode.BRANCH_NOT_FOUND,
            CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT,
            CandidateReasonCode.BRANCH_PROVIDER_FAILED,
        }
        - {reason}
    ).intersection(result.decisions[0].reason_codes)
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
            collections=(
                _known_branch_facts(
                    brand,
                    branch,
                    dynamic=PoiPlanningFacts(
                        provider=branch.provider,
                        poi_id=branch.poi_id,
                        route=RouteAssessment.UNREACHABLE,
                        weather=WeatherAssessment.COMPATIBLE,
                        availability=AvailabilityAssessment.AVAILABLE,
                    ),
                ),
            ),
            pois=(
                PoiPlanningFacts(
                    provider=branch.provider,
                    poi_id=branch.poi_id,
                    route=RouteAssessment.UNREACHABLE,
                    weather=WeatherAssessment.COMPATIBLE,
                    availability=AvailabilityAssessment.AVAILABLE,
                ),
            ),
        ),
        now=NOW,
    )

    assert result.decisions[0].outcome is CandidateOutcome.EXCLUDED
    assert CandidateReasonCode.ROUTE_UNREACHABLE in result.decisions[0].reason_codes


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
        facts=PlanningFactSnapshot(
            collections=(_known_branch_facts(brand, poi),),
            pois=(_known_poi_facts(poi),),
        ),
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
    search_timeout: bool = False,
    weather_timeout: bool = False,
    calls: list[object] | None = None,
) -> StubMapProvider:
    route_request = RouteRequest(
        city=constraints.city_scope,
        origin=constraints.origin or SHENZHEN_COORDINATE,
        destination=SHENZHEN_COORDINATE,
        mode=(
            constraints.transport_modes[0] if constraints.transport_modes else TransportMode.TRANSIT
        ),
    )
    weather_request = WeatherRequest(
        city=constraints.city_scope,
        on_date=constraints.start_at.date(),
    )
    search_request = SearchPoiRequest(
        query="测试咖啡",
        city=constraints.city_scope,
        district=constraints.area.districts[0] if constraints.area else None,
        location=constraints.origin,
    )
    search_results = {}
    if search_pois:
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
        timeout_requests=tuple(
            request
            for request, timed_out in (
                (search_request, search_timeout),
                (weather_request, weather_timeout),
            )
            if timed_out
        ),
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
    assert sum(isinstance(call, RouteRequest) for call in calls) == 0


@pytest.mark.asyncio
async def test_one_hundred_exact_collections_do_not_prefetch_origin_routes(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    items = tuple(
        _place(user_id, title=f"准确收藏 {index}", poi=_poi(f"exact-{index}"))
        for index in range(100)
    )
    constraints = _constraints(origin=ORIGIN)
    calls: list[object] = []

    facts = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=items,
        constraints=constraints,
        provider=_map_fact_provider(constraints=constraints, calls=calls),
    )

    assert len(facts.draft.candidates) == 100
    assert not any(isinstance(call, RouteRequest) for call in calls)


@pytest.mark.asyncio
async def test_proposal_routes_fetch_only_the_deduplicated_used_edge(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    item = _place(user_id, poi=_poi("used-exact"))
    constraints = _constraints(origin=ORIGIN)
    calls: list[object] = []
    provider = _map_fact_provider(
        constraints=constraints,
        weather_timeout=True,
        calls=calls,
    )
    database = Database(retrieval_database)
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(
            user_id=user_id,
            user=User(id=user_id, mode=UserMode.REAL, created_at=NOW),
        )
        await repository.add_collection_item(user_id=user_id, item=item)
        await session.commit()
    proposals = PlanProposalSet(
        options=tuple(
            PlanOptionProposal(
                role=PlanOptionRole.MAIN if index == 0 else PlanOptionRole.ALTERNATIVE,
                items=(
                    PlanProposalItem(
                        candidate_key="candidate_0",
                        visit_duration_seconds=1800 + index * 600,
                    ),
                ),
                reason=f"方案 {index}",
            )
            for index in range(3)
        )
    )
    async with database.session() as session:
        resolver = MapPlanFactResolver(
            session=session,
            map_provider=provider,
            matching_policy=Settings(_env_file=None, app_env="test").place_matching_policy(),
        )
        base = await resolver.resolve(user_id=user_id, constraints=constraints)
        assert not any(isinstance(call, RouteRequest) for call in calls)
        resolved = await resolver.resolve_proposal_routes(
            proposals=proposals,
            candidate_keys={"candidate_0": (item.id,)},
            base=base.draft,
        )
    await database.close()

    assert sum(isinstance(call, RouteRequest) for call in calls) == 1
    assert len(resolved.routes) == 1
    assert resolved.weather_status is WeatherAssessment.PROVIDER_FAILED
    assert resolved.weather_source == "amap"
    assert resolved.weather_queried_at is not None
    assert resolved.weather_summary == "The map provider request timed out."


@pytest.mark.asyncio
async def test_map_fact_chain_includes_date_range_event_with_visit_duration(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    poi = _poi("poi_date_only_event").model_copy(
        update={"district": None, "business_area": None, "address": None}
    )
    event = _event(
        user_id,
        start_at=None,
        end_at=None,
        start_date=START.date(),
        end_date=START.date(),
        target=_exact_target(poi),
    )
    constraints = _constraints(origin=ORIGIN, area=None)
    calls: list[object] = []

    result = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(event,),
        constraints=constraints,
        provider=_map_fact_provider(constraints=constraints, calls=calls),
    )

    assert result.draft.candidates[0].collection_item_ids == (event.id,)
    assert result.draft.candidates[0].event_start_at is None
    assert result.draft.candidates[0].event_end_at is None
    assert sum(isinstance(call, RouteRequest) for call in calls) == 0
    assert sum(isinstance(call, WeatherRequest) for call in calls) == 0
    assert result.draft.weather_status is None
    assert result.draft.weather_source is None
    assert result.draft.weather_queried_at is None
    assert result.draft.weather_summary is None

    retrieval_service, _ = _service([event])
    retrieval = await retrieval_service.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=result.retrieval,
        now=NOW,
    )
    draft = PlanDraftService().generate(
        constraints=constraints,
        collections=retrieval,
        facts=result.draft,
    )

    assert draft.outcome is PlanDraftOutcome.NOT_GENERATED


@pytest.mark.asyncio
async def test_weather_is_not_queried_before_model_proposal(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    poi = _poi("poi_weather_failure").model_copy(update={"opening_hours_summary": "开放时间已确认"})
    item = _place(user_id, poi=poi)
    constraints = _constraints(origin=ORIGIN)
    facts = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(item,),
        constraints=constraints,
        provider=_map_fact_provider(
            constraints=constraints,
            weather_timeout=True,
        ),
    )
    retrieval, _ = _service([item])
    collections = await retrieval.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts.retrieval,
        now=NOW,
    )
    draft = PlanDraftService().generate(
        constraints=constraints,
        collections=collections,
        facts=facts.draft,
    )

    assert collections.decisions[0].outcome is CandidateOutcome.INCLUDED
    assert draft.outcome is PlanDraftOutcome.NOT_GENERATED
    assert facts.draft.weather_status is None


@pytest.mark.asyncio
async def test_area_only_plan_never_queries_or_fakes_an_origin_route(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    poi = _poi("poi_area_only").model_copy(update={"opening_hours_summary": "开放时间已确认"})
    item = _place(user_id, poi=poi)
    constraints = _constraints(origin=None)
    calls: list[object] = []
    facts = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(item,),
        constraints=constraints,
        provider=_map_fact_provider(constraints=constraints, calls=calls),
    )
    retrieval, _ = _service([item])
    collections = await retrieval.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts.retrieval,
        now=NOW,
    )
    draft = PlanDraftService().generate(
        constraints=constraints,
        collections=collections,
        facts=facts.draft,
    )

    assert not any(isinstance(call, RouteRequest) for call in calls)
    assert collections.decisions[0].reason_codes == (
        CandidateReasonCode.ROUTE_UNKNOWN,
        CandidateReasonCode.WEATHER_UNKNOWN,
    )
    assert draft.outcome is PlanDraftOutcome.GENERATED
    route = draft.options[0].items[0].inbound_route
    assert route.duration_seconds is None
    assert route.distance_meters is None
    assert PlanRiskCode.ROUTE_UNKNOWN in draft.options[0].risk_codes


@pytest.mark.asyncio
async def test_one_failed_origin_route_excludes_only_that_candidate(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    failed_poi = _poi("poi_route_failed").model_copy(
        update={
            "opening_hours_summary": "开放时间已确认",
            "coordinate": Coordinate(
                latitude=22.54,
                longitude=114.04,
                coordinate_system=CoordinateSystem.GCJ_02,
            ),
        }
    )
    working_poi = _poi("poi_route_working").model_copy(
        update={
            "opening_hours_summary": "开放时间已确认",
            "coordinate": Coordinate(
                latitude=22.55,
                longitude=114.05,
                coordinate_system=CoordinateSystem.GCJ_02,
            ),
        }
    )
    failed = _place(user_id, title="路线失败", poi=failed_poi)
    working = _place(user_id, title="路线成功", poi=working_poi)
    constraints = _constraints(origin=ORIGIN)
    mode = TransportMode.TRANSIT
    route_request = RouteRequest(
        city=constraints.city_scope,
        origin=ORIGIN,
        destination=working_poi.coordinate,
        mode=mode,
    )
    weather_request = WeatherRequest(
        city=constraints.city_scope,
        on_date=constraints.start_at.date(),
    )
    provider = StubMapProvider(
        route_results={
            route_request: RouteResult(
                city_code=constraints.city_code.value,
                origin=route_request.origin,
                destination=route_request.destination,
                mode=mode,
                distance_meters=900,
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
    )
    facts = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(failed, working),
        constraints=constraints,
        provider=provider,
    )
    retrieval, _ = _service([failed, working])
    collections = await retrieval.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts.retrieval,
        now=NOW,
    )
    draft = PlanDraftService().generate(
        constraints=constraints,
        collections=collections,
        facts=facts.draft,
    )

    assert {candidate.title for candidate in collections.included} == {"路线失败", "路线成功"}
    assert collections.excluded == ()
    assert facts.draft.routes == ()
    assert draft.outcome is PlanDraftOutcome.NOT_GENERATED


@pytest.mark.asyncio
async def test_all_failed_origin_routes_report_the_route_reason(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    poi = _poi("poi_all_routes_failed").model_copy(
        update={"opening_hours_summary": "开放时间已确认"}
    )
    item = _place(user_id, poi=poi)
    constraints = _constraints(origin=ORIGIN)
    weather_request = WeatherRequest(
        city=constraints.city_scope,
        on_date=constraints.start_at.date(),
    )
    facts = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(item,),
        constraints=constraints,
        provider=StubMapProvider(
            weather_results={
                weather_request: WeatherResult(
                    city_code=constraints.city_code.value,
                    on_date=constraints.start_at.date(),
                    condition="晴",
                    temperature_celsius=28,
                )
            }
        ),
    )
    retrieval, _ = _service([item])
    collections = await retrieval.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts.retrieval,
        now=NOW,
    )
    draft = PlanDraftService().generate(
        constraints=constraints,
        collections=collections,
        facts=facts.draft,
    )

    assert draft.outcome is PlanDraftOutcome.NOT_GENERATED
    assert collections.included[0].title == item.title
    assert draft.exclusions == ()


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
    assert result.retrieval.collections[0].resolved_poi == branch
    assert sum(isinstance(call, SearchPoiRequest) for call in calls) == 1
    assert sum(isinstance(call, RouteRequest) for call in calls) == 1


@pytest.mark.asyncio
async def test_selected_any_branch_resolves_without_literal_area_label_match(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    chosen = _poi(
        "a-nanshan",
        district="南山区",
        name="测试咖啡",
        branch_name="蛇口店",
        poi_type=PoiType.CAFE,
    ).model_copy(update={"business_area": "蛇口", "address": "望海路1号"})
    candidates = (
        _poi(
            "outside-futian",
            name="测试咖啡",
            branch_name="福田店",
            poi_type=PoiType.CAFE,
        ),
        chosen,
        _poi(
            "b-nanshan",
            district="南山区",
            name="测试咖啡",
            branch_name="科技园店",
            poi_type=PoiType.CAFE,
        ),
    )
    item = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
    )
    constraints = _constraints(
        area=ActivityArea(districts=("南山区",), labels=("海上世界",)),
        origin=ORIGIN,
        selected_collection_item_ids=(item.id,),
    )
    calls: list[object] = []
    facts = await _resolve_map_facts(
        database_url=retrieval_database,
        user_id=user_id,
        items=(item,),
        constraints=constraints,
        provider=_map_fact_provider(
            constraints=constraints,
            search_pois=candidates,
            calls=calls,
        ),
    )
    retrieval, _ = _service([item])
    collections = await retrieval.retrieve(
        user_id=user_id,
        constraints=constraints,
        facts=facts.retrieval,
        now=NOW,
    )
    draft = PlanDraftService().generate(
        constraints=constraints,
        collections=collections,
        facts=facts.draft,
    )

    assert collections.included[0].poi == chosen
    assert CandidateReasonCode.AREA_MISMATCH not in collections.included[0].reason_codes
    assert sum(isinstance(call, SearchPoiRequest) for call in calls) == 1
    assert draft.outcome is PlanDraftOutcome.GENERATED
    source = draft.options[0].items[0].source
    assert source.concrete_poi == chosen
    assert source.any_branch_collection_item_ids == (item.id,)
    assert source.poi_queried_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("search_pois", "search_timeout", "expected_reason"),
    [
        ((), False, CandidateReasonCode.BRANCH_NOT_FOUND),
        (
            (_poi("poi_branch_weak", name="不相关地点"),),
            False,
            CandidateReasonCode.BRANCH_EVIDENCE_INSUFFICIENT,
        ),
        ((), True, CandidateReasonCode.BRANCH_PROVIDER_FAILED),
    ],
)
async def test_map_fact_and_retrieval_chain_freezes_one_branch_failure(
    retrieval_database: str,
    search_pois: tuple[Poi, ...],
    search_timeout: bool,
    expected_reason: CandidateReasonCode,
) -> None:
    user_id = generate_user_id()
    item = _place(
        user_id,
        title="测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
    )
    constraints = _constraints(area=None, origin=ORIGIN)
    calls: list[object] = []
    provider = _map_fact_provider(
        constraints=constraints,
        search_pois=search_pois,
        search_timeout=search_timeout,
        calls=calls,
    )
    database = Database(retrieval_database)
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(
            user_id=user_id,
            user=User(id=user_id, mode=UserMode.REAL, created_at=NOW),
        )
        await repository.add_collection_item(user_id=user_id, item=item)
        await session.commit()
    async with database.session() as session:
        facts = await MapPlanFactResolver(
            session=session,
            map_provider=provider,
            matching_policy=Settings(
                _env_file=None,
                app_env="test",
            ).place_matching_policy(),
        ).resolve(user_id=user_id, constraints=constraints)
        result = await StructuredCollectionRetrievalService(
            repository=SqlAlchemyCollectionRepository(session)
        ).retrieve(
            user_id=user_id,
            constraints=constraints,
            facts=facts.retrieval,
            now=NOW,
        )
    await database.close()

    assert facts.retrieval.collections[0].branch_failure_reason is expected_reason
    assert expected_reason in result.decisions[0].reason_codes
    assert sum(isinstance(call, SearchPoiRequest) for call in calls) == 1


@pytest.mark.asyncio
async def test_existing_plan_executor_reuses_one_frozen_any_branch_match(
    retrieval_database: str,
) -> None:
    user_id = generate_user_id()
    branch = _poi(
        "poi_executor_branch",
        name="测试咖啡",
        branch_name="市民中心店",
        poi_type=PoiType.CAFE,
    ).model_copy(update={"opening_hours_summary": "10:00-22:00"})
    item = _place(
        user_id,
        title="A测试咖啡",
        target=_brand_target(),
        tags=("咖啡",),
    )
    exact_poi = branch
    exact = _place(user_id, title="城市展览馆", poi=exact_poi)
    current = datetime.now(UTC)
    constraints = _constraints(area=None, origin=ORIGIN).model_copy(
        update={
            "start_at": current + timedelta(hours=1),
            "end_at": current + timedelta(hours=7),
            "created_at": current,
            "expires_at": current + timedelta(days=1),
            "pace": PlanPace.PACKED,
            "include": ("测试咖啡",),
            "original_request": "周六从前海出发，先看展再找一家安静咖啡店",
        }
    )
    calls: list[object] = []
    provider = _map_fact_provider(
        constraints=constraints,
        search_pois=(branch,),
        calls=calls,
    )
    database = Database(retrieval_database)
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(
            user_id=user_id,
            user=User(id=user_id, mode=UserMode.REAL, created_at=NOW),
        )
        await repository.add_collection_item(user_id=user_id, item=item)
        await repository.add_collection_item(user_id=user_id, item=exact)
        await MemoryService(session).create_explicit(
            user_id=user_id,
            memory_type=MemoryType.PACE_PREFERENCE,
            content="以后偏好轻松节奏",
            value="relaxed",
            expires_at=None,
            explicit_authorization=True,
            location_granularity=None,
            client_idempotency_key="executor-pace-memory",
        )
        await session.commit()
    async with database.session() as session:
        resolved_constraints: list[PlanConstraints] = []
        delegate = MapPlanFactResolver(
            session=session,
            map_provider=provider,
            matching_policy=Settings(
                _env_file=None,
                app_env="test",
            ).place_matching_policy(),
        )

        class CapturingFacts:
            async def resolve(self, *, user_id: str, constraints: PlanConstraints):
                resolved_constraints.append(constraints)
                return await delegate.resolve(user_id=user_id, constraints=constraints)

            async def resolve_proposal_routes(self, **kwargs):
                return await delegate.resolve_proposal_routes(**kwargs)

        proposal_inputs: list[dict[str, Any]] = []

        class FixedProposals:
            async def propose(self, **kwargs):
                proposal_inputs.append(kwargs)
                keys = tuple(item.candidate_key for item in kwargs["candidates"])
                return PlanProposalSet(
                    options=(
                        PlanOptionProposal(
                            role=PlanOptionRole.MAIN,
                            items=tuple(
                                PlanProposalItem(
                                    candidate_key=key,
                                    visit_duration_seconds=3600,
                                )
                                for key in keys
                            ),
                            reason="executor integration",
                        ),
                        PlanOptionProposal(
                            role=PlanOptionRole.ALTERNATIVE,
                            items=(
                                PlanProposalItem(
                                    candidate_key=keys[0],
                                    visit_duration_seconds=2700,
                                ),
                            ),
                            reason="executor alternative 1",
                        ),
                        PlanOptionProposal(
                            role=PlanOptionRole.ALTERNATIVE,
                            items=(
                                PlanProposalItem(
                                    candidate_key=keys[-1],
                                    visit_duration_seconds=4500,
                                ),
                            ),
                            reason="executor alternative 2",
                        ),
                    )
                )

        result = await ExistingPlanServicesExecutor(
            session=session,
            map_provider=provider,
            matching_policy=Settings(
                _env_file=None,
                app_env="test",
            ).place_matching_policy(),
            facts=CapturingFacts(),  # type: ignore[arg-type]
            proposals=FixedProposals(),  # type: ignore[arg-type]
        ).execute(user_id=user_id, constraints=constraints, approval=None)
    assert result.outcome is PlanGenerationOutcome.DRAFT
    assert proposal_inputs[0]["request"] == constraints.original_request
    proposal_tags = tuple(candidate.tags for candidate in proposal_inputs[0]["candidates"])
    assert any("咖啡" in tags for tags in proposal_tags), proposal_tags
    assert resolved_constraints == [constraints]
    assert resolved_constraints[0].pace is PlanPace.PACKED
    assert result.memory_usages == {}
    assert result.draft is not None
    planned = tuple(
        draft_item
        for option in result.draft.options
        for draft_item in option.items
        if item.id in draft_item.source.collection_item_ids
    )
    assert planned, result.draft.model_dump(mode="json")
    assert all(draft_item.source.concrete_poi == branch for draft_item in planned)
    assert all(
        draft_item.source.collection_item_ids == tuple(sorted((item.id, exact.id)))
        for draft_item in planned
    )
    assert sum(isinstance(call, SearchPoiRequest) for call in calls) == 1

    calls.clear()
    default_constraints = constraints.model_copy(
        update={
            "pace": PlanPace.BALANCED,
            "pace_source": PlanPaceSource.SYSTEM_DEFAULT,
        }
    )
    async with database.session() as session:
        default_resolved: list[PlanConstraints] = []
        delegate = MapPlanFactResolver(
            session=session,
            map_provider=provider,
            matching_policy=Settings(
                _env_file=None,
                app_env="test",
            ).place_matching_policy(),
        )

        class CapturingDefaultFacts:
            async def resolve(self, *, user_id: str, constraints: PlanConstraints):
                default_resolved.append(constraints)
                return await delegate.resolve(user_id=user_id, constraints=constraints)

            async def resolve_proposal_routes(self, **kwargs):
                return await delegate.resolve_proposal_routes(**kwargs)

        default_result = await ExistingPlanServicesExecutor(
            session=session,
            map_provider=provider,
            matching_policy=Settings(
                _env_file=None,
                app_env="test",
            ).place_matching_policy(),
            facts=CapturingDefaultFacts(),  # type: ignore[arg-type]
            proposals=FixedProposals(),  # type: ignore[arg-type]
        ).execute(user_id=user_id, constraints=default_constraints, approval=None)
    await database.close()

    assert default_result.outcome is PlanGenerationOutcome.DRAFT
    assert default_resolved[0].pace is PlanPace.RELAXED
    assert default_resolved[0].pace_source is PlanPaceSource.MEMORY_DEFAULT
    assert len(default_result.memory_usages) == 1
    assert default_result.effective_constraints == default_resolved[0]


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
        _place(user_id, title=f"地点 {index}", poi=_poi(f"poi_{index:03d}")) for index in range(100)
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
    assert len(result.draft.candidates) == len(items)
    assert route_calls <= MAX_PLAN_ROUTE_CALLS

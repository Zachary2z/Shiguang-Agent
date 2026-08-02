"""M0-3D selection persistence, idempotency, isolation, and rollback tests."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config

from app.application import CollectionWriteService, PlaceTargetSelectionService
from app.domain.collections import (
    CandidateField,
    CollectionDataIntegrityError,
    CollectionItem,
    CollectionItemPatch,
    CollectionKind,
    CollectionStatus,
    ExtractionResult,
    IdempotencyConflictError,
    ResourceNotFoundError,
    Source,
    SourceParseStatus,
    SourceType,
    UndoOutcome,
    User,
    UserMode,
    VersionConflictError,
)
from app.domain.collections import (
    PlaceCandidate as ExtractedPlaceCandidate,
)
from app.domain.identifiers import (
    generate_collection_item_id,
    generate_source_id,
    generate_user_id,
)
from app.domain.places import (
    BrandIdentityConfirmationSource,
    ConfirmedBrandIdentity,
    EvidenceField,
    EvidenceOutcome,
    EvidenceReason,
    MatchConfidence,
    MatchEvidence,
    MatchStatus,
    PlaceConfirmationSource,
    PlaceMatchCandidate,
    PlaceMatchResult,
    PlaceScope,
    PlaceSelection,
    PlaceSelectionKind,
    ResolvedPlaceTargetKind,
    normalize_brand_name,
    resolve_place_target,
)
from app.infrastructure.db import Database
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.providers import MapProviderError, MapProviderErrorCode
from tests.fixtures.place_matching import M_STAND_COASTAL, M_STAND_MIXC

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, 5, 0, tzinfo=UTC)


class _UnavailablePlaceMatching:
    async def match(self, request: object) -> object:
        del request
        raise MapProviderError(code=MapProviderErrorCode.UNAVAILABLE)


@pytest.fixture
def target_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[str, Path]:
    database_path = tmp_path / "targets.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_url, database_path


def _evidence() -> tuple[MatchEvidence, ...]:
    return tuple(
        MatchEvidence(
            field=field,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.SOURCE_MISSING,
            score_delta=0.0,
        )
        for field in EvidenceField
    )


def _candidate(index: int) -> PlaceMatchCandidate:
    poi = (M_STAND_COASTAL, M_STAND_MIXC)[index]
    return PlaceMatchCandidate(
        provider=poi.provider,
        poi_id=poi.poi_id,
        city_code=poi.city_code,
        coordinate=poi.coordinate,
        name=poi.name,
        branch_name=poi.branch_name,
        district=poi.district,
        business_area=poi.business_area,
        address=poi.address,
        poi_type=poi.poi_type,
        provider_rank=index + 1,
        rank=index + 1,
        score=70.0 - index,
        confidence=MatchConfidence.MEDIUM,
        evidence=_evidence(),
    )


def _match_result() -> PlaceMatchResult:
    return PlaceMatchResult(
        status=MatchStatus.AMBIGUOUS,
        candidates=(_candidate(0), _candidate(1)),
    )


def _unique_match_result() -> PlaceMatchResult:
    candidate = _candidate(0).model_copy(
        update={"confidence": MatchConfidence.HIGH, "score": 92.0},
        deep=True,
    )
    return PlaceMatchResult(status=MatchStatus.MATCHED, candidates=(candidate,))


def _brand(*, stable_id: str = "brand_mstand_cn") -> ConfirmedBrandIdentity:
    return ConfirmedBrandIdentity(
        namespace="curated_brand",
        stable_id=stable_id,
        display_name="M Stand 咖啡",
        normalized_name=normalize_brand_name("M Stand 咖啡"),
        identity_confirmed_by=BrandIdentityConfirmationSource.CURATED,
        identity_confirmed_at=NOW,
    )


async def _seed_pending(
    database: Database,
    *,
    user: User | None = None,
) -> tuple[User, Source, CollectionItem]:
    owner = user or User(id=generate_user_id(), mode=UserMode.REAL, created_at=NOW)
    source = Source(
        id=generate_source_id(),
        user_id=owner.id,
        type=SourceType.TEXT,
        parse_status=SourceParseStatus.PARSED,
        created_at=NOW,
        updated_at=NOW,
    )
    item = CollectionItem(
        id=generate_collection_item_id(),
        user_id=owner.id,
        kind=CollectionKind.PLACE,
        title="M Stand 咖啡",
        city_hint="深圳",
        status=CollectionStatus.PENDING_DETAILS,
        created_at=NOW,
        updated_at=NOW,
    )
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        if await repository.get_user(user_id=owner.id) is None:
            await repository.add_user(user_id=owner.id, user=owner)
        await repository.add_source(user_id=owner.id, source=source)
        await repository.add_collection_item(user_id=owner.id, item=item)
        await repository.add_collection_source(
            user_id=owner.id,
            collection_item_id=item.id,
            source_id=source.id,
            created_at=NOW,
        )
        await session.commit()
    return owner, source, item


async def _record(
    database: Database,
    user: User,
    source: Source,
    item: CollectionItem,
) -> CollectionItem:
    async with database.session() as session:
        return await PlaceTargetSelectionService(session=session).record_candidates(
            user_id=user.id,
            collection_item_id=item.id,
            source_id=source.id,
            match_result=_match_result(),
            queried_at=NOW,
            expected_version=item.version,
        )


async def _record_result(
    database: Database,
    user: User,
    source: Source,
    item: CollectionItem,
    result: PlaceMatchResult,
) -> CollectionItem:
    async with database.session() as session:
        return await PlaceTargetSelectionService(session=session).record_candidates(
            user_id=user.id,
            collection_item_id=item.id,
            source_id=source.id,
            match_result=result,
            queried_at=NOW,
            expected_version=item.version,
        )


async def _attach_source(
    database: Database,
    *,
    user: User,
    item: CollectionItem,
) -> Source:
    source = Source(
        id=generate_source_id(),
        user_id=user.id,
        type=SourceType.TEXT,
        parse_status=SourceParseStatus.PARSED,
        created_at=NOW,
        updated_at=NOW,
    )
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_source(user_id=user.id, source=source)
        await repository.add_collection_source(
            user_id=user.id,
            collection_item_id=item.id,
            source_id=source.id,
            created_at=NOW,
        )
        await session.commit()
    return source


def _candidate_choice(index: int) -> PlaceSelection:
    candidate = _candidate(index)
    return PlaceSelection(
        kind=PlaceSelectionKind.CANDIDATE,
        provider=candidate.provider,
        poi_id=candidate.poi_id,
    )


def _snapshot_fingerprint(item: CollectionItem) -> str:
    assert item.place_candidate_snapshot is not None
    return item.place_candidate_snapshot.fingerprint


def _exception_graph_text(error: BaseException) -> str:
    pending: list[object] = [error]
    seen: set[int] = set()
    rendered: list[str] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        rendered.append(repr(current))
        if isinstance(current, BaseException):
            rendered.extend((str(current), repr(current.args), repr(vars(current))))
            pending.extend(current.args)
            pending.extend(vars(current).values())
            pending.extend(
                linked
                for linked in (current.__context__, current.__cause__)
                if linked is not None
            )
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset)):
            pending.extend(current)
    return "\n".join(rendered)


def _assert_safe_collection_integrity_error(
    error: CollectionDataIntegrityError,
    *,
    sensitive_values: tuple[str, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixed_message = "collection data integrity violation"
    assert error.__context__ is None
    assert error.__cause__ is None
    assert str(error) == fixed_message
    assert repr(error) == f"CollectionDataIntegrityError('{fixed_message}')"
    assert error.args == (fixed_message,)
    assert vars(error) == {}
    exposed = _exception_graph_text(error)
    for sensitive in sensitive_values:
        assert sensitive not in exposed
        assert sensitive not in caplog.text


async def _select_exact_place(
    database: Database,
    *,
    idempotency_key: str,
) -> tuple[User, CollectionItem]:
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)
    async with database.session() as session:
        result = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key=idempotency_key,
            expected_version=pending.version,
        )
    return user, result.items[0]


async def _select_any_branch_place(
    database: Database,
    *,
    idempotency_key: str,
) -> tuple[User, CollectionItem]:
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)
    async with database.session() as session:
        result = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(PlaceSelection(kind=PlaceSelectionKind.ANY_BRANCH),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key=idempotency_key,
            expected_version=pending.version,
            brand_identity=_brand(),
        )
    return user, result.items[0]


@pytest.mark.asyncio
async def test_candidate_refresh_saves_queried_at_without_creating_collections(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, item = await _seed_pending(database)

    stored = await _record(database, user, source, item)

    assert stored.status is CollectionStatus.PENDING_SELECTION
    assert stored.place_target is None
    assert stored.place_candidate_snapshot.queried_at == NOW
    assert len(stored.place_candidate_snapshot.candidates) == 2
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM collection_items").fetchone() == (1,)
        assert connection.execute(
            "SELECT candidate_count FROM collection_items WHERE id = ?", (item.id,)
        ).fetchone() == (2,)


@pytest.mark.asyncio
async def test_unique_high_confidence_match_atomically_becomes_active_exact(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, item = await _seed_pending(database)

    stored = await _record_result(database, user, source, item, _unique_match_result())

    target = stored.place_target
    snapshot = stored.place_candidate_snapshot
    assert stored.status is CollectionStatus.ACTIVE
    assert target.scope is PlaceScope.EXACT
    assert target.poi.poi_id == M_STAND_COASTAL.poi_id
    assert target.confirmed_by is PlaceConfirmationSource.AUTO_UNIQUE_MATCH
    assert target.confirmed_at == NOW
    assert target.confidence is MatchConfidence.HIGH
    assert target.evidence_summary == snapshot.candidates[0].evidence
    assert snapshot.queried_at == NOW
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT status, place_scope, poi_provider, poi_id, place_confirmed_by, "
            "candidate_count, candidates_queried_at FROM collection_items WHERE id = ?",
            (item.id,),
        ).fetchone() == (
            "active",
            "exact",
            M_STAND_COASTAL.provider.value,
            M_STAND_COASTAL.poi_id,
            "auto_unique_match",
            1,
            "2026-07-22 05:00:00.000000",
        )


@pytest.mark.asyncio
async def test_temporary_provider_failure_preserves_existing_trusted_target(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    user, source, item = await _seed_pending(database)
    active = await _record_result(database, user, source, item, _unique_match_result())
    async with database.session() as session:
        service = CollectionWriteService(session=session, now=lambda: NOW)
        with pytest.raises(MapProviderError) as exc_info:
            await service.patch(
                user_id=user.id,
                collection_item_id=active.id,
                expected_version=active.version,
                patch=CollectionItemPatch(title="修改后的地点线索"),
                place_matching=_UnavailablePlaceMatching(),  # type: ignore[arg-type]
            )
        stored = await service._repository.get_collection_item(
            user_id=user.id,
            collection_item_id=active.id,
        )

    assert exc_info.value.code is MapProviderErrorCode.UNAVAILABLE
    assert stored == active


@pytest.mark.asyncio
async def test_unique_high_match_ignores_lower_supporting_candidates_for_auto_binding(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    user, source, item = await _seed_pending(database)
    high = _unique_match_result().candidates[0]
    result = PlaceMatchResult(
        status=MatchStatus.MATCHED,
        candidates=(high, _candidate(1)),
    )

    stored = await _record_result(database, user, source, item, result)

    assert stored.status is CollectionStatus.ACTIVE
    assert stored.place_target is not None
    assert stored.place_target.poi is not None
    assert stored.place_target.poi.poi_id == high.poi_id


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["medium", "hard_conflict"])
async def test_illegal_matched_results_are_rejected_without_writes(
    target_database: tuple[str, Path],
    invalid_kind: str,
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, item = await _seed_pending(database)
    high = _unique_match_result().candidates[0]
    if invalid_kind == "medium":
        result = PlaceMatchResult(
            status=MatchStatus.MATCHED,
            candidates=(_candidate(0),),
        )
    else:
        hard_evidence = high.evidence[0].model_copy(
            update={
                "outcome": EvidenceOutcome.CONFLICT,
                "reason": EvidenceReason.CONFLICT,
                "score_delta": -10.0,
                "hard_conflict": True,
            }
        )
        hard = high.model_copy(
            update={"evidence": (hard_evidence, *high.evidence[1:])}, deep=True
        )
        result = PlaceMatchResult.model_construct(
            status=MatchStatus.MATCHED,
            candidates=(hard,),
        )

    with pytest.raises(ValueError):
        await _record_result(database, user, source, item, result)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT status, version, place_scope, candidate_count FROM collection_items "
            "WHERE id = ?",
            (item.id,),
        ).fetchone() == ("pending_details", item.version, None, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "with_candidate"),
    [
        (MatchStatus.NEEDS_CONTEXT, True),
        (MatchStatus.NEEDS_CONTEXT, False),
        (MatchStatus.NOT_FOUND, False),
    ],
)
async def test_candidate_presence_alone_controls_selection_vs_detail_readiness(
    target_database: tuple[str, Path],
    status: MatchStatus,
    with_candidate: bool,
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    user, source, item = await _seed_pending(database)
    candidates = (_candidate(0),) if with_candidate else ()

    stored = await _record_result(
        database,
        user,
        source,
        item,
        PlaceMatchResult(status=status, candidates=candidates),
    )

    assert stored.status is (
        CollectionStatus.PENDING_SELECTION
        if with_candidate
        else CollectionStatus.PENDING_DETAILS
    )
    assert stored.place_target is None
    assert stored.place_candidate_snapshot.result.status is status


@pytest.mark.asyncio
async def test_second_specific_candidate_becomes_one_exact_confirmed_poi(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)

    async with database.session() as session:
        result = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(_candidate_choice(1),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="choose-second",
            expected_version=pending.version,
        )

    exact = result.items[0]
    assert exact.status is CollectionStatus.ACTIVE
    assert exact.place_target.scope is PlaceScope.EXACT
    assert exact.place_target.poi.poi_id == M_STAND_MIXC.poi_id
    assert exact.place_target.poi.city_code == "shenzhen"
    assert exact.address == M_STAND_MIXC.address
    assert resolve_place_target(exact.place_target, collection_status=exact.status.value).kind is (
        ResolvedPlaceTargetKind.EXACT
    )


@pytest.mark.asyncio
async def test_multi_select_creates_independent_exact_items_with_one_source(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)

    async with database.session() as session:
        selected = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(_candidate_choice(0), _candidate_choice(1)),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="choose-two",
            expected_version=pending.version,
        )

    assert len(selected.items) == 2
    assert len({item.id for item in selected.items}) == 2
    assert {item.place_target.poi.poi_id for item in selected.items} == {
        M_STAND_COASTAL.poi_id,
        M_STAND_MIXC.poi_id,
    }
    assert [item.version for item in selected.items] == [pending.version + 1, 1]
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        for exact in selected.items:
            links = await repository.list_collection_sources(
                user_id=user.id,
                collection_item_id=exact.id,
            )
            assert {link.source_id for link in links} == {source.id}


@pytest.mark.asyncio
async def test_any_branch_requires_explicit_identity_and_is_idempotent_across_keys(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)
    selection = (PlaceSelection(kind=PlaceSelectionKind.ANY_BRANCH),)

    async with database.session() as session:
        service = PlaceTargetSelectionService(session=session)
        with pytest.raises(ValueError, match="confirmed brand identity"):
            await service.apply_selection(
                user_id=user.id,
                collection_item_id=pending.id,
                source_id=source.id,
                selections=selection,
                queried_at=NOW,
                snapshot_fingerprint=_snapshot_fingerprint(pending),
                idempotency_key="missing-brand",
                expected_version=pending.version,
            )
        first = await service.apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=selection,
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="brand-one",
            expected_version=pending.version,
            brand_identity=_brand(),
        )
    async with database.session() as session:
        second = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=selection,
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="brand-two",
            expected_version=pending.version,
            brand_identity=_brand(),
        )

    assert first.items[0].id == second.items[0].id
    assert first.items[0].place_target.scope is PlaceScope.ANY_BRANCH
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_items WHERE place_scope = 'any_branch' "
            "AND status <> 'deleted'"
        ).fetchone() == (1,)


@pytest.mark.asyncio
async def test_concurrent_any_branch_choices_converge_to_one_user_brand_collection(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, first_source, first_initial = await _seed_pending(database)
    _, second_source, second_initial = await _seed_pending(database, user=user)
    first_pending, second_pending = await asyncio.gather(
        _record(database, user, first_source, first_initial),
        _record(database, user, second_source, second_initial),
    )
    selection = (PlaceSelection(kind=PlaceSelectionKind.ANY_BRANCH),)

    async def choose(
        item: CollectionItem,
        source: Source,
        idempotency_key: str,
    ) -> str:
        async with database.session() as session:
            result = await PlaceTargetSelectionService(session=session).apply_selection(
                user_id=user.id,
                collection_item_id=item.id,
                source_id=source.id,
                selections=selection,
                queried_at=NOW,
                snapshot_fingerprint=_snapshot_fingerprint(item),
                idempotency_key=idempotency_key,
                expected_version=item.version,
                brand_identity=_brand(),
            )
            return result.items[0].id

    result_ids = await asyncio.gather(
        choose(first_pending, first_source, "concurrent-brand-one"),
        choose(second_pending, second_source, "concurrent-brand-two"),
    )

    assert len(set(result_ids)) == 1
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_items WHERE place_scope = 'any_branch' "
            "AND status <> 'deleted'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_sources WHERE collection_item_id = ?",
            (result_ids[0],),
        ).fetchone() == (2,)


@pytest.mark.asyncio
async def test_duplicate_exact_poi_reuses_collection_and_keeps_both_sources(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, first_source, first_initial = await _seed_pending(database)
    _, second_source, second_initial = await _seed_pending(database, user=user)
    third_source = await _attach_source(
        database,
        user=user,
        item=second_initial,
    )
    _, foreign_source, _ = await _seed_pending(database)
    first_pending = await _record(database, user, first_source, first_initial)
    second_pending = await _record(database, user, second_source, second_initial)

    async with database.session() as session:
        first = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=first_pending.id,
            source_id=first_source.id,
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(first_pending),
            idempotency_key="exact-first",
            expected_version=first_pending.version,
        )
    async with database.session() as session:
        second = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=second_pending.id,
            source_id=second_source.id,
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(second_pending),
            idempotency_key="exact-second",
            expected_version=second_pending.version,
        )
    async with database.session() as session:
        replay = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=second_pending.id,
            source_id=second_source.id,
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(second_pending),
            idempotency_key="exact-second",
            expected_version=second_pending.version,
        )
        with pytest.raises(IdempotencyConflictError):
            await PlaceTargetSelectionService(session=session).apply_selection(
                user_id=user.id,
                collection_item_id=second_pending.id,
                source_id=second_source.id,
                selections=(_candidate_choice(1),),
                queried_at=NOW,
                snapshot_fingerprint=_snapshot_fingerprint(second_pending),
                idempotency_key="exact-second",
                expected_version=second_pending.version,
            )

    assert first.items[0].id == second.items[0].id
    assert replay.replayed is True
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_items WHERE place_scope = 'exact' "
            "AND poi_id = ? AND status <> 'deleted'",
            (M_STAND_COASTAL.poi_id,),
        ).fetchone() == (1,)
        linked_sources = connection.execute(
            "SELECT source_id FROM collection_sources WHERE collection_item_id = ? "
            "ORDER BY source_id",
            (first.items[0].id,),
        ).fetchall()
        assert linked_sources == sorted(
            [(first_source.id,), (second_source.id,), (third_source.id,)]
        )
        assert (foreign_source.id,) not in linked_sources


@pytest.mark.asyncio
async def test_any_branch_merge_preserves_every_source_without_replay_duplicates(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, first_source, first_initial = await _seed_pending(database)
    _, second_source, second_initial = await _seed_pending(database, user=user)
    extra_source = await _attach_source(
        database,
        user=user,
        item=second_initial,
    )
    first_pending = await _record(database, user, first_source, first_initial)
    second_pending = await _record(database, user, second_source, second_initial)
    selection = (PlaceSelection(kind=PlaceSelectionKind.ANY_BRANCH),)

    async with database.session() as session:
        first = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=first_pending.id,
            source_id=first_source.id,
            selections=selection,
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(first_pending),
            idempotency_key="brand-all-sources-first",
            expected_version=first_pending.version,
            brand_identity=_brand(),
        )
    async with database.session() as session:
        merged = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=second_pending.id,
            source_id=second_source.id,
            selections=selection,
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(second_pending),
            idempotency_key="brand-all-sources-second",
            expected_version=second_pending.version,
            brand_identity=_brand(),
        )
    async with database.session() as session:
        replay = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=second_pending.id,
            source_id=second_source.id,
            selections=selection,
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(second_pending),
            idempotency_key="brand-all-sources-second",
            expected_version=second_pending.version,
            brand_identity=_brand(),
        )

    assert first.items[0].id == merged.items[0].id
    assert replay.replayed is True
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT source_id FROM collection_sources WHERE collection_item_id = ? "
            "ORDER BY source_id",
            (first.items[0].id,),
        ).fetchall() == sorted(
            [(first_source.id,), (second_source.id,), (extra_source.id,)]
        )


@pytest.mark.asyncio
async def test_same_key_replay_is_stable_and_conflicting_payload_is_rejected(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)

    async with database.session() as session:
        service = PlaceTargetSelectionService(session=session)
        first = await service.apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="stable-replay",
            expected_version=pending.version,
        )
    async with database.session() as session:
        service = PlaceTargetSelectionService(session=session)
        replay = await service.apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="stable-replay",
            expected_version=pending.version,
        )
        with pytest.raises(IdempotencyConflictError):
            await service.apply_selection(
                user_id=user.id,
                collection_item_id=pending.id,
                source_id=source.id,
                selections=(_candidate_choice(1),),
                queried_at=NOW,
                snapshot_fingerprint=_snapshot_fingerprint(pending),
                idempotency_key="stable-replay",
                expected_version=pending.version,
            )
    assert replay.replayed is True
    assert replay.items[0].id == first.items[0].id


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper_kind", ["forged_poi", "stale_time", "different_snapshot"])
async def test_selection_rejects_candidate_state_not_in_persisted_snapshot(
    target_database: tuple[str, Path],
    tamper_kind: str,
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)
    queried_at = NOW
    fingerprint = _snapshot_fingerprint(pending)
    selection = _candidate_choice(0)
    if tamper_kind == "forged_poi":
        selection = PlaceSelection(
            kind=PlaceSelectionKind.CANDIDATE,
            provider=M_STAND_COASTAL.provider,
            poi_id="poi-never-shown",
        )
    elif tamper_kind == "stale_time":
        queried_at = NOW - timedelta(minutes=1)
    else:
        fingerprint = "f" * 64

    async with database.session() as session:
        with pytest.raises(ValueError):
            await PlaceTargetSelectionService(session=session).apply_selection(
                user_id=user.id,
                collection_item_id=pending.id,
                source_id=source.id,
                selections=(selection,),
                queried_at=queried_at,
                snapshot_fingerprint=fingerprint,
                idempotency_key=f"tampered-{tamper_kind}",
                expected_version=pending.version,
            )

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT status, version, place_scope FROM collection_items WHERE id = ?",
            (pending.id,),
        ).fetchone() == ("pending_selection", pending.version, None)
        assert connection.execute("SELECT COUNT(*) FROM place_selection_operations").fetchone() == (
            0,
        )


@pytest.mark.asyncio
async def test_same_key_concurrent_cas_conflict_replays_one_stable_operation(
    target_database: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)
    barrier = asyncio.Barrier(2)
    winner_completed = asyncio.Event()
    leader_repositories: set[int] = set()
    original_apply = SqlAlchemyCollectionRepository.apply_place_resolution

    async def synchronized_cas(
        repository: SqlAlchemyCollectionRepository,
        *,
        user_id: str,
        item: CollectionItem,
        expected_version: int,
    ) -> CollectionItem:
        position = await barrier.wait()
        if position == 0:
            leader_repositories.add(id(repository))
            return await original_apply(
                repository,
                user_id=user_id,
                item=item,
                expected_version=expected_version,
            )
        await winner_completed.wait()
        raise VersionConflictError

    monkeypatch.setattr(
        SqlAlchemyCollectionRepository,
        "apply_place_resolution",
        synchronized_cas,
    )

    async def choose() -> tuple[str, bool]:
        async with database.session() as session:
            service = PlaceTargetSelectionService(session=session)
            try:
                result = await service.apply_selection(
                    user_id=user.id,
                    collection_item_id=pending.id,
                    source_id=source.id,
                    selections=(_candidate_choice(0),),
                    queried_at=NOW,
                    snapshot_fingerprint=_snapshot_fingerprint(pending),
                    idempotency_key="concurrent-stable-replay",
                    expected_version=pending.version,
                )
                return result.items[0].id, result.replayed
            finally:
                if id(service._repository) in leader_repositories:
                    winner_completed.set()

    results = await asyncio.gather(choose(), choose())

    assert len({identifier for identifier, _ in results}) == 1
    assert sorted(replayed for _, replayed in results) == [False, True]
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM place_selection_operations").fetchone() == (
            1,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_items WHERE place_scope = 'exact' "
            "AND status <> 'deleted'"
        ).fetchone() == (1,)


@pytest.mark.asyncio
async def test_real_version_conflict_without_idempotency_operation_is_preserved(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)

    async with database.session() as session:
        with pytest.raises(VersionConflictError):
            await PlaceTargetSelectionService(session=session).apply_selection(
                user_id=user.id,
                collection_item_id=pending.id,
                source_id=source.id,
                selections=(_candidate_choice(0),),
                queried_at=NOW,
                snapshot_fingerprint=_snapshot_fingerprint(pending),
                idempotency_key="genuine-version-conflict",
                expected_version=pending.version - 1,
            )


@pytest.mark.asyncio
async def test_none_of_above_enters_pending_details_and_cannot_resolve_for_planning(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)

    async with database.session() as session:
        result = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(PlaceSelection(kind=PlaceSelectionKind.NONE_OF_ABOVE),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="none",
            expected_version=pending.version,
        )
    assert result.items[0].status is CollectionStatus.PENDING_DETAILS
    assert (
        resolve_place_target(
            result.items[0].place_target,
            collection_status=result.items[0].status.value,
        ).kind
        is ResolvedPlaceTargetKind.UNCONFIRMED
    )


@pytest.mark.asyncio
async def test_multi_select_second_write_failure_rolls_back_everything(
    target_database: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)

    async with database.session() as session:
        service = PlaceTargetSelectionService(session=session)

        async def fail_add(**_kwargs: Any) -> CollectionItem:
            raise RuntimeError("synthetic second branch failure")

        monkeypatch.setattr(service._repository, "add_collection_item", fail_add)
        with pytest.raises(RuntimeError, match="second branch failure"):
            await service.apply_selection(
                user_id=user.id,
                collection_item_id=pending.id,
                source_id=source.id,
                selections=(_candidate_choice(0), _candidate_choice(1)),
                queried_at=NOW,
                snapshot_fingerprint=_snapshot_fingerprint(pending),
                idempotency_key="rollback-two",
                expected_version=pending.version,
            )

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM collection_items").fetchone() == (1,)
        assert connection.execute(
            "SELECT status, version, place_scope FROM collection_items WHERE id = ?",
            (pending.id,),
        ).fetchone() == ("pending_selection", pending.version, None)
        assert connection.execute("SELECT COUNT(*) FROM place_selection_operations").fetchone() == (
            0,
        )


@pytest.mark.asyncio
async def test_multi_select_extends_original_write_group_so_undo_deletes_all_branches(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user = User(id=generate_user_id(), mode=UserMode.REAL, created_at=NOW)
    source = Source(
        id=generate_source_id(),
        user_id=user.id,
        type=SourceType.TEXT,
        parse_status=SourceParseStatus.PARSED,
        created_at=NOW,
        updated_at=NOW,
    )
    undo_token = "undo_" + "d" * 43
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        await session.commit()
    async with database.session() as session:
        saved = await CollectionWriteService(
            session=session,
            now=lambda: NOW,
            token_factory=lambda: undo_token,
        ).auto_save(
            user_id=user.id,
            idempotency_key="split-with-undo",
            source=source,
            extraction_result=ExtractionResult.with_candidates(
                (
                    ExtractedPlaceCandidate(
                        title="M Stand 咖啡",
                        city_hint="深圳",
                        missing_fields=(
                            CandidateField.DISTRICT,
                            CandidateField.ADDRESS,
                            CandidateField.BUSINESS_DISTRICT,
                            CandidateField.LANDMARK,
                            CandidateField.METRO_STATION,
                            CandidateField.PRICE,
                            CandidateField.TAGS,
                        ),
                    ),
                )
            ),
        )
    pending = await _record(database, user, source, saved.items[0])
    async with database.session() as session:
        selected = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(_candidate_choice(0), _candidate_choice(1)),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="split-two-for-undo",
            expected_version=pending.version,
        )
    async with database.session() as session:
        undone = await CollectionWriteService(session=session, now=lambda: NOW).undo(
            user_id=user.id,
            undo_token=undo_token,
        )

    assert undone.outcome is UndoOutcome.UNDONE
    assert set(undone.collection_item_ids) == {item.id for item in selected.items}
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_items WHERE status = 'deleted'"
        ).fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone() == (1,)


@pytest.mark.asyncio
async def test_source_and_collection_ownership_are_enforced(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    first_user, first_source, first_initial = await _seed_pending(database)
    pending = await _record(database, first_user, first_source, first_initial)
    second_user, second_source, _ = await _seed_pending(database)

    async with database.session() as session:
        with pytest.raises(ResourceNotFoundError):
            await PlaceTargetSelectionService(session=session).apply_selection(
                user_id=first_user.id,
                collection_item_id=pending.id,
                source_id=second_source.id,
                selections=(_candidate_choice(0),),
                queried_at=NOW,
                snapshot_fingerprint=_snapshot_fingerprint(pending),
                idempotency_key="cross-user-source",
                expected_version=pending.version,
            )
    assert second_user.id != first_user.id


@pytest.mark.asyncio
async def test_different_users_and_distinct_stable_brand_ids_do_not_merge(
    target_database: tuple[str, Path],
) -> None:
    database_url, _ = target_database
    database = Database(database_url)
    selections = (PlaceSelection(kind=PlaceSelectionKind.ANY_BRANCH),)
    ids: list[str] = []
    for index in range(2):
        user, source, initial = await _seed_pending(database)
        pending = await _record(database, user, source, initial)
        async with database.session() as session:
            result = await PlaceTargetSelectionService(session=session).apply_selection(
                user_id=user.id,
                collection_item_id=pending.id,
                source_id=source.id,
                selections=selections,
                queried_at=NOW,
                snapshot_fingerprint=_snapshot_fingerprint(pending),
                idempotency_key=f"brand-user-{index}",
                expected_version=pending.version,
                brand_identity=_brand(),
            )
        ids.append(result.items[0].id)
    assert len(set(ids)) == 2

    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)
    async with database.session() as session:
        first = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=selections,
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="similar-one",
            expected_version=pending.version,
            brand_identity=_brand(stable_id="brand_one"),
        )
    user_source_two = Source(
        id=generate_source_id(),
        user_id=user.id,
        type=SourceType.TEXT,
        parse_status=SourceParseStatus.PARSED,
        created_at=NOW,
        updated_at=NOW,
    )
    item_two = CollectionItem(
        user_id=user.id,
        kind=CollectionKind.PLACE,
        title="M Stand 咖啡",
        status=CollectionStatus.PENDING_DETAILS,
        created_at=NOW,
        updated_at=NOW,
    )
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_source(user_id=user.id, source=user_source_two)
        await repository.add_collection_item(user_id=user.id, item=item_two)
        await repository.add_collection_source(
            user_id=user.id,
            collection_item_id=item_two.id,
            source_id=user_source_two.id,
            created_at=NOW,
        )
        await session.commit()
    pending_two = await _record(database, user, user_source_two, item_two)
    async with database.session() as session:
        second = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending_two.id,
            source_id=user_source_two.id,
            selections=selections,
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending_two),
            idempotency_key="similar-two",
            expected_version=pending_two.version,
            brand_identity=_brand(stable_id="brand_two"),
        )
    assert first.items[0].id != second.items[0].id
    assert first.items[0].place_target.brand_identity.normalized_name == (
        second.items[0].place_target.brand_identity.normalized_name
    )


@pytest.mark.asyncio
async def test_exact_poi_and_any_branch_brand_identity_remain_isolated(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, exact_source, exact_initial = await _seed_pending(database)
    _, brand_source, brand_initial = await _seed_pending(database, user=user)
    exact_pending = await _record(database, user, exact_source, exact_initial)
    brand_pending = await _record(database, user, brand_source, brand_initial)

    async with database.session() as session:
        exact = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=exact_pending.id,
            source_id=exact_source.id,
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(exact_pending),
            idempotency_key="isolated-exact",
            expected_version=exact_pending.version,
        )
    async with database.session() as session:
        brand = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=brand_pending.id,
            source_id=brand_source.id,
            selections=(PlaceSelection(kind=PlaceSelectionKind.ANY_BRANCH),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(brand_pending),
            idempotency_key="isolated-brand",
            expected_version=brand_pending.version,
            brand_identity=_brand(),
        )

    assert exact.items[0].id != brand.items[0].id
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT place_scope, COUNT(*) FROM collection_items "
            "WHERE status <> 'deleted' AND place_scope IS NOT NULL GROUP BY place_scope "
            "ORDER BY place_scope"
        ).fetchall() == [("any_branch", 1), ("exact", 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("column", "corrupt_value"),
    [
        ("poi_provider", "forged_provider"),
        ("poi_id", "forged-poi"),
        ("poi_city_code", "forged_city"),
        ("poi_latitude", 1.25),
        ("poi_longitude", 2.5),
        ("poi_coordinate_system", "wgs_84"),
        ("place_confirmed_by", "auto_unique_match"),
        ("candidate_count", 1),
        ("candidates_queried_at", "2026-07-22 04:59:00.000000"),
    ],
)
async def test_repository_rejects_exact_json_and_flat_column_mismatches(
    target_database: tuple[str, Path],
    column: str,
    corrupt_value: object,
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)
    async with database.session() as session:
        selected = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key=f"integrity-{column}",
            expected_version=pending.version,
        )
    exact_id = selected.items[0].id

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            f"UPDATE collection_items SET {column} = ? WHERE id = ?",  # noqa: S608
            (corrupt_value, exact_id),
        )
        connection.commit()

    async with database.session() as session:
        with pytest.raises(
            CollectionDataIntegrityError,
            match="^collection data integrity violation$",
        ):
            await SqlAlchemyCollectionRepository(session).get_collection_item(
                user_id=user.id,
                collection_item_id=exact_id,
            )


@pytest.mark.asyncio
async def test_repository_rejects_brand_json_and_flat_identity_mismatch(
    target_database: tuple[str, Path],
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    user, source, initial = await _seed_pending(database)
    pending = await _record(database, user, source, initial)
    async with database.session() as session:
        selected = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(PlaceSelection(kind=PlaceSelectionKind.ANY_BRANCH),),
            queried_at=NOW,
            snapshot_fingerprint=_snapshot_fingerprint(pending),
            idempotency_key="integrity-brand",
            expected_version=pending.version,
            brand_identity=_brand(),
        )
    brand_id = selected.items[0].id

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE collection_items SET brand_id = 'forged-brand' WHERE id = ?",
            (brand_id,),
        )
        connection.commit()

    async with database.session() as session:
        with pytest.raises(CollectionDataIntegrityError):
            await SqlAlchemyCollectionRepository(session).get_collection_item(
                user_id=user.id,
                collection_item_id=brand_id,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption_kind",
    ["place_target_schema", "candidate_snapshot_schema", "invalid_json_structure"],
)
async def test_malformed_place_json_raises_detached_secret_safe_error(
    target_database: tuple[str, Path],
    caplog: pytest.LogCaptureFixture,
    corruption_kind: str,
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    fake_secret = f"FAKE_PERSISTED_PLACE_SECRET_{corruption_kind.upper()}"

    if corruption_kind == "place_target_schema":
        user, item = await _select_exact_place(
            database,
            idempotency_key="malformed-target",
        )
        raw_json = json.dumps(
            {"scope": fake_secret, "raw_provider_payload": fake_secret},
            separators=(",", ":"),
        )
        statement = "UPDATE collection_items SET place_target_json = ? WHERE id = ?"
    else:
        user, source, initial = await _seed_pending(database)
        item = await _record(database, user, source, initial)
        payload: object
        if corruption_kind == "candidate_snapshot_schema":
            payload = {
                "match_result": {"status": fake_secret},
                "queried_at": NOW.isoformat(),
                "raw_provider_payload": fake_secret,
            }
        else:
            payload = [fake_secret, {"raw_provider_payload": fake_secret}]
        raw_json = json.dumps(payload, separators=(",", ":"))
        statement = (
            "UPDATE collection_items SET place_candidate_snapshot_json = ? WHERE id = ?"
        )

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(statement, (raw_json, item.id))
        connection.commit()

    caplog.clear()
    async with database.session() as session:
        with caplog.at_level("DEBUG"), pytest.raises(
            CollectionDataIntegrityError,
            match="^collection data integrity violation$",
        ) as exc_info:
            await SqlAlchemyCollectionRepository(session).get_collection_item(
                user_id=user.id,
                collection_item_id=item.id,
            )

    _assert_safe_collection_integrity_error(
        exc_info.value,
        sensitive_values=(fake_secret, raw_json),
        caplog=caplog,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch_kind",
    ["poi", "brand", "candidate_count", "queried_at"],
)
async def test_place_json_flat_mismatches_raise_detached_secret_safe_error(
    target_database: tuple[str, Path],
    caplog: pytest.LogCaptureFixture,
    mismatch_kind: str,
) -> None:
    database_url, database_path = target_database
    database = Database(database_url)
    fake_secret = f"FAKE_FLAT_PLACE_SECRET_{mismatch_kind.upper()}"

    if mismatch_kind == "poi":
        user, item = await _select_exact_place(
            database,
            idempotency_key="safe-mismatch-poi",
        )
    elif mismatch_kind == "brand":
        user, item = await _select_any_branch_place(
            database,
            idempotency_key="safe-mismatch-brand",
        )
    else:
        user, source, initial = await _seed_pending(database)
        item = await _record(database, user, source, initial)

    with sqlite3.connect(database_path) as connection:
        raw_place_json = connection.execute(
            "SELECT place_target_json, place_candidate_snapshot_json "
            "FROM collection_items WHERE id = ?",
            (item.id,),
        ).fetchone()
        assert raw_place_json is not None
        connection.execute("PRAGMA ignore_check_constraints=ON")
        if mismatch_kind == "poi":
            connection.execute(
                "UPDATE collection_items SET poi_id = ? WHERE id = ?",
                (fake_secret, item.id),
            )
        elif mismatch_kind == "brand":
            connection.execute(
                "UPDATE collection_items SET brand_id = ? WHERE id = ?",
                (fake_secret, item.id),
            )
        elif mismatch_kind == "candidate_count":
            connection.execute(
                "UPDATE collection_items SET address = ?, candidate_count = 1 WHERE id = ?",
                (fake_secret, item.id),
            )
        else:
            connection.execute(
                "UPDATE collection_items SET address = ?, candidates_queried_at = ? "
                "WHERE id = ?",
                (fake_secret, "2026-07-22 04:59:00.000000", item.id),
            )
        connection.commit()

    persisted_json = tuple(
        value for value in raw_place_json if isinstance(value, str)
    )
    caplog.clear()
    async with database.session() as session:
        with caplog.at_level("DEBUG"), pytest.raises(
            CollectionDataIntegrityError,
            match="^collection data integrity violation$",
        ) as exc_info:
            await SqlAlchemyCollectionRepository(session).get_collection_item(
                user_id=user.id,
                collection_item_id=item.id,
            )

    _assert_safe_collection_integrity_error(
        exc_info.value,
        sensitive_values=(fake_secret, *persisted_json),
        caplog=caplog,
    )

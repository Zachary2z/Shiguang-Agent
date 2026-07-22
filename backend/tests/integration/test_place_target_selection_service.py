"""M0-3D selection persistence, idempotency, isolation, and rollback tests."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config

from app.application import CollectionWriteService, PlaceTargetSelectionService
from app.domain.collections import (
    CandidateField,
    CollectionItem,
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
from tests.fixtures.place_matching import M_STAND_COASTAL, M_STAND_MIXC

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, 5, 0, tzinfo=UTC)


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


def _candidate_choice(index: int) -> PlaceSelection:
    candidate = _candidate(index)
    return PlaceSelection(
        kind=PlaceSelectionKind.CANDIDATE,
        provider=candidate.provider,
        poi_id=candidate.poi_id,
    )


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
            match_result=_match_result(),
            selections=(_candidate_choice(1),),
            queried_at=NOW,
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
            match_result=_match_result(),
            selections=(_candidate_choice(0), _candidate_choice(1)),
            queried_at=NOW,
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
                match_result=_match_result(),
                selections=selection,
                queried_at=NOW,
                idempotency_key="missing-brand",
                expected_version=pending.version,
            )
        first = await service.apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            match_result=_match_result(),
            selections=selection,
            queried_at=NOW,
            idempotency_key="brand-one",
            expected_version=pending.version,
            brand_identity=_brand(),
        )
    async with database.session() as session:
        second = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            match_result=_match_result(),
            selections=selection,
            queried_at=NOW,
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
                match_result=_match_result(),
                selections=selection,
                queried_at=NOW,
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
    first_pending = await _record(database, user, first_source, first_initial)
    second_pending = await _record(database, user, second_source, second_initial)

    async with database.session() as session:
        first = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=first_pending.id,
            source_id=first_source.id,
            match_result=_match_result(),
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            idempotency_key="exact-first",
            expected_version=first_pending.version,
        )
    async with database.session() as session:
        second = await PlaceTargetSelectionService(session=session).apply_selection(
            user_id=user.id,
            collection_item_id=second_pending.id,
            source_id=second_source.id,
            match_result=_match_result(),
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            idempotency_key="exact-second",
            expected_version=second_pending.version,
        )

    assert first.items[0].id == second.items[0].id
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_items WHERE place_scope = 'exact' "
            "AND poi_id = ? AND status <> 'deleted'",
            (M_STAND_COASTAL.poi_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_sources WHERE collection_item_id = ?",
            (first.items[0].id,),
        ).fetchone() == (2,)


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
            match_result=_match_result(),
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            idempotency_key="stable-replay",
            expected_version=pending.version,
        )
    async with database.session() as session:
        service = PlaceTargetSelectionService(session=session)
        replay = await service.apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            match_result=_match_result(),
            selections=(_candidate_choice(0),),
            queried_at=NOW,
            idempotency_key="stable-replay",
            expected_version=pending.version,
        )
        with pytest.raises(IdempotencyConflictError):
            await service.apply_selection(
                user_id=user.id,
                collection_item_id=pending.id,
                source_id=source.id,
                match_result=_match_result(),
                selections=(_candidate_choice(1),),
                queried_at=NOW,
                idempotency_key="stable-replay",
                expected_version=pending.version,
            )
    assert replay.replayed is True
    assert replay.items[0].id == first.items[0].id


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
            match_result=_match_result(),
            selections=(PlaceSelection(kind=PlaceSelectionKind.NONE_OF_ABOVE),),
            queried_at=NOW,
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
                match_result=_match_result(),
                selections=(_candidate_choice(0), _candidate_choice(1)),
                queried_at=NOW,
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
            match_result=_match_result(),
            selections=(_candidate_choice(0), _candidate_choice(1)),
            queried_at=NOW,
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
                match_result=_match_result(),
                selections=(_candidate_choice(0),),
                queried_at=NOW,
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
                match_result=_match_result(),
                selections=selections,
                queried_at=NOW,
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
            match_result=_match_result(),
            selections=selections,
            queried_at=NOW,
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
            match_result=_match_result(),
            selections=selections,
            queried_at=NOW,
            idempotency_key="similar-two",
            expected_version=pending_two.version,
            brand_identity=_brand(stable_id="brand_two"),
        )
    assert first.items[0].id != second.items[0].id
    assert first.items[0].place_target.brand_identity.normalized_name == (
        second.items[0].place_target.brand_identity.normalized_name
    )

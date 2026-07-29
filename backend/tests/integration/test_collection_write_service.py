"""M0-2C transactional auto-save, idempotency, Undo, patch, and delete tests."""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from app.application import (
    CollectionWriteService,
    PlaceMatchingService,
    PlaceTargetSelectionService,
)
from app.domain.collections import (
    CandidateField,
    CollectionItemPatch,
    CollectionStatus,
    EventCandidate,
    ExtractionReasonCode,
    ExtractionResult,
    IdempotencyConflictError,
    PlaceCandidate,
    ResourceNotFoundError,
    Source,
    SourceMetadata,
    SourceParseStatus,
    SourceType,
    Uncertainty,
    UndoOutcome,
    User,
    UserMode,
    VersionConflictError,
)
from app.domain.identifiers import generate_source_id, generate_user_id
from app.domain.places import (
    PlaceMatchingPolicy,
    PlaceSelection,
    PlaceSelectionKind,
)
from app.infrastructure.db import Database
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from tests.fixtures.maps import make_stub_map_provider

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 21, 9, 0, tzinfo=UTC)
TOKEN_ONE = "undo_" + "a" * 43
TOKEN_TWO = "undo_" + "b" * 43


@dataclass
class MutableClock:
    value: datetime = NOW

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture
def write_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[str, Path]:
    database_path = tmp_path / "writes.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_url, database_path


def _user() -> User:
    return User(id=generate_user_id(), mode=UserMode.REAL, created_at=NOW)


def _source(user_id: str, *, source_id: str | None = None) -> Source:
    return Source(
        id=source_id or generate_source_id(),
        user_id=user_id,
        type=SourceType.TEXT,
        parse_status=SourceParseStatus.PARSED,
        metadata=SourceMetadata(content_sha256="a" * 64),
        created_at=NOW,
        updated_at=NOW,
    )


def _candidate_fields(
    *,
    title: str = "候选地点",
    city_hint: str | None = "深圳",
) -> dict[str, Any]:
    return {
        "title": title,
        "city_hint": city_hint,
        "district": "福田区",
        "address": "福中一路 1 号",
        "business_district": "中心区",
        "landmark": "市民中心",
        "metro_station": "市民中心站",
        "price_amount": Decimal("50.00"),
        "price_currency": "CNY",
        "tags": ("室内",),
    }


def _place(
    *,
    title: str = "候选地点",
    city_hint: str | None = "深圳",
) -> PlaceCandidate:
    return PlaceCandidate(**_candidate_fields(title=title, city_hint=city_hint))


def _event(
    *,
    title: str = "周末展览",
    start_at: datetime | None = NOW + timedelta(hours=1),
    end_at: datetime | None = NOW + timedelta(hours=3),
) -> EventCandidate:
    values = _candidate_fields(title=title)
    if start_at is None or end_at is None:
        return EventCandidate(
            **values,
            event_start_clue="周六上午",
            event_end_clue="中午前",
            missing_fields=(
                CandidateField.EVENT_START_DATE,
                CandidateField.EVENT_END_DATE,
                CandidateField.EVENT_START_AT,
                CandidateField.EVENT_END_AT,
            ),
        )
    return EventCandidate(
        **values,
        event_start_at=start_at,
        event_end_at=end_at,
        missing_fields=(
            CandidateField.EVENT_START_DATE,
            CandidateField.EVENT_END_DATE,
        ),
    )


def _date_only_event() -> EventCandidate:
    return EventCandidate(
        **_candidate_fields(title="夏季展览"),
        event_start_date=date(2026, 6, 13),
        event_end_date=date(2026, 7, 31),
        missing_fields=(
            CandidateField.EVENT_START_AT,
            CandidateField.EVENT_END_AT,
        ),
    )


async def _add_user(database: Database, user: User) -> None:
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        await session.commit()


def _service(
    session: Any,
    *,
    clock: MutableClock | None = None,
    token: str = TOKEN_ONE,
) -> CollectionWriteService:
    return CollectionWriteService(
        session=session,
        now=clock or MutableClock(),
        token_factory=lambda: token,
    )


@pytest.mark.asyncio
async def test_auto_save_place_preserves_all_candidate_metadata_and_one_time_token(
    write_database: tuple[str, Path],
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    source = _source(user.id)
    candidate_values = _candidate_fields(city_hint=None)
    candidate_values["address"] = None
    candidate = PlaceCandidate(
        **candidate_values,
        missing_fields=(CandidateField.CITY_HINT, CandidateField.ADDRESS),
        uncertainties=(
            Uncertainty(field=CandidateField.LANDMARK, reason="入口位置待确认"),
        ),
    )

    async with database.session() as session:
        result = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="message-1",
            source=source,
            extraction_result=ExtractionResult.with_candidates((candidate,)),
        )

    assert result.replayed is False
    assert result.undo_token is not None
    assert result.undo_token.get_secret_value() == TOKEN_ONE
    assert TOKEN_ONE not in repr(result)
    assert TOKEN_ONE not in result.model_dump_json()
    assert len(result.items) == 1
    item = result.items[0]
    assert item.status is CollectionStatus.PENDING_DETAILS
    assert item.city_hint is None
    assert item.business_district == "中心区"
    assert item.landmark == "市民中心"
    assert item.metro_station == "市民中心站"
    assert item.missing_fields == (CandidateField.CITY_HINT, CandidateField.ADDRESS)
    assert item.uncertainties[0].reason == "入口位置待确认"

    with sqlite3.connect(database_path) as connection:
        operation = connection.execute(
            "SELECT request_fingerprint, undo_token_hash FROM collection_write_operations"
        ).fetchone()
        assert operation is not None
        assert operation[0] != candidate.model_dump_json()
        assert operation[1] == hashlib.sha256(TOKEN_ONE.encode()).hexdigest()
        dump = "\n".join(connection.iterdump())
    assert TOKEN_ONE not in dump
    await database.close()


@pytest.mark.asyncio
async def test_auto_save_event_and_multiple_cross_city_candidates_share_one_source(
    write_database: tuple[str, Path],
) -> None:
    database_url, _ = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    source = _source(user.id)
    candidates = (
        _event(),
        _place(title="广州地点", city_hint="广州"),
        _place(title="上海地点", city_hint="上海"),
    )

    async with database.session() as session:
        original = tuple(candidate.model_dump(mode="python") for candidate in candidates)
        result = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="multi-city",
            source=source,
            extraction_result=ExtractionResult.with_candidates(candidates),
        )
        assert original == tuple(candidate.model_dump(mode="python") for candidate in candidates)

    assert [item.status for item in result.items] == [
        CollectionStatus.PENDING_DETAILS,
        CollectionStatus.PENDING_DETAILS,
        CollectionStatus.PENDING_DETAILS,
    ]
    assert [item.city_hint for item in result.items] == ["深圳", "广州", "上海"]
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        links = [
            await repository.list_collection_sources(
                user_id=user.id,
                collection_item_id=item.id,
            )
            for item in result.items
        ]
        assert {link[0].source_id for link in links} == {source.id}
        assert len(await repository.list_sources(user_id=user.id)) == 1
    await database.close()


@pytest.mark.asyncio
async def test_date_only_event_auto_save_and_replay_preserve_dates_but_stay_pending(
    write_database: tuple[str, Path],
) -> None:
    database_url, _ = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    source = _source(user.id)
    candidate = _date_only_event()

    async with database.session() as session:
        service = _service(session)
        first = await service.auto_save(
            user_id=user.id,
            idempotency_key="date-only-event",
            source=source,
            extraction_result=ExtractionResult.with_candidates((candidate,)),
        )
    async with database.session() as session:
        replay = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="date-only-event",
            source=source,
            extraction_result=ExtractionResult.with_candidates((candidate,)),
        )

    assert first.items[0].status is CollectionStatus.PENDING_DETAILS
    assert first.items[0].event_start_date == date(2026, 6, 13)
    assert first.items[0].event_end_date == date(2026, 7, 31)
    assert first.items[0].event_start_at is None
    assert replay.replayed is True
    assert replay.items == first.items
    await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extraction_result",
    [
        ExtractionResult.unsupported(reason_code=ExtractionReasonCode.INPUT_EMPTY),
        ExtractionResult.insufficient(
            missing_fields=(CandidateField.TITLE,),
            recovery_suggestions=("请补充名称",),
        ),
        ExtractionResult.model_invalid(),
    ],
)
async def test_non_candidate_outcomes_create_no_collection_or_write_operation(
    write_database: tuple[str, Path],
    extraction_result: ExtractionResult,
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    async with database.session() as session:
        result = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="no-candidate",
            source=_source(user.id),
            extraction_result=extraction_result,
        )
    assert result.items == () and result.undo_token is None and result.source_id is None
    with sqlite3.connect(database_path) as connection:
        for table in ("sources", "collection_items", "collection_write_operations"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
    await database.close()


@pytest.mark.asyncio
async def test_idempotency_replays_without_new_rows_or_second_plaintext_token_and_conflicts(
    write_database: tuple[str, Path],
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    source = _source(user.id)
    extraction = ExtractionResult.with_candidates((_place(), _event()))

    async with database.session() as session:
        service = _service(session)
        first = await service.auto_save(
            user_id=user.id,
            idempotency_key="same-key",
            source=source,
            extraction_result=extraction,
        )
        replay = await service.auto_save(
            user_id=user.id,
            idempotency_key="same-key",
            source=source,
            extraction_result=extraction,
        )
        source_replay = await service.auto_save(
            user_id=user.id,
            idempotency_key="different-key-same-source",
            source=source,
            extraction_result=extraction,
        )
        with pytest.raises(IdempotencyConflictError):
            await service.auto_save(
                user_id=user.id,
                idempotency_key="same-key",
                source=source,
                extraction_result=ExtractionResult.with_candidates(
                    (_place(title="不同载荷"),)
                ),
            )

    assert first.undo_token is not None
    assert replay.replayed and replay.undo_token is None
    assert source_replay.replayed and source_replay.undo_token is None
    assert [item.id for item in first.items] == [item.id for item in replay.items]
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_write_operations"
        ).fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM collection_items").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM collection_sources").fetchone() == (2,)
    await database.close()


@pytest.mark.asyncio
async def test_same_key_isolated_by_user_and_concurrent_same_key_creates_one_result(
    write_database: tuple[str, Path],
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    first_user, second_user = _user(), _user()
    await _add_user(database, first_user)
    await _add_user(database, second_user)

    async with database.session() as first_session, database.session() as second_session:
        first, second = await asyncio.gather(
            _service(first_session, token=TOKEN_ONE).auto_save(
                user_id=first_user.id,
                idempotency_key="shared-key",
                source=_source(first_user.id),
                extraction_result=ExtractionResult.with_candidates((_place(),)),
            ),
            _service(second_session, token=TOKEN_TWO).auto_save(
                user_id=second_user.id,
                idempotency_key="shared-key",
                source=_source(second_user.id),
                extraction_result=ExtractionResult.with_candidates((_place(),)),
            ),
        )
    assert first.items[0].user_id == first_user.id
    assert second.items[0].user_id == second_user.id

    concurrent_source = _source(first_user.id)
    concurrent_extraction = ExtractionResult.with_candidates((_place(title="并发"),))
    async with database.session() as left_session, database.session() as right_session:
        left, right = await asyncio.gather(
            _service(left_session, token="undo_" + "c" * 43).auto_save(
                user_id=first_user.id,
                idempotency_key="concurrent-key",
                source=concurrent_source,
                extraction_result=concurrent_extraction,
            ),
            _service(right_session, token="undo_" + "d" * 43).auto_save(
                user_id=first_user.id,
                idempotency_key="concurrent-key",
                source=concurrent_source,
                extraction_result=concurrent_extraction,
            ),
        )
    assert left.items[0].id == right.items[0].id
    assert {left.replayed, right.replayed} == {False, True}
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_write_operations WHERE idempotency_key = ?",
            ("concurrent-key",),
        ).fetchone() == (1,)
    await database.close()


@pytest.mark.asyncio
async def test_mid_transaction_failure_rolls_back_everything_and_retry_is_safe(
    write_database: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    source = _source(user.id)
    extraction = ExtractionResult.with_candidates((_place(), _event()))

    async with database.session() as session:
        service = _service(session)
        original = service._repository.add_collection_source
        calls = 0

        async def fail_second_link(**kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected failure")
            return await original(**kwargs)

        monkeypatch.setattr(service._repository, "add_collection_source", fail_second_link)
        with pytest.raises(RuntimeError, match="injected failure"):
            await service.auto_save(
                user_id=user.id,
                idempotency_key="retry-after-failure",
                source=source,
                extraction_result=extraction,
            )
        with sqlite3.connect(database_path) as connection:
            for table in (
                "sources",
                "collection_items",
                "collection_sources",
                "collection_write_operations",
                "collection_write_operation_items",
            ):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (
                    0,
                )
        monkeypatch.setattr(service._repository, "add_collection_source", original)
        retried = await service.auto_save(
            user_id=user.id,
            idempotency_key="retry-after-failure",
            source=source,
            extraction_result=extraction,
        )

    assert len(retried.items) == 2
    with sqlite3.connect(database_path) as connection:
        for table, expected in (
            ("sources", 1),
            ("collection_items", 2),
            ("collection_sources", 2),
            ("collection_write_operations", 1),
            ("collection_write_operation_items", 2),
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (
                expected,
            )
    await database.close()


@pytest.mark.asyncio
async def test_undo_group_is_atomic_idempotent_and_never_deletes_shared_source(
    write_database: tuple[str, Path],
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    source = _source(user.id)
    clock = MutableClock()
    async with database.session() as session:
        service = _service(session, clock=clock)
        saved = await service.auto_save(
            user_id=user.id,
            idempotency_key="undo-group",
            source=source,
            extraction_result=ExtractionResult.with_candidates((_place(), _event())),
        )
        assert saved.undo_token is not None
        token = saved.undo_token.get_secret_value()
        undone = await service.undo(user_id=user.id, undo_token=token)
        repeated = await service.undo(user_id=user.id, undo_token=token)

    assert undone.outcome is UndoOutcome.UNDONE
    assert repeated.outcome is UndoOutcome.ALREADY_UNDONE
    assert set(undone.collection_item_ids) == {item.id for item in saved.items}
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM collection_sources").fetchone() == (
            2,
        )
        assert connection.execute(
            "SELECT DISTINCT status FROM collection_items"
        ).fetchall() == [("deleted",)]
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        assert await repository.list_collection_items(user_id=user.id) == []
        assert len(
            await repository.list_collection_items(user_id=user.id, include_inactive=True)
        ) == 2
    await database.close()


@pytest.mark.asyncio
async def test_concurrent_undo_claims_once_and_both_requests_are_idempotent(
    write_database: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    source = _source(user.id)
    async with database.session() as session:
        saved = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="concurrent-undo",
            source=source,
            extraction_result=ExtractionResult.with_candidates((_place(), _event())),
        )
    assert saved.undo_token is not None
    token = saved.undo_token.get_secret_value()

    claim_barrier = asyncio.Barrier(2)
    delete_calls = 0
    async with database.session() as left_session, database.session() as right_session:
        left = _service(left_session)
        right = _service(right_session)

        def install_claim_gate(service: CollectionWriteService) -> None:
            original_claim = service._repository.claim_write_operation_undo
            original_delete = service._repository.delete_collection_item

            async def gated_claim(**kwargs: Any) -> bool:
                await claim_barrier.wait()
                return await original_claim(**kwargs)

            async def counted_delete(**kwargs: Any) -> Any:
                nonlocal delete_calls
                delete_calls += 1
                return await original_delete(**kwargs)

            monkeypatch.setattr(
                service._repository,
                "claim_write_operation_undo",
                gated_claim,
            )
            monkeypatch.setattr(
                service._repository,
                "delete_collection_item",
                counted_delete,
            )

        install_claim_gate(left)
        install_claim_gate(right)
        results = await asyncio.gather(
            left.undo(user_id=user.id, undo_token=token),
            right.undo(user_id=user.id, undo_token=token),
        )

    assert {result.outcome for result in results} == {
        UndoOutcome.UNDONE,
        UndoOutcome.ALREADY_UNDONE,
    }
    assert all(
        set(result.collection_item_ids) == {item.id for item in saved.items}
        for result in results
    )
    assert delete_calls == len(saved.items)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM collection_sources").fetchone() == (
            len(saved.items),
        )
        assert connection.execute(
            "SELECT undone_at IS NOT NULL FROM collection_write_operations"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT status, version FROM collection_items ORDER BY id"
        ).fetchall() == [("deleted", 2), ("deleted", 2)]
    await database.close()


@pytest.mark.asyncio
async def test_undo_expiry_boundary_wrong_user_random_token_and_already_deleted_item(
    write_database: tuple[str, Path],
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user, other = _user(), _user()
    await _add_user(database, user)
    await _add_user(database, other)
    clock = MutableClock()
    async with database.session() as session:
        service = _service(session, clock=clock)
        saved = await service.auto_save(
            user_id=user.id,
            idempotency_key="expiry",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((_place(),)),
        )
        assert saved.undo_token is not None and saved.undo_expires_at is not None
        token = saved.undo_token.get_secret_value()
        assert (
            await service.undo(user_id=other.id, undo_token=token)
        ).outcome is UndoOutcome.NOT_AVAILABLE
        assert (
            await service.undo(user_id=user.id, undo_token="random-token")
        ).outcome is UndoOutcome.NOT_AVAILABLE
        await service.delete(
            user_id=user.id,
            collection_item_id=saved.items[0].id,
            expected_version=1,
        )
        clock.value = saved.undo_expires_at - timedelta(microseconds=1)
        assert (
            await service.undo(user_id=user.id, undo_token=token)
        ).outcome is UndoOutcome.UNDONE

    async with database.session() as session:
        second_clock = MutableClock()
        second_service = _service(session, clock=second_clock, token=TOKEN_TWO)
        second = await second_service.auto_save(
            user_id=user.id,
            idempotency_key="expiry-boundary",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((_place(),)),
        )
        assert second.undo_token is not None and second.undo_expires_at is not None
        second_clock.value = second.undo_expires_at
        assert (
            await second_service.undo(
                user_id=user.id,
                undo_token=second.undo_token.get_secret_value(),
            )
        ).outcome is UndoOutcome.NOT_AVAILABLE
    await database.close()


@pytest.mark.asyncio
async def test_undo_partial_failure_rolls_back_all_items_and_can_retry(
    write_database: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    async with database.session() as session:
        service = _service(session)
        saved = await service.auto_save(
            user_id=user.id,
            idempotency_key="undo-rollback",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((_place(), _event())),
        )
        assert saved.undo_token is not None
        original = service._repository.delete_collection_item
        calls = 0

        async def fail_second_delete(**kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("undo failure")
            return await original(**kwargs)

        monkeypatch.setattr(service._repository, "delete_collection_item", fail_second_delete)
        with pytest.raises(RuntimeError, match="undo failure"):
            await service.undo(
                user_id=user.id,
                undo_token=saved.undo_token.get_secret_value(),
            )
        with sqlite3.connect(database_path) as connection:
            assert set(
                connection.execute("SELECT status FROM collection_items").fetchall()
            ) == {("pending_details",)}
            assert connection.execute(
                "SELECT undone_at FROM collection_write_operations"
            ).fetchone() == (None,)
        monkeypatch.setattr(service._repository, "delete_collection_item", original)
        retried = await service.undo(
            user_id=user.id,
            undo_token=saved.undo_token.get_secret_value(),
        )
    assert retried.outcome is UndoOutcome.UNDONE
    await database.close()


@pytest.mark.asyncio
async def test_concurrent_undo_failure_rolls_back_claim_and_items_before_retry(
    write_database: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, database_path = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    async with database.session() as session:
        saved = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="concurrent-undo-rollback",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((_place(), _event())),
        )
    assert saved.undo_token is not None
    token = saved.undo_token.get_secret_value()

    second_waiting = asyncio.Event()
    release_second = asyncio.Event()
    async with database.session() as failing_session, database.session() as retry_session:
        failing = _service(failing_session)
        retrying = _service(retry_session)
        failing_claim = failing._repository.claim_write_operation_undo
        retry_claim = retrying._repository.claim_write_operation_undo
        failing_delete = failing._repository.delete_collection_item
        delete_calls = 0

        async def claim_then_wait_for_contender(**kwargs: Any) -> bool:
            claimed = await failing_claim(**kwargs)
            await second_waiting.wait()
            return claimed

        async def wait_before_retry_claim(**kwargs: Any) -> bool:
            second_waiting.set()
            await release_second.wait()
            return await retry_claim(**kwargs)

        async def fail_second_delete(**kwargs: Any) -> Any:
            nonlocal delete_calls
            delete_calls += 1
            if delete_calls == 2:
                raise RuntimeError("concurrent undo failure")
            return await failing_delete(**kwargs)

        monkeypatch.setattr(
            failing._repository,
            "claim_write_operation_undo",
            claim_then_wait_for_contender,
        )
        monkeypatch.setattr(
            retrying._repository,
            "claim_write_operation_undo",
            wait_before_retry_claim,
        )
        monkeypatch.setattr(
            failing._repository,
            "delete_collection_item",
            fail_second_delete,
        )

        failed_task = asyncio.create_task(failing.undo(user_id=user.id, undo_token=token))
        retry_task = asyncio.create_task(retrying.undo(user_id=user.id, undo_token=token))
        with pytest.raises(RuntimeError, match="concurrent undo failure"):
            await failed_task

        with sqlite3.connect(database_path) as connection:
            assert connection.execute(
                "SELECT undone_at FROM collection_write_operations"
            ).fetchone() == (None,)
            assert set(
                connection.execute("SELECT status, version FROM collection_items").fetchall()
            ) == {("pending_details", 1)}

        release_second.set()
        retried = await retry_task

    assert retried.outcome is UndoOutcome.UNDONE
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT undone_at IS NOT NULL FROM collection_write_operations"
        ).fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM collection_sources").fetchone() == (
            2,
        )
    await database.close()


@pytest.mark.asyncio
async def test_patch_all_allowed_fields_version_conflict_noop_and_domain_validation(
    write_database: tuple[str, Path],
) -> None:
    database_url, _ = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    clock = MutableClock()
    async with database.session() as session:
        service = _service(session, clock=clock)
        saved = await service.auto_save(
            user_id=user.id,
            idempotency_key="patch-event",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((_event(),)),
        )
        item = saved.items[0]
        clock.value += timedelta(minutes=1)
        updated = await service.patch(
            user_id=user.id,
            collection_item_id=item.id,
            expected_version=1,
            patch=CollectionItemPatch(
                title="新展览",
                city_hint=" 上海 ",
                district="黄浦区",
                address="人民大道 1 号",
                business_district="人民广场",
                landmark="上海博物馆",
                metro_station="人民广场站",
                event_start_at=NOW + timedelta(days=1),
                event_end_at=NOW + timedelta(days=1, hours=2),
                event_start_clue="明日上午",
                event_end_clue="明日中午",
                price_amount=Decimal("0.00"),
                tags=("免费", "室内"),
                missing_fields=(),
                uncertainties=(
                    Uncertainty(field=CandidateField.ADDRESS, reason="入口待确认"),
                ),
            ),
        )
        assert updated.version == 2
        assert updated.city_hint == "上海"
        assert updated.title == "新展览"
        assert updated.tags == ("免费", "室内")
        assert updated.price_amount == Decimal("0.00")
        assert updated.price_currency == "CNY"
        noop = await service.patch(
            user_id=user.id,
            collection_item_id=item.id,
            expected_version=2,
            patch=CollectionItemPatch(title="新展览"),
        )
        assert noop.version == 2 and noop.updated_at == updated.updated_at
        with pytest.raises(VersionConflictError):
            await service.patch(
                user_id=user.id,
                collection_item_id=item.id,
                expected_version=1,
                patch=CollectionItemPatch(title="旧写覆盖"),
            )
        with pytest.raises(ValidationError):
            await service.patch(
                user_id=user.id,
                collection_item_id=item.id,
                expected_version=2,
                patch=CollectionItemPatch(city_hint="   "),
            )
        with pytest.raises(ValidationError):
            await service.patch(
                user_id=user.id,
                collection_item_id=item.id,
                expected_version=2,
                patch=CollectionItemPatch(price_currency=None),
            )
        with pytest.raises(ValidationError):
            await service.patch(
                user_id=user.id,
                collection_item_id=item.id,
                expected_version=2,
                patch=CollectionItemPatch(
                    event_start_at=NOW + timedelta(days=2),
                    event_end_at=NOW + timedelta(days=1),
                ),
            )
        cleared = await service.patch(
            user_id=user.id,
            collection_item_id=item.id,
            expected_version=2,
            patch=CollectionItemPatch(price_amount=None),
        )
        assert cleared.price_amount is None
        assert cleared.price_currency is None
        assert cleared.version == 3
    await database.close()


@pytest.mark.asyncio
async def test_patch_resolves_missing_metadata_then_requires_ambiguous_place_selection(
    write_database: tuple[str, Path],
) -> None:
    database_url, _ = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    source = _source(user.id)
    candidate = PlaceCandidate(
        title="未名咖啡",
        city_hint="深圳",
        missing_fields=(
            CandidateField.DISTRICT,
            CandidateField.BUSINESS_DISTRICT,
            CandidateField.LANDMARK,
            CandidateField.METRO_STATION,
            CandidateField.PRICE,
            CandidateField.TAGS,
        ),
        uncertainties=(
            Uncertainty(field=CandidateField.ADDRESS, reason="地址待补充"),
        ),
    )
    matching = PlaceMatchingService(
        map_provider=make_stub_map_provider(),
        policy=PlaceMatchingPolicy(
            unique_match_score=70,
            minimum_score_gap=10,
            candidate_score=35,
        ),
    )

    async with database.session() as session:
        saved = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="details-to-candidates",
            source=source,
            extraction_result=ExtractionResult.with_candidates((candidate,)),
        )
        pending = await _service(session).patch(
            user_id=user.id,
            collection_item_id=saved.items[0].id,
            expected_version=saved.items[0].version,
            patch=CollectionItemPatch(address="福中一路"),
            place_matching=matching,
        )

        assert pending.status is CollectionStatus.PENDING_SELECTION
        assert CandidateField.ADDRESS not in pending.missing_fields
        assert all(
            uncertainty.field is not CandidateField.ADDRESS
            for uncertainty in pending.uncertainties
        )
        assert pending.place_candidate_snapshot is not None
        assert len(pending.place_candidate_snapshot.candidates) == 2

        selected_candidate = pending.place_candidate_snapshot.candidates[0]
        selection = await PlaceTargetSelectionService(
            session=session
        ).apply_selection(
            user_id=user.id,
            collection_item_id=pending.id,
            source_id=source.id,
            selections=(
                PlaceSelection(
                    kind=PlaceSelectionKind.CANDIDATE,
                    provider=selected_candidate.provider,
                    poi_id=selected_candidate.poi_id,
                ),
            ),
            queried_at=pending.place_candidate_snapshot.queried_at,
            snapshot_fingerprint=pending.place_candidate_snapshot.fingerprint,
            idempotency_key="choose-branch",
            expected_version=pending.version,
        )

    active = selection.items[0]
    assert active.status is CollectionStatus.ACTIVE
    assert active.place_target is not None
    assert CandidateField.CITY_HINT not in active.missing_fields
    assert CandidateField.ADDRESS not in active.missing_fields
    await database.close()


@pytest.mark.asyncio
async def test_patch_can_activate_one_clear_place_but_never_provider_rank_alone(
    write_database: tuple[str, Path],
) -> None:
    database_url, _ = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    candidate = PlaceCandidate(
        title="深圳当代艺术与城市规划馆",
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
    )
    matching = PlaceMatchingService(
        map_provider=make_stub_map_provider(),
        policy=PlaceMatchingPolicy(
            unique_match_score=35,
            minimum_score_gap=5,
            candidate_score=30,
        ),
    )

    async with database.session() as session:
        saved = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="unique-place",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((candidate,)),
        )
        active = await _service(session).patch(
            user_id=user.id,
            collection_item_id=saved.items[0].id,
            expected_version=saved.items[0].version,
            patch=CollectionItemPatch(address="福中路184号"),
            place_matching=matching,
        )

    assert active.status is CollectionStatus.ACTIVE
    assert active.place_target is not None
    assert active.place_target.poi.poi_id == "poi_sz_moca_up"
    await database.close()


@pytest.mark.asyncio
async def test_patch_and_delete_hide_cross_user_existence_and_delete_is_idempotent(
    write_database: tuple[str, Path],
) -> None:
    database_url, _ = write_database
    database = Database(database_url)
    user, other = _user(), _user()
    await _add_user(database, user)
    await _add_user(database, other)
    async with database.session() as session:
        service = _service(session)
        saved = await service.auto_save(
            user_id=user.id,
            idempotency_key="delete",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((_place(),)),
        )
        item = saved.items[0]
        missing_id = "col_1234567890abcdef1234567890abcdef"
        errors: list[str] = []
        for owner, identifier in ((other.id, item.id), (user.id, missing_id)):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await service.patch(
                    user_id=owner,
                    collection_item_id=identifier,
                    expected_version=1,
                    patch=CollectionItemPatch(title="不可见"),
                )
            errors.append(str(exc_info.value))
        assert errors[0] == errors[1] == "resource not found"

        deleted = await service.delete(
            user_id=user.id,
            collection_item_id=item.id,
            expected_version=1,
        )
        repeated = await service.delete(
            user_id=user.id,
            collection_item_id=item.id,
            expected_version=1,
        )
        assert deleted.status is CollectionStatus.DELETED and deleted.version == 2
        assert repeated == deleted

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        assert await repository.list_collection_items(user_id=user.id) == []
        assert await repository.list_collection_items(
            user_id=user.id,
            include_inactive=True,
        ) == [deleted]
    await database.close()


@pytest.mark.asyncio
async def test_concurrent_delete_is_idempotent_and_increments_version_once(
    write_database: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, _ = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    async with database.session() as session:
        saved = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="concurrent-delete",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((_place(),)),
        )
    item = saved.items[0]

    delete_barrier = asyncio.Barrier(2)
    async with database.session() as left_session, database.session() as right_session:
        left = _service(left_session)
        right = _service(right_session)

        def install_delete_gate(service: CollectionWriteService) -> None:
            original = service._repository.delete_collection_item

            async def gated_delete(**kwargs: Any) -> Any:
                await delete_barrier.wait()
                return await original(**kwargs)

            monkeypatch.setattr(service._repository, "delete_collection_item", gated_delete)

        install_delete_gate(left)
        install_delete_gate(right)
        deleted = await asyncio.gather(
            left.delete(
                user_id=user.id,
                collection_item_id=item.id,
                expected_version=1,
            ),
            right.delete(
                user_id=user.id,
                collection_item_id=item.id,
                expected_version=1,
            ),
        )

    assert all(result.status is CollectionStatus.DELETED for result in deleted)
    assert [result.version for result in deleted] == [2, 2]
    async with database.session() as session:
        stored = await SqlAlchemyCollectionRepository(session).get_collection_item(
            user_id=user.id,
            collection_item_id=item.id,
        )
    assert stored is not None
    assert stored.status is CollectionStatus.DELETED
    assert stored.version == 2
    await database.close()


@pytest.mark.asyncio
async def test_delete_cas_miss_after_other_edit_remains_a_version_conflict(
    write_database: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, _ = write_database
    database = Database(database_url)
    user = _user()
    await _add_user(database, user)
    async with database.session() as session:
        saved = await _service(session).auto_save(
            user_id=user.id,
            idempotency_key="delete-versus-patch",
            source=_source(user.id),
            extraction_result=ExtractionResult.with_candidates((_place(),)),
        )
    item = saved.items[0]

    delete_waiting = asyncio.Event()
    patch_committed = asyncio.Event()
    async with database.session() as patch_session, database.session() as delete_session:
        patch_service = _service(patch_session)
        delete_service = _service(delete_session)
        original_delete = delete_service._repository.delete_collection_item

        async def delete_after_patch(**kwargs: Any) -> Any:
            delete_waiting.set()
            await patch_committed.wait()
            return await original_delete(**kwargs)

        async def commit_patch() -> Any:
            await delete_waiting.wait()
            updated = await patch_service.patch(
                user_id=user.id,
                collection_item_id=item.id,
                expected_version=1,
                patch=CollectionItemPatch(title="并发修改后的标题"),
            )
            patch_committed.set()
            return updated

        monkeypatch.setattr(
            delete_service._repository,
            "delete_collection_item",
            delete_after_patch,
        )
        delete_task = asyncio.create_task(
            delete_service.delete(
                user_id=user.id,
                collection_item_id=item.id,
                expected_version=1,
            )
        )
        updated = await commit_patch()
        with pytest.raises(VersionConflictError):
            await delete_task

    assert updated.version == 2
    assert updated.status is CollectionStatus.PENDING_DETAILS
    async with database.session() as session:
        stored = await SqlAlchemyCollectionRepository(session).get_collection_item(
            user_id=user.id,
            collection_item_id=item.id,
        )
    assert stored is not None
    assert stored.title == "并发修改后的标题"
    assert stored.status is CollectionStatus.PENDING_DETAILS
    assert stored.version == 2
    await database.close()

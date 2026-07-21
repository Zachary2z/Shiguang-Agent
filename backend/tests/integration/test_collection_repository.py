"""M0-2A repository round trips, isolation, association, and rollback tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from app.domain.collections import (
    CollectionItem,
    CollectionKind,
    CollectionStatus,
    Message,
    MessageContentType,
    MessageRole,
    ResourceNotFoundError,
    Session,
    SessionChannel,
    Source,
    SourceMetadata,
    SourceParseStatus,
    SourceType,
    User,
    UserMode,
)
from app.domain.identifiers import (
    generate_collection_item_id,
    generate_message_id,
    generate_session_id,
    generate_source_id,
    generate_user_id,
)
from app.infrastructure.db import Database
from app.infrastructure.repositories import SqlAlchemyCollectionRepository

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)


@pytest.fixture
def collection_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[str, Path]:
    database_path = tmp_path / "collections.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_url, database_path


def _user(*, user_id: str | None = None) -> User:
    return User(id=user_id or generate_user_id(), mode=UserMode.REAL, created_at=NOW)


def _session(user_id: str) -> Session:
    return Session(
        id=generate_session_id(),
        user_id=user_id,
        channel=SessionChannel.WEB,
        created_at=NOW,
        updated_at=NOW,
    )


def _message(session_id: str) -> Message:
    return Message(
        id=generate_message_id(),
        session_id=session_id,
        role=MessageRole.USER,
        content_type=MessageContentType.TEXT,
        content="想去深圳当代艺术与城市规划馆",
        created_at=NOW,
    )


def _source(user_id: str) -> Source:
    return Source(
        id=generate_source_id(),
        user_id=user_id,
        type=SourceType.TEXT,
        parse_status=SourceParseStatus.PENDING,
        metadata=SourceMetadata(content_sha256="a" * 64),
        created_at=NOW,
        updated_at=NOW,
    )


def _item(
    user_id: str,
    *,
    status: CollectionStatus = CollectionStatus.ACTIVE,
    title: str = "深圳当代艺术与城市规划馆",
) -> CollectionItem:
    return CollectionItem(
        id=generate_collection_item_id(),
        user_id=user_id,
        kind=CollectionKind.PLACE,
        title=title,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_all_entities_create_read_list_update_and_link_round_trip(
    collection_database: tuple[str, Path],
) -> None:
    database_url, _database_path = collection_database
    database = Database(database_url)
    user = _user()
    session_entity = _session(user.id)
    message = _message(session_entity.id)
    source = _source(user.id)
    item = _item(user.id, status=CollectionStatus.RECOGNIZING)

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        assert await repository.add_user(user_id=user.id, user=user) == user
        assert (
            await repository.add_session(user_id=user.id, session=session_entity)
            == session_entity
        )
        assert await repository.add_message(user_id=user.id, message=message) == message
        assert await repository.add_source(user_id=user.id, source=source) == source
        assert await repository.add_collection_item(user_id=user.id, item=item) == item
        link = await repository.add_collection_source(
            user_id=user.id,
            collection_item_id=item.id,
            source_id=source.id,
            created_at=NOW,
        )
        await session.commit()

        assert link.user_id == user.id
        assert await repository.get_user(user_id=user.id) == user
        assert await repository.get_session(
            user_id=user.id,
            session_id=session_entity.id,
        ) == session_entity
        assert await repository.get_message(user_id=user.id, message_id=message.id) == message
        assert await repository.get_source(user_id=user.id, source_id=source.id) == source
        assert await repository.get_collection_item(
            user_id=user.id,
            collection_item_id=item.id,
        ) == item
        assert await repository.list_sessions(user_id=user.id) == [session_entity]
        assert await repository.list_messages(
            user_id=user.id,
            session_id=session_entity.id,
        ) == [message]
        assert await repository.list_sources(user_id=user.id) == [source]
        assert await repository.list_collection_sources(
            user_id=user.id,
            collection_item_id=item.id,
        ) == [link]

        updated_source = await repository.update_source_parse_status(
            user_id=user.id,
            source_id=source.id,
            parse_status=SourceParseStatus.PARSED,
            updated_at=NOW + timedelta(seconds=1),
        )
        active_item = await repository.transition_collection_status(
            user_id=user.id,
            collection_item_id=item.id,
            target=CollectionStatus.ACTIVE,
            updated_at=NOW + timedelta(seconds=1),
        )
        await session.commit()

        assert updated_source.parse_status is SourceParseStatus.PARSED
        assert updated_source.updated_at == NOW + timedelta(seconds=1)
        assert active_item.status is CollectionStatus.ACTIVE
        assert active_item.version == 2
        assert await repository.list_collection_items(user_id=user.id) == [active_item]
    await database.close()


@pytest.mark.asyncio
async def test_default_collection_query_excludes_non_effective_and_deleted_states(
    collection_database: tuple[str, Path],
) -> None:
    database_url, _database_path = collection_database
    database = Database(database_url)
    user = _user()
    items = [
        _item(user.id, status=status, title=status.value)
        for status in CollectionStatus
        if status is not CollectionStatus.FAILED
    ]
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        for item in items:
            await repository.add_collection_item(user_id=user.id, item=item)
        await session.commit()

        default_statuses = {
            item.status for item in await repository.list_collection_items(user_id=user.id)
        }
        all_statuses = {
            item.status
            for item in await repository.list_collection_items(
                user_id=user.id,
                include_inactive=True,
            )
        }

    assert CollectionStatus.FAILED not in default_statuses
    assert CollectionStatus.DELETED not in default_statuses
    assert CollectionStatus.RECOGNIZING not in default_statuses
    assert CollectionStatus.ARCHIVED not in default_statuses
    assert default_statuses == {
        CollectionStatus.ACTIVE,
        CollectionStatus.PENDING_SELECTION,
        CollectionStatus.PENDING_DETAILS,
        CollectionStatus.VISITED,
    }
    assert all_statuses == set(CollectionStatus) - {CollectionStatus.FAILED}
    await database.close()


@pytest.mark.asyncio
async def test_failed_source_persists_but_failed_collection_item_never_does(
    collection_database: tuple[str, Path],
) -> None:
    database_url, database_path = collection_database
    database = Database(database_url)
    user = _user()
    failed_source = _source(user.id).model_copy(
        update={"parse_status": SourceParseStatus.FAILED}
    )
    unsafe_failed_item = CollectionItem.model_construct(
        id=generate_collection_item_id(),
        user_id=user.id,
        kind=CollectionKind.PLACE,
        title="uncollected raw result",
        status=CollectionStatus.FAILED,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        await repository.add_source(user_id=user.id, source=failed_source)
        await session.commit()

        with pytest.raises(
            ValueError,
            match="failed recognition outcomes cannot be persisted as CollectionItem",
        ):
            await repository.add_collection_item(
                user_id=user.id,
                item=unsafe_failed_item,
            )
        assert await repository.list_collection_items(
            user_id=user.id,
            include_inactive=True,
        ) == []
        assert (await repository.list_sources(user_id=user.id))[0].parse_status is (
            SourceParseStatus.FAILED
        )
    await database.close()

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO collection_items (
                    id, user_id, kind, title, city, tags_json, status, version,
                    created_at, updated_at
                ) VALUES (?, ?, 'place', 'raw failure', 'shenzhen', '[]',
                    'failed', 1, ?, ?)
                """,
                (
                    generate_collection_item_id(),
                    user.id,
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )
        connection.rollback()
        assert connection.execute("SELECT COUNT(*) FROM collection_items").fetchone() == (0,)


@pytest.mark.asyncio
async def test_transition_to_failed_is_rejected_without_changing_persisted_item(
    collection_database: tuple[str, Path],
) -> None:
    database_url, _database_path = collection_database
    database = Database(database_url)
    user = _user()
    item = _item(user.id, status=CollectionStatus.RECOGNIZING)

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        await repository.add_collection_item(user_id=user.id, item=item)
        await session.commit()

        with pytest.raises(
            ValueError,
            match="failed recognition outcomes cannot be persisted as CollectionItem",
        ):
            await repository.transition_collection_status(
                user_id=user.id,
                collection_item_id=item.id,
                target=CollectionStatus.FAILED,
                updated_at=NOW + timedelta(seconds=1),
            )
        unchanged = await repository.get_collection_item(
            user_id=user.id,
            collection_item_id=item.id,
        )
        assert unchanged is not None
        assert unchanged.status is CollectionStatus.RECOGNIZING
        assert unchanged.version == 1
    await database.close()


@pytest.mark.asyncio
async def test_system_and_tool_raw_message_content_cannot_be_persisted(
    collection_database: tuple[str, Path],
) -> None:
    database_url, database_path = collection_database
    database = Database(database_url)
    user = _user()
    session_entity = _session(user.id)
    forbidden_messages = [
        Message.model_construct(
            id=generate_message_id(),
            session_id=session_entity.id,
            role=role,
            content_type=MessageContentType.TEXT,
            content=f"private-{role}-payload",
            trace_id=None,
            created_at=NOW,
        )
        for role in ("system", "tool")
    ]

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        await repository.add_session(user_id=user.id, session=session_entity)
        await session.commit()

        for message in forbidden_messages:
            with pytest.raises(
                ValueError,
                match="persisted Message role must be user or assistant",
            ):
                await repository.add_message(user_id=user.id, message=message)
        assert await repository.list_messages(
            user_id=user.id,
            session_id=session_entity.id,
        ) == []
    await database.close()

    with sqlite3.connect(database_path) as connection:
        for index, role in enumerate(("system", "tool"), start=1):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO messages (
                        id, session_id, role, content_type, content, created_at
                    ) VALUES (?, ?, ?, 'text', ?, ?)
                    """,
                    (
                        f"msg_{index:032x}",
                        session_entity.id,
                        role,
                        f"private-{role}-raw-payload",
                        NOW.isoformat(),
                    ),
                )
            connection.rollback()
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone() == (0,)
        dump = "\n".join(connection.iterdump())
        assert "private-system" not in dump
        assert "private-tool" not in dump


@pytest.mark.asyncio
async def test_reads_lists_updates_messages_and_links_are_user_isolated(
    collection_database: tuple[str, Path],
) -> None:
    database_url, _database_path = collection_database
    database = Database(database_url)
    user_a = _user()
    user_b = _user()
    session_a = _session(user_a.id)
    session_b = _session(user_b.id)
    message_b = _message(session_b.id)
    source_a = _source(user_a.id)
    source_b = _source(user_b.id)
    item_a = _item(user_a.id, title="same query")
    item_b = _item(user_b.id, title="same query")

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        for user in (user_a, user_b):
            await repository.add_user(user_id=user.id, user=user)
        for owner, session_entity in ((user_a, session_a), (user_b, session_b)):
            await repository.add_session(user_id=owner.id, session=session_entity)
        await repository.add_message(user_id=user_b.id, message=message_b)
        await repository.add_source(user_id=user_a.id, source=source_a)
        await repository.add_source(user_id=user_b.id, source=source_b)
        await repository.add_collection_item(user_id=user_a.id, item=item_a)
        await repository.add_collection_item(user_id=user_b.id, item=item_b)
        await session.commit()

        assert await repository.get_session(
            user_id=user_a.id,
            session_id=session_b.id,
        ) is None
        assert await repository.get_message(user_id=user_a.id, message_id=message_b.id) is None
        assert await repository.get_source(user_id=user_a.id, source_id=source_b.id) is None
        assert await repository.get_collection_item(
            user_id=user_a.id,
            collection_item_id=item_b.id,
        ) is None
        assert await repository.list_messages(
            user_id=user_a.id,
            session_id=session_b.id,
        ) == []
        assert {item.id for item in await repository.list_collection_items(user_id=user_a.id)} == {
            item_a.id
        }
        assert {item.id for item in await repository.list_collection_items(user_id=user_b.id)} == {
            item_b.id
        }

        missing_source_id = generate_source_id()
        errors: list[str] = []
        for source_id in (source_b.id, missing_source_id):
            with pytest.raises(ResourceNotFoundError) as caught:
                await repository.update_source_parse_status(
                    user_id=user_a.id,
                    source_id=source_id,
                    parse_status=SourceParseStatus.PARSED,
                    updated_at=NOW + timedelta(seconds=1),
                )
            errors.append(str(caught.value))
        assert errors == ["resource not found", "resource not found"]

        for collection_item_id in (item_b.id, generate_collection_item_id()):
            with pytest.raises(ResourceNotFoundError, match="^resource not found$"):
                await repository.transition_collection_status(
                    user_id=user_a.id,
                    collection_item_id=collection_item_id,
                    target=CollectionStatus.VISITED,
                    updated_at=NOW + timedelta(seconds=1),
                )

        with pytest.raises(ResourceNotFoundError, match="^resource not found$"):
            await repository.add_message(user_id=user_a.id, message=message_b)
        with pytest.raises(ResourceNotFoundError, match="^resource not found$"):
            await repository.add_collection_source(
                user_id=user_a.id,
                collection_item_id=item_a.id,
                source_id=source_b.id,
                created_at=NOW,
            )
        with pytest.raises(ResourceNotFoundError, match="^resource not found$"):
            await repository.add_collection_source(
                user_id=user_a.id,
                collection_item_id=item_b.id,
                source_id=source_a.id,
                created_at=NOW,
            )
    await database.close()


@pytest.mark.asyncio
async def test_duplicate_collection_source_fails_and_rollback_keeps_one_link(
    collection_database: tuple[str, Path],
) -> None:
    database_url, _database_path = collection_database
    database = Database(database_url)
    user = _user()
    source = _source(user.id)
    item = _item(user.id)

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        await repository.add_source(user_id=user.id, source=source)
        await repository.add_collection_item(user_id=user.id, item=item)
        await repository.add_collection_source(
            user_id=user.id,
            collection_item_id=item.id,
            source_id=source.id,
            created_at=NOW,
        )
        await session.commit()

    with pytest.raises(IntegrityError):
        async with database.session() as session:
            repository = SqlAlchemyCollectionRepository(session)
            await repository.add_collection_source(
                user_id=user.id,
                collection_item_id=item.id,
                source_id=source.id,
                created_at=NOW + timedelta(seconds=1),
            )

    async with database.session() as session:
        links = await SqlAlchemyCollectionRepository(session).list_collection_sources(
            user_id=user.id,
            collection_item_id=item.id,
        )
        assert len(links) == 1
    await database.close()


@pytest.mark.asyncio
async def test_transaction_error_rolls_back_prior_uncommitted_collection_write(
    collection_database: tuple[str, Path],
) -> None:
    database_url, _database_path = collection_database
    database = Database(database_url)
    user = _user()
    item = _item(user.id)

    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        await session.commit()

    with pytest.raises(ResourceNotFoundError):
        async with database.session() as session:
            repository = SqlAlchemyCollectionRepository(session)
            await repository.add_collection_item(user_id=user.id, item=item)
            await repository.add_collection_source(
                user_id=user.id,
                collection_item_id=item.id,
                source_id=generate_source_id(),
                created_at=NOW,
            )

    async with database.session() as session:
        assert await SqlAlchemyCollectionRepository(session).get_collection_item(
            user_id=user.id,
            collection_item_id=item.id,
        ) is None
    await database.close()


@pytest.mark.asyncio
async def test_persisted_source_metadata_and_database_dump_exclude_sensitive_raw_fields(
    collection_database: tuple[str, Path],
) -> None:
    database_url, database_path = collection_database
    database = Database(database_url)
    user = _user()
    source = Source(
        id=generate_source_id(),
        user_id=user.id,
        type=SourceType.URL,
        url="https://example.test/place",
        metadata=SourceMetadata(
            media_type="text/html",
            byte_size=1024,
            content_sha256="b" * 64,
            http_status=200,
        ),
        fetched_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    async with database.session() as session:
        repository = SqlAlchemyCollectionRepository(session)
        await repository.add_user(user_id=user.id, user=user)
        await repository.add_source(user_id=user.id, source=source)
        await session.commit()
    await database.close()

    dump = database_path.read_bytes().lower()
    for forbidden in (
        b"authorization",
        b"bearer test-secret",
        b"cookie",
        b"set-cookie",
        b"raw_content",
        b"test-secret",
    ):
        assert forbidden not in dump

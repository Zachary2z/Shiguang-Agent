"""M0-2A domain entity, identifier, state, and repository-contract tests."""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.collections import (
    PERSISTABLE_COLLECTION_STATUSES,
    CollectionItem,
    CollectionKind,
    CollectionSource,
    CollectionStatus,
    CollectionWorkflowStatus,
    Message,
    MessageContentType,
    MessageRole,
    PlanCity,
    RecognitionStatus,
    Session,
    SessionChannel,
    SessionStatus,
    Source,
    SourceMetadata,
    SourceParseStatus,
    SourceType,
    SupportedTimezone,
    User,
    UserMode,
    can_collection_enter_plan,
    ensure_collection_transition,
    ensure_persistable_collection_status,
    is_collection_visible_by_default,
)
from app.domain.identifiers import (
    generate_collection_item_id,
    generate_message_id,
    generate_session_id,
    generate_source_id,
    generate_user_id,
    validate_collection_item_id,
    validate_message_id,
    validate_session_id,
    validate_source_id,
    validate_user_id,
)
from app.infrastructure.repositories import SqlAlchemyCollectionRepository

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
USER_ID = "usr_1234567890abcdef1234567890abcdef"
SESSION_ID = "ses_1234567890abcdef1234567890abcdef"
MESSAGE_ID = "msg_1234567890abcdef1234567890abcdef"
SOURCE_ID = "src_1234567890abcdef1234567890abcdef"
ITEM_ID = "col_1234567890abcdef1234567890abcdef"


@pytest.mark.parametrize(
    ("generate", "validate", "prefix"),
    [
        (generate_user_id, validate_user_id, "usr_"),
        (generate_session_id, validate_session_id, "ses_"),
        (generate_message_id, validate_message_id, "msg_"),
        (generate_source_id, validate_source_id, "src_"),
        (generate_collection_item_id, validate_collection_item_id, "col_"),
    ],
)
def test_entity_identifiers_are_opaque_unique_and_format_validated(
    generate: object,
    validate: object,
    prefix: str,
) -> None:
    generator = generate
    validator = validate
    assert callable(generator)
    assert callable(validator)
    identifiers = {generator() for _ in range(128)}

    assert len(identifiers) == 128
    assert all(
        identifier.startswith(prefix) and len(identifier) == 36 for identifier in identifiers
    )
    assert all(validator(identifier) == identifier for identifier in identifiers)


@pytest.mark.parametrize(
    ("validate", "invalid"),
    [
        (validate_user_id, ""),
        (validate_user_id, "   "),
        (validate_user_id, "1"),
        (validate_user_id, "usr_1"),
        (validate_user_id, "usr_00000000000000000000000000000000"),
        (validate_user_id, "12345678-1234-1234-1234-123456789012"),
        (validate_user_id, "usr_1234567890ABCDEF1234567890ABCDEF"),
        (validate_session_id, USER_ID),
        (validate_message_id, SESSION_ID),
        (validate_source_id, MESSAGE_ID),
        (validate_collection_item_id, SOURCE_ID),
    ],
)
def test_invalid_blank_sequential_and_wrong_namespace_ids_are_rejected(
    validate: object,
    invalid: str,
) -> None:
    validator = validate
    assert callable(validator)
    with pytest.raises(ValueError):
        validator(invalid)


def test_user_mode_default_plan_city_timezone_and_utc_boundaries() -> None:
    local_time = datetime(2026, 7, 21, 16, 0, tzinfo=timezone(timedelta(hours=8)))
    user = User(
        id=USER_ID,
        mode=UserMode.REAL,
        default_plan_city=PlanCity.SHENZHEN,
        timezone=SupportedTimezone.ASIA_SHANGHAI,
        created_at=local_time,
    )
    assert user.created_at == NOW
    assert user.created_at.tzinfo is UTC
    assert set(PlanCity) == {PlanCity.SHENZHEN}

    with pytest.raises(ValidationError):
        User(id=USER_ID, mode="real", created_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        User.model_validate(
            {
                "id": USER_ID,
                "mode": UserMode.REAL,
                "default_plan_city": "guangzhou",
                "timezone": SupportedTimezone.ASIA_SHANGHAI,
                "created_at": NOW,
            }
        )
    with pytest.raises(ValidationError):
        User(id=USER_ID, mode=UserMode.REAL, created_at=NOW.replace(tzinfo=None))


def test_session_channel_status_owner_summary_and_time_boundaries() -> None:
    session = Session(
        id=SESSION_ID,
        user_id=USER_ID,
        channel=SessionChannel.WEB,
        status=SessionStatus.ACTIVE,
        summary="first session",
        created_at=NOW,
        updated_at=NOW,
    )
    assert session.user_id == USER_ID
    assert set(SessionChannel) == {SessionChannel.WEB, SessionChannel.DEMO}
    for unavailable_channel in ("wechat", "clawbot"):
        with pytest.raises(ValueError):
            SessionChannel(unavailable_channel)

    with pytest.raises(ValidationError):
        Session(
            id=SESSION_ID,
            user_id="usr_bad",
            channel=SessionChannel.WEB,
            created_at=NOW,
            updated_at=NOW,
        )
    with pytest.raises(ValidationError):
        Session(
            id=SESSION_ID,
            user_id=USER_ID,
            channel="email",  # type: ignore[arg-type]
            created_at=NOW,
            updated_at=NOW,
        )
    with pytest.raises(ValidationError):
        Session(
            id=SESSION_ID,
            user_id=USER_ID,
            channel=SessionChannel.WEB,
            summary="   ",
            created_at=NOW,
            updated_at=NOW,
        )
    with pytest.raises(ValidationError):
        Session(
            id=SESSION_ID,
            user_id=USER_ID,
            channel=SessionChannel.WEB,
            created_at=NOW,
            updated_at=NOW - timedelta(seconds=1),
        )


def test_message_role_content_type_content_and_optional_trace_boundaries() -> None:
    sensitive_content = "private-user-message"
    message = Message(
        id=MESSAGE_ID,
        session_id=SESSION_ID,
        role=MessageRole.USER,
        content_type=MessageContentType.TEXT,
        content=sensitive_content,
        trace_id="trc_1234567890abcdef1234567890abcdef",
        created_at=NOW,
    )
    assert message.trace_id is not None
    assert set(MessageRole) == {MessageRole.USER, MessageRole.ASSISTANT}
    assert sensitive_content not in repr(message)
    assert sensitive_content not in str(message)
    assert Message(
        id=generate_message_id(),
        session_id=SESSION_ID,
        role=MessageRole.ASSISTANT,
        content_type=MessageContentType.TEXT,
        content="已记录",
        created_at=NOW,
    ).trace_id is None

    for field, invalid in (
        ("role", "human"),
        ("content_type", "audio"),
        ("content", "   "),
        ("trace_id", "trc_1"),
    ):
        payload = message.model_dump()
        payload[field] = invalid
        with pytest.raises(ValidationError):
            Message.model_validate(payload)

    for forbidden_role in ("system", "tool"):
        payload = message.model_dump()
        payload["role"] = forbidden_role
        with pytest.raises(ValidationError):
            Message.model_validate(payload, strict=False)


def test_source_type_parse_status_and_allowlisted_security_metadata() -> None:
    metadata = SourceMetadata(
        media_type="text/html",
        byte_size=42,
        content_sha256="a" * 64,
        http_status=200,
    )
    url_source = Source(
        id=SOURCE_ID,
        user_id=USER_ID,
        type=SourceType.URL,
        url="https://example.test/place",
        platform="public_web",
        parse_status=SourceParseStatus.PARSED,
        fetched_at=NOW,
        metadata=metadata,
        created_at=NOW,
        updated_at=NOW,
    )
    assert url_source.metadata == metadata

    Source(
        id=generate_source_id(),
        user_id=USER_ID,
        type=SourceType.TEXT,
        created_at=NOW,
        updated_at=NOW,
    )
    Source(
        id=generate_source_id(),
        user_id=USER_ID,
        type=SourceType.IMAGE,
        file_key="A" * 32,
        created_at=NOW,
        updated_at=NOW,
    )

    with pytest.raises(ValidationError):
        SourceMetadata.model_validate({"authorization": "Bearer secret"})
    with pytest.raises(ValidationError):
        SourceMetadata.model_validate({"cookie": "session=secret"})
    with pytest.raises(ValidationError):
        SourceMetadata.model_validate({"raw_content": "secret"})
    with pytest.raises(ValidationError):
        Source(
            id=generate_source_id(),
            user_id=USER_ID,
            type=SourceType.URL,
            url="https://user:secret@example.test/place",
            created_at=NOW,
            updated_at=NOW,
        )
    with pytest.raises(ValidationError):
        Source(
            id=generate_source_id(),
            user_id=USER_ID,
            type=SourceType.IMAGE,
            url="https://example.test/image.png",
            created_at=NOW,
            updated_at=NOW,
        )


def test_provider_independent_place_event_fields_version_price_and_tags() -> None:
    place = CollectionItem(
        id=ITEM_ID,
        user_id=USER_ID,
        kind=CollectionKind.PLACE,
        title="  深圳当代艺术与城市规划馆  ",
        city_hint="  广州市  ",
        district="福田区",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("室内", "博物馆"),
        status=CollectionStatus.ACTIVE,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    assert place.title == "深圳当代艺术与城市规划馆"
    assert place.city_hint == "广州市"
    assert place.kind is CollectionKind.PLACE
    assert can_collection_enter_plan(place.status)

    event = CollectionItem(
        id=generate_collection_item_id(),
        user_id=USER_ID,
        kind=CollectionKind.EVENT,
        title="设计展",
        event_start_date=date(2026, 7, 25),
        event_end_date=date(2026, 7, 31),
        event_start_at=NOW,
        event_end_at=NOW + timedelta(hours=2),
        status=CollectionStatus.PENDING_DETAILS,
        created_at=NOW,
        updated_at=NOW,
    )
    assert event.kind is CollectionKind.EVENT
    assert event.event_start_date == date(2026, 7, 25)
    assert event.event_end_date == date(2026, 7, 31)
    assert not can_collection_enter_plan(event.status)

    for update in (
        {"version": 0},
        {"price_amount": Decimal("10"), "price_currency": None},
        {"price_amount": None, "price_currency": "CNY"},
        {"price_amount": Decimal("10"), "price_currency": "USD"},
        {"tags": ("室内", "室内")},
        {"event_start_date": date(2026, 7, 25)},
        {"event_start_at": NOW, "event_end_at": NOW + timedelta(hours=1)},
    ):
        payload = place.model_dump()
        payload.update(update)
        with pytest.raises(ValidationError):
            CollectionItem.model_validate(payload)

    for city_hint in ("", "   ", "城" * 101):
        payload = place.model_dump()
        payload["city_hint"] = city_hint
        with pytest.raises(ValidationError):
            CollectionItem.model_validate(payload)

    assert CollectionItem.model_validate(
        {**place.model_dump(), "city_hint": None}
    ).city_hint is None
    assert CollectionItem.model_validate(
        {**place.model_dump(), "city_hint": "上海"}
    ).city_hint == "上海"

    invalid_event = event.model_dump()
    invalid_event["event_end_date"] = date(2026, 7, 24)
    with pytest.raises(ValidationError, match="event_date_order_invalid"):
        CollectionItem.model_validate(invalid_event)

    invalid_event = event.model_dump()
    invalid_event["event_end_at"] = NOW
    with pytest.raises(ValidationError):
        CollectionItem.model_validate(invalid_event)

    for recognition_status in RecognitionStatus:
        uncollected_item = place.model_dump()
        uncollected_item["status"] = recognition_status
        with pytest.raises(ValidationError):
            CollectionItem.model_validate(uncollected_item)


def test_collection_source_validates_owner_and_both_foreign_identifiers() -> None:
    link = CollectionSource(
        user_id=USER_ID,
        collection_item_id=ITEM_ID,
        source_id=SOURCE_ID,
        created_at=NOW,
    )
    assert link.user_id == USER_ID
    with pytest.raises(ValidationError):
        CollectionSource(
            user_id=USER_ID,
            collection_item_id=SOURCE_ID,
            source_id=SOURCE_ID,
            created_at=NOW,
        )


LEGAL_TRANSITIONS = {
    (RecognitionStatus.RECOGNIZING, CollectionStatus.ACTIVE),
    (RecognitionStatus.RECOGNIZING, CollectionStatus.PENDING_SELECTION),
    (RecognitionStatus.RECOGNIZING, CollectionStatus.PENDING_DETAILS),
    (RecognitionStatus.RECOGNIZING, RecognitionStatus.FAILED),
    (CollectionStatus.ACTIVE, CollectionStatus.PENDING_DETAILS),
    (CollectionStatus.ACTIVE, CollectionStatus.VISITED),
    (CollectionStatus.ACTIVE, CollectionStatus.ARCHIVED),
    (CollectionStatus.ACTIVE, CollectionStatus.DELETED),
    (CollectionStatus.PENDING_SELECTION, CollectionStatus.ACTIVE),
    (CollectionStatus.PENDING_SELECTION, CollectionStatus.PENDING_DETAILS),
    (CollectionStatus.PENDING_SELECTION, CollectionStatus.DELETED),
    (CollectionStatus.PENDING_DETAILS, RecognitionStatus.RECOGNIZING),
    (CollectionStatus.PENDING_DETAILS, CollectionStatus.ACTIVE),
    (CollectionStatus.PENDING_DETAILS, CollectionStatus.PENDING_SELECTION),
    (CollectionStatus.PENDING_DETAILS, CollectionStatus.DELETED),
}


@pytest.mark.parametrize(("current", "target"), sorted(LEGAL_TRANSITIONS))
def test_every_legal_collection_transition_succeeds(
    current: CollectionWorkflowStatus,
    target: CollectionWorkflowStatus,
) -> None:
    ensure_collection_transition(current, target)


WORKFLOW_STATUSES: tuple[CollectionWorkflowStatus, ...] = (
    *RecognitionStatus,
    *CollectionStatus,
)


@pytest.mark.parametrize("status", WORKFLOW_STATUSES)
def test_idempotent_collection_transition_succeeds(
    status: CollectionWorkflowStatus,
) -> None:
    ensure_collection_transition(status, status)


ILLEGAL_TRANSITIONS = sorted(
    (current, target)
    for current in WORKFLOW_STATUSES
    for target in WORKFLOW_STATUSES
    if current is not target and (current, target) not in LEGAL_TRANSITIONS
)


@pytest.mark.parametrize(("current", "target"), ILLEGAL_TRANSITIONS)
def test_regressions_skips_and_terminal_collection_transitions_are_rejected(
    current: CollectionWorkflowStatus,
    target: CollectionWorkflowStatus,
) -> None:
    with pytest.raises(ValueError, match="illegal collection workflow transition"):
        ensure_collection_transition(current, target)


def test_recognition_states_are_not_collection_statuses_or_persistable() -> None:
    assert set(PERSISTABLE_COLLECTION_STATUSES) == set(CollectionStatus)
    assert {status.value for status in CollectionStatus}.isdisjoint(
        {status.value for status in RecognitionStatus}
    )
    for status in RecognitionStatus:
        with pytest.raises(
            ValueError,
            match="recognizing and failed outcomes cannot be persisted as CollectionItem",
        ):
            ensure_persistable_collection_status(status)


def test_deleted_and_archived_are_not_default_or_plan_eligible() -> None:
    for status in (CollectionStatus.ARCHIVED, CollectionStatus.DELETED):
        assert not is_collection_visible_by_default(status)
        assert not can_collection_enter_plan(status)
    for status in (CollectionStatus.PENDING_SELECTION, CollectionStatus.PENDING_DETAILS):
        assert is_collection_visible_by_default(status)
        assert not can_collection_enter_plan(status)
    assert is_collection_visible_by_default(CollectionStatus.ACTIVE)
    assert can_collection_enter_plan(CollectionStatus.ACTIVE)


def test_repository_has_no_public_unscoped_query_or_write_method() -> None:
    public_methods = {
        name: member
        for name, member in inspect.getmembers(
            SqlAlchemyCollectionRepository,
            predicate=inspect.iscoroutinefunction,
        )
        if not name.startswith("_")
    }
    assert public_methods
    for name, method in public_methods.items():
        assert "user_id" in inspect.signature(method).parameters, name

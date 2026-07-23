"""Offline contract coverage for the one M0-4D input pipeline."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import text

from app.application.collection_writes import CollectionWriteService
from app.application.demo_sessions import DEMO_USER_ID
from app.application.input_contracts import ImageInput, TextInput, UrlInput
from app.application.pricing import ConfiguredPricingPolicy
from app.application.text_collection_workflow import TextCollectionWorkflow
from app.config import Settings
from app.domain.collections import (
    CandidateField,
    EventCandidate,
    ExtractionResult,
    PlaceCandidate,
    Session,
    SessionChannel,
    User,
    UserMode,
)
from app.domain.identifiers import generate_session_id, generate_user_id
from app.domain.web import (
    WebFetchDiagnostics,
    WebFetchFailure,
    WebFetchFailureCode,
    WebPageContent,
)
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.main import create_app
from app.providers.storage import StorageProviderError, StorageProviderErrorCode
from app.providers.web import WebContentProvider
from nanobot_core.providers import (
    Message,
    ModelProvider,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    StructuredOutput,
    ToolDefinition,
)
from tests.core.fakes import FakeProvider, fake_response
from tests.fixtures.images import JPEG_SCREENSHOT, PNG_SCREENSHOT, WEBP_SCREENSHOT

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, tzinfo=UTC)


class StubWebProvider(WebContentProvider):
    def __init__(self, result: WebPageContent | WebFetchFailure) -> None:
        self.result = result
        self.calls: list[str] = []

    async def fetch(self, url: str) -> WebPageContent | WebFetchFailure:
        self.calls.append(url)
        return self.result


class BlockingWebProvider(WebContentProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, url: str) -> WebPageContent | WebFetchFailure:
        del url
        self.calls += 1
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class SharedBudgetImageProvider(ModelProvider):
    """Use most of one workflow budget before blocking the sole repair call."""

    def __init__(self) -> None:
        self.initial_started = asyncio.Event()
        self.release_initial = asyncio.Event()
        self.repair_started = asyncio.Event()
        self.repair_cancelled = asyncio.Event()
        self.calls = 0

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_format: StructuredOutput | None = None,
    ) -> ModelResponse:
        del messages, tools, response_format
        self.calls += 1
        if self.calls == 1:
            self.initial_started.set()
            await self.release_initial.wait()
            return fake_response(
                content=(
                    '{"outcome":"candidates","candidates":['
                    '{"kind":"place","title":"Image",'
                    '"missing_fields":["city_hint","city_hint"]}]}'
                )
            )
        self.repair_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.repair_cancelled.set()
            raise
        raise AssertionError("unreachable")


def _place(title: str = "深圳当代艺术与城市规划馆") -> PlaceCandidate:
    return PlaceCandidate(
        title=title,
        city_hint="深圳",
        district="福田区",
        address="福中路184号",
        business_district="市民中心",
        landmark="市民中心",
        metro_station="市民中心站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("室内",),
    )


def _response(title: str = "深圳当代艺术与城市规划馆"):
    return fake_response(
        content=ExtractionResult.with_candidates((_place(title),)).model_dump_json()
    )


def _date_event(title: str) -> EventCandidate:
    return EventCandidate(
        title=title,
        city_hint="深圳",
        district="南山区",
        address="海上世界文化艺术中心",
        business_district="海上世界",
        landmark="海上世界文化艺术中心",
        metro_station="海上世界站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("展览",),
        event_start_date=date(2026, 8, 30),
        event_end_date=date(2026, 9, 1),
        missing_fields=(
            CandidateField.EVENT_START_AT,
            CandidateField.EVENT_END_AT,
        ),
    )


def _date_response(title: str):
    return fake_response(
        content=ExtractionResult.with_candidates((_date_event(title),)).model_dump_json()
    )


def _replay_date_event() -> EventCandidate:
    return _date_event("夏季展览").model_copy(
        update={
            "event_start_date": date(2026, 6, 13),
            "event_end_date": date(2026, 7, 31),
        }
    )


def _exact_time_event() -> EventCandidate:
    return EventCandidate(
        title="准确场次",
        city_hint="深圳",
        district="南山区",
        address="海上世界文化艺术中心",
        business_district="海上世界",
        landmark="海上世界文化艺术中心",
        metro_station="海上世界站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("展览",),
        event_start_at=datetime(2026, 7, 31, 6, 0, tzinfo=UTC),
        event_end_at=datetime(2026, 7, 31, 9, 0, tzinfo=UTC),
        missing_fields=(
            CandidateField.EVENT_START_DATE,
            CandidateField.EVENT_END_DATE,
        ),
    )


def _web_success() -> WebPageContent:
    return WebPageContent(
        normalized_url="https://example.com/article?a=1&b=2",
        final_url="https://example.com/final",
        title="A page",
        text="深圳当代艺术与城市规划馆，福田区，免费 RAW_WEB_PRIVATE_MARKER",
        content_type="text/html",
        fetched_at=NOW,
        diagnostics=WebFetchDiagnostics(
            http_status=200,
            redirect_count=1,
            decoded_byte_size=88,
        ),
    )


def _migrate(settings: Settings) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@asynccontextmanager
async def _client(
    settings: Settings,
    provider: ModelProvider,
    *,
    web: WebContentProvider | None = None,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, LocalPrivateStorageProvider]]:
    database_path = Path(settings.database_url.removeprefix("sqlite+aiosqlite:///"))
    active_settings = settings.model_copy(
        update={"storage_private_root": database_path.parent / "private"}
    )
    await asyncio.to_thread(_migrate, active_settings)
    storage = LocalPrivateStorageProvider.from_settings(active_settings)
    api = create_app(
        active_settings,
        text_provider=provider,
        web_provider=web,
        storage_provider=storage,
    )
    async with api.router.lifespan_context(api):
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield api, client, storage


async def _demo(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/v1/demo/sessions")
    assert response.status_code == 201
    return str(response.json()["session_id"])


@pytest.mark.asyncio
async def test_text_url_and_image_share_one_result_and_collection_mapping(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("Text"), _response("URL"), _response("Image")])
    web = StubWebProvider(_web_success())
    async with _client(test_settings, provider, web=web) as (api, client, _storage):
        session_id = await _demo(client)
        text_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"type": "text", "idempotency_key": "text", "text": "具体地点"},
        )
        url_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "url",
                "url": "https://example.com/article?a=1&b=2",
            },
        )
        image_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "image"},
        )
        runs = [
            await client.get(f"/api/v1/agent-runs/{result.json()['trace_id']}")
            for result in (text_result, url_result, image_result)
        ]
        async with api.state.database.session() as session:
            sources = await SqlAlchemyCollectionRepository(session).list_sources(
                user_id=DEMO_USER_ID
            )

    assert all(result.status_code == 200 for result in (text_result, url_result, image_result))
    assert [result.json()["input_type"] for result in (text_result, url_result, image_result)] == [
        "text",
        "url",
        "image",
    ]
    assert {
        result.json()["collections"][0]["status"]
        for result in (
            text_result,
            url_result,
            image_result,
        )
    } == {"pending_details"}
    assert [len(run.json()["tool_runs"]) for run in runs] == [0, 1, 1]
    assert runs[1].json()["tool_runs"][0]["tool_name"] == "web_content_fetch"
    assert runs[2].json()["tool_runs"][0]["tool_name"] == "image_recognition"
    assert len(sources) == 3
    assert sources[1].url == "https://example.com/article?a=1&b=2"
    assert sources[1].metadata.final_url == "https://example.com/final"
    assert sources[2].file_key is not None
    assert sources[2].metadata.content_sha256 is not None
    assert sources[2].file_key not in image_result.text
    database_path = Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///"))
    database_dump = await asyncio.to_thread(database_path.read_bytes)
    assert b"RAW_WEB_PRIVATE_MARKER" not in database_dump
    assert PNG_SCREENSHOT not in database_dump


@pytest.mark.asyncio
async def test_text_url_and_image_preserve_date_only_events_without_inventing_times(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [
            _date_response("Text dates"),
            _date_response("URL dates"),
            _date_response("Image dates"),
        ]
    )
    web = StubWebProvider(_web_success())
    async with _client(test_settings, provider, web=web) as (_api, client, _storage):
        session_id = await _demo(client)
        text_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"type": "text", "idempotency_key": "date-text", "text": "8月30日-9月1日"},
        )
        url_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "date-url",
                "url": "https://example.com/article?a=1&b=2",
            },
        )
        image_result = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "date-image"},
        )

    assert all(result.status_code == 200 for result in (text_result, url_result, image_result))
    collections = [
        result.json()["collections"][0]
        for result in (text_result, url_result, image_result)
    ]
    assert [item["title"] for item in collections] == [
        "Text dates",
        "URL dates",
        "Image dates",
    ]
    assert {item["event_start_date"] for item in collections} == {"2026-08-30"}
    assert {item["event_end_date"] for item in collections} == {"2026-09-01"}
    assert {item["event_start_at"] for item in collections} == {None}
    assert {item["event_end_at"] for item in collections} == {None}
    assert {item["status"] for item in collections} == {"pending_details"}


@pytest.mark.asyncio
async def test_public_text_replay_preserves_event_dates_and_existing_candidate_boundaries(
    test_settings: Settings,
) -> None:
    candidates = (_replay_date_event(), _exact_time_event(), _place("Replay place"))
    provider = FakeProvider(
        [
            fake_response(
                content=ExtractionResult.with_candidates((candidate,)).model_dump_json()
            )
            for candidate in candidates
        ]
    )
    payloads = [
        {
            "type": "text",
            "idempotency_key": f"replay-{index}",
            "text": f"immutable input {index}",
        }
        for index in range(len(candidates))
    ]
    payload_snapshots = [dict(payload) for payload in payloads]
    first_results: list[httpx.Response] = []
    replay_results: list[httpx.Response] = []
    saved_snapshots: list[dict[str, object]] = []

    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        for payload in payloads:
            first = await client.post(
                f"/api/v1/sessions/{session_id}/messages",
                json=payload,
            )
            first_results.append(first)
            item_id = str(first.json()["collections"][0]["id"])
            async with api.state.database.session() as session:
                repository = SqlAlchemyCollectionRepository(session)
                saved = await repository.get_collection_item(
                    user_id=DEMO_USER_ID,
                    collection_item_id=item_id,
                )
                assert saved is not None
                saved_snapshots.append(saved.model_dump(mode="python"))

            replay_results.append(
                await client.post(
                    f"/api/v1/sessions/{session_id}/messages",
                    json=payload,
                )
            )
            assert len(provider.calls) == len(first_results)

        async with api.state.database.session() as session:
            repository = SqlAlchemyCollectionRepository(session)
            stored = await repository.list_collection_items(
                user_id=DEMO_USER_ID,
                include_inactive=True,
            )

    assert payloads == payload_snapshots
    assert len(provider.calls) == 3
    assert len(stored) == 3
    assert all(result.status_code == 200 for result in (*first_results, *replay_results))
    assert all(result.json()["replayed"] is True for result in replay_results)
    for first, replay, saved_snapshot in zip(
        first_results,
        replay_results,
        saved_snapshots,
        strict=True,
    ):
        assert replay.json()["collections"] == first.json()["collections"]
        assert replay.json()["collections"][0]["id"] == first.json()["collections"][0]["id"]
        matching_item = next(
            item for item in stored if item.id == first.json()["collections"][0]["id"]
        )
        assert matching_item.model_dump(mode="python") == saved_snapshot

    date_item = replay_results[0].json()["collections"][0]
    assert date_item["event_start_date"] == "2026-06-13"
    assert date_item["event_end_date"] == "2026-07-31"
    assert date_item["event_start_at"] is None
    assert date_item["event_end_at"] is None
    assert date_item["status"] == "pending_details"

    exact_item = replay_results[1].json()["collections"][0]
    assert exact_item["event_start_date"] is None
    assert exact_item["event_end_date"] is None
    assert exact_item["event_start_at"] == "2026-07-31T06:00:00Z"
    assert exact_item["event_end_at"] == "2026-07-31T09:00:00Z"
    assert exact_item["status"] == "active"

    place_item = replay_results[2].json()["collections"][0]
    assert place_item["kind"] == "place"
    assert place_item["event_start_date"] is None
    assert place_item["event_end_date"] is None
    assert place_item["event_start_at"] is None
    assert place_item["event_end_at"] is None


@pytest.mark.asyncio
async def test_url_failure_is_recoverable_and_never_calls_model(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([])
    web = StubWebProvider(WebFetchFailure.for_code(WebFetchFailureCode.TARGET_BLOCKED))
    async with _client(test_settings, provider, web=web) as (api, client, _storage):
        session_id = await _demo(client)
        response = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "blocked",
                "url": "http://127.0.0.1/private?secret=hidden",
            },
        )
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "blocked",
                "url": "http://127.0.0.1/private?secret=hidden",
            },
        )
        run = await client.get(f"/api/v1/agent-runs/{response.json()['trace_id']}")
        async with api.state.database.session() as session:
            sources = await SqlAlchemyCollectionRepository(session).list_sources(
                user_id=DEMO_USER_ID
            )

    assert response.status_code == replay.status_code == 200
    assert response.json()["run_status"] == "partially_succeeded"
    assert response.json()["error_code"] == "WEB_TARGET_BLOCKED"
    assert response.json()["collections"] == []
    assert set(response.json()["recovery_actions"]) == {"supply_text", "send_screenshot"}
    assert replay.json()["replayed"] is True
    assert replay.json()["source_parse_status"] == response.json()["source_parse_status"]
    assert replay.json()["error_code"] == response.json()["error_code"]
    assert replay.json()["recovery_actions"] == response.json()["recovery_actions"]
    assert len(web.calls) == 1 and provider.calls == []
    assert run.json()["status"] == "partially_succeeded"
    assert run.json()["tool_runs"][0]["status"] == "failed"
    assert len(sources) == 1 and sources[0].parse_status.value == "failed"
    assert sources[0].metadata.failure_code == "WEB_TARGET_BLOCKED"
    assert "hidden" not in run.text


@pytest.mark.asyncio
async def test_normalized_url_replay_and_different_content_conflict(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response()])
    web = StubWebProvider(_web_success())
    async with _client(test_settings, provider, web=web) as (_api, client, _storage):
        session_id = await _demo(client)
        first = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "normalized",
                "url": "HTTPS://EXAMPLE.COM:443/article?a=1&b=2",
            },
        )
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "type": "url",
                "idempotency_key": "normalized",
                "url": "https://example.com/article?a=1&b=2",
            },
        )
        conflict = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"type": "text", "idempotency_key": "normalized", "text": "different"},
        )

    assert first.status_code == replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert conflict.status_code == 409
    assert len(web.calls) == len(provider.calls) == 1


@pytest.mark.asyncio
async def test_same_key_is_isolated_between_sessions_and_image_replay_stores_once(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("First"), _response("Second"), _response("Image")])
    async with _client(test_settings, provider) as (_api, client, _storage):
        first_session, second_session = await _demo(client), await _demo(client)
        first, second = await asyncio.gather(
            client.post(
                f"/api/v1/sessions/{first_session}/messages",
                json={"idempotency_key": "shared", "content": "first"},
            ),
            client.post(
                f"/api/v1/sessions/{second_session}/messages",
                json={"idempotency_key": "shared", "content": "second"},
            ),
        )
        image = await client.post(
            f"/api/v1/sessions/{first_session}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "same-image"},
        )
        replay = await client.post(
            f"/api/v1/sessions/{first_session}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "same-image"},
        )

    assert first.status_code == second.status_code == image.status_code == replay.status_code == 200
    assert first.json()["trace_id"] != second.json()["trace_id"]
    assert first.json()["message_id"] != second.json()["message_id"]
    assert replay.json()["replayed"] is True
    assert replay.json()["source_id"] == image.json()["source_id"]
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_same_key_and_frozen_input_remain_isolated_across_users(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("Demo user"), _response("Second user")])
    second_user_id = generate_user_id()
    second_session_id = generate_session_id()
    second_input = TextInput(text="同一个键的第二位用户")
    input_snapshot = second_input.model_dump(mode="python")
    async with _client(test_settings, provider) as (api, client, _storage):
        demo_session_id = await _demo(client)
        first = await client.post(
            f"/api/v1/sessions/{demo_session_id}/messages",
            json={"idempotency_key": "cross-user", "content": "第一位用户"},
        )
        async with api.state.database.session() as session:
            repository = SqlAlchemyCollectionRepository(session)
            await repository.add_user(
                user_id=second_user_id,
                user=User(id=second_user_id, mode=UserMode.DEMO, created_at=NOW),
            )
            await repository.add_session(
                user_id=second_user_id,
                session=Session(
                    id=second_session_id,
                    user_id=second_user_id,
                    channel=SessionChannel.DEMO,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            await session.commit()
            second = await TextCollectionWorkflow(
                session=session,
                provider=provider,
                pricing=ConfiguredPricingPolicy.from_settings(test_settings),
                locks=api.state.idempotency_locks,
                timeout_seconds=test_settings.agent_timeout_seconds,
                now=lambda: NOW,
            ).submit_input(
                user_id=second_user_id,
                session_id=second_session_id,
                idempotency_key="cross-user",
                input=second_input,
            )
            first_sources = await repository.list_sources(user_id=DEMO_USER_ID)
            second_sources = await repository.list_sources(user_id=second_user_id)

    assert first.status_code == 200
    assert first.json()["message_id"] != second.message.id
    assert first.json()["trace_id"] != second.trace_id
    assert first.json()["source_id"] != second.source.id
    assert len(first_sources) == len(second_sources) == 1
    assert len(provider.calls) == 2
    assert second_input.model_dump(mode="python") == input_snapshot


@pytest.mark.asyncio
async def test_invalid_and_different_image_payloads_never_duplicate_or_leak_files(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response("Image")])
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        invalid = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=b"not-an-image-private-marker",
            headers={"Content-Type": "image/png", "Idempotency-Key": "invalid-image"},
        )
        first = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "image-conflict"},
        )
        conflict = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT + b"different",
            headers={"Content-Type": "image/png", "Idempotency-Key": "image-conflict"},
        )
        invalid_run = await client.get(f"/api/v1/agent-runs/{invalid.json()['trace_id']}")

    private_root = (
        Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent / "private"
    )
    objects = list((private_root / "objects").iterdir())
    combined = (
        invalid.text
        + invalid_run.text
        + repr(
            ImageInput.from_bytes(
                PNG_SCREENSHOT,
                content_type="image/png",
            )
        )
    )
    assert invalid.status_code == 500
    assert invalid.json()["error_code"] == "IMAGE_CONTENT_SIGNATURE_MISMATCH"
    assert invalid.json()["recovery_actions"] == ["reupload_image", "supply_text"]
    assert invalid_run.json()["status"] == "failed"
    assert invalid_run.json()["tool_runs"][0]["error_code"] == ("IMAGE_CONTENT_SIGNATURE_MISMATCH")
    assert first.status_code == 200 and conflict.status_code == 409
    assert len(provider.calls) == 1 and len(objects) == 1
    assert "not-an-image-private-marker" not in combined
    assert str(private_root) not in combined


@pytest.mark.asyncio
async def test_image_idempotency_identity_includes_normalized_media_type(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([])
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        declared_jpeg = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/jpeg", "Idempotency-Key": "mime-conflict"},
        )
        declared_png = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "IMAGE/PNG", "Idempotency-Key": "mime-conflict"},
        )
        async with api.state.database.session() as session:
            message_content = await session.scalar(text("SELECT content FROM messages LIMIT 1"))

    assert declared_jpeg.status_code == 500
    assert declared_jpeg.json()["error_code"] == "IMAGE_CONTENT_SIGNATURE_MISMATCH"
    assert declared_png.status_code == 409
    assert declared_png.json()["error_code"] == "IDEMPOTENCY_CONFLICT"
    assert provider.calls == []
    assert isinstance(message_content, str)
    assert message_content.startswith("image:image/jpeg:sha256:")
    assert "PNG" not in message_content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("media_type", "payload"),
    (
        ("image/jpeg", JPEG_SCREENSHOT),
        ("image/png", PNG_SCREENSHOT),
        ("image/webp", WEBP_SCREENSHOT),
    ),
)
async def test_each_image_media_type_replays_without_duplicate_side_effects(
    test_settings: Settings,
    media_type: str,
    payload: bytes,
) -> None:
    provider = FakeProvider([_response(media_type)])
    key = media_type.replace("/", "-")
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        first = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=payload,
            headers={"Content-Type": media_type, "Idempotency-Key": key},
        )
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=payload,
            headers={"Content-Type": media_type.upper(), "Idempotency-Key": key},
        )
        run = await client.get(f"/api/v1/agent-runs/{first.json()['trace_id']}")
        async with api.state.database.session() as session:
            count_values: list[int] = []
            for table in ("messages", "sources", "agent_runs", "tool_runs"):
                count_values.append(
                    int(await session.scalar(text(f"SELECT COUNT(*) FROM {table}")) or 0)
                )
            counts = tuple(count_values)

    private_root = (
        Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent / "private"
    )
    assert first.status_code == replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["message_id"] == first.json()["message_id"]
    assert replay.json()["source_id"] == first.json()["source_id"]
    assert replay.json()["trace_id"] == first.json()["trace_id"]
    for field in (
        "run_status",
        "source_parse_status",
        "error_code",
        "recovery_actions",
        "extraction",
        "collections",
    ):
        assert replay.json()[field] == first.json()[field]
    assert counts == (1, 1, 1, 1)
    assert len(provider.calls) == 1
    assert len(list((private_root / "objects").iterdir())) == 1
    assert media_type in run.json()["tool_runs"][0]["input_summary"]


@pytest.mark.asyncio
async def test_image_insufficient_information_keeps_private_source_unconfirmed(
    test_settings: Settings,
) -> None:
    insufficient = ExtractionResult.insufficient(
        missing_fields=(CandidateField.TITLE, CandidateField.ADDRESS),
        recovery_suggestions=("请补充店名或重新上传清晰截图。",),
    )
    provider = FakeProvider([fake_response(content=insufficient.model_dump_json())])
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        response = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "insufficient"},
        )
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "insufficient"},
        )
        async with api.state.database.session() as session:
            sources = await SqlAlchemyCollectionRepository(session).list_sources(
                user_id=DEMO_USER_ID
            )

    assert response.status_code == 200
    assert response.json()["extraction"]["outcome"] == "insufficient_information"
    assert response.json()["collections"] == []
    assert response.json()["source_parse_status"] == "failed"
    assert response.json()["recovery_actions"] == ["supply_text", "reupload_image"]
    assert replay.json()["replayed"] is True
    assert replay.json()["source_parse_status"] == response.json()["source_parse_status"]
    assert replay.json()["extraction"] == response.json()["extraction"]
    assert replay.json()["recovery_actions"] == response.json()["recovery_actions"]
    assert len(provider.calls) == 1
    assert len(sources) == 1 and sources[0].file_key is not None


@pytest.mark.asyncio
async def test_text_and_url_recoverable_results_replay_the_same_safe_state(
    test_settings: Settings,
) -> None:
    insufficient = ExtractionResult.insufficient(
        missing_fields=(CandidateField.ADDRESS,),
        recovery_suggestions=("请补充区域或地址。",),
    )
    provider = FakeProvider([fake_response(content=insufficient.model_dump_json())])
    web = StubWebProvider(_web_success())
    async with _client(test_settings, provider, web=web) as (_api, client, _storage):
        session_id = await _demo(client)
        text_payload = {
            "type": "text",
            "idempotency_key": "unsupported-replay",
            "text": "请给我一份番茄炒蛋菜谱和制作步骤",
        }
        url_payload = {
            "type": "url",
            "idempotency_key": "url-insufficient-replay",
            "url": "https://example.com/article?a=private-query",
        }
        text_first = await client.post(f"/api/v1/sessions/{session_id}/messages", json=text_payload)
        text_replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages", json=text_payload
        )
        url_first = await client.post(f"/api/v1/sessions/{session_id}/messages", json=url_payload)
        url_replay = await client.post(f"/api/v1/sessions/{session_id}/messages", json=url_payload)

    for first, replay in ((text_first, text_replay), (url_first, url_replay)):
        assert first.status_code == replay.status_code == 200
        assert replay.json()["replayed"] is True
        for field in (
            "run_status",
            "source_parse_status",
            "error_code",
            "recovery_actions",
            "extraction",
            "collections",
        ):
            assert replay.json()[field] == first.json()[field]
    assert text_first.json()["recovery_actions"] == ["supply_text"]
    assert url_first.json()["recovery_actions"] == ["supply_text", "send_screenshot"]
    assert len(web.calls) == len(provider.calls) == 1


@pytest.mark.asyncio
async def test_url_timeout_is_terminal_replayable_and_does_not_retry(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"agent_timeout_seconds": 0.01})
    provider = FakeProvider([])
    web = BlockingWebProvider()
    async with _client(settings, provider, web=web) as (_api, client, _storage):
        session_id = await _demo(client)
        payload = {
            "type": "url",
            "idempotency_key": "url-timeout",
            "url": "https://example.com/slow",
        }
        timed_out = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=payload,
        )
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=payload,
        )
        run = await client.get(f"/api/v1/agent-runs/{timed_out.json()['trace_id']}")

    assert timed_out.status_code == replay.status_code == 504
    assert timed_out.json()["error_code"] == replay.json()["error_code"] == "RUN_TIMEOUT"
    assert web.calls == 1 and provider.calls == []
    assert run.json()["status"] == "failed"
    assert run.json()["tool_runs"][0]["status"] == "cancelled"
    assert run.json()["tool_runs"][0]["error_code"] == "RUN_TIMEOUT"


@pytest.mark.asyncio
async def test_image_cancellation_finalizes_run_and_removes_new_file(
    test_settings: Settings,
) -> None:
    cancellation = asyncio.CancelledError()
    provider = FakeProvider([cancellation])
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        with pytest.raises(asyncio.CancelledError) as caught:
            await client.post(
                f"/api/v1/sessions/{session_id}/messages",
                content=PNG_SCREENSHOT,
                headers={"Content-Type": "image/png", "Idempotency-Key": "cancel-image"},
            )
        async with api.state.database.session() as session:
            trace_id = await session.scalar(
                text("SELECT trace_id FROM agent_runs ORDER BY created_at DESC LIMIT 1")
            )
        run = await client.get(f"/api/v1/agent-runs/{trace_id}")
        replay = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={"Content-Type": "image/png", "Idempotency-Key": "cancel-image"},
        )

    private_root = (
        Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent / "private"
    )
    assert caught.value is cancellation
    assert run.json()["status"] == "cancelled"
    assert run.json()["error_code"] == "RUN_CANCELLED"
    assert run.json()["tool_runs"][0]["status"] == "cancelled"
    assert replay.status_code == 500
    assert replay.json()["error_code"] == "RUN_CANCELLED"
    assert len(provider.calls) == 1
    assert list((private_root / "objects").iterdir()) == []


@pytest.mark.asyncio
async def test_image_provider_failure_replay_has_no_additional_side_effects(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([ProviderError(code=ProviderErrorCode.TIMEOUT)])
    async with _client(test_settings, provider) as (_api, client, _storage):
        session_id = await _demo(client)
        request = {
            "content": PNG_SCREENSHOT,
            "headers": {
                "Content-Type": "image/png",
                "Idempotency-Key": "provider-failure-replay",
            },
        }
        first = await client.post(f"/api/v1/sessions/{session_id}/messages", **request)
        replay = await client.post(f"/api/v1/sessions/{session_id}/messages", **request)
        run = await client.get(f"/api/v1/agent-runs/{first.json()['trace_id']}")

    private_root = (
        Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent / "private"
    )
    assert first.status_code == replay.status_code == 502
    assert replay.json() == first.json()
    assert len(provider.calls) == 1
    assert run.json()["status"] == "failed"
    assert run.json()["error_code"] == "PROVIDER_TIMEOUT"
    assert run.json()["tool_runs"][0]["status"] == "failed"
    assert list((private_root / "objects").iterdir()) == []


@pytest.mark.asyncio
async def test_image_initial_and_repair_share_one_outer_workflow_budget(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"agent_timeout_seconds": 0.12})
    provider = SharedBudgetImageProvider()
    async with _client(settings, provider) as (_api, client, _storage):
        session_id = await _demo(client)
        request = asyncio.create_task(
            client.post(
                f"/api/v1/sessions/{session_id}/messages",
                content=PNG_SCREENSHOT,
                headers={
                    "Content-Type": "image/png",
                    "Idempotency-Key": "shared-image-budget",
                },
            )
        )
        await provider.initial_started.wait()
        started_at = monotonic()
        asyncio.get_running_loop().call_later(
            0.08,
            provider.release_initial.set,
        )
        response = await request

    private_root = (
        Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent
        / "private"
    )
    assert response.status_code == 504
    assert response.json()["error_code"] == "RUN_TIMEOUT"
    assert provider.calls == 2
    assert provider.repair_started.is_set()
    assert provider.repair_cancelled.is_set()
    assert monotonic() - started_at < 0.18
    for directory in ("objects", "metadata", ".tmp", ".reservations"):
        assert list((private_root / directory).iterdir()) == []


@pytest.mark.asyncio
async def test_cleanup_failure_is_fixed_and_does_not_leak_sensitive_context(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "cleanup-secret Authorization=Bearer-private"
    private_path = "/private/uploads/original.png?token=url-query-secret"
    provider = FakeProvider([_response("Image")])

    async def fail_write(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("database-private-trigger")

    async def fail_delete(file_key: str) -> object:
        del file_key
        raise RuntimeError(f"{marker} {private_path}")

    monkeypatch.setattr(CollectionWriteService, "auto_save", fail_write)
    async with _client(test_settings, provider) as (api, client, storage):
        monkeypatch.setattr(storage, "delete", fail_delete)
        session_id = await _demo(client)
        response = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={
                "Content-Type": "image/png",
                "Idempotency-Key": "cleanup-failure",
                "Authorization": "Bearer-private",
            },
        )
        run = await client.get(f"/api/v1/agent-runs/{response.json()['trace_id']}")
        async with api.state.database.session() as session:
            tool_rows = (
                await session.execute(
                    text(
                        "SELECT arguments_fingerprint, input_summary, output_summary, "
                        "error_code FROM tool_runs"
                    )
                )
            ).all()

    combined = response.text + run.text + repr(tool_rows) + caplog.text
    assert response.status_code == 500
    assert response.json()["error_code"] == "IMAGE_CLEANUP_FAILED"
    assert run.json()["status"] == "failed"
    assert run.json()["error_code"] == "IMAGE_CLEANUP_FAILED"
    assert len(provider.calls) == 1 and len(tool_rows) == 1
    for secret in (marker, private_path, "Bearer-private", "url-query-secret"):
        assert secret not in combined
    assert "base64" not in combined.lower()


@pytest.mark.asyncio
async def test_collection_cancellation_survives_storage_cleanup_failure(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancellation = asyncio.CancelledError()
    provider = FakeProvider([_response("Image")])
    delete_calls = 0

    async def cancel_write(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise cancellation

    async def fail_delete(file_key: str) -> object:
        nonlocal delete_calls
        del file_key
        delete_calls += 1
        raise StorageProviderError(code=StorageProviderErrorCode.DELETE_FAILED)

    monkeypatch.setattr(CollectionWriteService, "auto_save", cancel_write)
    async with _client(test_settings, provider) as (api, client, storage):
        monkeypatch.setattr(storage, "delete", fail_delete)
        session_id = await _demo(client)
        with pytest.raises(asyncio.CancelledError) as caught:
            await client.post(
                f"/api/v1/sessions/{session_id}/messages",
                content=PNG_SCREENSHOT,
                headers={"Content-Type": "image/png", "Idempotency-Key": "cancel-cleanup"},
            )
        async with api.state.database.session() as session:
            run = (
                await session.execute(
                    text(
                        "SELECT trace_id, status, error_code FROM agent_runs "
                        "ORDER BY created_at DESC LIMIT 1"
                    )
                )
            ).one()
            tool_count = int(await session.scalar(text("SELECT COUNT(*) FROM tool_runs")) or 0)

    combined = (
        repr(caught.value)
        + repr(run)
        + repr(
            ImageInput.from_bytes(
                PNG_SCREENSHOT,
                content_type="image/png",
            )
        )
    )
    assert caught.value is cancellation
    assert delete_calls == 1
    assert run.status == "cancelled" and run.error_code == "RUN_CANCELLED"
    assert tool_count == 1 and len(provider.calls) == 1
    assert "STORAGE_DELETE_FAILED" not in combined
    assert "private" not in combined.lower()


@pytest.mark.asyncio
async def test_image_collection_write_failure_rolls_back_and_cleans_file(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider([_response("Image")])

    async def fail_write(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("private-database-failure-marker")

    monkeypatch.setattr(CollectionWriteService, "auto_save", fail_write)
    async with _client(test_settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        with pytest.raises(RuntimeError, match="private-database-failure-marker"):
            await client.post(
                f"/api/v1/sessions/{session_id}/messages",
                content=PNG_SCREENSHOT,
                headers={"Content-Type": "image/png", "Idempotency-Key": "db-failure"},
            )
        async with api.state.database.session() as session:
            count_values: list[int] = []
            for table in ("sources", "collection_items", "collection_write_operations"):
                value = await session.scalar(text(f"SELECT COUNT(*) FROM {table}"))
                count_values.append(int(value or 0))
            counts = tuple(count_values)
            run_status = await session.scalar(
                text("SELECT status FROM agent_runs ORDER BY created_at DESC LIMIT 1")
            )

    private_root = (
        Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent / "private"
    )
    assert counts == (0, 0, 0)
    assert run_status == "failed"
    assert list((private_root / "objects").iterdir()) == []


@pytest.mark.asyncio
async def test_image_database_write_timeout_cleans_all_private_file_state(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = test_settings.model_copy(update={"agent_timeout_seconds": 0.03})
    provider = FakeProvider([_response("Image")])
    write_started = asyncio.Event()
    write_cancelled = asyncio.Event()

    async def block_write(*args: object, **kwargs: object) -> object:
        del args, kwargs
        write_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            write_cancelled.set()
            raise
        raise AssertionError("unreachable")

    monkeypatch.setattr(CollectionWriteService, "auto_save", block_write)
    async with _client(settings, provider) as (api, client, _storage):
        session_id = await _demo(client)
        response = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            content=PNG_SCREENSHOT,
            headers={
                "Content-Type": "image/png",
                "Idempotency-Key": "database-write-timeout",
            },
        )
        async with api.state.database.session() as session:
            count_values: list[int] = []
            for table in (
                "sources",
                "collection_items",
                "collection_write_operations",
            ):
                value = await session.scalar(text(f"SELECT COUNT(*) FROM {table}"))
                count_values.append(int(value or 0))
            counts = tuple(count_values)

    private_root = (
        Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///")).parent
        / "private"
    )
    assert response.status_code == 504
    assert response.json()["error_code"] == "RUN_TIMEOUT"
    assert write_started.is_set()
    assert write_cancelled.is_set()
    assert counts == (0, 0, 0)
    assert len(provider.calls) == 1
    for directory in ("objects", "metadata", ".tmp", ".reservations"):
        assert list((private_root / directory).iterdir()) == []


def test_input_contracts_are_frozen_and_hide_sensitive_payloads() -> None:
    text = TextInput(text="private text")
    url = UrlInput(url="https://example.com/?token=private")
    image = ImageInput.from_bytes(PNG_SCREENSHOT, content_type="image/png")

    for value in (text, url, image):
        with pytest.raises(ValidationError):
            value.type = "changed"  # type: ignore[misc]
    combined = repr(text) + repr(url) + repr(image)
    assert "private text" not in combined
    assert "token=private" not in combined
    assert "PNG" not in combined

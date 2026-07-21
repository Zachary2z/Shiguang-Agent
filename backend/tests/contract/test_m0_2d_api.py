"""Offline contract coverage for the synchronous M0-2D `/api/v1` surface."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import text

from app.application.collection_writes import CollectionWriteService
from app.config import Settings
from app.domain.collections import (
    CandidateField,
    CollectionItem,
    CollectionKind,
    CollectionStatus,
    EventCandidate,
    ExtractionResult,
    PlaceCandidate,
    PlanCity,
    Session,
    SessionChannel,
    SupportedTimezone,
    User,
    UserMode,
)
from app.domain.identifiers import generate_trace_id
from app.domain.runs import AgentRunCreate
from app.domain.time import utc_now
from app.infrastructure.repositories import AgentRunRepository, SqlAlchemyCollectionRepository
from app.main import create_app
from nanobot_core.providers import (
    Message,
    ModelProvider,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    ToolDefinition,
)
from tests.core.fakes import FakeProvider, fake_response

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EVENT_START = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def _place(
    *,
    title: str = "深圳当代艺术与城市规划馆",
    city_hint: str | None = "深圳",
    district: str = "福田区",
    tags: tuple[str, ...] = ("室内", "博物馆"),
) -> PlaceCandidate:
    missing = () if city_hint is not None else (CandidateField.CITY_HINT,)
    return PlaceCandidate(
        title=title,
        city_hint=city_hint,
        district=district,
        address="福中路184号",
        business_district="市民中心",
        landmark="市民中心",
        metro_station="市民中心站",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=tags,
        missing_fields=missing,
    )


def _event(*, title: str = "上海周末设计展", city_hint: str = "上海") -> EventCandidate:
    return EventCandidate(
        title=title,
        city_hint=city_hint,
        district="浦东新区",
        address="世博园区",
        business_district="世博园",
        landmark="世博园区",
        metro_station="世博大道站",
        price_amount=Decimal("88.00"),
        price_currency="CNY",
        tags=("展览", "室内"),
        event_start_at=EVENT_START,
        event_end_at=EVENT_START + timedelta(hours=3),
    )


def _response(*candidates: PlaceCandidate | EventCandidate):
    return fake_response(
        content=ExtractionResult.with_candidates(candidates).model_dump_json(),
    )


def _migrate(settings: Settings) -> None:
    database_path = settings.database_url.removeprefix("sqlite+aiosqlite:///")
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    assert Path(database_path).exists()


@asynccontextmanager
async def _client(
    settings: Settings,
    provider: ModelProvider | None = None,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    await asyncio.to_thread(_migrate, settings)
    api = create_app(settings, text_provider=provider)
    async with api.router.lifespan_context(api):
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield api, client


async def _demo(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/v1/demo/sessions")
    assert response.status_code == 201
    return str(response.json()["session_id"])


async def _submit(
    client: httpx.AsyncClient,
    session_id: str,
    *,
    key: str,
    content: str,
) -> httpx.Response:
    return await client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"idempotency_key": key, "content": content},
    )


@pytest.mark.asyncio
async def test_demo_session_works_without_model_config_and_rejects_client_user_id(
    test_settings: Settings,
) -> None:
    async with _client(test_settings) as (_api, client):
        first = await client.post("/api/v1/demo/sessions")
        second = await client.post("/api/v1/demo/sessions", json={})
        spoofed = await client.post(
            "/api/v1/demo/sessions",
            json={"user_id": "usr_0123456789abcdef0123456789abcdef"},
        )
        unavailable = await _submit(
            client,
            first.json()["session_id"],
            key="no-provider",
            content="广州塔",
        )

    assert first.status_code == second.status_code == 201
    assert first.json()["session_id"] != second.json()["session_id"]
    assert spoofed.status_code == 422
    assert "usr_0123456789abcdef0123456789abcdef" not in spoofed.text
    assert unavailable.status_code == 503
    assert unavailable.json()["error_code"] == "PROVIDER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_place_flow_run_detail_patch_delete_and_undo_are_safe(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response(_place())])
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        created = await _submit(
            client,
            session_id,
            key="place-one",
            content="想去深圳当代艺术与城市规划馆，福田区，免费",
        )
        assert created.status_code == 200
        payload = created.json()
        item = payload["collections"][0]
        item_id = item["id"]
        token = payload["undo_token"]

        run = await client.get(f"/api/v1/agent-runs/{payload['trace_id']}")
        detail = await client.get(f"/api/v1/collections/{item_id}")
        patched = await client.patch(
            f"/api/v1/collections/{item_id}",
            json={
                "expected_version": item["version"],
                "changes": {"title": "深圳城市规划馆（想去）"},
            },
        )
        stale = await client.patch(
            f"/api/v1/collections/{item_id}",
            json={"expected_version": 1, "changes": {"title": "旧写入"}},
        )
        deleted = await client.delete(
            f"/api/v1/collections/{item_id}",
            params={"expected_version": patched.json()["version"]},
        )
        repeated_delete = await client.delete(
            f"/api/v1/collections/{item_id}",
            params={"expected_version": patched.json()["version"]},
        )
        undone = await client.post(
            f"/api/v1/collections/{item_id}/undo",
            json={"undo_token": token},
        )

    assert payload["run_status"] == "succeeded"
    assert payload["extraction"]["outcome"] == "candidates"
    assert token and token not in run.text and token not in detail.text
    assert run.status_code == 200 and run.json()["status"] == "succeeded"
    assert run.json()["model_calls"][0]["model_name"] == "fixture-model"
    assert "user_id" not in run.text
    assert "arguments_fingerprint" not in run.text
    assert detail.status_code == 200
    assert detail.json()["sources"][0]["type"] == "text"
    assert "metadata" not in detail.text and "fingerprint" not in detail.text
    assert patched.status_code == 200 and patched.json()["version"] == 2
    assert stale.status_code == 409 and stale.json()["error_code"] == "VERSION_CONFLICT"
    assert deleted.json()["status"] == repeated_delete.json()["status"] == "deleted"
    assert deleted.json()["version"] == repeated_delete.json()["version"] == 3
    assert undone.status_code == 200 and undone.json()["outcome"] == "undone"


@pytest.mark.asyncio
async def test_sequential_and_concurrent_idempotency_do_not_repeat_data(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response(_place(title="广州塔", city_hint="广州"))])
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        first, concurrent = await asyncio.gather(
            _submit(client, session_id, key="same-key", content="广州塔看夜景"),
            _submit(client, session_id, key="same-key", content="广州塔看夜景"),
        )
        replay = await _submit(
            client,
            session_id,
            key="same-key",
            content="广州塔看夜景",
        )
        conflict = await _submit(
            client,
            session_id,
            key="same-key",
            content="上海外滩",
        )

    responses = [first.json(), concurrent.json(), replay.json()]
    assert all(response.status_code == 200 for response in (first, concurrent, replay))
    assert len(provider.calls) == 1
    assert len({response["message_id"] for response in responses}) == 1
    assert len({response["trace_id"] for response in responses}) == 1
    assert len({response["collections"][0]["id"] for response in responses}) == 1
    assert sum(response["undo_token"] is not None for response in responses) == 1
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "IDEMPOTENCY_CONFLICT"

    database_path = Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///"))
    with sqlite3.connect(database_path) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "messages",
                "sources",
                "collection_items",
                "collection_sources",
                "collection_write_operations",
                "collection_write_operation_items",
            )
        }
    assert counts == {
        "messages": 1,
        "sources": 1,
        "collection_items": 1,
        "collection_sources": 1,
        "collection_write_operations": 1,
        "collection_write_operation_items": 1,
    }


@pytest.mark.asyncio
async def test_multiple_cross_city_items_event_and_city_title_without_hint(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [
            _response(
                _place(title="广州塔", city_hint="广州", district="海珠区"),
                _event(),
                _place(title="深圳湾咖啡", city_hint=None, district="南山区"),
            )
        ]
    )
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        response = await _submit(
            client,
            session_id,
            key="cross-city",
            content="广州塔、上海周末设计展，以及名叫深圳湾咖啡但城市未知",
        )

    assert response.status_code == 200
    items = response.json()["collections"]
    assert [item["kind"] for item in items] == ["place", "event", "place"]
    assert [item["city_hint"] for item in items] == ["广州", "上海", None]
    assert items[2]["city_pending"] is True
    assert items[0]["status"] == "pending_details"
    assert items[1]["status"] == "active"


@pytest.mark.asyncio
async def test_collection_filters_stable_pagination_and_explicit_inactive_status(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [
            _response(_place(title="广州塔", city_hint="广州", district="海珠区")),
            _response(_event()),
            _response(_place(title="未知咖啡", city_hint=None, district="南山区")),
        ]
    )
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        first = await _submit(client, session_id, key="filter-1", content="广州塔")
        await _submit(client, session_id, key="filter-2", content="上海设计展")
        await _submit(client, session_id, key="filter-3", content="未知咖啡")
        deleted_id = first.json()["collections"][0]["id"]
        await client.delete(f"/api/v1/collections/{deleted_id}")

        pending = await client.get("/api/v1/collections", params={"city_pending": "true"})
        shanghai_event = await client.get(
            "/api/v1/collections",
            params=[("city_hint", "上海"), ("kind", "event"), ("tags", "展览")],
        )
        default = await client.get("/api/v1/collections")
        deleted = await client.get(
            "/api/v1/collections",
            params={"status": "deleted"},
        )
        page_one = await client.get(
            "/api/v1/collections",
            params={"include_inactive": "true", "sort": "created_at", "page_size": 1},
        )
        page_two = await client.get(
            "/api/v1/collections",
            params={
                "include_inactive": "true",
                "sort": "created_at",
                "page_size": 1,
                "page": 2,
            },
        )
        invalid = await client.get("/api/v1/collections", params={"page_size": 101})

    assert [item["title"] for item in pending.json()["items"]] == ["未知咖啡"]
    assert [item["title"] for item in shanghai_event.json()["items"]] == [
        "上海周末设计展"
    ]
    assert deleted_id not in {item["id"] for item in default.json()["items"]}
    assert [item["id"] for item in deleted.json()["items"]] == [deleted_id]
    assert page_one.json()["total"] == page_two.json()["total"] == 3
    assert page_one.json()["items"][0]["id"] != page_two.json()["items"][0]["id"]
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_wrong_item_random_and_repeated_undo_are_safe(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response(_place(title="A")), _response(_place(title="B"))])
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        first = await _submit(client, session_id, key="undo-a", content="地点 A")
        second = await _submit(client, session_id, key="undo-b", content="地点 B")
        first_data = first.json()
        second_id = second.json()["collections"][0]["id"]
        first_id = first_data["collections"][0]["id"]
        token = first_data["undo_token"]

        wrong_item = await client.post(
            f"/api/v1/collections/{second_id}/undo",
            json={"undo_token": token},
        )
        random_token = await client.post(
            f"/api/v1/collections/{first_id}/undo",
            json={"undo_token": "opaque-random-token"},
        )
        valid = await client.post(
            f"/api/v1/collections/{first_id}/undo",
            json={"undo_token": token},
        )
        repeated = await client.post(
            f"/api/v1/collections/{first_id}/undo",
            json={"undo_token": token},
        )

    assert wrong_item.status_code == random_token.status_code == 404
    assert token not in wrong_item.text and token not in random_token.text
    assert valid.json()["outcome"] == "undone"
    assert repeated.json()["outcome"] == "already_undone"


@pytest.mark.asyncio
async def test_provider_error_has_stable_code_trace_and_no_sensitive_detail(
    test_settings: Settings,
) -> None:
    marker = "provider-private-response-body"
    provider = FakeProvider([ProviderError(code=ProviderErrorCode.TIMEOUT)])
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        response = await _submit(
            client,
            session_id,
            key="provider-failure",
            content=f"广州塔 {marker}",
        )
        trace_id = response.json()["trace_id"]
        run = await client.get(f"/api/v1/agent-runs/{trace_id}")

    assert response.status_code == 502
    assert response.json()["error_code"] == "PROVIDER_TIMEOUT"
    assert marker not in response.text and marker not in run.text
    assert run.json()["status"] == "failed"
    assert run.json()["error_code"] == "PROVIDER_TIMEOUT"


@pytest.mark.asyncio
async def test_validation_and_request_logs_never_echo_message_or_undo_token(
    test_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    message_marker = "private-message-marker"
    token_marker = "private-undo-token-marker"
    caplog.set_level(logging.INFO, logger="shiguang.request")
    async with _client(test_settings, FakeProvider([])) as (_api, client):
        session_id = await _demo(client)
        invalid_message = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"idempotency_key": "bad key", "content": message_marker},
            headers={"Authorization": "Bearer private-auth", "Cookie": "sid=private-cookie"},
        )
        invalid_token = await client.post(
            "/api/v1/collections/col_0123456789abcdef0123456789abcdef/undo",
            json={"undo_token": token_marker, "extra": token_marker},
        )

    logs = "\n".join(record.getMessage() for record in caplog.records)
    combined = invalid_message.text + invalid_token.text + logs
    assert invalid_message.status_code == invalid_token.status_code == 422
    for secret in (message_marker, token_marker, "private-auth", "private-cookie"):
        assert secret not in combined


@pytest.mark.asyncio
async def test_openapi_has_unique_routes_and_no_future_m0_endpoints(
    test_settings: Settings,
) -> None:
    async with _client(test_settings) as (api, client):
        response = await client.get("/openapi.json")
        missing = await client.get(
            "/api/v1/agent-runs/trc_0123456789abcdef0123456789abcdef/events"
        )
        paths = response.json()["paths"]

    assert response.status_code == 200
    routable = [route for route in api.routes if hasattr(route, "path")]
    assert len(routable) == len(
        {(route.path, tuple(sorted(route.methods or ()))) for route in routable}
    )
    assert "/api/v1/collections/{item_id}/poi-candidates" not in paths
    assert "/api/v1/agent-runs/{trace_id}/events" not in paths
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_preflight_rejections_repair_failure_and_strict_message_schema(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [fake_response(content="not-json"), fake_response(content='{"outcome":"broken"}')]
    )
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        cases = {
            "recipe": "请给我一份番茄炒蛋菜谱和制作步骤",
            "product": "这款商品的型号参数是什么，值得买吗",
            "travel": "帮我安排深圳到广州三日游旅游行程",
            "generic": "咖啡店",
        }
        results = {
            key: await _submit(client, session_id, key=key, content=text)
            for key, text in cases.items()
        }
        broken = await _submit(
            client,
            session_id,
            key="broken-structure",
            content="深圳一个具体的新地点",
        )
        blank = await _submit(client, session_id, key="blank", content="   ")
        too_long = await _submit(client, session_id, key="long", content="长" * 20_001)
        spoofed = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={
                "idempotency_key": "spoof",
                "content": "广州塔",
                "user_id": "usr_0123456789abcdef0123456789abcdef",
            },
        )

    assert results["recipe"].json()["extraction"]["unsupported_reason"] == "recipe"
    assert results["product"].json()["extraction"]["unsupported_reason"] == "product"
    assert results["travel"].json()["extraction"]["unsupported_reason"] == "multi_city_travel"
    assert results["generic"].json()["extraction"]["outcome"] == "insufficient_information"
    assert all(response.json()["collections"] == [] for response in results.values())
    assert broken.json()["extraction"]["outcome"] == "model_invalid_output"
    assert len(provider.calls) == 2
    assert blank.status_code == too_long.status_code == spoofed.status_code == 422
    assert "长" * 100 not in too_long.text
    assert "usr_0123456789abcdef0123456789abcdef" not in spoofed.text


@pytest.mark.asyncio
async def test_patch_reuses_domain_validation_and_noop_keeps_version(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response(_place())])
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        created = await _submit(client, session_id, key="patch-domain", content="具体地点")
        item = created.json()["collections"][0]
        item_id = item["id"]
        noop = await client.patch(
            f"/api/v1/collections/{item_id}",
            json={"expected_version": 1, "changes": {"title": item["title"]}},
        )
        forbidden = await client.patch(
            f"/api/v1/collections/{item_id}",
            json={"expected_version": 1, "changes": {"status": "active"}},
        )
        invalid_place_schedule = await client.patch(
            f"/api/v1/collections/{item_id}",
            json={
                "expected_version": 1,
                "changes": {"event_start_at": "2026-07-25T14:00:00+08:00"},
            },
        )
        invalid_price = await client.patch(
            f"/api/v1/collections/{item_id}",
            json={"expected_version": 1, "changes": {"price_currency": None}},
        )

    assert noop.status_code == 200 and noop.json()["version"] == 1
    assert forbidden.status_code == 422
    assert invalid_place_schedule.status_code == 422
    assert invalid_price.status_code == 422


@pytest.mark.asyncio
async def test_other_user_session_collection_and_trace_have_same_404(
    test_settings: Settings,
) -> None:
    async with _client(test_settings, FakeProvider([])) as (api, client):
        await _demo(client)
        now = utc_now()
        other_user = User(
            mode=UserMode.REAL,
            default_plan_city=PlanCity.SHENZHEN,
            timezone=SupportedTimezone.ASIA_SHANGHAI,
            created_at=now,
        )
        other_session = Session(
            user_id=other_user.id,
            channel=SessionChannel.WEB,
            created_at=now,
            updated_at=now,
        )
        other_item = CollectionItem(
            user_id=other_user.id,
            kind=CollectionKind.PLACE,
            title="Other user private place",
            status=CollectionStatus.PENDING_DETAILS,
            created_at=now,
            updated_at=now,
        )
        trace_id = generate_trace_id()
        async with api.state.database.session() as db_session:
            repository = SqlAlchemyCollectionRepository(db_session)
            await repository.add_user(user_id=other_user.id, user=other_user)
            await repository.add_session(user_id=other_user.id, session=other_session)
            await repository.add_collection_item(user_id=other_user.id, item=other_item)
            await AgentRunRepository(db_session).create_queued(
                AgentRunCreate(
                    trace_id=trace_id,
                    user_id=other_user.id,
                    session_id=other_session.id,
                    intent="private",
                    workflow="private",
                ),
                now=now,
            )
            await db_session.commit()

        responses = [
            await _submit(
                client,
                other_session.id,
                key="cross-user",
                content="不应访问",
            ),
            await client.get(f"/api/v1/collections/{other_item.id}"),
            await client.patch(
                f"/api/v1/collections/{other_item.id}",
                json={"expected_version": 1, "changes": {"title": "越权"}},
            ),
            await client.delete(f"/api/v1/collections/{other_item.id}"),
            await client.get(f"/api/v1/agent-runs/{trace_id}"),
        ]
        missing_collection = await client.get(
            "/api/v1/collections/col_0123456789abcdef0123456789abcdef"
        )

    assert all(response.status_code == 404 for response in responses)
    assert all(response.json() == missing_collection.json() for response in responses)


@pytest.mark.asyncio
async def test_cancelled_error_propagates_and_records_cancelled_without_collection_writes(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([asyncio.CancelledError()])
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        with pytest.raises(asyncio.CancelledError):
            await _submit(
                client,
                session_id,
                key="cancelled-provider",
                content="广州塔",
            )

    database_path = Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///"))
    with sqlite3.connect(database_path) as connection:
        run = connection.execute("SELECT status, error_code FROM agent_runs").fetchone()
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "messages",
                "sources",
                "collection_items",
                "collection_write_operations",
            )
        )
    assert run == ("cancelled", "RUN_CANCELLED")
    assert counts == (1, 0, 0, 0)


@pytest.mark.asyncio
async def test_mid_transaction_failure_rolls_back_all_collection_artifacts(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider([_response(_place(title="One"), _place(title="Two"))])
    original = CollectionWriteService._item_from_candidate
    calls = 0

    def fail_second(owner: str, candidate: PlaceCandidate | EventCandidate, now: datetime):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("transaction-fixture-failure")
        return original(owner, candidate, now)

    monkeypatch.setattr(
        CollectionWriteService,
        "_item_from_candidate",
        staticmethod(fail_second),
    )
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        with pytest.raises(RuntimeError, match="transaction-fixture-failure"):
            await _submit(
                client,
                session_id,
                key="rollback-artifacts",
                content="两个具体地点",
            )

    database_path = Path(test_settings.database_url.removeprefix("sqlite+aiosqlite:///"))
    with sqlite3.connect(database_path) as connection:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "sources",
                "collection_items",
                "collection_sources",
                "collection_write_operations",
                "collection_write_operation_items",
            )
        )
        run = connection.execute("SELECT status, error_code FROM agent_runs").fetchone()
    assert counts == (0, 0, 0, 0, 0)
    assert run == ("failed", "RUN_INTERNAL_ERROR")


@pytest.mark.asyncio
async def test_concurrent_undo_is_idempotent_and_expired_token_is_unavailable(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [
            _response(_place(title="Concurrent A"), _place(title="Concurrent B")),
            _response(_place(title="Expired")),
        ]
    )
    async with _client(test_settings, provider) as (api, client):
        session_id = await _demo(client)
        created = await _submit(
            client,
            session_id,
            key="concurrent-undo-api",
            content="两个地点",
        )
        data = created.json()
        path_item = data["collections"][0]["id"]
        token = data["undo_token"]
        first, second = await asyncio.gather(
            client.post(
                f"/api/v1/collections/{path_item}/undo",
                json={"undo_token": token},
            ),
            client.post(
                f"/api/v1/collections/{path_item}/undo",
                json={"undo_token": token},
            ),
        )

        expiring = await _submit(
            client,
            session_id,
            key="expired-undo-api",
            content="过期地点",
        )
        expiring_data = expiring.json()
        async with api.state.database.session() as db_session:
            await db_session.execute(
                text(
                    "UPDATE collection_write_operations "
                    "SET created_at = :created, undo_expires_at = :expired "
                    "WHERE idempotency_key = :key"
                ),
                {
                    "created": "2000-01-01T00:00:00+00:00",
                    "expired": "2000-01-01T00:10:00+00:00",
                    "key": "expired-undo-api",
                },
            )
            await db_session.commit()
        expired = await client.post(
            f"/api/v1/collections/{expiring_data['collections'][0]['id']}/undo",
            json={"undo_token": expiring_data["undo_token"]},
        )

    assert {first.json()["outcome"], second.json()["outcome"]} == {
        "undone",
        "already_undone",
    }
    assert set(first.json()["collection_item_ids"]) == {
        item["id"] for item in data["collections"]
    }
    assert expired.status_code == 404
    assert expiring_data["undo_token"] not in expired.text


@pytest.mark.asyncio
async def test_synchronous_workflow_enforces_configured_run_timeout(
    test_settings: Settings,
) -> None:
    class SlowProvider(ModelProvider):
        async def chat(
            self,
            *,
            messages: list[Message],
            tools: list[ToolDefinition] | None,
        ) -> ModelResponse:
            del messages, tools
            await asyncio.sleep(10)
            raise AssertionError("timeout did not cancel the provider")

    settings = test_settings.model_copy(update={"agent_timeout_seconds": 0.01})
    async with _client(settings, SlowProvider()) as (_api, client):
        session_id = await _demo(client)
        response = await _submit(
            client,
            session_id,
            key="workflow-timeout",
            content="广州塔",
        )
        replay = await _submit(
            client,
            session_id,
            key="workflow-timeout",
            content="广州塔",
        )

    assert response.status_code == 504
    assert response.json()["error_code"] == "RUN_TIMEOUT"
    assert replay.status_code == 504
    assert replay.json()["error_code"] == "RUN_TIMEOUT"
    assert replay.json()["trace_id"] == response.json()["trace_id"]
    database_path = Path(settings.database_url.removeprefix("sqlite+aiosqlite:///"))
    with sqlite3.connect(database_path) as connection:
        run = connection.execute("SELECT status, error_code FROM agent_runs").fetchone()
    assert run == ("failed", "RUN_TIMEOUT")

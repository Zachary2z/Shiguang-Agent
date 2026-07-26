"""M1-1 browser identity, CSRF, and physical Demo isolation contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.application.web_sessions import WebSessionService
from app.config import Settings
from app.domain.collections import User, UserMode
from app.domain.identity import SESSION_COOKIE_NAME, PrincipalMode
from app.infrastructure.db.models import (
    BrowserSessionModel,
    SessionModel,
    UserModel,
)
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from tests.contract.test_m0_2d_api import (
    _client,
    _demo,
    _place,
    _response,
    _submit,
)
from tests.core.fakes import FakeProvider


async def _owner_id(api: FastAPI, session_id: str) -> str:
    database = api.state.demo_database
    async with database.session() as session:
        owner = await session.scalar(
            select(SessionModel.user_id).where(SessionModel.id == session_id)
        )
    assert owner is not None
    return owner


@pytest.mark.asyncio
async def test_cookie_hash_csrf_and_same_browser_restore_are_safe(
    test_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with _client(test_settings) as (api, client):
        attacker_token = "a" * 43
        client.cookies.set(
            SESSION_COOKIE_NAME,
            attacker_token,
            domain="test.local",
            path="/",
        )
        first = await client.post("/api/v1/demo/sessions")
        token = client.cookies.get(SESSION_COOKIE_NAME)
        assert token is not None
        assert token != attacker_token
        first_payload = first.json()

        async with api.state.demo_database.session() as session:
            stored = await session.scalar(select(BrowserSessionModel))
            demo_users = await session.scalar(select(func.count()).select_from(UserModel))
        async with api.state.database.session() as session:
            real_users = await session.scalar(select(func.count()).select_from(UserModel))

        second = await client.post("/api/v1/demo/sessions")
        second_payload = second.json()
        rotated_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert rotated_token is not None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://test",
        ) as stale_client:
            stale_client.cookies.set(
                SESSION_COOKIE_NAME,
                token,
                domain="test.local",
                path="/",
            )
            stale_credential = await stale_client.get("/api/v1/collections")
        current_credential = await client.get("/api/v1/collections")
        openapi = json.dumps(api.openapi())

    cookie = first.headers["set-cookie"].lower()
    assert first.status_code == second.status_code == 201
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "domain=" not in cookie
    assert "secure" not in cookie
    assert stored is not None
    assert stored.token_hash != token
    assert stored.csrf_token_hash not in {
        first_payload["csrf_token"],
        second_payload["csrf_token"],
    }
    assert rotated_token != token
    assert stale_credential.status_code == 401
    assert current_credential.status_code == 200
    assert token not in first.text and token not in second.text
    assert token not in caplog.text
    assert first_payload["csrf_token"] not in caplog.text
    assert second_payload["csrf_token"] not in caplog.text
    assert "token_hash" not in first.text
    assert "user_id" not in first.text
    for private_field in (
        "token_hash",
        "csrf_token_hash",
        SESSION_COOKIE_NAME,
        "user_id",
    ):
        assert private_field not in openapi
    assert first_payload["session_id"] == second_payload["session_id"]
    assert first_payload["resumed"] is False and second_payload["resumed"] is True
    assert first_payload["csrf_token"] != second_payload["csrf_token"]
    assert demo_users == 1
    assert real_users == 0


@pytest.mark.asyncio
async def test_missing_forged_expired_and_revoked_credentials_have_stable_boundaries(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response(_place())])
    async with _client(test_settings, provider) as (_api, client):
        unauthenticated = await client.get("/api/v1/collections")
        started = await client.post("/api/v1/demo/sessions")
        session_id = started.json()["session_id"]
        csrf = started.json()["csrf_token"]

        missing_csrf = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"idempotency_key": "missing-csrf", "content": "深圳湾公园"},
        )
        bad_csrf = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"idempotency_key": "bad-csrf", "content": "深圳湾公园"},
            headers={"X-CSRF-Token": "a" * 43},
        )
        good = await client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"idempotency_key": "good-csrf", "content": "深圳湾公园"},
            headers={"X-CSRF-Token": csrf},
        )
        missing_logout_csrf = await client.delete("/api/v1/web-session")
        revoked = await client.delete(
            "/api/v1/web-session",
            headers={"X-CSRF-Token": csrf},
        )
        after_revoke = await client.get("/api/v1/collections")
        client.cookies.set(SESSION_COOKIE_NAME, "not-a-session-token")
        malformed = await client.get("/api/v1/collections")
        client.cookies.set(SESSION_COOKIE_NAME, "z" * 43)
        forged = await client.get("/api/v1/collections")

    assert unauthenticated.status_code == 401
    assert missing_csrf.status_code == bad_csrf.status_code == 403
    assert good.status_code == 200
    assert missing_logout_csrf.status_code == 403
    assert revoked.status_code == 200
    assert revoked.json() == {"status": "revoked"}
    assert after_revoke.status_code == malformed.status_code == forged.status_code == 401
    assert {response.json()["error_code"] for response in (after_revoke, malformed, forged)} == {
        "AUTHENTICATION_REQUIRED"
    }


@pytest.mark.asyncio
async def test_two_cookie_jars_cannot_cross_read_or_write_demo_resources(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response(_place())])
    async with _client(test_settings, provider) as (api, first_client):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://test",
        ) as second_client:
            first_session = await _demo(first_client)
            second_session = await _demo(second_client)
            first_owner = await _owner_id(api, first_session)
            second_owner = await _owner_id(api, second_session)
            created = await _submit(
                first_client,
                first_session,
                key="browser-a",
                content="深圳当代艺术与城市规划馆",
            )
            item_id = created.json()["collections"][0]["id"]
            trace_id = created.json()["trace_id"]
            undo_token = created.json()["undo_token"]

            cross_session = await _submit(
                second_client,
                first_session,
                key="browser-b-cross-session",
                content="不能写入",
            )
            cross_item = await second_client.get(f"/api/v1/collections/{item_id}")
            cross_run = await second_client.get(f"/api/v1/agent-runs/{trace_id}")
            cross_events = await second_client.get(
                f"/api/v1/agent-runs/{trace_id}/events"
            )
            cross_undo = await second_client.post(
                f"/api/v1/collections/{item_id}/undo",
                json={"undo_token": undo_token},
            )
            second_list = await second_client.get("/api/v1/collections")
            first_list = await first_client.get("/api/v1/collections")

    assert first_owner != second_owner
    assert first_session != second_session
    assert created.status_code == 200
    assert cross_session.status_code == 404
    assert cross_item.status_code == cross_run.status_code == cross_events.status_code == 404
    assert cross_undo.status_code == 404
    assert second_list.json()["total"] == 0
    assert first_list.json()["total"] == 1


@pytest.mark.asyncio
async def test_real_session_capability_uses_real_database_and_absolute_expiry(
    test_settings: Settings,
) -> None:
    now = datetime(2026, 7, 27, 12, tzinfo=UTC)
    async with _client(test_settings) as (api, client):
        async with api.state.database.session() as session:
            repository = SqlAlchemyCollectionRepository(session)
            user = User(mode=UserMode.REAL, created_at=now)
            await repository.add_user(user_id=user.id, user=user)
            issued = await WebSessionService(
                session=session,
                now=lambda: now,
            ).create(
                user_id=user.id,
                mode=PrincipalMode.REAL,
                lifetime=timedelta(days=30),
            )
            await session.commit()

        client.cookies.set(
            SESSION_COOKIE_NAME,
            issued.session_token,
            domain="test.local",
            path="/",
        )
        real_collections = await client.get("/api/v1/collections")
        async with api.state.database.session() as session:
            before = await WebSessionService(
                session=session,
                now=lambda: issued.browser_session.expires_at
                - timedelta(microseconds=1),
            ).resolve(
                session_token=issued.session_token,
                mode=PrincipalMode.REAL,
            )
        async with api.state.database.session() as session:
            at_expiry = await WebSessionService(
                session=session,
                now=lambda: issued.browser_session.expires_at,
            ).resolve(
                session_token=issued.session_token,
                mode=PrincipalMode.REAL,
            )
        async with api.state.demo_database.session() as session:
            demo_user = await session.get(UserModel, user.id)

    assert real_collections.status_code == 200
    assert before is not None
    assert at_expiry is None
    assert demo_user is None

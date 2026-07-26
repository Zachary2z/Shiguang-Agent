"""M1-1 browser identity, CSRF, and physical Demo isolation contracts."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update

from app.application.web_sessions import IssuedWebSession, WebSessionService
from app.config import Settings
from app.domain.collections import User, UserMode
from app.domain.identity import (
    SESSION_COOKIE_NAME,
    BrowserSession,
    CurrentPrincipal,
    PrincipalMode,
    derive_csrf_token,
    hash_session_secret,
)
from app.domain.time import utc_now
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
    return str(owner)


def _copy_session_cookie(client: httpx.AsyncClient, token: str) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, token, domain="test.local", path="/")


def _set_cookie_parts(response: httpx.Response) -> tuple[int, datetime]:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    morsel = cookie[SESSION_COOKIE_NAME]
    return int(morsel["max-age"]), parsedate_to_datetime(morsel["expires"])


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
        restored_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert restored_token is not None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://test",
        ) as restored_client:
            _copy_session_cookie(restored_client, token)
            restored_credential = await restored_client.get("/api/v1/collections")
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
    assert stored.token_hash == hash_session_secret(token)
    assert stored.csrf_token_hash not in {
        first_payload["csrf_token"],
        second_payload["csrf_token"],
    }
    assert stored.csrf_token_hash == hash_session_secret(derive_csrf_token(token))
    assert restored_token == token
    assert restored_credential.status_code == 200
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
    assert first_payload["csrf_token"] == second_payload["csrf_token"]
    assert demo_users == 1
    assert real_users == 0


@pytest.mark.asyncio
async def test_concurrent_same_cookie_restores_keep_every_response_usable(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restore_count = 8
    async with _client(test_settings) as (api, owner_client):
        initial = await owner_client.post("/api/v1/demo/sessions")
        initial_payload = initial.json()
        token = owner_client.cookies.get(SESSION_COOKIE_NAME)
        assert token is not None

        original_resume = WebSessionService.resume
        entered = 0
        entered_lock = asyncio.Lock()
        all_entered = asyncio.Event()

        async def gated_resume(
            service: WebSessionService,
            *,
            session_token: str,
            mode: PrincipalMode,
            at: datetime | None = None,
        ) -> tuple[CurrentPrincipal, IssuedWebSession] | None:
            nonlocal entered
            result = await original_resume(
                service,
                session_token=session_token,
                mode=mode,
                at=at,
            )
            async with entered_lock:
                entered += 1
                if entered == restore_count:
                    all_entered.set()
            await all_entered.wait()
            return result

        monkeypatch.setattr(WebSessionService, "resume", gated_resume)
        clients = [
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api),
                base_url="http://test",
            )
            for _ in range(restore_count)
        ]
        try:
            for client in clients:
                _copy_session_cookie(client, token)
            responses = await asyncio.gather(
                *(client.post("/api/v1/demo/sessions") for client in clients)
            )
            reads = await asyncio.gather(
                *(client.get("/api/v1/collections") for client in clients)
            )
            writes = await asyncio.gather(
                *(
                    client.post(
                        "/api/v1/collections/col_"
                        + "0123456789abcdef" * 2
                        + "/undo",
                        json={"undo_token": "not-available"},
                        headers={"X-CSRF-Token": response.json()["csrf_token"]},
                    )
                    for client, response in zip(clients, responses, strict=True)
                )
            )
        finally:
            await asyncio.gather(*(client.aclose() for client in clients))

        async with api.state.demo_database.session() as session:
            user_count = await session.scalar(select(func.count()).select_from(UserModel))
            message_session_count = await session.scalar(
                select(func.count()).select_from(SessionModel)
            )
            web_session_count = await session.scalar(
                select(func.count()).select_from(BrowserSessionModel)
            )
        owner_ids = {
            await _owner_id(api, response.json()["session_id"])
            for response in responses
        }

    assert all(response.status_code == 201 for response in responses)
    assert all(response.json()["resumed"] is True for response in responses)
    assert {
        response.json()["session_id"] for response in responses
    } == {initial_payload["session_id"]}
    assert {response.json()["csrf_token"] for response in responses} == {
        initial_payload["csrf_token"]
    }
    assert {
        client.cookies.get(SESSION_COOKIE_NAME) for client in clients
    } == {token}
    assert all(response.status_code == 200 for response in reads)
    assert all(response.status_code == 404 for response in writes)
    assert len(owner_ids) == 1
    assert user_count == message_session_count == web_session_count == 1


@pytest.mark.asyncio
async def test_restored_cookie_uses_database_remaining_lifetime(
    test_settings: Settings,
) -> None:
    async with _client(test_settings) as (api, client):
        created = await client.post("/api/v1/demo/sessions")
        created_max_age, created_expires = _set_cookie_parts(created)
        token = client.cookies.get(SESSION_COOKIE_NAME)
        assert token is not None

        near_expiry = utc_now() + timedelta(seconds=65)
        async with api.state.demo_database.session() as session:
            await session.execute(
                update(BrowserSessionModel)
                .where(BrowserSessionModel.token_hash == hash_session_secret(token))
                .values(expires_at=near_expiry)
            )
            await session.commit()

        restored = await client.post("/api/v1/demo/sessions")
        restored_max_age, restored_expires = _set_cookie_parts(restored)

    assert created_max_age == test_settings.demo_web_session_ttl_seconds
    response_expiry = datetime.fromisoformat(created.json()["expires_at"])
    assert abs((created_expires - response_expiry).total_seconds()) < 1
    assert restored.status_code == 201
    assert restored.json()["resumed"] is True
    assert 1 <= restored_max_age <= 65
    assert restored_max_age < test_settings.demo_web_session_ttl_seconds
    assert abs((restored_expires - near_expiry).total_seconds()) < 1


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
async def test_expired_and_revoked_demo_cookies_create_new_random_sandboxes(
    test_settings: Settings,
) -> None:
    async with _client(test_settings) as (api, client):
        first = await client.post("/api/v1/demo/sessions")
        first_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert first_token is not None
        first_owner = await _owner_id(api, first.json()["session_id"])

        async with api.state.demo_database.session() as session:
            await session.execute(
                update(BrowserSessionModel)
                .where(BrowserSessionModel.token_hash == hash_session_secret(first_token))
                .values(expires_at=utc_now())
            )
            await session.commit()
        expired_replacement = await client.post("/api/v1/demo/sessions")
        second_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert second_token is not None
        second_owner = await _owner_id(api, expired_replacement.json()["session_id"])

        revoked = await client.delete(
            "/api/v1/web-session",
            headers={"X-CSRF-Token": expired_replacement.json()["csrf_token"]},
        )
        _copy_session_cookie(client, second_token)
        revoked_replacement = await client.post("/api/v1/demo/sessions")
        third_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert third_token is not None
        third_owner = await _owner_id(api, revoked_replacement.json()["session_id"])

        async with api.state.demo_database.session() as session:
            counts = (
                await session.scalar(select(func.count()).select_from(UserModel)),
                await session.scalar(select(func.count()).select_from(SessionModel)),
                await session.scalar(
                    select(func.count()).select_from(BrowserSessionModel)
                ),
            )

    assert expired_replacement.status_code == revoked_replacement.status_code == 201
    assert expired_replacement.json()["resumed"] is False
    assert revoked_replacement.json()["resumed"] is False
    assert revoked.status_code == 200
    assert len({first_token, second_token, third_token}) == 3
    assert len({first_owner, second_owner, third_owner}) == 3
    assert counts == (3, 3, 3)


@pytest.mark.asyncio
async def test_restore_and_revoke_race_keeps_database_revocation_authoritative(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _client(test_settings) as (api, bootstrap_client):
        initial = await bootstrap_client.post("/api/v1/demo/sessions")
        token = bootstrap_client.cookies.get(SESSION_COOKIE_NAME)
        assert token is not None
        csrf = initial.json()["csrf_token"]

        original_resolve = WebSessionService.resolve
        entered = 0
        entered_lock = asyncio.Lock()
        both_resolved = asyncio.Event()

        async def gated_resolve(
            service: WebSessionService,
            *,
            session_token: str,
            mode: PrincipalMode,
            at: datetime | None = None,
        ) -> tuple[CurrentPrincipal, BrowserSession] | None:
            nonlocal entered
            result = await original_resolve(
                service,
                session_token=session_token,
                mode=mode,
                at=at,
            )
            async with entered_lock:
                entered += 1
                if entered == 2:
                    both_resolved.set()
            await both_resolved.wait()
            return result

        monkeypatch.setattr(WebSessionService, "resolve", gated_resolve)
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api),
                base_url="http://test",
            ) as restore_client,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api),
                base_url="http://test",
            ) as revoke_client,
        ):
            _copy_session_cookie(restore_client, token)
            _copy_session_cookie(revoke_client, token)
            restored, revoked = await asyncio.gather(
                restore_client.post("/api/v1/demo/sessions"),
                revoke_client.delete(
                    "/api/v1/web-session",
                    headers={"X-CSRF-Token": csrf},
                ),
            )
            final_access = await restore_client.get("/api/v1/collections")

        async with api.state.demo_database.session() as session:
            user_count = await session.scalar(select(func.count()).select_from(UserModel))
            message_session_count = await session.scalar(
                select(func.count()).select_from(SessionModel)
            )
            web_session_count = await session.scalar(
                select(func.count()).select_from(BrowserSessionModel)
            )
            revoked_at = await session.scalar(select(BrowserSessionModel.revoked_at))

    assert restored.status_code == 201
    assert restored.json()["resumed"] is True
    assert revoked.status_code == 200
    assert final_access.status_code == 401
    assert revoked_at is not None
    assert user_count == message_session_count == web_session_count == 1


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

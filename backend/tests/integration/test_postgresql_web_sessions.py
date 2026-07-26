"""PostgreSQL concurrency and physical isolation for M1-1 Web Sessions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.application.web_sessions import IssuedWebSession, WebSessionService
from app.config import Settings
from app.domain.collections import User, UserMode
from app.domain.identity import (
    SESSION_COOKIE_NAME,
    CurrentPrincipal,
    PrincipalMode,
)
from app.domain.time import utc_now
from app.infrastructure.db import Database
from app.infrastructure.db.models import (
    BrowserSessionModel,
    SessionModel,
    UserModel,
)
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.main import create_app


@pytest.mark.postgresql
def test_postgresql_concurrent_creation_revocation_and_database_isolation(
    postgresql_database_pair_urls: tuple[str, str],
) -> None:
    real_url, demo_url = postgresql_database_pair_urls

    async def scenario() -> None:
        real_database = Database(real_url)
        demo_database = Database(demo_url)
        await real_database.connect()
        await demo_database.connect()
        try:
            async with demo_database.session() as session:
                demo_user = User(mode=UserMode.DEMO, created_at=utc_now())
                await SqlAlchemyCollectionRepository(session).add_user(
                    user_id=demo_user.id,
                    user=demo_user,
                )
                await session.commit()

            async def issue_one() -> tuple[str, str]:
                async with demo_database.session() as session:
                    issued = await WebSessionService(session=session).create(
                        user_id=demo_user.id,
                        mode=PrincipalMode.DEMO,
                        lifetime=timedelta(hours=2),
                    )
                    await session.commit()
                    return issued.session_token, issued.browser_session.id

            issued = await asyncio.gather(*(issue_one() for _ in range(20)))
            tokens = [item[0] for item in issued]
            session_ids = [item[1] for item in issued]

            async def revoke_one() -> None:
                async with demo_database.session() as session:
                    await WebSessionService(session=session).revoke(
                        session_id=session_ids[0]
                    )
                    await session.commit()

            await asyncio.gather(*(revoke_one() for _ in range(10)))

            async with demo_database.session() as session:
                demo_session_count = await session.scalar(
                    select(func.count()).select_from(BrowserSessionModel)
                )
                revoked_at = await session.scalar(
                    select(BrowserSessionModel.revoked_at).where(
                        BrowserSessionModel.id == session_ids[0]
                    )
                )
                stored_hashes = set(
                    (
                        await session.scalars(select(BrowserSessionModel.token_hash))
                    ).all()
                )
            async with real_database.session() as session:
                real_user = await session.get(UserModel, demo_user.id)
                real_session_count = await session.scalar(
                    select(func.count()).select_from(BrowserSessionModel)
                )

            assert len(set(tokens)) == len(set(session_ids)) == 20
            assert demo_session_count == 20
            assert revoked_at is not None
            assert not (set(tokens) & stored_hashes)
            assert real_user is None
            assert real_session_count == 0
        finally:
            await demo_database.close()
            await real_database.close()

    asyncio.run(scenario())


@pytest.mark.postgresql
def test_postgresql_concurrent_demo_restore_keeps_all_credentials_usable(
    postgresql_database_pair_urls: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_url, demo_url = postgresql_database_pair_urls

    async def scenario() -> None:
        settings = Settings(
            _env_file=None,
            app_env="test",
            database_url=real_url,
            demo_database_url=demo_url,
            log_level="DEBUG",
        )
        api = create_app(settings)
        async with api.router.lifespan_context(api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api),
                base_url="http://test",
            ) as owner_client:
                initial = await owner_client.post("/api/v1/demo/sessions")
                token = owner_client.cookies.get(SESSION_COOKIE_NAME)
                assert token is not None

            restore_count = 8
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
                    client.cookies.set(
                        SESSION_COOKIE_NAME,
                        token,
                        domain="test.local",
                        path="/",
                    )
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
                restored_tokens = {
                    client.cookies.get(SESSION_COOKIE_NAME) for client in clients
                }
            finally:
                await asyncio.gather(*(client.aclose() for client in clients))

            async with api.state.demo_database.session() as session:
                counts = (
                    await session.scalar(select(func.count()).select_from(UserModel)),
                    await session.scalar(
                        select(func.count()).select_from(SessionModel)
                    ),
                    await session.scalar(
                        select(func.count()).select_from(BrowserSessionModel)
                    ),
                )
            async with api.state.database.session() as session:
                real_counts = (
                    await session.scalar(select(func.count()).select_from(UserModel)),
                    await session.scalar(
                        select(func.count()).select_from(BrowserSessionModel)
                    ),
                )

        assert initial.status_code == 201
        assert all(response.status_code == 201 for response in responses)
        assert all(response.json()["resumed"] is True for response in responses)
        assert {response.json()["session_id"] for response in responses} == {
            initial.json()["session_id"]
        }
        assert {response.json()["csrf_token"] for response in responses} == {
            initial.json()["csrf_token"]
        }
        assert restored_tokens == {token}
        assert all(response.status_code == 200 for response in reads)
        assert all(response.status_code == 404 for response in writes)
        assert counts == (1, 1, 1)
        assert real_counts == (0, 0)

    asyncio.run(scenario())

"""PostgreSQL concurrency and physical isolation for M1-1 Web Sessions."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.application.web_sessions import WebSessionService
from app.domain.collections import User, UserMode
from app.domain.identity import PrincipalMode
from app.domain.time import utc_now
from app.infrastructure.db import Database
from app.infrastructure.db.models import BrowserSessionModel, UserModel
from app.infrastructure.repositories import SqlAlchemyCollectionRepository


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

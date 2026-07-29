"""PostgreSQL serialization and partial-unique enforcement for M1-8."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.domain.identity import SESSION_COOKIE_NAME
from app.infrastructure.db.models import PlanShareLinkModel
from app.main import create_app
from tests.contract.test_m1_6_execution import _seed_plan


@pytest.mark.postgresql
def test_postgresql_plan_share_creation_serializes_per_plan(
    postgresql_database_url: str,
) -> None:
    async def scenario() -> None:
        settings = Settings(
            _env_file=None,
            app_env="test",
            database_url=postgresql_database_url,
            demo_database_url=postgresql_database_url,
            log_level="DEBUG",
        )
        api = create_app(settings)
        async with api.router.lifespan_context(api):
            transport = httpx.ASGITransport(app=api)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as bootstrap:
                issued = await bootstrap.post("/api/v1/demo/sessions")
                assert issued.status_code == 201
                csrf = issued.json()["csrf_token"]
                session_token = bootstrap.cookies.get(SESSION_COOKIE_NAME)
                assert session_token is not None
                first_plan, _collection_id, _item_ids = await _seed_plan(
                    api, confirmed=True
                )
                second_plan, _collection_id, _item_ids = await _seed_plan(
                    api, confirmed=True
                )

            clients = [
                httpx.AsyncClient(transport=transport, base_url="http://test")
                for _ in range(8)
            ]
            try:
                for client in clients:
                    client.cookies.set(
                        SESSION_COOKIE_NAME,
                        session_token,
                        domain="test.local",
                        path="/",
                    )
                same_plan = await asyncio.gather(
                    *(
                        client.post(
                            f"/api/v1/plans/{first_plan}/share",
                            headers={"X-CSRF-Token": csrf},
                        )
                        for client in clients
                    )
                )
                assert all(response.status_code == 200 for response in same_plan)
                assert sum(
                    response.json()["share_url"] is not None
                    for response in same_plan
                ) == 1

                independent = await asyncio.gather(
                    clients[0].post(
                        f"/api/v1/plans/{first_plan}/share/regenerate",
                        headers={"X-CSRF-Token": csrf},
                    ),
                    clients[1].post(
                        f"/api/v1/plans/{second_plan}/share",
                        headers={"X-CSRF-Token": csrf},
                    ),
                )
                assert all(response.status_code == 200 for response in independent)
                assert all(
                    response.json()["share_url"] is not None
                    for response in independent
                )

                async with api.state.demo_database.session_factory() as session:
                    active = await session.scalar(
                        select(func.count())
                        .select_from(PlanShareLinkModel)
                        .where(PlanShareLinkModel.revoked_at.is_(None))
                    )
                    assert active == 2
                    plans = set(
                        (
                            await session.scalars(
                                select(PlanShareLinkModel.plan_id).where(
                                    PlanShareLinkModel.revoked_at.is_(None)
                                )
                            )
                        ).all()
                    )
                    assert plans == {first_plan, second_plan}
            finally:
                await asyncio.gather(*(client.aclose() for client in clients))

    asyncio.run(scenario())

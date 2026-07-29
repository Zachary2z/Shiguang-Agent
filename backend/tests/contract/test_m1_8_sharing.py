"""M1-8 hashed, revocable, latest-confirmed plan-sharing contracts."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, update

from app.application.plan_sharing import PlanShareService
from app.domain.identifiers import generate_plan_id, generate_trace_id
from app.domain.identity import SESSION_COOKIE_NAME
from app.domain.plans import PlanOperation, PlanStatus, PlanVersion
from app.domain.sharing import (
    SHARE_TOKEN_BYTES,
    SHARE_TOKEN_LENGTH,
    PublicShareStatus,
    hash_share_token,
    share_expiry_for,
)
from app.domain.time import utc_now
from app.infrastructure.db.models import PlanModel, PlanShareLinkModel
from app.infrastructure.repositories import (
    SqlAlchemyPlanRepository,
    plan_request_fingerprint,
)
from tests.contract.test_m0_2d_api import _client, _demo
from tests.contract.test_m1_6_execution import _constraints, _draft, _seed_plan
from tests.fixtures.maps import make_stub_map_provider


@pytest.fixture(autouse=True)
def _fixed_business_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = datetime(2026, 7, 28, 2, tzinfo=UTC)

    def clock() -> datetime:
        return fixed

    monkeypatch.setattr("app.application.plan_sharing.utc_now", clock)
    monkeypatch.setattr("tests.contract.test_m1_8_sharing.utc_now", clock)


async def _create_share(
    client: httpx.AsyncClient,
    *,
    plan_id: str,
    csrf: str,
    regenerate: bool = False,
) -> httpx.Response:
    suffix = "/regenerate" if regenerate else ""
    return await client.post(
        f"/api/v1/plans/{plan_id}/share{suffix}",
        headers={"X-CSRF-Token": csrf},
    )


async def _read_public(
    client: httpx.AsyncClient,
    token: str,
) -> httpx.Response:
    return await client.get(
        "/api/v1/public/plan-share",
        headers={"Authorization": f"Share {token}"},
    )


def _issued_token(response: httpx.Response) -> str:
    share_url = response.json()["share_url"]
    assert isinstance(share_url, str) and share_url.startswith("/share#")
    return share_url.partition("#")[2]


@pytest.mark.asyncio
async def test_create_repeat_regenerate_and_revoke_keep_only_hash(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        csrf = str(client.headers["X-CSRF-Token"])
        plan_id, _collection_id, _item_ids = await _seed_plan(api, confirmed=True)

        created = await _create_share(client, plan_id=plan_id, csrf=csrf)
        assert created.status_code == 200
        first_token = _issued_token(created)
        assert SHARE_TOKEN_BYTES == 32
        assert len(first_token) == SHARE_TOKEN_LENGTH
        assert created.json()["created"] is True

        repeated = await _create_share(client, plan_id=plan_id, csrf=csrf)
        assert repeated.status_code == 200
        assert repeated.json()["status"] == "active"
        assert repeated.json()["share_url"] is None
        assert repeated.json()["created"] is False

        async with api.state.demo_database.session_factory() as session:
            rows = (
                await session.scalars(
                    select(PlanShareLinkModel).order_by(
                        PlanShareLinkModel.created_at
                    )
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].token_hash == hash_share_token(first_token)
            assert first_token not in rows[0].token_hash

        regenerated = await _create_share(
            client,
            plan_id=plan_id,
            csrf=csrf,
            regenerate=True,
        )
        second_token = _issued_token(regenerated)
        assert regenerated.status_code == 200
        assert second_token != first_token
        old = await _read_public(client, first_token)
        current = await _read_public(client, second_token)
        assert old.json() == {"status": "unavailable", "plan": None}
        assert current.json()["status"] == "active"

        revoked = await client.delete(
            f"/api/v1/plans/{plan_id}/share",
            headers={"X-CSRF-Token": csrf},
        )
        assert revoked.status_code == 200
        assert revoked.json() == {
            "status": "inactive",
            "created_at": None,
            "expires_at": None,
            "share_url": None,
            "created": False,
        }
        unavailable = await _read_public(client, second_token)
        assert unavailable.json() == {"status": "unavailable", "plan": None}


@pytest.mark.asyncio
async def test_public_snapshot_is_redacted_read_only_and_has_security_headers(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        plan_id, collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        created = await _create_share(
            client,
            plan_id=plan_id,
            csrf=str(client.headers["X-CSRF-Token"]),
        )
        token = _issued_token(created)

        public = await _read_public(client, token)
        assert public.status_code == 200
        assert public.headers["cache-control"] == "no-store"
        assert public.headers["referrer-policy"] == "no-referrer"
        assert public.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
        assert "set-cookie" not in public.headers
        body = public.json()
        assert body["status"] == "active"
        snapshot = body["plan"]
        assert snapshot["version"] == 1
        assert snapshot["origin_label"] == "福田区"
        assert snapshot["items"][0]["public_address"] == "福中路184号"
        assert snapshot["items"][0]["map_url"].startswith("geo:")
        assert snapshot["items"][1]["queried_at"] is not None
        assert snapshot["expires_at"] == (
            datetime.fromisoformat(snapshot["end_at"]) + timedelta(days=7)
        ).isoformat().replace("+00:00", "Z")

        serialized = public.text
        forbidden = (
            collection_id,
            plan_id,
            "user_id",
            "session",
            "trace",
            "idempotency",
            "conversation",
            "memory",
            "authorization",
            token,
        )
        assert all(value.lower() not in serialized.lower() for value in forbidden)

        write_attempts = (
            await client.post("/api/v1/public/plan-share"),
            await client.delete("/api/v1/public/plan-share"),
            await client.patch("/api/v1/public/plan-share", json={}),
        )
        assert all(response.status_code == 405 for response in write_attempts)


@pytest.mark.asyncio
async def test_latest_confirmation_updates_share_while_draft_stays_private(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        api.state.map_provider = make_stub_map_provider()
        await _demo(client)
        plan_id, collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        created = await _create_share(
            client,
            plan_id=plan_id,
            csrf=str(client.headers["X-CSRF-Token"]),
        )
        token = _issued_token(created)

        async with api.state.demo_database.session_factory() as session:
            repository = SqlAlchemyPlanRepository(session)
            now = utc_now()
            version_two_id = generate_plan_id()
            user_id = await session.scalar(
                select(PlanModel.user_id).where(PlanModel.id == plan_id)
            )
            assert user_id is not None
            version_two = PlanVersion(
                id=version_two_id,
                root_plan_id=plan_id,
                parent_plan_id=plan_id,
                user_id=user_id,
                version=2,
                operation=PlanOperation.ADJUST,
                status=PlanStatus.GENERATING,
                constraints=_constraints(),
                adjustment_text="只修改未确认草稿",
                trace_id=generate_trace_id(),
                idempotency_key=f"draft-{version_two_id}",
                created_at=now,
                updated_at=now,
            )
            await repository.add(
                version_two,
                request_fingerprint=plan_request_fingerprint("v2"),
            )
            second_draft = _draft(collection_id)
            second_option = second_draft.options[0]
            await repository.complete_generation(
                user_id=version_two.user_id,
                plan_id=version_two_id,
                draft=second_draft.model_copy(
                    update={
                        "options": (
                            second_option.model_copy(
                                update={
                                    "items": (
                                        second_option.items[0].model_copy(
                                            update={"title": "未确认草稿标题"}
                                        ),
                                        second_option.items[1],
                                    )
                                }
                            ),
                        )
                    }
                ),
                now=now,
            )
            await session.commit()

        draft_hidden = await _read_public(client, token)
        assert draft_hidden.json()["plan"]["version"] == 1
        assert "未确认草稿标题" not in draft_hidden.text

        async with api.state.demo_database.session_factory() as session:
            repository = SqlAlchemyPlanRepository(session)
            version_two = await repository.require(
                user_id=(
                    await session.scalar(
                        select(PlanModel.user_id).where(
                            PlanModel.id == version_two_id
                        )
                    )
                ),
                plan_id=version_two_id,
            )
            await repository.confirm(
                user_id=version_two.user_id,
                plan_id=version_two_id,
                idempotency_key=f"confirm-{version_two_id}",
                request_fingerprint=plan_request_fingerprint("confirm-v2"),
                now=utc_now(),
            )
            await session.commit()

        confirmed_visible = await _read_public(client, token)
        assert confirmed_visible.json()["plan"]["version"] == 2
        assert "未确认草稿标题" in confirmed_visible.text


@pytest.mark.asyncio
async def test_cancelled_and_unavailable_states_are_safe(test_settings) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        plan_id, _collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        created = await _create_share(
            client,
            plan_id=plan_id,
            csrf=str(client.headers["X-CSRF-Token"]),
        )
        token = _issued_token(created)
        async with api.state.demo_database.session_factory() as session:
            await session.execute(
                update(PlanModel)
                .where(PlanModel.id == plan_id)
                .values(
                    status=PlanStatus.CANCELLED.value,
                    draft_json=None,
                    confirmed_at=None,
                )
            )
            await session.commit()
        cancelled = await _read_public(client, token)
        missing = await _read_public(client, "not-a-real-share")
        assert cancelled.json() == {"status": "cancelled", "plan": None}
        assert missing.json() == {"status": "unavailable", "plan": None}


@pytest.mark.asyncio
async def test_expiry_boundary_and_owner_security(test_settings) -> None:
    async with _client(test_settings) as (api, owner):
        await _demo(owner)
        plan_id, _collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        csrf = str(owner.headers.pop("X-CSRF-Token"))
        no_csrf = await owner.post(f"/api/v1/plans/{plan_id}/share")
        assert no_csrf.status_code == 403
        owner.headers["X-CSRF-Token"] = csrf
        created = await _create_share(
            owner,
            plan_id=plan_id,
            csrf=csrf,
        )
        token = _issued_token(created)

        async with api.state.demo_database.session_factory() as session:
            share = await session.scalar(select(PlanShareLinkModel))
            assert share is not None
            expiry = _constraints().end_at + timedelta(days=7)
            assert share_expiry_for(_constraints().end_at) == expiry
            active = await PlanShareService(
                session
            ).read_public(token=token, now=expiry - timedelta(microseconds=1))
            expired = await PlanShareService(session).read_public(
                token=token,
                now=expiry,
            )
            assert active.status is PublicShareStatus.ACTIVE
            assert expired.status is PublicShareStatus.UNAVAILABLE

        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as stranger:
            await _demo(stranger)
            forbidden = await _create_share(
                stranger,
                plan_id=plan_id,
                csrf=str(stranger.headers["X-CSRF-Token"]),
            )
            assert forbidden.status_code == 404
            forbidden_revoke = await stranger.delete(
                f"/api/v1/plans/{plan_id}/share",
                headers={
                    "X-CSRF-Token": str(stranger.headers["X-CSRF-Token"])
                },
            )
            assert forbidden_revoke.status_code == 404
            public = await _read_public(stranger, token)
            assert public.status_code == 200
            assert "set-cookie" not in public.headers

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={SESSION_COOKIE_NAME: token},
        ) as bearer_as_session:
            rejected = await bearer_as_session.get("/api/v1/plans")
            assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_public_token_is_redacted_from_request_logs(
    test_settings,
) -> None:
    token = "A" * 43
    records: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("shiguang.request")
    handler = _CaptureHandler()
    logger.addHandler(handler)
    try:
        async with _client(test_settings) as (_api, client):
            response = await _read_public(client, token)
        assert response.status_code == 200
    finally:
        logger.removeHandler(handler)
    output = "\n".join(records)
    assert token not in output
    assert "/api/v1/public/plan-share" in output


@pytest.mark.asyncio
async def test_same_plan_concurrent_create_converges_to_one_unrevoked_row(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        plan_id, _collection_id, _item_ids = await _seed_plan(api, confirmed=True)
        results = await asyncio.gather(
            _create_share(
                client,
                plan_id=plan_id,
                csrf=str(client.headers["X-CSRF-Token"]),
            ),
            _create_share(
                client,
                plan_id=plan_id,
                csrf=str(client.headers["X-CSRF-Token"]),
            ),
        )
        assert all(result.status_code == 200 for result in results)
        async with api.state.demo_database.session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(PlanShareLinkModel)
                .where(PlanShareLinkModel.revoked_at.is_(None))
            )
            assert count == 1


@pytest.mark.asyncio
async def test_different_plans_create_shares_concurrently_without_interference(
    test_settings,
) -> None:
    async with _client(test_settings) as (api, client):
        await _demo(client)
        first_plan, _collection_id, _item_ids = await _seed_plan(
            api, confirmed=True
        )
        second_plan, _collection_id, _item_ids = await _seed_plan(
            api, confirmed=True
        )
        csrf = str(client.headers["X-CSRF-Token"])
        results = await asyncio.gather(
            _create_share(client, plan_id=first_plan, csrf=csrf),
            _create_share(client, plan_id=second_plan, csrf=csrf),
        )
        assert all(result.status_code == 200 for result in results)
        tokens = {_issued_token(result) for result in results}
        assert len(tokens) == 2
        async with api.state.demo_database.session_factory() as session:
            rows = (
                await session.scalars(
                    select(PlanShareLinkModel).where(
                        PlanShareLinkModel.revoked_at.is_(None)
                    )
                )
            ).all()
            assert {row.plan_id for row in rows} == {first_plan, second_plan}
            assert len({row.token_hash for row in rows}) == 2

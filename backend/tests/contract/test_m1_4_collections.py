"""M1-4 collection library, detail, and persisted place-selection contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.application.place_targets import PlaceTargetSelectionService
from app.config import Settings
from app.domain.places import (
    Coordinate,
    CoordinateSystem,
    EvidenceField,
    EvidenceOutcome,
    EvidenceReason,
    MatchConfidence,
    MatchEvidence,
    MatchStatus,
    PlaceMatchCandidate,
    PlaceMatchResult,
    PoiProvider,
    PoiType,
)
from app.infrastructure.db.models import CollectionItemModel
from tests.contract.test_m0_2d_api import (
    _client,
    _demo,
    _event,
    _place,
    _response,
    _submit,
)
from tests.core.fakes import FakeProvider


def _evidence() -> tuple[MatchEvidence, ...]:
    return tuple(
        MatchEvidence(
            field=field,
            outcome=EvidenceOutcome.MISSING,
            reason=EvidenceReason.SOURCE_MISSING,
            score_delta=0.0,
        )
        for field in EvidenceField
    )


def _candidate(
    poi_id: str,
    *,
    city_code: str = "shenzhen",
    branch_name: str,
    district: str,
    business_area: str,
    address: str,
    rank: int = 1,
    confidence: MatchConfidence = MatchConfidence.MEDIUM,
) -> PlaceMatchCandidate:
    return PlaceMatchCandidate(
        provider=PoiProvider.AMAP,
        poi_id=poi_id,
        city_code=city_code,
        coordinate=Coordinate(
            latitude=22.53 + rank / 1000,
            longitude=114.05 + rank / 1000,
            coordinate_system=CoordinateSystem.GCJ_02,
        ),
        name="一尺花园",
        branch_name=branch_name,
        district=district,
        business_area=business_area,
        address=address,
        poi_type=PoiType.CAFE,
        provider_rank=rank,
        rank=rank,
        score=80.0 - rank,
        confidence=confidence,
        evidence=_evidence(),
    )


def _ambiguous() -> PlaceMatchResult:
    return PlaceMatchResult(
        status=MatchStatus.AMBIGUOUS,
        candidates=(
            _candidate(
                "garden-seaworld",
                branch_name="海上世界店",
                district="南山区",
                business_area="海上世界",
                address="太子路118号，近海上世界文化艺术中心",
            ),
            _candidate(
                "garden-mixc",
                branch_name="万象天地店",
                district="南山区",
                business_area="高新园",
                address="深南大道9668号万象天地",
                rank=2,
            ),
        ),
    )


async def _record_candidates(
    api: object,
    *,
    item_id: str,
    source_id: str,
    version: int,
    result: PlaceMatchResult,
) -> None:
    database = api.state.demo_database  # type: ignore[attr-defined]
    async with database.session_factory() as read_session:
        user_id = await read_session.scalar(
            select(CollectionItemModel.user_id).where(CollectionItemModel.id == item_id)
        )
        assert user_id is not None
    async with database.session_factory() as write_session:
        await PlaceTargetSelectionService(session=write_session).record_candidates(
            user_id=user_id,
            collection_item_id=item_id,
            source_id=source_id,
            match_result=result,
            queried_at=datetime.now(UTC),
            expected_version=version,
        )


@pytest.mark.asyncio
async def test_search_combined_filters_stable_pages_and_city_groups(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [
            _response(_place(title="一尺花园", city_hint="深圳", district="南山区")),
            _response(_place(title="广州塔咖啡", city_hint="广州", district="海珠区")),
            _response(_place(title="城市未知书店", city_hint=None, district="南山区")),
            _response(_event(title="上海设计展", city_hint="上海")),
        ]
    )
    async with _client(test_settings, provider) as (api, client):
        session_id = await _demo(client)
        shenzhen = await _submit(
            client, session_id, key="m14-list-1", content="一尺花园"
        )
        guangzhou = await _submit(
            client, session_id, key="m14-list-2", content="广州塔咖啡"
        )
        await _submit(client, session_id, key="m14-list-3", content="城市未知书店")
        await _submit(client, session_id, key="m14-list-4", content="上海设计展")
        for response, result in (
            (
                shenzhen,
                PlaceMatchResult(
                    status=MatchStatus.MATCHED,
                    candidates=(
                        _candidate(
                            "garden-unique",
                            branch_name="南山店",
                            district="南山区",
                            business_area="海上世界",
                            address="太子路118号",
                            confidence=MatchConfidence.HIGH,
                        ),
                    ),
                ),
            ),
            (
                guangzhou,
                PlaceMatchResult(
                    status=MatchStatus.MATCHED,
                    candidates=(
                        _candidate(
                            "gz-cafe",
                            city_code="guangzhou",
                            branch_name="广州塔店",
                            district="海珠区",
                            business_area="珠江新城",
                            address="阅江西路222号",
                            confidence=MatchConfidence.HIGH,
                        ),
                    ),
                ),
            ),
        ):
            payload = response.json()
            await _record_candidates(
                api,
                item_id=payload["collections"][0]["id"],
                source_id=payload["source_id"],
                version=payload["collections"][0]["version"],
                result=result,
            )

        searched = await client.get(
            "/api/v1/collections",
            params={"search": "花园", "city_group": "shenzhen", "kind": "place"},
        )
        other = await client.get(
            "/api/v1/collections", params={"city_group": "other"}
        )
        pending = await client.get(
            "/api/v1/collections",
            params={"city_group": "pending", "kind": "place"},
        )
        first = await client.get(
            "/api/v1/collections",
            params={"sort": "created_at", "page_size": 2, "page": 1},
        )
        second = await client.get(
            "/api/v1/collections",
            params={"sort": "created_at", "page_size": 2, "page": 2},
        )
        beyond = await client.get(
            "/api/v1/collections", params={"page": 99, "page_size": 2}
        )
        invalid = await client.get(
            "/api/v1/collections", params={"city_group": "invalid"}
        )
        conflicting = await client.get(
            "/api/v1/collections",
            params={"city_code": "shenzhen", "city_group": "pending"},
        )

    assert searched.status_code == other.status_code == pending.status_code == 200
    assert [item["title"] for item in searched.json()["items"]] == ["一尺花园（南山店）"]
    assert [item["formal_city_code"] for item in other.json()["items"]] == [
        "guangzhou"
    ]
    assert [item["city_group"] for item in other.json()["items"]] == ["other"]
    assert {item["title"] for item in pending.json()["items"]} == {"城市未知书店"}
    page_ids = [
        *(item["id"] for item in first.json()["items"]),
        *(item["id"] for item in second.json()["items"]),
    ]
    assert len(page_ids) == len(set(page_ids)) == 4
    assert beyond.json()["items"] == [] and beyond.json()["total"] == 4
    assert invalid.status_code == 422
    assert conflicting.status_code == 422


@pytest.mark.asyncio
async def test_detail_candidates_selection_none_replay_and_stale_version(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [
            _response(_place(title="一尺花园", city_hint="深圳")),
            _response(_place(title="另一家一尺花园", city_hint="深圳")),
        ]
    )
    async with _client(test_settings, provider) as (api, client):
        session_id = await _demo(client)
        first = await _submit(client, session_id, key="m14-choice-1", content="一尺花园")
        second = await _submit(
            client, session_id, key="m14-choice-2", content="另一家一尺花园"
        )
        for response in (first, second):
            payload = response.json()
            await _record_candidates(
                api,
                item_id=payload["collections"][0]["id"],
                source_id=payload["source_id"],
                version=payload["collections"][0]["version"],
                result=_ambiguous(),
            )

        item_id = first.json()["collections"][0]["id"]
        detail = await client.get(f"/api/v1/collections/{item_id}")
        candidates = await client.get(
            f"/api/v1/collections/{item_id}/poi-candidates"
        )
        choice_payload = {
            "expected_version": candidates.json()["expected_version"],
            "snapshot_fingerprint": candidates.json()["snapshot_fingerprint"],
            "idempotency_key": "m14-select-exact",
            "choice": "candidate",
            "provider": "amap",
            "poi_id": "garden-seaworld",
        }
        selected = await client.post(
            f"/api/v1/collections/{item_id}/poi-selection", json=choice_payload
        )
        replayed = await client.post(
            f"/api/v1/collections/{item_id}/poi-selection", json=choice_payload
        )
        stale = await client.post(
            f"/api/v1/collections/{item_id}/poi-selection",
            json={
                **choice_payload,
                "idempotency_key": "m14-stale",
                "poi_id": "garden-mixc",
            },
        )

        other_id = second.json()["collections"][0]["id"]
        other_candidates = await client.get(
            f"/api/v1/collections/{other_id}/poi-candidates"
        )
        none = await client.post(
            f"/api/v1/collections/{other_id}/poi-selection",
            json={
                "expected_version": other_candidates.json()["expected_version"],
                "snapshot_fingerprint": other_candidates.json()[
                    "snapshot_fingerprint"
                ],
                "idempotency_key": "m14-none",
                "choice": "none_of_above",
                "provider": None,
                "poi_id": None,
            },
        )

    assert detail.status_code == candidates.status_code == 200
    assert "place_target" not in detail.text
    assert "place_candidate_snapshot" not in detail.text
    assert len(candidates.json()["candidates"]) == 2
    assert candidates.json()["candidates"][0] == {
        "provider": "amap",
        "poi_id": "garden-seaworld",
        "name": "一尺花园",
        "branch_name": "海上世界店",
        "city_code": "shenzhen",
        "district": "南山区",
        "business_area": "海上世界",
        "address": "太子路118号，近海上世界文化艺术中心",
        "poi_type": "cafe",
        "matching_clues": [],
    }
    assert "coordinate" not in candidates.text and "evidence" not in candidates.text
    assert selected.status_code == 200, selected.text
    assert selected.json()["items"][0]["status"] == "active"
    assert selected.json()["items"][0]["formal_city_code"] == "shenzhen"
    assert replayed.status_code == 200 and replayed.json()["replayed"] is True
    assert stale.status_code == 409
    assert none.status_code == 200
    assert none.json()["items"][0]["status"] == "pending_details"


@pytest.mark.asyncio
async def test_collection_detail_candidates_and_sources_are_cross_user_invisible(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response(_place(title="私有地点", city_hint="深圳"))])
    async with _client(test_settings, provider) as (api, owner):
        session_id = await _demo(owner)
        created = await _submit(owner, session_id, key="m14-private", content="私有地点")
        payload = created.json()
        item_id = payload["collections"][0]["id"]
        await _record_candidates(
            api,
            item_id=item_id,
            source_id=payload["source_id"],
            version=payload["collections"][0]["version"],
            result=_ambiguous(),
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://test",
        ) as stranger:
            stranger_session = await stranger.post("/api/v1/demo/sessions")
            stranger.headers["X-CSRF-Token"] = stranger_session.json()["csrf_token"]
            listing = await stranger.get("/api/v1/collections")
            detail = await stranger.get(f"/api/v1/collections/{item_id}")
            candidates = await stranger.get(
                f"/api/v1/collections/{item_id}/poi-candidates"
            )
            patch = await stranger.patch(
                f"/api/v1/collections/{item_id}",
                json={"expected_version": 2, "changes": {"title": "越权"}},
            )
            delete = await stranger.delete(f"/api/v1/collections/{item_id}")

    assert listing.json()["items"] == []
    assert detail.status_code == candidates.status_code == 404
    assert patch.status_code == delete.status_code == 404
    combined = detail.text + candidates.text + patch.text + delete.text
    assert payload["source_id"] not in combined


@pytest.mark.asyncio
async def test_patch_accepts_json_tag_arrays_atomically_and_keeps_strict_edges(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [_response(_place(title="原始标题", city_hint="深圳", tags=("旧标签",)))]
    )
    async with _client(test_settings, provider) as (api, owner):
        session_id = await _demo(owner)
        created = await _submit(
            owner,
            session_id,
            key="m14-patch-tags",
            content="带标签的收藏",
        )
        original = created.json()["collections"][0]
        item_id = original["id"]
        changed = await owner.patch(
            f"/api/v1/collections/{item_id}",
            json={
                "expected_version": original["version"],
                "changes": {
                    "title": "海边夜景",
                    "city_hint": "深圳",
                    "district": "南山区",
                    "address": "深圳湾公园",
                    "tags": ["海边", "夜景"],
                },
            },
        )
        detail = await owner.get(f"/api/v1/collections/{item_id}")
        listing = await owner.get("/api/v1/collections")
        invalid_responses = [
            await owner.patch(
                f"/api/v1/collections/{item_id}",
                json={
                    "expected_version": changed.json()["version"],
                    "changes": {"title": "不应保存", "tags": invalid_tags},
                },
            )
            for invalid_tags in (
                "海边",
                ["海边", 7],
                {"unexpected": "shape"},
            )
        ]
        after_invalid = await owner.get(f"/api/v1/collections/{item_id}")
        stale = await owner.patch(
            f"/api/v1/collections/{item_id}",
            json={
                "expected_version": original["version"],
                "changes": {"tags": []},
            },
        )
        cleared = await owner.patch(
            f"/api/v1/collections/{item_id}",
            json={
                "expected_version": changed.json()["version"],
                "changes": {"tags": []},
            },
        )
        cleared_detail = await owner.get(f"/api/v1/collections/{item_id}")
        cleared_listing = await owner.get("/api/v1/collections")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://test",
        ) as stranger:
            stranger_session = await stranger.post("/api/v1/demo/sessions")
            stranger.headers["X-CSRF-Token"] = stranger_session.json()["csrf_token"]
            foreign_patch = await stranger.patch(
                f"/api/v1/collections/{item_id}",
                json={
                    "expected_version": cleared.json()["version"],
                    "changes": {"tags": ["越权"]},
                },
            )

    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == original["version"] + 1
    expected_fields = {
        "title": "海边夜景",
        "city_hint": "深圳",
        "district": "南山区",
        "address": "深圳湾公园",
        "tags": ["海边", "夜景"],
    }
    for field, expected in expected_fields.items():
        assert changed.json()[field] == expected
        assert detail.json()["item"][field] == expected
        assert listing.json()["items"][0][field] == expected
    assert all(response.status_code == 422 for response in invalid_responses)
    assert after_invalid.json()["item"]["title"] == "海边夜景"
    assert after_invalid.json()["item"]["version"] == changed.json()["version"]
    assert stale.status_code == 409
    assert cleared.status_code == 200
    assert cleared.json()["tags"] == []
    assert cleared.json()["version"] == changed.json()["version"] + 1
    assert cleared_detail.json()["item"]["tags"] == []
    assert cleared_listing.json()["items"][0]["tags"] == []
    assert foreign_patch.status_code == 404


@pytest.mark.asyncio
async def test_expected_version_conflict_delete_restore_and_agent_shared_read(
    test_settings: Settings,
) -> None:
    provider = FakeProvider([_response(_place(title="共享数据", city_hint="深圳"))])
    async with _client(test_settings, provider) as (_api, client):
        session_id = await _demo(client)
        created = await _submit(client, session_id, key="m14-shared", content="共享数据")
        payload = created.json()
        item = payload["collections"][0]
        requests = (
            client.patch(
                f"/api/v1/collections/{item['id']}",
                json={"expected_version": item["version"], "changes": {"title": "客户端 A"}},
            ),
            client.patch(
                f"/api/v1/collections/{item['id']}",
                json={"expected_version": item["version"], "changes": {"title": "客户端 B"}},
            ),
        )
        first, second = await asyncio.gather(*requests)
        winner = first if first.status_code == 200 else second
        loser = second if first.status_code == 200 else first
        agent = await client.get(
            f"/api/v1/agent-runs/{payload['trace_id']}/result"
        )
        deleted = await client.delete(
            f"/api/v1/collections/{item['id']}",
            params={"expected_version": winner.json()["version"]},
        )
        repeated_delete = await client.delete(f"/api/v1/collections/{item['id']}")
        restored = await client.post(f"/api/v1/collections/{item['id']}/restore")
        repeated_restore = await client.post(
            f"/api/v1/collections/{item['id']}/restore"
        )

    assert {first.status_code, second.status_code} == {200, 409}
    assert loser.json()["error_code"] == "VERSION_CONFLICT"
    assert agent.json()["collections"][0]["title"] == winner.json()["title"]
    assert deleted.json()["status"] == repeated_delete.json()["status"] == "deleted"
    assert restored.json()["status"] == "pending_details"
    assert repeated_restore.status_code == 200
    public_text = agent.text + winner.text
    for forbidden in ("csrf", "cookie", "authorization", "provider_response"):
        assert forbidden not in public_text.casefold()


@pytest.mark.asyncio
async def test_pending_and_other_city_items_are_explicitly_ineligible_for_shenzhen(
    test_settings: Settings,
) -> None:
    provider = FakeProvider(
        [
            _response(_place(title="待确认地点", city_hint=None)),
            _response(_place(title="广州地点", city_hint="广州", district="海珠区")),
        ]
    )
    async with _client(test_settings, provider) as (api, client):
        session_id = await _demo(client)
        pending = await _submit(
            client, session_id, key="m14-plan-pending", content="待确认地点"
        )
        other = await _submit(
            client, session_id, key="m14-plan-other", content="广州地点"
        )
        other_payload = other.json()
        await _record_candidates(
            api,
            item_id=other_payload["collections"][0]["id"],
            source_id=other_payload["source_id"],
            version=other_payload["collections"][0]["version"],
            result=PlaceMatchResult(
                status=MatchStatus.MATCHED,
                candidates=(
                    _candidate(
                        "guangzhou-place",
                        city_code="guangzhou",
                        branch_name="海珠店",
                        district="海珠区",
                        business_area="广州塔",
                        address="阅江西路",
                        confidence=MatchConfidence.HIGH,
                    ),
                ),
            ),
        )
        listing = await client.get("/api/v1/collections")

    by_title = {item["title"]: item for item in listing.json()["items"]}
    pending_item = by_title[pending.json()["collections"][0]["title"]]
    other_item = by_title["一尺花园（海珠店）"]
    assert pending_item["planning_eligible"] is False
    assert pending_item["planning_exclusion_reason"] == "location_unconfirmed"
    assert other_item["formal_city_code"] == "guangzhou"
    assert other_item["planning_eligible"] is False
    assert other_item["planning_exclusion_reason"] == "other_city"

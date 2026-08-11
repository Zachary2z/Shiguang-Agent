"""Selected-option adjustments use the sole model proposal boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.application.plan_proposals import PlanProposalError, PlanProposalService
from app.domain.collections import CollectionKind, PlanCity
from app.domain.places import TransportMode
from app.domain.plans import (
    ActivityArea,
    PlanConstraints,
    PlanPace,
    PlanProposalCandidate,
    PlanProposalItem,
)
from nanobot_core.providers import StructuredOutputMode
from tests.core.fakes import FakeProvider, fake_response

NOW = datetime(2026, 8, 11, 2, tzinfo=UTC)


def _constraints() -> PlanConstraints:
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=datetime(2026, 8, 12, 6, tzinfo=UTC),
        end_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        area=ActivityArea(districts=("南山区",)),
        pace=PlanPace.BALANCED,
        transport_modes=(TransportMode.WALKING,),
        include=("咖啡",),
        exclude=("商场",),
        selected_collection_item_ids=("col_0123456789abcdef0123456789abcdef",),
        required_collection_item_ids=("col_0123456789abcdef0123456789abcdef",),
        collection_only=True,
        created_at=NOW,
        expires_at=NOW + timedelta(days=2),
    )


def _candidates() -> tuple[PlanProposalCandidate, ...]:
    return (
        PlanProposalCandidate(
            candidate_key="museum", title="美术馆", kind=CollectionKind.PLACE, required=True
        ),
        PlanProposalCandidate(
            candidate_key="coffee", title="咖啡店", kind=CollectionKind.PLACE
        ),
        PlanProposalCandidate(
            candidate_key="park", title="公园", kind=CollectionKind.PLACE
        ),
    )


def _base() -> tuple[PlanProposalItem, ...]:
    return (
        PlanProposalItem(candidate_key="museum", visit_duration_seconds=3600),
        PlanProposalItem(candidate_key="coffee", visit_duration_seconds=1800),
    )


async def _adjust(content: str):
    provider = FakeProvider([fake_response(content=content)])
    result = await PlanProposalService(
        provider, structured_output_mode=StructuredOutputMode.JSON_SCHEMA
    ).adjust(
        instruction="只修改我说的部分",
        constraints=_constraints(),
        base_items=_base(),
        candidates=_candidates(),
        now=NOW,
    )
    return (*result, provider)


@pytest.mark.asyncio
async def test_add_preserves_all_existing_places() -> None:
    proposals, constraints, summary, provider = await _adjust(
        '{"actions":[{"kind":"add","candidate_key":"park",'
        '"after_candidate_key":"coffee","visit_duration_seconds":2400}],'
        '"change_summary":"新增公园，保留原地点"}'
    )

    assert [item.candidate_key for item in proposals.options[0].items] == [
        "museum",
        "coffee",
        "park",
    ]
    assert constraints == _constraints()
    assert summary == "新增公园，保留原地点"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actions", "expected", "durations"),
    [
        ('[{"kind":"remove","target_candidate_key":"coffee"}]', ["museum"], [3600]),
        (
            '[{"kind":"replace","target_candidate_key":"coffee",'
            '"candidate_key":"park","visit_duration_seconds":2400}]',
            ["museum", "park"],
            [3600, 2400],
        ),
        (
            '[{"kind":"reorder","candidate_keys":["coffee","museum"]}]',
            ["coffee", "museum"],
            [1800, 3600],
        ),
        (
            '[{"kind":"change_duration","target_candidate_key":"coffee",'
            '"visit_duration_seconds":3600}]',
            ["museum", "coffee"],
            [3600, 3600],
        ),
    ],
)
async def test_each_explicit_action_only_changes_the_selected_option(
    actions: str, expected: list[str], durations: list[int]
) -> None:
    proposals, _, _, _ = await _adjust(
        f'{{"actions":{actions},"change_summary":"按要求调整"}}'
    )

    assert [item.candidate_key for item in proposals.options[0].items] == expected
    assert [item.visit_duration_seconds for item in proposals.options[0].items] == durations
    assert len(proposals.options) == 1


@pytest.mark.asyncio
async def test_constraint_change_preserves_private_collection_ids() -> None:
    _, constraints, _, provider = await _adjust(
        '{"constraint_changes":{"pace":"relaxed","collection_only":false},'
        '"change_summary":"节奏放松"}'
    )

    assert constraints.pace is PlanPace.RELAXED
    assert constraints.collection_only is False
    assert constraints.required_collection_item_ids == _constraints().required_collection_item_ids
    request = str(provider.calls[0].messages)
    assert "required_collection_item_ids" not in request
    assert "selected_collection_item_ids" not in request


@pytest.mark.asyncio
async def test_required_candidate_cannot_be_removed() -> None:
    with pytest.raises(PlanProposalError):
        await _adjust(
            '{"actions":[{"kind":"remove","target_candidate_key":"museum"}],'
            '"change_summary":"删除美术馆"}'
        )


@pytest.mark.asyncio
async def test_empty_or_unknown_adjustment_has_no_rule_fallback() -> None:
    with pytest.raises(PlanProposalError):
        await _adjust('{"actions":[],"change_summary":"不明确"}')

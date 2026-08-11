"""One model call proposes three plans without scheduling or external work."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from app.application.plan_proposals import (
    PlanProposalError,
    PlanProposalService,
)
from app.domain.collections import CollectionKind, PlanCity
from app.domain.places import TransportMode
from app.domain.plans import (
    ActivityArea,
    PlanConstraints,
    PlanOptionRole,
    PlanProposalCandidate,
)
from nanobot_core.providers import StructuredOutputMode, ToolCall
from tests.core.fakes import FakeProvider, fake_response

NOW = datetime(2026, 8, 11, 2, tzinfo=UTC)


def _constraints() -> PlanConstraints:
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=datetime(2026, 8, 12, 6, tzinfo=UTC),
        end_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        area=ActivityArea(districts=("南山区",)),
        transport_modes=(TransportMode.WALKING, TransportMode.TRANSIT),
        include=("看展", "喝咖啡"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=2),
    )


def _candidates() -> tuple[PlanProposalCandidate, ...]:
    return (
        PlanProposalCandidate(
            candidate_key="candidate_exhibit",
            title="当代艺术展",
            kind=CollectionKind.EVENT,
            district="南山区",
            tags=("展览",),
            required=True,
        ),
        PlanProposalCandidate(
            candidate_key="candidate_coffee",
            title="海边咖啡店",
            kind=CollectionKind.PLACE,
            district="南山区",
            tags=("咖啡", "安静"),
            preferred=True,
        ),
        PlanProposalCandidate(
            candidate_key="candidate_park",
            title="海滨公园",
            kind=CollectionKind.PLACE,
            district="南山区",
            tags=("散步",),
        ),
    )


def _proposal_json() -> str:
    return """{
      "options": [
        {"role":"main","items":[
          {"candidate_key":"candidate_exhibit","visit_duration_seconds":5400},
          {"candidate_key":"candidate_coffee","visit_duration_seconds":2700}
        ],"reason":"最符合看展后喝咖啡的原始要求"},
        {"role":"alternative","items":[
          {"candidate_key":"candidate_exhibit","visit_duration_seconds":4800},
          {"candidate_key":"candidate_park","visit_duration_seconds":3600}
        ],"reason":"展览后增加散步"},
        {"role":"alternative","items":[
          {"candidate_key":"candidate_coffee","visit_duration_seconds":2400},
          {"candidate_key":"candidate_exhibit","visit_duration_seconds":6000}
        ],"reason":"先休息再看展"}
      ]
    }"""


async def _propose(content: str):
    provider = FakeProvider([fake_response(content=content)])
    result = await PlanProposalService(
        provider,
        structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
    ).propose(
        request="明天下午想看展、喝咖啡，轻松一点",
        constraints=_constraints(),
        candidates=_candidates(),
        now=NOW,
    )
    return result, provider


@pytest.mark.asyncio
async def test_initial_generation_returns_exactly_three_role_ordered_options() -> None:
    result, provider = await _propose(_proposal_json())

    assert len(result.options) == 3
    assert tuple(option.role for option in result.options) == (
        PlanOptionRole.MAIN,
        PlanOptionRole.ALTERNATIVE,
        PlanOptionRole.ALTERNATIVE,
    )
    assert len(provider.calls) == 1
    assert provider.calls[0].tools is None
    assert provider.calls[0].response_format is not None
    assert provider.calls[0].response_format.mode is StructuredOutputMode.JSON_SCHEMA
    payload = json.loads(provider.calls[0].messages[1]["content"])
    assert payload["constraints"]["include"] == ["看展", "喝咖啡"]


@pytest.mark.asyncio
async def test_unknown_candidate_key_is_rejected() -> None:
    with pytest.raises(PlanProposalError):
        await _propose(_proposal_json().replace("candidate_park", "candidate_unknown"))


@pytest.mark.asyncio
async def test_required_candidate_cannot_be_silently_omitted() -> None:
    with pytest.raises(PlanProposalError):
        await _propose(_proposal_json().replace("candidate_exhibit", "candidate_park"))


@pytest.mark.asyncio
async def test_visit_duration_must_be_positive() -> None:
    with pytest.raises(PlanProposalError):
        await _propose(_proposal_json().replace("5400", "0", 1))


@pytest.mark.asyncio
async def test_three_identical_options_are_rejected() -> None:
    identical = """{"options":[
      {"role":"main","items":[{"candidate_key":"candidate_exhibit","visit_duration_seconds":3600}],"reason":"A"},
      {"role":"alternative","items":[{"candidate_key":"candidate_exhibit","visit_duration_seconds":3600}],"reason":"B"},
      {"role":"alternative","items":[{"candidate_key":"candidate_exhibit","visit_duration_seconds":3600}],"reason":"C"}
    ]}"""

    with pytest.raises(PlanProposalError):
        await _propose(identical)


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not-json", "{}", "[]"])
async def test_invalid_json_or_shape_fails_safely(content: str) -> None:
    with pytest.raises(PlanProposalError) as captured:
        await _propose(content)

    assert str(captured.value) == "The model plan proposal is invalid."


@pytest.mark.asyncio
async def test_tool_call_response_fails_safely() -> None:
    provider = FakeProvider(
        [
            fake_response(
                tool_calls=(ToolCall(id="call-1", name="other", arguments={}),)
            )
        ]
    )

    with pytest.raises(PlanProposalError):
        await PlanProposalService(
            provider,
            structured_output_mode=StructuredOutputMode.JSON_OBJECT,
        ).propose(
            request="帮我安排",
            constraints=_constraints(),
            candidates=_candidates(),
            now=NOW,
        )

    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_inputs_are_not_modified_and_request_is_desensitized() -> None:
    constraints = _constraints()
    candidates = _candidates()
    before_constraints = deepcopy(constraints)
    before_candidates = deepcopy(candidates)
    provider = FakeProvider([fake_response(content=_proposal_json())])

    await PlanProposalService(
        provider,
        structured_output_mode=StructuredOutputMode.JSON_OBJECT,
    ).propose(
        request="  帮我安排一下  ",
        constraints=constraints,
        candidates=candidates,
        now=NOW,
    )
    request_text = str(provider.calls[0].messages[-1])

    assert constraints == before_constraints
    assert candidates == before_candidates
    assert "selected_collection_item_ids" not in request_text
    assert "created_at" not in request_text
    assert "expires_at" not in request_text
    assert "coordinate" not in request_text


@pytest.mark.asyncio
async def test_cancelled_error_object_propagates() -> None:
    cancelled = asyncio.CancelledError("cancel-now")
    provider = FakeProvider([cancelled])

    with pytest.raises(asyncio.CancelledError) as captured:
        await PlanProposalService(
            provider,
            structured_output_mode=None,
        ).propose(
            request="帮我安排",
            constraints=_constraints(),
            candidates=_candidates(),
            now=NOW,
        )

    assert captured.value is cancelled
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_failure_and_repr_do_not_expose_candidate_input_or_configuration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "complete-private-candidate-description"
    candidates = _candidates() + (
        PlanProposalCandidate(
            candidate_key="candidate_private",
            title=secret,
            kind=CollectionKind.PLACE,
        ),
    )
    provider = FakeProvider([fake_response(content="invalid")])
    service = PlanProposalService(
        provider,
        structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
    )

    with pytest.raises(PlanProposalError) as captured:
        await service.propose(
            request="帮我安排",
            constraints=_constraints(),
            candidates=candidates,
            now=NOW,
        )

    assert secret not in repr(candidates[-1])
    assert secret not in repr(service)
    assert secret not in repr(captured.value)
    assert secret not in caplog.text
    assert "json_schema" not in repr(service)

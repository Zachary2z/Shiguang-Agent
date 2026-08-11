"""The sole model boundary for initial plan-option proposals."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime

from pydantic import ValidationError

from app.application.extraction_output import (
    MAX_MODEL_OUTPUT_CHARS,
    structured_response_format,
)
from app.domain.plans import (
    PlanAdjustmentActionKind,
    PlanAdjustmentProposal,
    PlanConstraintChanges,
    PlanConstraints,
    PlanOptionProposal,
    PlanOptionRole,
    PlanPaceSource,
    PlanProposalCandidate,
    PlanProposalItem,
    PlanProposalSet,
    plan_constraint_expires_at,
    plan_constraints_internal_dump,
)
from app.domain.time import ASIA_SHANGHAI, require_aware_utc
from nanobot_core.providers import Message, ModelProvider, ModelResponse, StructuredOutputMode


class PlanProposalError(ValueError):
    """A fixed failure that never retains model input or provider details."""

    __slots__ = ()
    code = "INVALID_PLAN_PROPOSAL"
    summary = "The model plan proposal is invalid."

    def __init__(self) -> None:
        super().__init__(self.summary)


_SCHEMA = PlanProposalSet.model_json_schema()
_ADJUSTMENT_SCHEMA = PlanAdjustmentProposal.model_json_schema()
_SYSTEM_PROMPT = (
    "Propose exactly three Shiguang plan options as JSON matching the schema below. "
    "The first option must be role main and best match the user's original request "
    "and pace; the next two must be role alternative without fixed styles. Choose "
    "candidate combinations, order, and positive suggested visit durations. Every "
    "required candidate must appear in every option; preferred candidates have priority "
    "but are not mandatory. Reference only supplied candidate_key values. Describe a "
    "necessary missing external step only in external_gap_description and classify its "
    "external_gap_kind as place or event. Never create or "
    "guess collections, POIs, database IDs, coordinates, routes, distances, prices, "
    "weather, opening hours, Event time facts, or provider internals. Schema:\n"
    + json.dumps(_SCHEMA, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
)
_ADJUSTMENT_SYSTEM_PROMPT = (
    "Adjust exactly one selected Shiguang option as JSON matching the schema below. "
    "Return only the smallest explicit actions requested: add, remove, replace, reorder, "
    "or change_duration, plus only explicitly changed constraints. Candidate keys not "
    "touched by an action must stay in the option. An add action inserts after "
    "after_candidate_key, or appends when it is null. Reorder must list every current "
    "candidate exactly once. Never silently remove a required candidate. Reference only "
    "supplied candidate_key values. The timezone is Asia/Shanghai; output aware ISO-8601 "
    "times with +08:00 unless the user explicitly says UTC. An area change uses districts "
    "or labels and never coordinates. Never invent collections, POIs, routes, distances, "
    "prices, weather, opening hours, Event facts, provider data, or unchanged constraints. "
    "Summarize the actual requested changes without private data. Schema:\n"
    + json.dumps(
        _ADJUSTMENT_SCHEMA,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
)


class PlanProposalService:
    """Make one structured provider call and validate its proposal without repair."""

    __slots__ = ("_provider", "_response_format", "_structured_output_mode")

    def __init__(
        self,
        provider: ModelProvider,
        *,
        structured_output_mode: StructuredOutputMode | None,
    ) -> None:
        self._provider = provider
        self._structured_output_mode = structured_output_mode
        self._response_format = structured_response_format(
            structured_output_mode,
            schema_name="plan_proposal_set",
            json_schema=_SCHEMA,
        )

    async def propose(
        self,
        *,
        request: str,
        constraints: PlanConstraints,
        candidates: tuple[PlanProposalCandidate, ...],
        now: datetime,
    ) -> PlanProposalSet:
        normalized_request = " ".join(request.split())
        keys = tuple(candidate.candidate_key for candidate in candidates)
        if (
            not normalized_request
            or len(normalized_request) > 4000
            or not candidates
            or len(set(keys)) != len(keys)
        ):
            raise PlanProposalError

        messages: list[Message] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "original_request": normalized_request,
                        "constraints": constraints.model_dump(
                            mode="json",
                            exclude={
                                "created_at",
                                "expires_at",
                                "selected_collection_item_ids",
                                "required_collection_item_ids",
                            },
                        ),
                        "current_time": require_aware_utc(now)
                        .astimezone(ASIA_SHANGHAI)
                        .isoformat(),
                        "candidates": [
                            candidate.model_dump(mode="json") for candidate in candidates
                        ],
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]
        response = await self._provider.chat(
            messages=deepcopy(messages),
            tools=None,
            response_format=self._response_format,
        )
        if (
            response.tool_calls
            or not isinstance(response.content, str)
            or not response.content.strip()
            or len(response.content) > MAX_MODEL_OUTPUT_CHARS
        ):
            raise PlanProposalError
        try:
            proposal = PlanProposalSet.model_validate_json(response.content)
        except (ValidationError, TypeError, ValueError):
            raise PlanProposalError from None
        if len(proposal.options) != 3:
            raise PlanProposalError

        allowed_keys = set(keys)
        required_keys = {candidate.candidate_key for candidate in candidates if candidate.required}
        if any(
            not {item.candidate_key for item in option.items}.issubset(allowed_keys)
            or not required_keys.issubset({item.candidate_key for item in option.items})
            for option in proposal.options
        ):
            raise PlanProposalError
        return proposal

    async def adjust(
        self,
        *,
        instruction: str,
        constraints: PlanConstraints,
        base_items: tuple[PlanProposalItem, ...],
        candidates: tuple[PlanProposalCandidate, ...],
        now: datetime,
        response_observer: Callable[[ModelResponse], None] | None = None,
    ) -> tuple[PlanProposalSet, PlanConstraints, str]:
        """Apply one model-produced action set to the selected option only."""

        normalized = " ".join(instruction.split())
        keys = tuple(candidate.candidate_key for candidate in candidates)
        if (
            not normalized
            or len(normalized) > 1000
            or not base_items
            or not candidates
            or len(set(keys)) != len(keys)
            or not {item.candidate_key for item in base_items}.issubset(keys)
        ):
            raise PlanProposalError
        response_format = structured_response_format(
            self._structured_output_mode,
            schema_name="plan_adjustment_proposal",
            json_schema=_ADJUSTMENT_SCHEMA,
        )
        response = await self._provider.chat(
            messages=[
                {"role": "system", "content": _ADJUSTMENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": normalized,
                            "timezone": ASIA_SHANGHAI.key,
                            "current_time": require_aware_utc(now)
                            .astimezone(ASIA_SHANGHAI)
                            .isoformat(),
                            "current_constraints": constraints.model_dump(
                                mode="json",
                                exclude={
                                    "created_at",
                                    "expires_at",
                                    "origin",
                                    "original_request",
                                    "selected_collection_item_ids",
                                    "required_collection_item_ids",
                                },
                            ),
                            "selected_option": [
                                item.model_dump(mode="json") for item in base_items
                            ],
                            "candidates": [
                                candidate.model_dump(mode="json") for candidate in candidates
                            ],
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            tools=None,
            response_format=response_format,
        )
        if response_observer is not None:
            response_observer(response)
        if (
            response.tool_calls
            or not isinstance(response.content, str)
            or not response.content.strip()
            or len(response.content) > MAX_MODEL_OUTPUT_CHARS
        ):
            raise PlanProposalError
        try:
            adjustment = PlanAdjustmentProposal.model_validate_json(response.content)
            items = _apply_actions(base_items, adjustment, allowed_keys=set(keys))
            adjusted_constraints = _apply_constraint_changes(
                constraints,
                adjustment.constraint_changes,
            )
        except (ValidationError, TypeError, ValueError):
            raise PlanProposalError from None
        required = {candidate.candidate_key for candidate in candidates if candidate.required}
        if not required.issubset(item.candidate_key for item in items):
            raise PlanProposalError
        return (
            PlanProposalSet(
                options=(
                    PlanOptionProposal(
                        role=PlanOptionRole.MAIN,
                        items=items,
                        reason=adjustment.change_summary[:240],
                    ),
                )
            ),
            adjusted_constraints,
            adjustment.change_summary,
        )


def _apply_actions(
    base_items: tuple[PlanProposalItem, ...],
    adjustment: PlanAdjustmentProposal,
    *,
    allowed_keys: set[str],
) -> tuple[PlanProposalItem, ...]:
    items = list(base_items)
    for action in adjustment.actions:
        positions = {item.candidate_key: index for index, item in enumerate(items)}
        if action.kind is PlanAdjustmentActionKind.ADD:
            assert action.candidate_key is not None
            assert action.visit_duration_seconds is not None
            if action.candidate_key not in allowed_keys or action.candidate_key in positions:
                raise ValueError("invalid add candidate")
            index = len(items)
            if action.after_candidate_key is not None:
                if action.after_candidate_key not in positions:
                    raise ValueError("invalid add position")
                index = positions[action.after_candidate_key] + 1
            items.insert(
                index,
                PlanProposalItem(
                    candidate_key=action.candidate_key,
                    visit_duration_seconds=action.visit_duration_seconds,
                ),
            )
        elif action.kind is PlanAdjustmentActionKind.REMOVE:
            assert action.target_candidate_key is not None
            if action.target_candidate_key not in positions:
                raise ValueError("invalid remove candidate")
            items.pop(positions[action.target_candidate_key])
        elif action.kind is PlanAdjustmentActionKind.REPLACE:
            assert action.target_candidate_key is not None
            assert action.candidate_key is not None
            assert action.visit_duration_seconds is not None
            if (
                action.target_candidate_key not in positions
                or action.candidate_key not in allowed_keys
                or action.candidate_key in positions
            ):
                raise ValueError("invalid replacement")
            items[positions[action.target_candidate_key]] = PlanProposalItem(
                candidate_key=action.candidate_key,
                visit_duration_seconds=action.visit_duration_seconds,
            )
        elif action.kind is PlanAdjustmentActionKind.REORDER:
            if set(action.candidate_keys) != set(positions):
                raise ValueError("reorder must contain the current option")
            by_key = {item.candidate_key: item for item in items}
            items = [by_key[key] for key in action.candidate_keys]
        else:
            assert action.target_candidate_key is not None
            assert action.visit_duration_seconds is not None
            if action.target_candidate_key not in positions:
                raise ValueError("invalid duration candidate")
            index = positions[action.target_candidate_key]
            items[index] = items[index].model_copy(
                update={"visit_duration_seconds": action.visit_duration_seconds}
            )
    if not items:
        raise ValueError("an adjusted option cannot be empty")
    return tuple(items)


def _apply_constraint_changes(
    constraints: PlanConstraints,
    changes: PlanConstraintChanges | None,
) -> PlanConstraints:
    if changes is None:
        return constraints
    values = plan_constraints_internal_dump(constraints, mode="python")
    for field_name in changes.model_fields_set:
        if field_name == "collection_only" and constraints.selected_collection_item_ids:
            continue
        values[field_name] = getattr(changes, field_name)
    if "area" in changes.model_fields_set:
        values["origin"] = None
    if "pace" in changes.model_fields_set:
        values["pace_source"] = PlanPaceSource.USER_REQUEST
    values["expires_at"] = max(
        constraints.expires_at,
        plan_constraint_expires_at(
            now=constraints.created_at,
            start_at=values["start_at"],
            end_at=values["end_at"],
        ),
    )
    return PlanConstraints.model_validate(values)


__all__ = ["PlanProposalError", "PlanProposalService"]

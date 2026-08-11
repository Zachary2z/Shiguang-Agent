"""The sole model boundary for initial plan-option proposals."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime

from pydantic import ValidationError

from app.application.extraction_output import (
    MAX_MODEL_OUTPUT_CHARS,
    structured_response_format,
)
from app.domain.plans import (
    PlanConstraints,
    PlanProposalCandidate,
    PlanProposalSet,
)
from app.domain.time import ASIA_SHANGHAI, require_aware_utc
from nanobot_core.providers import Message, ModelProvider, StructuredOutputMode


class PlanProposalError(ValueError):
    """A fixed failure that never retains model input or provider details."""

    __slots__ = ()
    code = "INVALID_PLAN_PROPOSAL"
    summary = "The model plan proposal is invalid."

    def __init__(self) -> None:
        super().__init__(self.summary)


_SCHEMA = PlanProposalSet.model_json_schema()
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


class PlanProposalService:
    """Make one structured provider call and validate its proposal without repair."""

    __slots__ = ("_provider", "_response_format")

    def __init__(
        self,
        provider: ModelProvider,
        *,
        structured_output_mode: StructuredOutputMode | None,
    ) -> None:
        self._provider = provider
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

        allowed_keys = set(keys)
        required_keys = {candidate.candidate_key for candidate in candidates if candidate.required}
        if any(
            not {item.candidate_key for item in option.items}.issubset(allowed_keys)
            or not required_keys.issubset({item.candidate_key for item in option.items})
            for option in proposal.options
        ):
            raise PlanProposalError
        return proposal


__all__ = ["PlanProposalError", "PlanProposalService"]

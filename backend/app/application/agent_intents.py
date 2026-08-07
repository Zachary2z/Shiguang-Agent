"""One model boundary that routes Agent text into existing workflows."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.application.extraction_output import structured_response_format
from app.domain.collections import ExtractionResult, PlanCity
from app.domain.memories import MemoryType
from app.domain.places import TransportMode
from app.domain.plans import (
    ActivityArea,
    PlanConstraintInput,
    PlanPace,
    PlanPaceSource,
    plan_constraint_expires_at,
)
from nanobot_core.providers import ModelProvider, ModelResponse, StructuredOutputMode


class AgentIntentError(ValueError):
    code = "AGENT_INTENT_INVALID"


class _Intent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CollectionIntent(_Intent):
    intent: Literal["collect_content"]
    extraction: ExtractionResult


class PlanIntent(_Intent):
    intent: Literal["plan"]
    start_at: datetime | None = None
    end_at: datetime | None = None
    area: ActivityArea | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    pace: PlanPace | None = None
    transport_modes: tuple[TransportMode, ...] = ()
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    collection_only: bool = False

    def constraints(self, *, now: datetime) -> PlanConstraintInput:
        return PlanConstraintInput(
            city_code=PlanCity.SHENZHEN,
            start_at=self.start_at,
            end_at=self.end_at,
            area=self.area,
            budget=self.budget,
            pace=self.pace or PlanPace.BALANCED,
            pace_source=(
                PlanPaceSource.USER_REQUEST
                if self.pace is not None
                else PlanPaceSource.SYSTEM_DEFAULT
            ),
            transport_modes=self.transport_modes,
            include=self.include,
            exclude=self.exclude,
            collection_only=self.collection_only,
            created_at=now,
            expires_at=plan_constraint_expires_at(
                now=now,
                start_at=self.start_at,
                end_at=self.end_at,
            ),
        )


class MemoryIntent(_Intent):
    intent: Literal["memory"]
    authorization: Literal["explicit", "needs_confirmation"]
    type: MemoryType
    content: str = Field(min_length=1, max_length=500)
    value: str = Field(min_length=1, max_length=100)


class ClarifyIntent(_Intent):
    intent: Literal["clarify"]
    question: str = Field(min_length=1, max_length=200)


AgentIntent = Annotated[
    CollectionIntent | PlanIntent | MemoryIntent | ClarifyIntent,
    Field(discriminator="intent"),
]
_ADAPTER: TypeAdapter[AgentIntent] = TypeAdapter(AgentIntent)
_SCHEMA = _ADAPTER.json_schema()
_SYSTEM_PROMPT = (
    "Understand one Shiguang Agent message and return exactly one JSON object matching "
    "the supplied schema. Do not use keyword matching. collect_content is only for a "
    "user asking to save Place/Event content and must include the complete existing "
    "ExtractionResult. plan is for creating or continuing one Shenzhen plan; extract "
    "only stated time, coarse activity area, activity wishes and temporary constraints, "
    "never invent missing required values. memory authorization is explicit only when "
    "the user clearly grants long-term storage, needs_confirmation for an unqualified "
    "preference. A preference limited to the current plan is plan.exclude, never memory. "
    "Use clarify "
    "with one necessary short question when meaning is genuinely ambiguous. A reply in "
    "pending_context continues that task. Never decide permissions or write data. Current "
    "time is supplied for resolving relative dates. Schema:\n"
    + json.dumps(_SCHEMA, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
)


class AgentIntentParser:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        structured_output_mode: StructuredOutputMode | None,
    ) -> None:
        self._provider = provider
        self._response_format = structured_response_format(
            structured_output_mode,
            schema_name="agent_intent",
            json_schema=_SCHEMA,
        )

    async def parse(
        self,
        *,
        text: str,
        now: datetime,
        pending_context: str | None = None,
        response_observer: Callable[[ModelResponse], None] | None = None,
    ) -> AgentIntent:
        normalized = " ".join(text.split())
        if not normalized or len(normalized) > 20_000:
            raise AgentIntentError
        response = await self._provider.chat(
            messages=deepcopy(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "current_time": now.isoformat(),
                                "pending_context": pending_context,
                                "message": normalized,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ]
            ),
            tools=None,
            response_format=self._response_format,
        )
        if response_observer is not None:
            response_observer(response)
        if response.tool_calls or response.content is None:
            raise AgentIntentError
        try:
            return _ADAPTER.validate_json(response.content)
        except (ValidationError, TypeError, ValueError):
            raise AgentIntentError from None


__all__ = [
    "AgentIntent",
    "AgentIntentError",
    "AgentIntentParser",
    "ClarifyIntent",
    "CollectionIntent",
    "MemoryIntent",
    "PlanIntent",
]

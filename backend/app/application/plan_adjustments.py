"""One structured model boundary for minimal PlanConstraints adjustments."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

from pydantic import Field, ValidationError, model_validator

from app.domain.places import Coordinate, TransportMode
from app.domain.plans import ActivityArea, PlanConstraints, PlanPace
from app.domain.plans.contracts import PlanContract
from nanobot_core.providers import (
    Message,
    ModelProvider,
    ModelResponse,
    StructuredOutput,
    StructuredOutputMode,
)


class PlanAdjustmentNotUnderstoodError(ValueError):
    code = "PLAN_ADJUSTMENT_NOT_UNDERSTOOD"


class PlanAdjustmentPatch(PlanContract):
    """Only fields explicitly present in model output replace current constraints."""

    start_at: datetime | None = None
    end_at: datetime | None = None
    area: ActivityArea | None = None
    origin: Coordinate | None = None
    budget: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    pace: PlanPace | None = None
    transport_modes: tuple[TransportMode, ...] | None = Field(
        default=None,
        min_length=1,
        max_length=4,
    )
    include: tuple[str, ...] | None = Field(default=None, max_length=20)
    exclude: tuple[str, ...] | None = Field(default=None, max_length=20)
    collection_only: bool | None = None

    @model_validator(mode="after")
    def require_explicit_patch(self) -> PlanAdjustmentPatch:
        if not self.model_fields_set:
            raise ValueError("an adjustment must change at least one field")
        if "area" in self.model_fields_set and "origin" in self.model_fields_set:
            if self.area is None and self.origin is None:
                raise ValueError("an adjustment cannot remove both activity ranges")
        return self


_PATCH_SCHEMA = PlanAdjustmentPatch.model_json_schema()
_RESPONSE_FORMAT = StructuredOutput(
    mode=StructuredOutputMode.JSON_SCHEMA,
    schema_name="plan_adjustment_patch",
    json_schema=_PATCH_SCHEMA,
    strict=True,
)
_SYSTEM_PROMPT = (
    "Convert one Shiguang plan-adjustment instruction into the smallest JSON patch "
    "matching the supplied schema. Include only fields the user explicitly changes. "
    "Omitted fields must remain unchanged. include and exclude are complete replacement "
    "lists when present. When the user replaces an activity category, remove the old "
    "category from include, add the requested category to include, and add an explicit "
    "rejection to exclude when requested. Use ISO-8601 aware datetimes and never invent "
    "times, budget, area, pace, transport, or collection_only. Return JSON only."
)


class PlanAdjustmentParser:
    """Parse one instruction through the existing ModelProvider, without phrase rules."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def parse(
        self,
        *,
        constraints: PlanConstraints,
        instruction: str,
        response_observer: Callable[[ModelResponse], None] | None = None,
    ) -> PlanAdjustmentPatch:
        normalized = " ".join(instruction.split())
        if not normalized or len(normalized) > 1000:
            raise PlanAdjustmentNotUnderstoodError
        messages: list[Message] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "current_constraints": constraints.model_dump(mode="json"),
                        "instruction": normalized,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]
        response = await self._provider.chat(
            messages=deepcopy(messages),
            tools=None,
            response_format=_RESPONSE_FORMAT,
        )
        if response_observer is not None:
            response_observer(response)
        if response.tool_calls or response.content is None:
            raise PlanAdjustmentNotUnderstoodError
        try:
            return PlanAdjustmentPatch.model_validate_json(response.content)
        except (ValidationError, TypeError, ValueError):
            raise PlanAdjustmentNotUnderstoodError from None


def apply_plan_adjustment(
    constraints: PlanConstraints,
    patch: PlanAdjustmentPatch,
) -> PlanConstraints:
    """Apply one strict patch and validate the complete PlanConstraints exactly once."""

    values = constraints.model_dump()
    for field_name in patch.model_fields_set:
        values[field_name] = getattr(patch, field_name)
    return PlanConstraints.model_validate(values)


__all__ = [
    "PlanAdjustmentNotUnderstoodError",
    "PlanAdjustmentParser",
    "PlanAdjustmentPatch",
    "apply_plan_adjustment",
]

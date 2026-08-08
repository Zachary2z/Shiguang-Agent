"""One structured model boundary for minimal PlanConstraints adjustments."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

from pydantic import Field, ValidationError, model_validator

from app.application.extraction_output import structured_response_format
from app.domain.places import TransportMode
from app.domain.plans import (
    PlanConstraints,
    PlanPace,
    PlanPaceSource,
    plan_constraint_expires_at,
    plan_constraints_internal_dump,
)
from app.domain.plans.contracts import PlanContract
from app.domain.time import ASIA_SHANGHAI, utc_now
from nanobot_core.providers import (
    Message,
    ModelProvider,
    ModelResponse,
    StructuredOutputMode,
)


class PlanAdjustmentNotUnderstoodError(ValueError):
    code = "PLAN_ADJUSTMENT_NOT_UNDERSTOOD"


class PlanAdjustmentUnsupportedError(ValueError):
    code = "PLAN_ADJUSTMENT_UNSUPPORTED"


class PlanAdjustmentPatch(PlanContract):
    """Only fields explicitly present in model output replace current constraints."""

    start_at: datetime | None = None
    end_at: datetime | None = None
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
        return self


_PATCH_SCHEMA = PlanAdjustmentPatch.model_json_schema()
_SYSTEM_PROMPT = (
    "Convert one Shiguang plan-adjustment instruction into the smallest JSON patch "
    "matching the supplied schema. Include only fields the user explicitly changes. "
    "Omitted fields must remain unchanged. include and exclude are complete replacement "
    "lists when present. When the user replaces an activity category, remove the old "
    "category from include, add the requested category to include, and add an explicit "
    "rejection to exclude when requested. The supplied timezone is Asia/Shanghai. "
    "Interpret dates and clock times in Asia/Shanghai and output aware ISO-8601 "
    "datetimes with +08:00, unless the user explicitly says UTC; only then may output "
    "use UTC. Never invent "
    "times, budget, pace, transport, or collection_only. Exact place and activity-area "
    "changes are not supported in this stage: for such a request return an empty object "
    "so the product can ask the user to create a new plan. Never emit coordinates. "
    "Return JSON matching this schema only:\n"
    + json.dumps(_PATCH_SCHEMA, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
)


class PlanAdjustmentParser:
    """Parse one instruction through the existing ModelProvider, without phrase rules."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        structured_output_mode: StructuredOutputMode | None,
    ) -> None:
        self._provider = provider
        self._response_format = structured_response_format(
            structured_output_mode,
            schema_name="plan_adjustment_patch",
            json_schema=_PATCH_SCHEMA,
        )

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
                        "timezone": ASIA_SHANGHAI.key,
                        "current_time": utc_now().astimezone(ASIA_SHANGHAI).isoformat(),
                        "current_constraints": {
                            **constraints.model_dump(mode="json"),
                            "start_at": constraints.start_at.astimezone(
                                ASIA_SHANGHAI
                            ).isoformat(),
                            "end_at": constraints.end_at.astimezone(
                                ASIA_SHANGHAI
                            ).isoformat(),
                        },
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
            response_format=self._response_format,
        )
        if response_observer is not None:
            response_observer(response)
        if response.tool_calls or response.content is None:
            raise PlanAdjustmentNotUnderstoodError
        try:
            if json.loads(response.content) == {}:
                raise PlanAdjustmentUnsupportedError
            return PlanAdjustmentPatch.model_validate_json(response.content)
        except PlanAdjustmentUnsupportedError:
            raise
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            raise PlanAdjustmentNotUnderstoodError from None


def apply_plan_adjustment(
    constraints: PlanConstraints,
    patch: PlanAdjustmentPatch,
) -> PlanConstraints:
    """Apply one strict patch and validate the complete PlanConstraints exactly once."""

    values = plan_constraints_internal_dump(constraints, mode="python")
    for field_name in patch.model_fields_set:
        values[field_name] = getattr(patch, field_name)
    if "pace" in patch.model_fields_set:
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


__all__ = [
    "PlanAdjustmentNotUnderstoodError",
    "PlanAdjustmentParser",
    "PlanAdjustmentPatch",
    "PlanAdjustmentUnsupportedError",
    "apply_plan_adjustment",
]

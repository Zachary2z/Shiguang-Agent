"""M1-5 structured PlanConstraints patch boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.application.plan_adjustments import (
    PlanAdjustmentNotUnderstoodError,
    PlanAdjustmentParser,
    PlanAdjustmentPatch,
    apply_plan_adjustment,
)
from app.domain.collections import PlanCity
from app.domain.places import TransportMode
from app.domain.plans import ActivityArea, PlanConstraints, PlanPace
from tests.core.fakes import FakeProvider, fake_response


def _constraints(*, budget: Decimal | None = Decimal("300")) -> PlanConstraints:
    created_at = datetime(2026, 7, 28, 1, tzinfo=UTC)
    return PlanConstraints(
        city_code=PlanCity.SHENZHEN,
        start_at=datetime(2026, 7, 29, 2, tzinfo=UTC),
        end_at=datetime(2026, 7, 29, 10, tzinfo=UTC),
        area=ActivityArea(districts=("南山区",), labels=("海上世界",)),
        budget=budget,
        pace=PlanPace.BALANCED,
        transport_modes=(TransportMode.WALKING, TransportMode.TRANSIT),
        include=("咖啡店",),
        exclude=("商场",),
        collection_only=False,
        created_at=created_at,
        expires_at=created_at + timedelta(days=2),
    )


@pytest.mark.asyncio
async def test_product_adjustment_replaces_category_and_preserves_every_other_field() -> None:
    original = _constraints()
    provider = FakeProvider(
        [
            fake_response(
                content=(
                    '{"include":["适合散步的地方"],'
                    '"exclude":["商场","咖啡店"]}'
                )
            )
        ]
    )

    patch = await PlanAdjustmentParser(provider).parse(
        constraints=original,
        instruction="不要咖啡店，换成适合散步的地方，其他不变。",
    )
    adjusted = apply_plan_adjustment(original, patch)

    assert adjusted.include == ("适合散步的地方",)
    assert adjusted.exclude == ("商场", "咖啡店")
    assert adjusted.model_copy(
        update={"include": original.include, "exclude": original.exclude}
    ) == original
    assert len(provider.calls) == 1
    assert provider.calls[0].response_format is not None


def test_complete_patch_is_validated_once_by_plan_constraints() -> None:
    original = _constraints(budget=None)
    patch = PlanAdjustmentPatch(
        pace=PlanPace.RELAXED,
        transport_modes=(TransportMode.TRANSIT,),
        collection_only=True,
    )

    adjusted = apply_plan_adjustment(original, patch)

    assert adjusted.pace is PlanPace.RELAXED
    assert adjusted.transport_modes == (TransportMode.TRANSIT,)
    assert adjusted.collection_only is True
    assert adjusted.budget is None
    assert adjusted.area == original.area


@pytest.mark.asyncio
async def test_invalid_or_empty_model_patch_is_rejected_without_phrase_fallback() -> None:
    provider = FakeProvider([fake_response(content="{}")])

    with pytest.raises(PlanAdjustmentNotUnderstoodError):
        await PlanAdjustmentParser(provider).parse(
            constraints=_constraints(),
            instruction="给我一个惊喜",
        )

    assert len(provider.calls) == 1

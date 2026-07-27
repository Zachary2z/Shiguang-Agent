"""M1-5 deterministic natural-language constraint patch contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.application.plan_adjustments import (
    PlanAdjustmentNotUnderstoodError,
    apply_plan_adjustment,
)
from app.domain.collections import PlanCity
from app.domain.places import TransportMode
from app.domain.plans import ActivityArea, PlanConstraints, PlanPace


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
        include=("咖啡",),
        exclude=("商场",),
        collection_only=False,
        created_at=created_at,
        expires_at=created_at + timedelta(days=2),
    )


def test_adjusting_one_condition_preserves_every_other_condition() -> None:
    original = _constraints()
    adjusted = apply_plan_adjustment(original, "节奏轻松一点")

    assert adjusted.pace is PlanPace.RELAXED
    assert adjusted.model_copy(update={"pace": original.pace}) == original


def test_exact_clock_uses_shenzhen_local_time_and_preserves_other_values() -> None:
    original = _constraints(budget=None)
    adjusted = apply_plan_adjustment(original, "调整为 14:30 到 20:00")

    assert adjusted.start_at == datetime(2026, 7, 29, 6, 30, tzinfo=UTC)
    assert adjusted.end_at == datetime(2026, 7, 29, 12, tzinfo=UTC)
    assert adjusted.budget is None
    assert adjusted.area == original.area


def test_budget_transport_and_collection_only_are_explicit_patches() -> None:
    adjusted = apply_plan_adjustment(
        _constraints(),
        "预算调整为 188.50，少走一点，只用收藏",
    )

    assert adjusted.budget == Decimal("188.50")
    assert adjusted.transport_modes == (TransportMode.TRANSIT,)
    assert adjusted.collection_only is True


def test_unknown_adjustment_is_rejected_instead_of_becoming_a_model_guess() -> None:
    with pytest.raises(PlanAdjustmentNotUnderstoodError):
        apply_plan_adjustment(_constraints(), "给我一个惊喜")

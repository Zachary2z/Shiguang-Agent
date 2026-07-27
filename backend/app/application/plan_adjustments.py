"""Deterministic plan-constraint patching for explicit user adjustment text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.places import TransportMode
from app.domain.plans import PlanConstraints, PlanPace

_SHIFT_PATTERN = re.compile(
    r"(?P<direction>晚|推迟|延后|早|提前)\s*(?P<amount>\d{1,3})\s*"
    r"(?P<unit>小时|分钟)"
)
_TIME_WINDOW_PATTERN = re.compile(
    r"(?P<start_hour>[01]?\d|2[0-3])[:：](?P<start_minute>[0-5]\d)"
    r"\s*(?:到|至|[-—–])\s*"
    r"(?P<end_hour>[01]?\d|2[0-3])[:：](?P<end_minute>[0-5]\d)"
)
_BUDGET_PATTERN = re.compile(r"预算(?:改成|调整为|设为|是|为)?\s*(?P<amount>\d+(?:\.\d{1,2})?)")
_EXCLUDE_PATTERN = re.compile(r"不要\s*(?P<value>[^，。；,;]{1,40})")
_SHENZHEN_TIME = ZoneInfo("Asia/Shanghai")


class PlanAdjustmentNotUnderstoodError(ValueError):
    code = "PLAN_ADJUSTMENT_NOT_UNDERSTOOD"


def apply_plan_adjustment(
    constraints: PlanConstraints,
    instruction: str,
) -> PlanConstraints:
    """Apply only explicitly recognized changes and preserve every other field."""

    normalized = " ".join(instruction.split())
    if not normalized or len(normalized) > 1000:
        raise PlanAdjustmentNotUnderstoodError
    changes: dict[str, object] = {}

    shift = _SHIFT_PATTERN.search(normalized)
    if shift is not None:
        amount = int(shift.group("amount"))
        delta = timedelta(
            hours=amount if shift.group("unit") == "小时" else 0,
            minutes=amount if shift.group("unit") == "分钟" else 0,
        )
        if shift.group("direction") in {"早", "提前"}:
            delta = -delta
        changes["start_at"] = constraints.start_at + delta
        changes["end_at"] = constraints.end_at + delta

    exact_window = _TIME_WINDOW_PATTERN.search(normalized)
    if exact_window is not None:
        start = _replace_local_clock(
            constraints.start_at,
            hour=int(exact_window.group("start_hour")),
            minute=int(exact_window.group("start_minute")),
        )
        end = _replace_local_clock(
            constraints.end_at,
            hour=int(exact_window.group("end_hour")),
            minute=int(exact_window.group("end_minute")),
        )
        changes["start_at"] = start
        changes["end_at"] = end

    if any(value in normalized for value in ("轻松一点", "节奏轻松", "慢一点")):
        changes["pace"] = PlanPace.RELAXED
    elif any(value in normalized for value in ("排满一点", "紧凑一点", "多安排")):
        changes["pace"] = PlanPace.PACKED
    elif "节奏适中" in normalized:
        changes["pace"] = PlanPace.BALANCED

    if "少走" in normalized or "公共交通" in normalized or "地铁" in normalized:
        changes["transport_modes"] = (TransportMode.TRANSIT,)
    elif "只步行" in normalized:
        changes["transport_modes"] = (TransportMode.WALKING,)
    elif "骑行" in normalized:
        changes["transport_modes"] = (TransportMode.CYCLING,)
    elif "驾车" in normalized or "开车" in normalized:
        changes["transport_modes"] = (TransportMode.DRIVING,)

    if "只用收藏" in normalized or "不要外部" in normalized:
        changes["collection_only"] = True
    elif "允许外部" in normalized or "可以补充外部" in normalized:
        changes["collection_only"] = False

    if any(
        value in normalized
        for value in ("不设预算", "预算未设置", "取消预算", "没有预算限制")
    ):
        changes["budget"] = None
    else:
        budget = _BUDGET_PATTERN.search(normalized)
        if budget is not None:
            changes["budget"] = Decimal(budget.group("amount"))

    exclusions = list(constraints.exclude)
    for match in _EXCLUDE_PATTERN.finditer(normalized):
        value = match.group("value").strip()
        if value and value not in exclusions:
            exclusions.append(value)
    if exclusions != list(constraints.exclude):
        changes["exclude"] = tuple(exclusions)

    if not changes:
        raise PlanAdjustmentNotUnderstoodError
    values: dict[str, object] = {
        "city_code": constraints.city_code,
        "start_at": constraints.start_at,
        "end_at": constraints.end_at,
        "area": constraints.area,
        "origin": constraints.origin,
        "budget": constraints.budget,
        "pace": constraints.pace,
        "transport_modes": constraints.transport_modes,
        "include": constraints.include,
        "exclude": constraints.exclude,
        "collection_only": constraints.collection_only,
        "created_at": constraints.created_at,
        "expires_at": constraints.expires_at,
    }
    values.update(changes)
    return PlanConstraints.model_validate(values)


def _replace_local_clock(value: datetime, *, hour: int, minute: int) -> datetime:
    local = value.astimezone(_SHENZHEN_TIME).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    return local.astimezone(value.tzinfo)


__all__ = [
    "PlanAdjustmentNotUnderstoodError",
    "apply_plan_adjustment",
]

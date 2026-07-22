"""Twenty deterministic M0-5C scenario specifications."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.plans import PlanPace


@dataclass(frozen=True)
class PlanFixtureSpec:
    name: str
    window_minutes: int
    candidate_count: int
    visit_minutes: int
    route_minutes: int
    pace: PlanPace


PLAN_FIXTURE_SPECS: tuple[PlanFixtureSpec, ...] = (
    PlanFixtureSpec("single-balanced", 180, 1, 60, 15, PlanPace.BALANCED),
    PlanFixtureSpec("single-packed", 120, 1, 45, 10, PlanPace.PACKED),
    PlanFixtureSpec("single-relaxed", 180, 1, 60, 10, PlanPace.RELAXED),
    PlanFixtureSpec("two-balanced", 240, 2, 60, 15, PlanPace.BALANCED),
    PlanFixtureSpec("two-packed", 180, 2, 45, 10, PlanPace.PACKED),
    PlanFixtureSpec("two-relaxed", 300, 2, 60, 15, PlanPace.RELAXED),
    PlanFixtureSpec("three-balanced", 300, 3, 60, 15, PlanPace.BALANCED),
    PlanFixtureSpec("three-packed", 240, 3, 45, 10, PlanPace.PACKED),
    PlanFixtureSpec("three-relaxed", 360, 3, 60, 15, PlanPace.RELAXED),
    PlanFixtureSpec("four-balanced", 360, 4, 60, 15, PlanPace.BALANCED),
    PlanFixtureSpec("four-packed", 300, 4, 45, 10, PlanPace.PACKED),
    PlanFixtureSpec("four-relaxed", 420, 4, 60, 15, PlanPace.RELAXED),
    PlanFixtureSpec("short-one", 75, 2, 30, 10, PlanPace.PACKED),
    PlanFixtureSpec("long-visits", 420, 3, 120, 20, PlanPace.BALANCED),
    PlanFixtureSpec("short-visits", 180, 3, 30, 10, PlanPace.PACKED),
    PlanFixtureSpec("route-heavy", 360, 3, 60, 40, PlanPace.BALANCED),
    PlanFixtureSpec("visit-heavy", 360, 3, 100, 10, PlanPace.RELAXED),
    PlanFixtureSpec("exact-end-packed", 100, 1, 60, 15, PlanPace.PACKED),
    PlanFixtureSpec("exact-end-balanced", 110, 1, 75, 15, PlanPace.BALANCED),
    PlanFixtureSpec("exact-end-relaxed", 120, 1, 75, 15, PlanPace.RELAXED),
)

assert len(PLAN_FIXTURE_SPECS) == 20

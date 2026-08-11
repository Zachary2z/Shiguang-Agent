"""Focused proposal-route coverage for the sole map fact resolver."""

from app.application.map_plan_facts import proposal_route_edges
from app.domain.plans.drafts import (
    PlanOptionProposal,
    PlanOptionRole,
    PlanProposalItem,
    PlanProposalSet,
)


def test_only_distinct_proposal_edges_are_requested() -> None:
    proposals = PlanProposalSet(
        options=(
            PlanOptionProposal(
                role=PlanOptionRole.MAIN,
                items=(
                    PlanProposalItem(candidate_key="a", visit_duration_seconds=1),
                    PlanProposalItem(candidate_key="b", visit_duration_seconds=1),
                    PlanProposalItem(candidate_key="c", visit_duration_seconds=1),
                ),
                reason="main",
            ),
            PlanOptionProposal(
                role=PlanOptionRole.ALTERNATIVE,
                items=(
                    PlanProposalItem(candidate_key="a", visit_duration_seconds=1),
                    PlanProposalItem(candidate_key="c", visit_duration_seconds=1),
                ),
                reason="alt 1",
            ),
            PlanOptionProposal(
                role=PlanOptionRole.ALTERNATIVE,
                items=(
                    PlanProposalItem(candidate_key="a", visit_duration_seconds=1),
                    PlanProposalItem(candidate_key="b", visit_duration_seconds=1),
                ),
                reason="alt 2",
            ),
        )
    )
    assert proposal_route_edges(proposals) == (
        (None, "a"),
        ("a", "b"),
        ("b", "c"),
        ("a", "c"),
    )

"""The single deterministic M0-5C plan-draft generation and validation service."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unicodedata import normalize

from app.domain.collections import PRICE_CURRENCY_CNY, CollectionKind
from app.domain.places import TransportMode
from app.domain.plans import PlanConstraints, PlanPace, WeatherAssessment
from app.domain.plans.drafts import (
    FAILURE_SUMMARIES,
    RISK_SUMMARIES,
    SELECTION_REASON_SUMMARIES,
    DraftCandidateFacts,
    DraftRouteFacts,
    ExternalDraftCandidate,
    PlanDraftExclusion,
    PlanDraftFactSnapshot,
    PlanDraftFailureCode,
    PlanDraftOutcome,
    PlanDraftResult,
    PlanDraftValidation,
    PlanDraftViolationCode,
    PlanItem,
    PlanItemRole,
    PlanItemSource,
    PlanItemSourceKind,
    PlanOption,
    PlanOptionRole,
    PlanRiskCode,
    PlanRouteLeg,
    PlanSelectionReasonCode,
)
from app.domain.plans.retrieval import (
    CandidateOutcome,
    CollectionCandidateDecision,
    StructuredCollectionResult,
)

_BUFFER_SECONDS: dict[PlanPace, tuple[int, int]] = {
    PlanPace.PACKED: (10 * 60, 15 * 60),
    PlanPace.BALANCED: (15 * 60, 20 * 60),
    PlanPace.RELAXED: (20 * 60, 30 * 60),
}


def _identity(value: str) -> str:
    return "".join(normalize("NFKC", value).casefold().split())


def _option_cost(items: tuple[PlanItem, ...]) -> tuple[Decimal | None, str | None]:
    if any(item.price_amount is None for item in items):
        return (None, None)
    return (
        sum(
            (item.price_amount for item in items if item.price_amount is not None),
            Decimal(),
        ),
        PRICE_CURRENCY_CNY,
    )


def _option_risks(
    items: tuple[PlanItem, ...],
    weather_status: WeatherAssessment | None,
) -> tuple[PlanRiskCode, ...]:
    selected = {risk for item in items for risk in item.risk_codes}
    if weather_status is WeatherAssessment.PROVIDER_FAILED:
        selected.add(PlanRiskCode.WEATHER_PROVIDER_FAILED)
    elif weather_status in {WeatherAssessment.UNKNOWN, WeatherAssessment.CONFLICT}:
        selected.add(PlanRiskCode.WEATHER_UNKNOWN)
    return tuple(code for code in PlanRiskCode if code in selected)


def _item_risks(
    price_amount: Decimal | None,
    *,
    budget: Decimal | None,
    route_known: bool,
) -> tuple[PlanRiskCode, ...]:
    selected: set[PlanRiskCode] = set()
    if price_amount is None:
        selected.add(
            PlanRiskCode.BUDGET_UNVERIFIED
            if budget is not None
            else PlanRiskCode.PRICE_UNKNOWN
        )
    if not route_known:
        selected.add(PlanRiskCode.ROUTE_UNKNOWN)
    return tuple(code for code in PlanRiskCode if code in selected)


class PlanDraftService:
    """Generate and validate plans through one deterministic business-rule path."""

    def generate(
        self,
        *,
        constraints: PlanConstraints,
        collections: StructuredCollectionResult,
        facts: PlanDraftFactSnapshot,
        external_candidate: ExternalDraftCandidate | None = None,
    ) -> PlanDraftResult:
        exclusions = self._exclusions(collections)
        if not collections.included and external_candidate is None:
            return self._failure(PlanDraftFailureCode.NO_INCLUDED_CANDIDATES, exclusions)

        candidate_facts = {item.collection_item_ids: item for item in facts.candidates}
        routes = {item.identity: item for item in facts.routes}
        ranked = sorted(
            collections.included,
            key=lambda item: self._rank_key(item, routes),
        )
        switch_buffer, end_buffer = _BUFFER_SECONDS[constraints.pace]
        options: list[PlanOption] = []
        seen_sequences: set[tuple[tuple[str, ...], ...]] = set()

        for core in ranked:
            if len(options) == 3:
                break
            core_item = self._schedule_item(
                decision=core,
                role=PlanItemRole.CORE,
                reason=(
                    PlanSelectionReasonCode.PRIMARY_STABLE_RANK
                    if not options
                    else PlanSelectionReasonCode.STABLE_ALTERNATIVE
                ),
                earliest_departure=constraints.start_at,
                from_ids=(),
                constraints=constraints,
                candidate_facts=candidate_facts,
                routes=routes,
                end_buffer_seconds=end_buffer,
                existing_items=(),
            )
            if core_item is None:
                continue

            items: tuple[PlanItem, ...] = (core_item,)
            if external_candidate is not None and not options:
                external_item = self._schedule_external_item(
                    candidate=external_candidate,
                    role=PlanItemRole.AUXILIARY,
                    earliest_departure=core_item.end_at
                    + timedelta(seconds=switch_buffer),
                    from_ids=core.collection_item_ids,
                    constraints=constraints,
                    end_buffer_seconds=end_buffer,
                    existing_items=items,
                )
                if external_item is not None:
                    items = (core_item, external_item)
            for auxiliary in ranked:
                if len(items) == 2:
                    break
                if auxiliary.collection_item_ids == core.collection_item_ids:
                    continue
                auxiliary_item = self._schedule_item(
                    decision=auxiliary,
                    role=PlanItemRole.AUXILIARY,
                    reason=PlanSelectionReasonCode.AUXILIARY_FITS_KNOWN_ROUTE,
                    earliest_departure=core_item.end_at + timedelta(seconds=switch_buffer),
                    from_ids=core.collection_item_ids,
                    constraints=constraints,
                    candidate_facts=candidate_facts,
                    routes=routes,
                    end_buffer_seconds=end_buffer,
                    existing_items=items,
                )
                if auxiliary_item is not None:
                    items = (core_item, auxiliary_item)
                    break

            sequence = tuple(item.source.collection_item_ids for item in items)
            if sequence in seen_sequences:
                continue
            seen_sequences.add(sequence)
            total_amount, total_currency = _option_cost(items)
            risks = _option_risks(items, facts.weather_status)
            options.append(
                PlanOption(
                    role=(PlanOptionRole.MAIN if not options else PlanOptionRole.ALTERNATIVE),
                    items=items,
                    switch_buffer_seconds=switch_buffer if len(items) == 2 else None,
                    end_buffer_seconds=end_buffer,
                    total_cost_amount=total_amount,
                    total_cost_currency=total_currency,
                    risk_codes=risks,
                    risks=tuple(RISK_SUMMARIES[risk] for risk in risks),
                )
            )

        if not options and external_candidate is not None:
            external_item = self._schedule_external_item(
                candidate=external_candidate,
                role=PlanItemRole.CORE,
                earliest_departure=constraints.start_at,
                from_ids=(),
                constraints=constraints,
                end_buffer_seconds=end_buffer,
                existing_items=(),
            )
            if external_item is not None:
                total_amount, total_currency = _option_cost((external_item,))
                risks = _option_risks((external_item,), facts.weather_status)
                options.append(
                    PlanOption(
                        role=PlanOptionRole.MAIN,
                        items=(external_item,),
                        end_buffer_seconds=end_buffer,
                        total_cost_amount=total_amount,
                        total_cost_currency=total_currency,
                        risk_codes=risks,
                        risks=tuple(RISK_SUMMARIES[risk] for risk in risks),
                    )
                )

        if not options:
            return self._failure(PlanDraftFailureCode.NO_EXECUTABLE_OPTION, exclusions)

        draft = PlanDraftResult(
            outcome=PlanDraftOutcome.GENERATED,
            options=tuple(options),
            exclusions=exclusions,
            weather_status=facts.weather_status,
            weather_source=facts.weather_source,
            weather_queried_at=facts.weather_queried_at,
            weather_summary=facts.weather_summary,
        )
        validation = self.validate(
            draft=draft,
            constraints=constraints,
            collections=collections,
            facts=facts,
            external_candidate=external_candidate,
        )
        if not validation.is_valid:
            return self._failure(
                PlanDraftFailureCode.POST_GENERATION_VALIDATION_FAILED,
                exclusions,
            )
        return draft

    def validate(
        self,
        *,
        draft: PlanDraftResult,
        constraints: PlanConstraints,
        collections: StructuredCollectionResult,
        facts: PlanDraftFactSnapshot,
        external_candidate: ExternalDraftCandidate | None = None,
    ) -> PlanDraftValidation:
        """Re-run every known scheduling invariant against the immutable facts."""

        violations: set[PlanDraftViolationCode] = set()
        if draft.outcome is PlanDraftOutcome.NOT_GENERATED:
            if (
                draft.options
                or draft.failure_code is None
                or draft.failure_summary
                != (None if draft.failure_code is None else FAILURE_SUMMARIES[draft.failure_code])
            ):
                violations.add(PlanDraftViolationCode.RESULT_SHAPE_INVALID)
            return self._validation(violations)

        if (
            not 1 <= len(draft.options) <= 3
            or draft.failure_code is not None
            or draft.failure_summary is not None
            or draft.exclusions != self._exclusions(collections)
            or draft.weather_status != facts.weather_status
            or draft.weather_source != facts.weather_source
            or draft.weather_queried_at != facts.weather_queried_at
            or draft.weather_summary != facts.weather_summary
        ):
            violations.add(PlanDraftViolationCode.RESULT_SHAPE_INVALID)

        included = {item.collection_item_ids: item for item in collections.included}
        candidate_facts = {item.collection_item_ids: item for item in facts.candidates}
        routes = {item.identity: item for item in facts.routes}
        expected_switch, expected_end = _BUFFER_SECONDS[constraints.pace]
        sequences: set[tuple[tuple[str, ...], ...]] = set()
        external_item_count = 0

        for option_index, option in enumerate(draft.options):
            if not 1 <= len(option.items) <= 2:
                violations.add(PlanDraftViolationCode.RESULT_SHAPE_INVALID)
            expected_role = PlanOptionRole.MAIN if option_index == 0 else PlanOptionRole.ALTERNATIVE
            if option.role is not expected_role:
                violations.add(PlanDraftViolationCode.OPTION_ROLE_INVALID)
            sequence = tuple(item.source.collection_item_ids for item in option.items)
            if sequence in sequences:
                violations.add(PlanDraftViolationCode.OPTION_DUPLICATED)
            sequences.add(sequence)
            if option.end_buffer_seconds != expected_end:
                violations.add(PlanDraftViolationCode.END_BUFFER_INVALID)
            expected_option_switch = expected_switch if len(option.items) == 2 else None
            if option.switch_buffer_seconds != expected_option_switch:
                violations.add(PlanDraftViolationCode.SWITCH_BUFFER_INVALID)

            seen_pois: set[tuple[object, str]] = set()
            previous_end = constraints.start_at
            previous_ids: tuple[str, ...] = ()
            for item_index, item in enumerate(option.items):
                expected_item_role = (
                    PlanItemRole.CORE if item_index == 0 else PlanItemRole.AUXILIARY
                )
                if item.role is not expected_item_role:
                    violations.add(PlanDraftViolationCode.ITEM_ROLE_INVALID)
                if item.source.kind is PlanItemSourceKind.EXTERNAL_PLACE:
                    external_item_count += 1
                    self._validate_external_item(
                        item=item,
                        candidate=external_candidate,
                        previous_end=previous_end,
                        previous_ids=previous_ids,
                        item_index=item_index,
                        option_index=option_index,
                        constraints=constraints,
                        expected_switch=expected_switch,
                        expected_end=expected_end,
                        seen_pois=seen_pois,
                        violations=violations,
                    )
                    previous_end = item.end_at
                    previous_ids = ()
                    continue

                decision = included.get(item.source.collection_item_ids)
                if decision is None:
                    violations.add(PlanDraftViolationCode.SOURCE_NOT_INCLUDED)
                    continue
                visit = candidate_facts.get(item.source.collection_item_ids)
                if visit is None or item.visit_duration_seconds != visit.visit_duration_seconds:
                    violations.add(PlanDraftViolationCode.FACTS_MISSING_OR_MISMATCHED)
                    continue
                if (
                    item.title != decision.title
                    or item.kind is not decision.kind
                    or item.price_amount != decision.price_amount
                    or item.price_currency != decision.price_currency
                    or (
                        decision.kind is CollectionKind.PLACE
                        and (visit.event_start_at is not None or visit.event_end_at is not None)
                    )
                ):
                    violations.add(PlanDraftViolationCode.FACTS_MISSING_OR_MISMATCHED)
                route = routes.get((previous_ids, item.source.collection_item_ids))
                unknown_origin_route = (
                    item_index == 0
                    and constraints.origin is None
                    and route is None
                    and item.inbound_route.duration_seconds is None
                    and item.inbound_route.distance_meters is None
                )
                if not unknown_origin_route and (
                    route is None or not self._route_matches(item.inbound_route, route)
                ):
                    violations.add(PlanDraftViolationCode.ROUTE_MISSING_OR_MISMATCHED)
                    continue
                if route is not None and (
                    constraints.transport_modes
                    and route.transport_mode not in constraints.transport_modes
                ):
                    violations.add(PlanDraftViolationCode.ROUTE_MISSING_OR_MISMATCHED)
                if (
                    item_index == 0
                    and route is not None
                    and not self._origin_route_matches_decision(decision, route)
                ):
                    violations.add(PlanDraftViolationCode.ROUTE_MISSING_OR_MISMATCHED)

                departure = previous_end
                if item_index == 1:
                    departure += timedelta(seconds=expected_switch)
                expected_start = departure + timedelta(
                    seconds=0 if route is None else route.duration_seconds
                )
                if visit.event_start_at is not None:
                    expected_start = max(expected_start, visit.event_start_at)
                expected_item_end = expected_start + timedelta(seconds=visit.visit_duration_seconds)
                if item.start_at != expected_start or item.end_at != expected_item_end:
                    violations.add(PlanDraftViolationCode.TIME_WINDOW_VIOLATED)
                if item.start_at < constraints.start_at or (
                    item.end_at + timedelta(seconds=expected_end) > constraints.end_at
                ):
                    violations.add(PlanDraftViolationCode.TIME_WINDOW_VIOLATED)
                if (
                    visit.event_start_at is not None
                    and visit.event_end_at is not None
                    and (item.start_at < visit.event_start_at or item.end_at > visit.event_end_at)
                ):
                    violations.add(PlanDraftViolationCode.EVENT_WINDOW_VIOLATED)

                if item.source.kind is not PlanItemSourceKind.COLLECTION_DERIVED:
                    violations.add(PlanDraftViolationCode.SOURCE_NOT_INCLUDED)
                if (
                    item.source.any_branch_collection_item_ids
                    != decision.any_branch_collection_item_ids
                    or item.source.concrete_poi != decision.poi
                ):
                    violations.add(PlanDraftViolationCode.BRANCH_SNAPSHOT_INVALID)
                if decision.any_branch_collection_item_ids and (
                    visit.poi_queried_at is None
                    or item.source.poi_queried_at != visit.poi_queried_at
                ):
                    violations.add(PlanDraftViolationCode.BRANCH_SNAPSHOT_INVALID)
                if (
                    not decision.any_branch_collection_item_ids
                    and item.source.poi_queried_at is not None
                ):
                    violations.add(PlanDraftViolationCode.BRANCH_SNAPSHOT_INVALID)
                if decision.poi_identity is not None:
                    if decision.poi_identity in seen_pois:
                        violations.add(PlanDraftViolationCode.DUPLICATE_POI)
                    seen_pois.add(decision.poi_identity)
                expected_reason = (
                    PlanSelectionReasonCode.PRIMARY_STABLE_RANK
                    if option_index == 0 and item_index == 0
                    else PlanSelectionReasonCode.STABLE_ALTERNATIVE
                    if item_index == 0
                    else PlanSelectionReasonCode.AUXILIARY_FITS_KNOWN_ROUTE
                )
                if item.selection_reason_code is not expected_reason:
                    violations.add(PlanDraftViolationCode.FACTS_MISSING_OR_MISMATCHED)
                if item.selection_reason != SELECTION_REASON_SUMMARIES[expected_reason]:
                    violations.add(PlanDraftViolationCode.FACTS_MISSING_OR_MISMATCHED)
                if item.risks != tuple(RISK_SUMMARIES[risk] for risk in item.risk_codes):
                    violations.add(PlanDraftViolationCode.RISK_INVALID)
                if item.risk_codes != _item_risks(
                    item.price_amount,
                    budget=constraints.budget,
                    route_known=item.inbound_route.duration_seconds is not None,
                ):
                    violations.add(PlanDraftViolationCode.RISK_INVALID)
                previous_end = item.end_at
                previous_ids = item.source.collection_item_ids

            expected_amount, expected_currency = _option_cost(option.items)
            if (
                option.total_cost_amount != expected_amount
                or option.total_cost_currency != expected_currency
            ):
                violations.add(PlanDraftViolationCode.COST_TOTAL_INVALID)
            expected_risks = _option_risks(option.items, facts.weather_status)
            if option.risk_codes != expected_risks or option.risks != tuple(
                RISK_SUMMARIES[risk] for risk in expected_risks
            ):
                violations.add(PlanDraftViolationCode.RISK_INVALID)
            if (
                constraints.budget is not None
                and expected_amount is not None
                and expected_amount > constraints.budget
            ):
                violations.add(PlanDraftViolationCode.BUDGET_VIOLATED)

        if external_item_count > 1:
            violations.add(PlanDraftViolationCode.SOURCE_NOT_INCLUDED)
        return self._validation(violations)

    @staticmethod
    def _external_risks(
        candidate: ExternalDraftCandidate,
        constraints: PlanConstraints,
    ) -> tuple[PlanRiskCode, ...]:
        risks = (
            [
                PlanRiskCode.BUDGET_UNVERIFIED
                if constraints.budget is not None
                else PlanRiskCode.PRICE_UNKNOWN
            ]
            if candidate.price_amount is None
            else []
        )
        if candidate.inbound_route.duration_seconds is None:
            risks.append(PlanRiskCode.ROUTE_UNKNOWN)
        if candidate.poi.opening_hours_summary is None:
            risks.append(PlanRiskCode.OPENING_HOURS_UNKNOWN)
        return tuple(risks)

    def _schedule_external_item(
        self,
        *,
        candidate: ExternalDraftCandidate,
        role: PlanItemRole,
        earliest_departure: datetime,
        from_ids: tuple[str, ...],
        constraints: PlanConstraints,
        end_buffer_seconds: int,
        existing_items: tuple[PlanItem, ...],
    ) -> PlanItem | None:
        route = candidate.inbound_route
        if route.from_collection_item_ids != from_ids:
            return None
        risks = self._external_risks(candidate, constraints)
        reason = (
            PlanSelectionReasonCode.PRIMARY_STABLE_RANK
            if role is PlanItemRole.CORE
            else PlanSelectionReasonCode.AUXILIARY_FITS_KNOWN_ROUTE
        )
        return self._schedule_known_item(
            role=role,
            title=candidate.poi.name,
            kind=CollectionKind.PLACE,
            visit_duration_seconds=candidate.visit_duration_seconds,
            event_start_at=None,
            event_end_at=None,
            route=route,
            price_amount=candidate.price_amount,
            source=PlanItemSource(
                kind=PlanItemSourceKind.EXTERNAL_PLACE,
                concrete_poi=candidate.poi.model_copy(deep=True),
                poi_queried_at=candidate.queried_at,
                supplement_reason=candidate.supplement_reason,
                source_label="高德补充 · 未收藏",
            ),
            reason=reason,
            earliest_departure=earliest_departure,
            constraints=constraints,
            end_buffer_seconds=end_buffer_seconds,
            existing_items=existing_items,
            risk_codes=risks,
        )

    def _validate_external_item(
        self,
        *,
        item: PlanItem,
        candidate: ExternalDraftCandidate | None,
        previous_end: datetime,
        previous_ids: tuple[str, ...],
        item_index: int,
        option_index: int,
        constraints: PlanConstraints,
        expected_switch: int,
        expected_end: int,
        seen_pois: set[tuple[object, str]],
        violations: set[PlanDraftViolationCode],
    ) -> None:
        if candidate is None:
            violations.add(PlanDraftViolationCode.SOURCE_NOT_INCLUDED)
            return
        expected_role = PlanItemRole.CORE if item_index == 0 else PlanItemRole.AUXILIARY
        expected = self._schedule_external_item(
            candidate=candidate,
            role=expected_role,
            earliest_departure=previous_end
            + timedelta(seconds=expected_switch if item_index == 1 else 0),
            from_ids=previous_ids,
            constraints=constraints,
            end_buffer_seconds=expected_end,
            existing_items=(),
        )
        identity = (candidate.poi.provider, candidate.poi.poi_id)
        if identity in seen_pois:
            violations.add(PlanDraftViolationCode.DUPLICATE_POI)
        seen_pois.add(identity)
        if (
            option_index != 0
            or expected is None
            or item != expected
        ):
            violations.add(PlanDraftViolationCode.FACTS_MISSING_OR_MISMATCHED)

    @staticmethod
    def _rank_key(
        decision: CollectionCandidateDecision,
        routes: dict[tuple[tuple[str, ...], tuple[str, ...]], DraftRouteFacts],
    ) -> tuple[object, ...]:
        origin_route = routes.get(((), decision.collection_item_ids))
        route_duration = 2**63 if origin_route is None else origin_route.duration_seconds
        poi_key = (
            ("", "")
            if decision.poi_identity is None
            else (decision.poi_identity[0].value, decision.poi_identity[1])
        )
        return (
            -decision.preference_score,
            route_duration,
            _identity(decision.title),
            poi_key,
            decision.collection_item_ids,
        )

    def _schedule_item(
        self,
        *,
        decision: CollectionCandidateDecision,
        role: PlanItemRole,
        reason: PlanSelectionReasonCode,
        earliest_departure: datetime,
        from_ids: tuple[str, ...],
        constraints: PlanConstraints,
        candidate_facts: dict[tuple[str, ...], DraftCandidateFacts],
        routes: dict[tuple[tuple[str, ...], tuple[str, ...]], DraftRouteFacts],
        end_buffer_seconds: int,
        existing_items: tuple[PlanItem, ...],
    ) -> PlanItem | None:
        # Kept as a narrow helper so generation and validation share the same fact shape.
        visit = candidate_facts.get(decision.collection_item_ids)
        route = routes.get((from_ids, decision.collection_item_ids))
        if visit is None or (route is None and (from_ids or constraints.origin is not None)):
            return None
        if decision.kind is CollectionKind.PLACE and (
            visit.event_start_at is not None or visit.event_end_at is not None
        ):
            return None
        if (
            route is not None
            and constraints.transport_modes
            and route.transport_mode not in constraints.transport_modes
        ):
            return None
        if decision.any_branch_collection_item_ids and visit.poi_queried_at is None:
            return None
        if (
            from_ids == ()
            and route is not None
            and not self._origin_route_matches_decision(decision, route)
        ):
            return None
        inbound_route = PlanRouteLeg(
            from_collection_item_ids=() if route is None else route.from_collection_item_ids,
            to_collection_item_ids=decision.collection_item_ids,
            duration_seconds=None if route is None else route.duration_seconds,
            distance_meters=None if route is None else route.distance_meters,
            transport_mode=(
                route.transport_mode
                if route is not None
                else constraints.transport_modes[0]
                if constraints.transport_modes
                else TransportMode.TRANSIT
            ),
        )
        risks = _item_risks(
            decision.price_amount,
            budget=constraints.budget,
            route_known=route is not None,
        )
        return self._schedule_known_item(
            role=role,
            title=decision.title,
            kind=decision.kind,
            visit_duration_seconds=visit.visit_duration_seconds,
            event_start_at=visit.event_start_at,
            event_end_at=visit.event_end_at,
            route=inbound_route,
            price_amount=decision.price_amount,
            source=PlanItemSource(
                collection_item_ids=decision.collection_item_ids,
                any_branch_collection_item_ids=decision.any_branch_collection_item_ids,
                concrete_poi=(
                    None if decision.poi is None else decision.poi.model_copy(deep=True)
                ),
                poi_queried_at=(
                    visit.poi_queried_at if decision.any_branch_collection_item_ids else None
                ),
            ),
            reason=reason,
            earliest_departure=earliest_departure,
            constraints=constraints,
            end_buffer_seconds=end_buffer_seconds,
            existing_items=existing_items,
            risk_codes=risks,
        )

    @staticmethod
    def _schedule_known_item(
        *,
        role: PlanItemRole,
        title: str,
        kind: CollectionKind,
        visit_duration_seconds: int,
        event_start_at: datetime | None,
        event_end_at: datetime | None,
        route: PlanRouteLeg,
        price_amount: Decimal | None,
        source: PlanItemSource,
        reason: PlanSelectionReasonCode,
        earliest_departure: datetime,
        constraints: PlanConstraints,
        end_buffer_seconds: int,
        existing_items: tuple[PlanItem, ...],
        risk_codes: tuple[PlanRiskCode, ...],
    ) -> PlanItem | None:
        """Schedule every collection or external item through one rule path."""

        if constraints.transport_modes and route.transport_mode not in constraints.transport_modes:
            return None
        start_at = earliest_departure + timedelta(seconds=route.duration_seconds or 0)
        if event_start_at is not None:
            start_at = max(start_at, event_start_at)
        end_at = start_at + timedelta(seconds=visit_duration_seconds)
        if event_end_at is not None and end_at > event_end_at:
            return None
        if start_at < constraints.start_at or (
            end_at + timedelta(seconds=end_buffer_seconds) > constraints.end_at
        ):
            return None
        prices = [item.price_amount for item in existing_items]
        prices.append(price_amount)
        if constraints.budget is not None and (
            sum((price for price in prices if price is not None), Decimal())
            > constraints.budget
        ):
            return None
        return PlanItem(
            role=role,
            title=title,
            kind=kind,
            start_at=start_at,
            end_at=end_at,
            visit_duration_seconds=visit_duration_seconds,
            inbound_route=route.model_copy(deep=True),
            price_amount=price_amount,
            price_currency=None if price_amount is None else PRICE_CURRENCY_CNY,
            source=source.model_copy(deep=True),
            selection_reason_code=reason,
            selection_reason=SELECTION_REASON_SUMMARIES[reason],
            risk_codes=risk_codes,
            risks=tuple(RISK_SUMMARIES[risk] for risk in risk_codes),
        )

    @staticmethod
    def _route_matches(item: PlanRouteLeg, fact: DraftRouteFacts) -> bool:
        return (
            item.from_collection_item_ids == fact.from_collection_item_ids
            and item.to_collection_item_ids == fact.to_collection_item_ids
            and item.duration_seconds == fact.duration_seconds
            and item.distance_meters == fact.distance_meters
            and item.transport_mode is fact.transport_mode
        )

    @staticmethod
    def _origin_route_matches_decision(
        decision: CollectionCandidateDecision,
        fact: DraftRouteFacts,
    ) -> bool:
        return decision.route_duration_seconds is None or (
            decision.route_duration_seconds == fact.duration_seconds
            and (
                decision.route_distance_meters is None
                or decision.route_distance_meters == fact.distance_meters
            )
        )

    @staticmethod
    def _exclusions(collections: StructuredCollectionResult) -> tuple[PlanDraftExclusion, ...]:
        return tuple(
            PlanDraftExclusion(
                collection_item_ids=decision.collection_item_ids,
                reason_codes=decision.reason_codes,
                summaries=decision.summaries,
            )
            for decision in collections.decisions
            if decision.outcome is not CandidateOutcome.INCLUDED
        )

    @staticmethod
    def _failure(
        code: PlanDraftFailureCode,
        exclusions: tuple[PlanDraftExclusion, ...],
    ) -> PlanDraftResult:
        return PlanDraftResult(
            outcome=PlanDraftOutcome.NOT_GENERATED,
            exclusions=exclusions,
            failure_code=code,
            failure_summary=FAILURE_SUMMARIES[code],
        )

    @staticmethod
    def _validation(
        violations: set[PlanDraftViolationCode],
    ) -> PlanDraftValidation:
        ordered = tuple(code for code in PlanDraftViolationCode if code in violations)
        return PlanDraftValidation(is_valid=not ordered, violations=ordered)

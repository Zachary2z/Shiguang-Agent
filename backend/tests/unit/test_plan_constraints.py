"""M0-5A deterministic PlanConstraints contract tests."""

from __future__ import annotations

import builtins
import json
import logging
import socket
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.collections import PlanCity
from app.domain.places import Coordinate, CoordinateSystem, TransportMode
from app.domain.plans import (
    ActivityArea,
    MissingPlanConstraint,
    MissingPlanConstraintInfo,
    PlanConstraintInput,
    PlanConstraintParseError,
    PlanConstraints,
    PlanPace,
    parse_plan_constraint_input,
    parse_plan_constraint_input_json,
    parse_plan_constraints,
    parse_plan_constraints_json,
    plan_constraint_expires_at,
    plan_constraints_internal_dump,
    resolve_plan_constraints,
)

CREATED_AT = datetime(2026, 7, 23, 0, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 7, 24, 0, 0, tzinfo=UTC)
START_AT = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
END_AT = datetime(2026, 7, 25, 11, 0, tzinfo=UTC)
ACTIVE_AT = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
AREA = ActivityArea(districts=("南山区",), labels=("大学城附近",))
ORIGIN = Coordinate(
    latitude=22.599999,
    longitude=113.999999,
    coordinate_system=CoordinateSystem.GCJ_02,
)


def input_values(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "city_code": PlanCity.SHENZHEN,
        "start_at": START_AT,
        "end_at": END_AT,
        "area": AREA,
        "budget": None,
        "pace": PlanPace.RELAXED,
        "transport_modes": (TransportMode.WALKING, TransportMode.TRANSIT),
        "include": ("室内", "看展"),
        "exclude": ("日料",),
        "collection_only": False,
        "created_at": CREATED_AT,
        "expires_at": EXPIRES_AT,
    }
    values.update(changes)
    return values


def complete(**changes: Any) -> PlanConstraints:
    return PlanConstraints(**input_values(**changes))


def partial(**changes: Any) -> PlanConstraintInput:
    return PlanConstraintInput(**input_values(**changes))


def test_complete_constraints_are_explicit_strict_and_provider_neutral() -> None:
    constraints = complete()

    assert constraints.city_code is PlanCity.SHENZHEN
    assert constraints.city_scope.city_code == "shenzhen"
    assert constraints.start_at == START_AT
    assert constraints.end_at == END_AT
    assert constraints.area == AREA
    assert constraints.budget is None
    assert constraints.pace is PlanPace.RELAXED
    assert constraints.transport_modes == (TransportMode.WALKING, TransportMode.TRANSIT)
    assert constraints.include == ("室内", "看展")
    assert constraints.exclude == ("日料",)
    assert constraints.collection_only is False


def test_city_is_required_and_only_explicit_shenzhen_is_accepted() -> None:
    missing = input_values()
    del missing["city_code"]

    with pytest.raises(ValidationError):
        PlanConstraints(**missing)
    with pytest.raises(ValidationError):
        PlanConstraints(**input_values(city_code="guangzhou"))
    assert set(PlanCity) == {PlanCity.SHENZHEN}


def test_aware_datetimes_are_normalized_to_utc_without_changing_instants() -> None:
    china = timezone(timedelta(hours=8))
    constraints = complete(
        start_at=datetime(2026, 7, 25, 14, 0, tzinfo=china),
        end_at=datetime(2026, 7, 25, 19, 0, tzinfo=china),
        created_at=datetime(2026, 7, 23, 8, 0, tzinfo=china),
        expires_at=datetime(2026, 7, 24, 8, 0, tzinfo=china),
    )

    assert constraints.start_at == START_AT
    assert constraints.end_at == END_AT
    assert constraints.created_at == CREATED_AT
    assert constraints.expires_at == EXPIRES_AT
    assert all(
        value.tzinfo is UTC
        for value in (
            constraints.start_at,
            constraints.end_at,
            constraints.created_at,
            constraints.expires_at,
        )
    )


@pytest.mark.parametrize("field", ["start_at", "end_at", "created_at", "expires_at"])
def test_naive_datetimes_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        complete(**{field: datetime(2026, 7, 23, 12, 0)})


@pytest.mark.parametrize("end_at", [START_AT, START_AT - timedelta(seconds=1)])
def test_end_must_be_later_than_start(end_at: datetime) -> None:
    with pytest.raises(ValidationError, match="later than"):
        complete(end_at=end_at)


def test_exactly_24_hours_is_allowed_and_more_is_rejected() -> None:
    exact = complete(end_at=START_AT + timedelta(hours=24))

    assert exact.duration == timedelta(hours=24)
    with pytest.raises(ValidationError, match="24 hours"):
        complete(end_at=START_AT + timedelta(hours=24, microseconds=1))


def test_area_or_origin_is_required_and_each_is_sufficient_alone() -> None:
    with pytest.raises(ValidationError, match="activity area or origin"):
        complete(area=None, origin=None)

    assert complete(area=AREA, origin=None).area == AREA
    assert complete(area=None, origin=ORIGIN).origin == ORIGIN


@pytest.mark.parametrize("budget", [None, Decimal("0.00"), Decimal("245.50")])
def test_budget_preserves_null_zero_and_positive_values(budget: Decimal | None) -> None:
    assert complete(budget=budget).budget == budget


@pytest.mark.parametrize(
    "budget",
    [
        Decimal("-0.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("1000000.001"),
        True,
        0,
        10.5,
        "10.00",
    ],
)
def test_budget_rejects_negative_non_finite_imprecise_bool_and_wrong_types(
    budget: object,
) -> None:
    with pytest.raises(ValidationError):
        complete(budget=budget)


def test_transport_modes_are_unique_and_use_the_existing_domain_enum() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        complete(transport_modes=(TransportMode.TRANSIT, TransportMode.TRANSIT))
    with pytest.raises(ValidationError):
        complete(transport_modes=("public_transit",))

    assert complete(transport_modes=(TransportMode.TRANSIT,)).transport_modes == (
        TransportMode.TRANSIT,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"include": ("看展", " 看展 ")}, "unique"),
        ({"exclude": ("日料", "日料")}, "unique"),
        ({"include": ("日料",), "exclude": ("日料",)}, "must not conflict"),
        ({"include": ("Cafe",), "exclude": ("cafe",)}, "must not conflict"),
    ],
)
def test_include_and_exclude_reject_duplicates_and_conflicts(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        complete(**changes)


def test_text_values_are_bounded_non_blank_normalized_and_unique() -> None:
    area = ActivityArea(districts=(" 南山   区 ",), labels=("大学城  附近",))
    constraints = complete(area=area, include=(" 室内   活动 ",))

    assert area.districts == ("南山 区",)
    assert area.labels == ("大学城 附近",)
    assert constraints.include == ("室内 活动",)
    with pytest.raises(ValidationError):
        ActivityArea()
    with pytest.raises(ValidationError, match="blank"):
        ActivityArea(labels=("  ",))
    with pytest.raises(ValidationError, match="unique"):
        ActivityArea(districts=("南山区", " 南山区 "))
    with pytest.raises(ValidationError, match="too many"):
        ActivityArea(districts=tuple(f"区域{index}" for index in range(9)))
    with pytest.raises(ValidationError, match="too many"):
        complete(include=tuple(f"要求{index}" for index in range(17)))


@pytest.mark.parametrize("collection_only", [True, False])
def test_collection_only_accepts_only_real_booleans(collection_only: bool) -> None:
    assert complete(collection_only=collection_only).collection_only is collection_only


@pytest.mark.parametrize("collection_only", [0, 1, "false", None])
def test_collection_only_rejects_bool_like_values(collection_only: object) -> None:
    with pytest.raises(ValidationError):
        complete(collection_only=collection_only)


@pytest.mark.parametrize(
    ("start_at", "end_at", "area", "expected"),
    [
        (None, END_AT, AREA, MissingPlanConstraint.TIME_WINDOW),
        (START_AT, None, AREA, MissingPlanConstraint.TIME_WINDOW),
        (None, None, None, MissingPlanConstraint.TIME_WINDOW),
        (START_AT, END_AT, None, MissingPlanConstraint.ACTIVITY_RANGE),
    ],
)
def test_resolution_returns_one_stable_required_item(
    start_at: datetime | None,
    end_at: datetime | None,
    area: ActivityArea | None,
    expected: MissingPlanConstraint,
) -> None:
    result = resolve_plan_constraints(
        partial(start_at=start_at, end_at=end_at, area=area, origin=None),
        now=ACTIVE_AT,
    )

    assert result == MissingPlanConstraintInfo(field=expected)
    assert result.model_dump() == {"field": expected}


def test_optional_fields_never_create_missing_questions() -> None:
    result = resolve_plan_constraints(
        partial(
            budget=None,
            pace=PlanPace.BALANCED,
            transport_modes=(),
            include=(),
            exclude=(),
            collection_only=False,
        ),
        now=ACTIVE_AT,
    )

    assert isinstance(result, PlanConstraints)
    assert result.budget is None
    assert result.transport_modes == ()


def test_origin_alone_satisfies_resolution_range_requirement() -> None:
    result = resolve_plan_constraints(partial(area=None, origin=ORIGIN), now=ACTIVE_AT)

    assert isinstance(result, PlanConstraints)
    assert result.area is None
    assert result.origin == ORIGIN


def test_temporary_constraints_are_active_only_on_half_open_lifetime() -> None:
    constraints = partial()

    assert constraints.is_active(CREATED_AT)
    assert constraints.is_active(EXPIRES_AT - timedelta(microseconds=1))
    assert not constraints.is_active(CREATED_AT - timedelta(microseconds=1))
    assert not constraints.is_active(EXPIRES_AT)
    assert resolve_plan_constraints(constraints, now=EXPIRES_AT) == MissingPlanConstraintInfo(
        field=MissingPlanConstraint.TIME_WINDOW
    )


def test_constraint_lifetime_covers_complete_plan_and_only_one_partial_round() -> None:
    future_start = CREATED_AT + timedelta(days=5)
    future_end = future_start + timedelta(hours=4)

    assert plan_constraint_expires_at(
        now=CREATED_AT,
        start_at=future_start,
        end_at=future_end,
    ) == future_end + timedelta(hours=1)
    assert plan_constraint_expires_at(
        now=CREATED_AT,
        start_at=None,
        end_at=future_end,
    ) == CREATED_AT + timedelta(hours=1)


def test_invalid_temporary_lifetime_and_naive_check_time_are_rejected() -> None:
    with pytest.raises(ValidationError, match="expires_at"):
        partial(expires_at=CREATED_AT)
    with pytest.raises(ValueError, match="timezone-aware"):
        partial().is_active(datetime(2026, 7, 23, 12, 0))


def test_models_are_frozen_extra_forbidden_and_do_not_mutate_input() -> None:
    raw = input_values(
        area=ActivityArea(districts=("南山区",)),
        include=(" 室内   活动 ",),
    )
    original = deepcopy(raw)
    constraints = PlanConstraints(**raw)

    assert raw == original
    assert PlanConstraints.model_validate(constraints.model_dump()).include == ("室内 活动",)
    plan_input = PlanConstraintInput(**raw)
    input_snapshot = plan_input.model_copy(deep=True)
    assert resolve_plan_constraints(plan_input, now=ACTIVE_AT) == resolve_plan_constraints(
        plan_input,
        now=ACTIVE_AT,
    )
    assert plan_input == input_snapshot
    frozen_field = "budget"
    with pytest.raises(ValidationError):
        setattr(constraints, frozen_field, Decimal("1.00"))
    with pytest.raises(ValidationError):
        PlanConstraints(**input_values(unexpected="value"))


def test_origin_is_absent_from_repr_public_dumps_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    constraints = complete(
        area=ActivityArea(labels=("临时位置标记",)),
        origin=ORIGIN,
        include=("私人本次要求",),
        exclude=("私人排除要求",),
    )
    sensitive_values = (
        "22.599999",
        "113.999999",
        "origin",
        "临时位置标记",
        "私人本次要求",
        "私人排除要求",
    )

    dumped = constraints.model_dump()
    serialized = constraints.model_dump_json()
    rendered = repr(constraints)
    with caplog.at_level(logging.INFO):
        logging.getLogger("plan-test").info("%s", constraints)

    assert "origin" not in dumped
    assert all(value not in serialized for value in sensitive_values[:3])
    assert all(value not in rendered for value in sensitive_values)
    assert all(value not in caplog.text for value in sensitive_values)


def test_internal_projection_round_trips_origin_without_changing_public_dump() -> None:
    constraints = complete(origin=ORIGIN)

    stored = plan_constraints_internal_dump(constraints, mode="json")
    restored = parse_plan_constraints_json(json.dumps(stored))

    assert restored.origin == ORIGIN
    assert stored["origin"] == ORIGIN.model_dump(mode="json")
    assert "origin" not in constraints.model_dump(mode="json")

PRIVATE_AREA = "PRIVATE_AREA_SENTINEL"
PRIVATE_REQUIREMENT = "PRIVATE_REQUIREMENT_SENTINEL"
PRIVATE_EXCLUSION = "PRIVATE_EXCLUSION_SENTINEL"
PRIVATE_LATITUDE = "22.123456"
PRIVATE_LONGITUDE = "113.654321"
PRIVATE_ORIGIN = Coordinate(
    latitude=float(PRIVATE_LATITUDE),
    longitude=float(PRIVATE_LONGITUDE),
    coordinate_system=CoordinateSystem.GCJ_02,
)
PRIVATE_VALUES = (
    "origin",
    PRIVATE_AREA,
    PRIVATE_REQUIREMENT,
    PRIVATE_EXCLUSION,
    PRIVATE_LATITUDE,
    PRIVATE_LONGITUDE,
)


def private_python_values(**changes: object) -> dict[str, Any]:
    values = input_values(
        area=ActivityArea(labels=(PRIVATE_AREA,)),
        origin=PRIVATE_ORIGIN,
        include=(PRIVATE_REQUIREMENT,),
        exclude=(PRIVATE_EXCLUSION,),
    )
    values.update(changes)
    return values


def private_json_values(**changes: object) -> dict[str, Any]:
    values: dict[str, Any] = {
        "city_code": "shenzhen",
        "start_at": START_AT.isoformat(),
        "end_at": END_AT.isoformat(),
        "area": {"labels": [PRIVATE_AREA]},
        "origin": {
            "latitude": float(PRIVATE_LATITUDE),
            "longitude": float(PRIVATE_LONGITUDE),
            "coordinate_system": "gcj_02",
        },
        "budget": 12.34,
        "pace": "relaxed",
        "transport_modes": ["walking"],
        "include": [PRIVATE_REQUIREMENT],
        "exclude": [PRIVATE_EXCLUSION],
        "collection_only": False,
        "created_at": CREATED_AT.isoformat(),
        "expires_at": EXPIRES_AT.isoformat(),
    }
    values.update(changes)
    return values


def assert_safe_parse_failure(
    action: Callable[[], object],
    caplog: pytest.LogCaptureFixture,
    *,
    original_input: object,
) -> tuple[object, ...]:
    """Exercise every application-observable safe parse-error representation."""

    with pytest.raises(PlanConstraintParseError) as exc_info:
        action()
    error = exc_info.value
    public = error.to_dict()
    outputs = (
        str(error),
        repr(error),
        repr(error.args),
        repr(vars(error)),
        repr(public),
    )
    with caplog.at_level(logging.INFO, logger="plan-validation-test"):
        logger = logging.getLogger("plan-validation-test")
        logger.info("%s", error)
        logger.info("%r", error)

    assert all(value not in output for value in PRIVATE_VALUES for output in outputs)
    assert all(value not in caplog.text for value in PRIVATE_VALUES)
    original_representations: tuple[str, ...] = (repr(original_input),)
    if isinstance(original_input, str):
        original_representations += (original_input,)
    assert all(
        original not in output
        for original in original_representations
        for output in outputs
    )
    assert all(original not in caplog.text for original in original_representations)
    assert all(
        marker not in output
        for marker in ("input", "ctx", "errors.pydantic.dev", "ValidationError")
        for output in outputs
    )
    assert error.code == "INVALID_PLAN_CONSTRAINTS"
    assert error.summary == "Plan constraints are invalid."
    assert error.args == (error.summary,)
    assert vars(error) == {}
    assert public == {"code": error.code, "summary": error.summary}
    assert error.__cause__ is None
    assert error.__context__ is None
    with pytest.raises(AttributeError, match="frozen"):
        error.args = (PRIVATE_REQUIREMENT,)
    return (*outputs, caplog.text)


@pytest.mark.parametrize(
    "changes",
    [
        {"end_at": START_AT},
        {"end_at": START_AT + timedelta(hours=24, microseconds=1)},
        {"expires_at": CREATED_AT},
        {
            "include": (PRIVATE_REQUIREMENT,),
            "exclude": (PRIVATE_REQUIREMENT,),
        },
        {"area": None, "origin": None},
        {"budget": PRIVATE_REQUIREMENT},
        {"unexpected": PRIVATE_EXCLUSION},
    ],
    ids=(
        "invalid-time-window",
        "over-24-hours",
        "invalid-temporary-lifetime",
        "private-conflict",
        "missing-activity-range",
        "wrong-python-type",
        "extra-field",
    ),
)
def test_safe_python_parser_returns_only_fixed_failure(
    changes: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = private_python_values(**changes)
    original = deepcopy(raw)

    results: list[tuple[object, ...]] = []
    for _ in range(2):
        caplog.clear()
        results.append(
            assert_safe_parse_failure(
                lambda: parse_plan_constraints(raw),
                caplog,
                original_input=raw,
            )
        )

    assert results[0] == results[1]
    assert raw == original


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param(
            {"origin": {"latitude": 91, "longitude": 181}},
            id="invalid-nested-coordinate",
        ),
        pytest.param(
            {"unexpected": PRIVATE_EXCLUSION},
            id="extra-field",
        ),
    ],
)
def test_safe_json_parser_returns_only_fixed_failure(
    changes: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = json.dumps(private_json_values(**changes))
    original = payload

    results: list[tuple[object, ...]] = []
    for _ in range(2):
        caplog.clear()
        results.append(
            assert_safe_parse_failure(
                lambda: parse_plan_constraints_json(payload),
                caplog,
                original_input=payload,
            )
        )

    assert results[0] == results[1]
    assert payload == original


def test_safe_json_parser_redacts_malformed_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = json.dumps(private_json_values())[:-1]
    original = payload

    results: list[tuple[object, ...]] = []
    for _ in range(2):
        caplog.clear()
        results.append(
            assert_safe_parse_failure(
                lambda: parse_plan_constraints_json(payload),
                caplog,
                original_input=payload,
            )
        )

    assert results[0] == results[1]
    assert payload == original


def test_safe_input_parser_stays_safe_after_repeated_model_rebuild(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = private_python_values(expires_at=CREATED_AT)
    original = deepcopy(raw)

    results: list[tuple[object, ...]] = []
    for _ in range(2):
        assert PlanConstraintInput.model_rebuild(force=True)
        caplog.clear()
        results.append(
            assert_safe_parse_failure(
                lambda: parse_plan_constraint_input(raw),
                caplog,
                original_input=raw,
            )
        )

    assert results[0] == results[1]
    assert raw == original


def test_safe_parsers_accept_python_and_json_without_mutating_input() -> None:
    python_values = private_python_values()
    python_original = deepcopy(python_values)
    payload = json.dumps(private_json_values())
    json_original = payload

    python_results = tuple(parse_plan_constraints(python_values) for _ in range(2))
    python_inputs = tuple(parse_plan_constraint_input(python_values) for _ in range(2))
    json_results = tuple(parse_plan_constraints_json(payload) for _ in range(2))
    json_inputs = tuple(parse_plan_constraint_input_json(payload) for _ in range(2))

    assert python_results[0] == python_results[1]
    assert python_inputs[0] == python_inputs[1]
    assert json_results[0] == json_results[1]
    assert json_inputs[0] == json_inputs[1]
    assert python_values == python_original
    assert payload == json_original

    for value in (*python_results, *python_inputs, *json_results, *json_inputs):
        dumped = value.model_dump()
        serialized = value.model_dump_json()
        assert "origin" not in dumped
        assert all(item not in serialized for item in ("origin", *PRIVATE_VALUES[-2:]))

    parsed_json_values: tuple[PlanConstraints | PlanConstraintInput, ...] = (
        *json_results,
        *json_inputs,
    )
    for value in parsed_json_values:
        assert value.start_at == START_AT
        assert value.end_at == END_AT
        assert value.budget == Decimal("12.34")
        assert value.pace is PlanPace.RELAXED
        assert value.transport_modes == (TransportMode.WALKING,)


def test_resolution_has_no_network_file_database_or_provider_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("I/O is forbidden in PlanConstraints resolution")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)

    result = resolve_plan_constraints(partial(), now=ACTIVE_AT)

    assert isinstance(result, PlanConstraints)

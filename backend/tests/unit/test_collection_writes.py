"""Deterministic M0-2C write contracts and status mapping."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.collections import (
    CandidateField,
    CollectionItemPatch,
    CollectionStatus,
    EventCandidate,
    PlaceCandidate,
    Uncertainty,
    status_for_extraction_candidate,
)

NOW = datetime(2026, 7, 21, 9, 0, tzinfo=UTC)


def _common_candidate_fields() -> dict[str, object]:
    return {
        "title": "候选",
        "city_hint": "广州",
        "district": "天河区",
        "address": "体育西路 1 号",
        "business_district": "体育西",
        "landmark": "天河城",
        "metro_station": "体育西路站",
        "price_amount": Decimal("50.00"),
        "price_currency": "CNY",
        "tags": ("室内",),
    }


def test_status_mapping_never_fakes_poi_selection_and_requires_exact_event_time() -> None:
    place = PlaceCandidate(**_common_candidate_fields())
    exact_event = EventCandidate(
        **_common_candidate_fields(),
        event_start_at=NOW,
        event_end_at=NOW.replace(hour=11),
    )
    clue_event = EventCandidate(
        **_common_candidate_fields(),
        event_start_clue="周六上午",
        event_end_clue="中午前",
        missing_fields=(CandidateField.EVENT_START_AT, CandidateField.EVENT_END_AT),
    )

    assert status_for_extraction_candidate(place) is CollectionStatus.PENDING_DETAILS
    assert status_for_extraction_candidate(exact_event) is CollectionStatus.ACTIVE
    assert status_for_extraction_candidate(clue_event) is CollectionStatus.PENDING_DETAILS
    assert CollectionStatus.PENDING_SELECTION not in {
        status_for_extraction_candidate(place),
        status_for_extraction_candidate(exact_event),
        status_for_extraction_candidate(clue_event),
    }


def test_patch_contract_allowlists_only_editable_fields_and_tracks_explicit_nulls() -> None:
    patch = CollectionItemPatch(
        title="新标题",
        city_hint=None,
        district="福田区",
        address="新地址",
        business_district="中心区",
        landmark="市民中心",
        metro_station="市民中心站",
        event_start_at=NOW,
        event_end_at=NOW.replace(hour=11),
        event_start_clue="上午",
        event_end_clue="中午",
        price_amount=Decimal("0.00"),
        price_currency="CNY",
        tags=("免费",),
        missing_fields=(),
        uncertainties=(
            Uncertainty(field=CandidateField.ADDRESS, reason="入口待确认"),
        ),
    )

    assert patch.updates()["city_hint"] is None
    assert set(patch.updates()) == patch.model_fields_set

    for forbidden in (
        "id",
        "user_id",
        "kind",
        "status",
        "version",
        "created_at",
        "idempotency_key",
        "source_id",
        "undo_token",
        "city_code",
        "poi_id",
    ):
        with pytest.raises(ValidationError):
            CollectionItemPatch.model_validate({forbidden: "forbidden"})


@pytest.mark.parametrize("field", ["title", "tags", "missing_fields", "uncertainties"])
def test_patch_contract_rejects_null_for_nonnullable_editable_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        CollectionItemPatch.model_validate({field: None})

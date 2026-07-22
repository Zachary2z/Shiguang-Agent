"""Collection status vocabulary and legal transitions."""

from enum import StrEnum


class CollectionStatus(StrEnum):
    ACTIVE = "active"
    PENDING_SELECTION = "pending_selection"
    PENDING_DETAILS = "pending_details"
    VISITED = "visited"
    ARCHIVED = "archived"
    DELETED = "deleted"


class RecognitionStatus(StrEnum):
    RECOGNIZING = "recognizing"
    FAILED = "failed"


CollectionWorkflowStatus = CollectionStatus | RecognitionStatus

PERSISTABLE_COLLECTION_STATUSES = tuple(CollectionStatus)

TERMINAL_COLLECTION_STATUSES = frozenset(
    {
        CollectionStatus.VISITED,
        CollectionStatus.ARCHIVED,
        CollectionStatus.DELETED,
    }
)
TERMINAL_RECOGNITION_STATUSES = frozenset({RecognitionStatus.FAILED})

DEFAULT_COLLECTION_STATUSES = frozenset(
    {
        CollectionStatus.ACTIVE,
        CollectionStatus.PENDING_SELECTION,
        CollectionStatus.PENDING_DETAILS,
        CollectionStatus.VISITED,
    }
)

PLAN_ELIGIBLE_COLLECTION_STATUSES = frozenset({CollectionStatus.ACTIVE})

DELETABLE_COLLECTION_STATUSES = frozenset(
    {
        CollectionStatus.ACTIVE,
        CollectionStatus.PENDING_SELECTION,
        CollectionStatus.PENDING_DETAILS,
    }
)

_ALLOWED_TRANSITIONS: dict[
    CollectionWorkflowStatus,
    frozenset[CollectionWorkflowStatus],
] = {
    RecognitionStatus.RECOGNIZING: frozenset(
        {
            CollectionStatus.ACTIVE,
            CollectionStatus.PENDING_SELECTION,
            CollectionStatus.PENDING_DETAILS,
            RecognitionStatus.FAILED,
        }
    ),
    CollectionStatus.ACTIVE: frozenset(
        {
            CollectionStatus.VISITED,
            CollectionStatus.ARCHIVED,
            CollectionStatus.DELETED,
        }
    ),
    CollectionStatus.PENDING_SELECTION: frozenset(
        {
            CollectionStatus.ACTIVE,
            CollectionStatus.PENDING_DETAILS,
            CollectionStatus.DELETED,
        }
    ),
    CollectionStatus.PENDING_DETAILS: frozenset(
        {
            RecognitionStatus.RECOGNIZING,
            CollectionStatus.PENDING_SELECTION,
            CollectionStatus.DELETED,
        }
    ),
}


def ensure_collection_transition(
    current: CollectionWorkflowStatus,
    target: CollectionWorkflowStatus,
) -> None:
    """Validate recognition outcomes and persisted collection transitions."""

    if current is target:
        return
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ValueError(
            f"illegal collection workflow transition: {current.value} -> {target.value}"
        )


def ensure_persistable_collection_status(status: CollectionWorkflowStatus) -> None:
    """Keep recognition progress and failures outside CollectionItem storage."""

    if not isinstance(status, CollectionStatus):
        raise ValueError(
            "recognizing and failed outcomes cannot be persisted as CollectionItem"
        )


def is_collection_visible_by_default(status: CollectionStatus) -> bool:
    return status in DEFAULT_COLLECTION_STATUSES


def can_collection_enter_plan(status: CollectionStatus) -> bool:
    return status in PLAN_ELIGIBLE_COLLECTION_STATUSES

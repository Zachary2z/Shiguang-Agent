"""Collection status vocabulary and legal transitions."""

from enum import StrEnum


class CollectionStatus(StrEnum):
    RECOGNIZING = "recognizing"
    ACTIVE = "active"
    PENDING_SELECTION = "pending_selection"
    PENDING_DETAILS = "pending_details"
    FAILED = "failed"
    VISITED = "visited"
    ARCHIVED = "archived"
    DELETED = "deleted"


PERSISTABLE_COLLECTION_STATUSES = tuple(
    status for status in CollectionStatus if status is not CollectionStatus.FAILED
)

TERMINAL_COLLECTION_STATUSES = frozenset(
    {
        CollectionStatus.FAILED,
        CollectionStatus.VISITED,
        CollectionStatus.ARCHIVED,
        CollectionStatus.DELETED,
    }
)

DEFAULT_COLLECTION_STATUSES = frozenset(
    {
        CollectionStatus.ACTIVE,
        CollectionStatus.PENDING_SELECTION,
        CollectionStatus.PENDING_DETAILS,
        CollectionStatus.VISITED,
    }
)

PLAN_ELIGIBLE_COLLECTION_STATUSES = frozenset({CollectionStatus.ACTIVE})

_ALLOWED_TRANSITIONS = {
    CollectionStatus.RECOGNIZING: frozenset(
        {
            CollectionStatus.ACTIVE,
            CollectionStatus.PENDING_SELECTION,
            CollectionStatus.PENDING_DETAILS,
            CollectionStatus.FAILED,
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
        {CollectionStatus.RECOGNIZING, CollectionStatus.DELETED}
    ),
}


def ensure_collection_transition(
    current: CollectionStatus,
    target: CollectionStatus,
) -> None:
    """Allow idempotent writes and reject regressions, skips, and terminal exits."""

    if current is target:
        return
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ValueError(
            f"illegal CollectionItem transition: {current.value} -> {target.value}"
        )


def ensure_persistable_collection_status(status: CollectionStatus) -> None:
    """Reject recognition failures at every CollectionItem write boundary."""

    if status not in PERSISTABLE_COLLECTION_STATUSES:
        raise ValueError("failed recognition outcomes cannot be persisted as CollectionItem")


def is_collection_visible_by_default(status: CollectionStatus) -> bool:
    return status in DEFAULT_COLLECTION_STATUSES


def can_collection_enter_plan(status: CollectionStatus) -> bool:
    return status in PLAN_ELIGIBLE_COLLECTION_STATUSES

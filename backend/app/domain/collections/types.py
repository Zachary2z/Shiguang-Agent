"""Small collection vocabularies that do not depend on collection entities."""

from enum import StrEnum


class CollectionKind(StrEnum):
    PLACE = "place"
    EVENT = "event"

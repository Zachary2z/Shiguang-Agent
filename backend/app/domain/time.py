"""UTC helpers shared by domain and persistence code."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize storage timestamps, interpreting SQLite's naive values as UTC."""

    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def required_utc(value: datetime) -> datetime:
    normalized = as_utc(value)
    assert normalized is not None
    return normalized


def require_aware_utc(value: datetime) -> datetime:
    """Validate an application timestamp before it reaches persistence."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("application timestamps must be timezone-aware")
    return value.astimezone(UTC)

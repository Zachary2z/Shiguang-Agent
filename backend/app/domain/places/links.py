"""Safe recognition of public Amap place links inside the unified URL boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs

from app.domain.web.security import UrlPolicyError, validate_web_url

_AMAP_PUBLIC_HOSTS = frozenset(
    {"www.amap.com", "ditu.amap.com", "uri.amap.com", "surl.amap.com"}
)
_AMAP_POI_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{5,127}$")
_SENSITIVE_QUERY_NAMES = frozenset(
    {"key", "apikey", "api_key", "access_token", "authorization"}
)


@dataclass(frozen=True, slots=True)
class AmapOfficialLink:
    """Safe classification only; it never retains arbitrary page content."""

    is_official: bool
    poi_id: str | None = None
    has_sensitive_query: bool = False


def inspect_amap_official_link(url: str) -> AmapOfficialLink:
    """Recognize an explicit official host and extract only an unambiguous POI ID."""

    try:
        target = validate_web_url(url)
    except UrlPolicyError:
        return AmapOfficialLink(is_official=False)
    if target.hostname not in _AMAP_PUBLIC_HOSTS:
        return AmapOfficialLink(is_official=False)
    try:
        query = parse_qs(
            target.query,
            keep_blank_values=True,
            max_num_fields=30,
        )
    except ValueError:
        return AmapOfficialLink(is_official=True)
    if any(name.casefold() in _SENSITIVE_QUERY_NAMES for name in query):
        return AmapOfficialLink(is_official=True, has_sensitive_query=True)

    candidates: list[str] = []
    segments = tuple(segment for segment in target.path.split("/") if segment)
    if (
        target.hostname in {"www.amap.com", "ditu.amap.com"}
        and len(segments) == 2
        and segments[0] == "place"
    ):
        candidates.append(segments[1])
    if target.hostname == "uri.amap.com" and target.path.rstrip("/") == "/marker":
        candidates.extend(query.get("poiid", ()))
    valid = tuple(value for value in candidates if _AMAP_POI_ID.fullmatch(value))
    poi_id = valid[0] if len(valid) == 1 and len(candidates) == 1 else None
    return AmapOfficialLink(is_official=True, poi_id=poi_id)


__all__ = ["AmapOfficialLink", "inspect_amap_official_link"]

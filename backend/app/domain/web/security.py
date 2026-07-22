"""The single URL normalization, DNS validation, and SSRF policy for web fetching."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", flags=re.ASCII)
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DOTTED_NUMERIC = re.compile(r"^[0-9.]+$", flags=re.ASCII)
_HEX_OR_OCTET = re.compile(r"^(?:0[xX][0-9A-Fa-f]+|0[0-9]+)$", flags=re.ASCII)

_BLOCKED_HOSTS = {
    "instance-data",
    "instance-data.ec2.internal",
    "ip6-localhost",
    "ip6-loopback",
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.azure.internal",
    "metadata.google.internal",
}
_BLOCKED_SUFFIXES = (".internal", ".local", ".localhost", ".home.arpa")


class UrlPolicyErrorCode(str):
    INVALID = "invalid"
    BLOCKED = "blocked"


class UrlPolicyError(ValueError):
    """Fixed internal signal that deliberately retains no source URL or hostname."""

    def __init__(self, code: str) -> None:
        if code not in {UrlPolicyErrorCode.INVALID, UrlPolicyErrorCode.BLOCKED}:
            raise ValueError("unknown URL policy error code")
        super().__init__("web URL rejected")
        self.code = code


class Resolver(Protocol):
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]: ...


@dataclass(frozen=True, repr=False)
class ValidatedWebUrl:
    normalized_url: str
    scheme: str
    hostname: str
    port: int
    path: str
    query: str
    literal_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None


@dataclass(frozen=True, repr=False)
class BoundWebTarget:
    logical: ValidatedWebUrl
    address: ipaddress.IPv4Address | ipaddress.IPv6Address
    request_url: str
    host_header: str
    sni_hostname: str | None


def validate_web_url(value: str) -> ValidatedWebUrl:
    """Normalize one HTTP(S) URL and reject ambiguous syntax or literal unsafe targets."""

    if not isinstance(value, str) or not value or len(value) > 2048:
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)
    if _contains_unsafe_character(value) or "\\" in value or _BAD_PERCENT_ESCAPE.search(value):
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID) from None

    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.netloc or parts.hostname is None:
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)
    if parts.username is not None or parts.password is not None:
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)
    expected_port = 80 if scheme == "http" else 443
    if port is not None and port != expected_port:
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)

    hostname, literal_ip = _normalize_hostname(parts.hostname)
    _reject_blocked_hostname(hostname, literal_ip)
    path = parts.path or "/"
    normalized = urlunsplit((scheme, _format_authority(hostname), path, parts.query, ""))
    return ValidatedWebUrl(
        normalized_url=normalized,
        scheme=scheme,
        hostname=hostname,
        port=expected_port,
        path=path,
        query=parts.query,
        literal_ip=literal_ip,
    )


def validate_resolved_addresses(
    target: ValidatedWebUrl,
    addresses: tuple[str, ...],
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    """Reject the whole DNS answer if any address is malformed or not globally routable."""

    if not addresses:
        raise UrlPolicyError(UrlPolicyErrorCode.BLOCKED)
    normalized: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            raise UrlPolicyError(UrlPolicyErrorCode.BLOCKED) from None
        _reject_unsafe_ip(address)
        if address not in normalized:
            normalized.append(address)
    if target.literal_ip is not None and normalized != [target.literal_ip]:
        raise UrlPolicyError(UrlPolicyErrorCode.BLOCKED)
    return tuple(normalized)


def bind_web_target(
    target: ValidatedWebUrl,
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> BoundWebTarget:
    """Pin the actual connection to a validated IP while preserving Host and TLS SNI."""

    _reject_unsafe_ip(address)
    ip_authority = f"[{address.compressed}]" if address.version == 6 else address.compressed
    request_url = urlunsplit(
        (target.scheme, ip_authority, target.path, target.query, "")
    )
    host_authority = _format_authority(target.hostname)
    return BoundWebTarget(
        logical=target,
        address=address,
        request_url=request_url,
        host_header=host_authority,
        sni_hostname=target.hostname if target.scheme == "https" else None,
    )


def _normalize_hostname(
    raw_hostname: str,
) -> tuple[str, ipaddress.IPv4Address | ipaddress.IPv6Address | None]:
    hostname = raw_hostname.rstrip(".").lower()
    if not hostname or len(hostname) > 253 or "%" in hostname:
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return literal.compressed, literal

    if _looks_like_ambiguous_ip(hostname):
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID) from None
    labels = ascii_hostname.split(".")
    if any(_DNS_LABEL.fullmatch(label) is None for label in labels):
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)
    return ascii_hostname, None


def _looks_like_ambiguous_ip(hostname: str) -> bool:
    if hostname.isdecimal() or hostname.lower().startswith("0x"):
        return True
    labels = hostname.split(".")
    if any(_HEX_OR_OCTET.fullmatch(label) for label in labels):
        return True
    return bool(_DOTTED_NUMERIC.fullmatch(hostname))


def _reject_blocked_hostname(
    hostname: str,
    literal_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None,
) -> None:
    if hostname in _BLOCKED_HOSTS or hostname.endswith(_BLOCKED_SUFFIXES):
        raise UrlPolicyError(UrlPolicyErrorCode.BLOCKED)
    if literal_ip is not None:
        _reject_unsafe_ip(literal_ip)


def _reject_unsafe_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        raise UrlPolicyError(UrlPolicyErrorCode.BLOCKED)
    if (
        not address.is_global
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        raise UrlPolicyError(UrlPolicyErrorCode.BLOCKED)


def _format_authority(hostname: str) -> str:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname
    return f"[{address.compressed}]" if address.version == 6 else address.compressed


def _contains_unsafe_character(value: str) -> bool:
    return any(char.isspace() or unicodedata.category(char) in {"Cc", "Cf"} for char in value)


def split_for_redirect(base: ValidatedWebUrl, location: str) -> str:
    """Resolve a redirect reference without allowing URL parser authority confusion."""

    from urllib.parse import urljoin

    if (
        not isinstance(location, str)
        or not location
        or _contains_unsafe_character(location)
        or "\\" in location
        or _BAD_PERCENT_ESCAPE.search(location)
    ):
        raise UrlPolicyError(UrlPolicyErrorCode.INVALID)
    return urljoin(base.normalized_url, location)


def safe_canonical_url(base_url: str, value: str) -> str | None:
    """Resolve allowlisted canonical metadata but never fetch it or expose unsafe targets."""

    try:
        base = validate_web_url(base_url)
        return validate_web_url(split_for_redirect(base, value)).normalized_url
    except UrlPolicyError:
        return None

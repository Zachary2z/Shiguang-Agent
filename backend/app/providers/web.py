"""The single safe public web retrieval Provider and its httpx implementation."""

from __future__ import annotations

import asyncio
import codecs
import re
import socket
import zlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Protocol, Self

import httpx
from bs4 import BeautifulSoup  # type: ignore[import-untyped]
from bs4.element import Tag  # type: ignore[import-untyped]

from app.domain.web import (
    WebFetchDiagnostics,
    WebFetchFailure,
    WebFetchFailureCode,
    WebFetchResult,
    WebPageContent,
    WebPageMetadata,
)
from app.domain.web.security import (
    BoundWebTarget,
    Resolver,
    UrlPolicyError,
    UrlPolicyErrorCode,
    ValidatedWebUrl,
    bind_web_target,
    safe_canonical_url,
    split_for_redirect,
    validate_resolved_addresses,
    validate_web_url,
)

SUPPORTED_WEB_CONTENT_TYPES = frozenset(
    {"text/html", "application/xhtml+xml", "text/plain"}
)
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_META_CHARSET = re.compile(
    rb"<meta\s+[^>]*charset\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)",
    flags=re.IGNORECASE,
)
_WHITESPACE = re.compile(r"[ \t\f\v]+")
_SAFE_ENCODINGS = {
    "ascii": "ascii",
    "big5": "big5",
    "gb18030": "gb18030",
    "gb2312": "gb18030",
    "gbk": "gb18030",
    "iso-8859-1": "windows-1252",
    "latin-1": "windows-1252",
    "latin1": "windows-1252",
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "utf-16": "utf-16",
    "utf-16be": "utf-16-be",
    "utf-16le": "utf-16-le",
    "windows-1252": "windows-1252",
}


class _StreamingDecompressor(Protocol):
    @property
    def unconsumed_tail(self) -> bytes: ...

    @property
    def unused_data(self) -> bytes: ...

    @property
    def eof(self) -> bool: ...

    def decompress(self, data: bytes, max_length: int = 0, /) -> bytes: ...

    def flush(self, length: int = 0, /) -> bytes: ...


@dataclass(frozen=True)
class WebFetchConfig:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    total_timeout_seconds: float = 20.0
    max_redirects: int = 5
    max_response_bytes: int = 2_000_000
    max_text_characters: int = 50_000

    def __post_init__(self) -> None:
        for value in (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.total_timeout_seconds,
        ):
            if isinstance(value, bool) or not isfinite(value) or value <= 0:
                raise ValueError("web timeouts must be finite positive numbers")
        if self.total_timeout_seconds > 20:
            raise ValueError("web total timeout cannot exceed 20 seconds")
        if isinstance(self.max_redirects, bool) or not 0 <= self.max_redirects <= 5:
            raise ValueError("web redirect limit must be between zero and five")
        if (
            isinstance(self.max_response_bytes, bool)
            or not 1 <= self.max_response_bytes <= 2_000_000
        ):
            raise ValueError("web response limit is invalid")
        if (
            isinstance(self.max_text_characters, bool)
            or not 1 <= self.max_text_characters <= 50_000
        ):
            raise ValueError("web text limit is invalid")

    def timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.connect_timeout_seconds,
            pool=self.connect_timeout_seconds,
        )


class WebContentProvider(ABC):
    """Fetch and parse one public page without persistence or input-workflow behavior."""

    @abstractmethod
    async def fetch(self, url: str) -> WebFetchResult:
        """Return safe content or an explicit recoverable failure."""


class SystemHostResolver:
    """Production resolver; tests replace this with deterministic offline stubs."""

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        return tuple(str(sockaddr[0]) for _, _, _, _, sockaddr in records)


def create_web_http_client(
    *,
    config: WebFetchConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Create a zero-retry client that ignores environment proxies, auth, and cookies."""

    active_config = config or WebFetchConfig()
    active_transport = transport or httpx.AsyncHTTPTransport(
        trust_env=False,
        retries=0,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=0),
    )
    return httpx.AsyncClient(
        transport=active_transport,
        trust_env=False,
        follow_redirects=False,
        timeout=active_config.timeout(),
        headers={},
        cookies=None,
        auth=None,
    )


class HttpxWebContentProvider(WebContentProvider):
    """SSRF-safe httpx fetcher with explicit redirects and one BeautifulSoup extractor."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        resolver: Resolver,
        config: WebFetchConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(http_client, httpx.AsyncClient):
            raise TypeError("http_client must be an httpx.AsyncClient")
        self._http_client = http_client
        self._resolver = resolver
        self._config = config or WebFetchConfig()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def fetch(self, url: str) -> WebFetchResult:
        try:
            async with asyncio.timeout(self._config.total_timeout_seconds):
                return await self._fetch_within_budget(url)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return WebFetchFailure.for_code(WebFetchFailureCode.TIMEOUT)
        except Exception:
            return WebFetchFailure.for_code(WebFetchFailureCode.UNKNOWN)

    async def _fetch_within_budget(self, url: str) -> WebFetchResult:
        try:
            original = validate_web_url(url)
        except UrlPolicyError as exc:
            code = (
                WebFetchFailureCode.TARGET_BLOCKED
                if exc.code == UrlPolicyErrorCode.BLOCKED
                else WebFetchFailureCode.INVALID_URL
            )
            return WebFetchFailure.for_code(code)

        current = original
        visited: set[str] = set()
        redirect_count = 0
        while True:
            if current.normalized_url in visited:
                return WebFetchFailure.for_code(WebFetchFailureCode.REDIRECT_LOOP)
            visited.add(current.normalized_url)

            target_or_failure = await self._resolve_and_bind(current)
            if isinstance(target_or_failure, WebFetchFailure):
                if (
                    redirect_count > 0
                    and target_or_failure.code is WebFetchFailureCode.TARGET_BLOCKED
                ):
                    return WebFetchFailure.for_code(WebFetchFailureCode.REDIRECT_BLOCKED)
                return target_or_failure
            response_or_failure = await self._send_once(target_or_failure)
            if isinstance(response_or_failure, WebFetchFailure):
                return response_or_failure

            response = response_or_failure
            try:
                if response.status_code in REDIRECT_STATUSES:
                    if redirect_count >= self._config.max_redirects:
                        return WebFetchFailure.for_code(WebFetchFailureCode.REDIRECT_LIMIT)
                    location = _single_header(response.headers, "location")
                    if location is None:
                        return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
                    try:
                        next_url = validate_web_url(split_for_redirect(current, location))
                    except UrlPolicyError:
                        return WebFetchFailure.for_code(WebFetchFailureCode.REDIRECT_BLOCKED)
                    redirect_count += 1
                    current = next_url
                    continue

                if not 200 <= response.status_code <= 299:
                    status = response.status_code if 400 <= response.status_code <= 599 else None
                    if status is None:
                        return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
                    return WebFetchFailure.for_code(
                        WebFetchFailureCode.HTTP_STATUS,
                        http_status=status,
                    )

                parsed_type = _parse_content_type(response.headers)
                if isinstance(parsed_type, WebFetchFailure):
                    return parsed_type
                media_type, charset = parsed_type
                body_or_failure = await _read_limited_body(response, self._config)
                if isinstance(body_or_failure, WebFetchFailure):
                    return body_or_failure
                decoded_or_failure = _decode_body(body_or_failure, media_type, charset)
                if isinstance(decoded_or_failure, WebFetchFailure):
                    return decoded_or_failure
                extracted_or_failure = _extract_content(
                    decoded_or_failure,
                    media_type=media_type,
                    final_url=current.normalized_url,
                    max_text_characters=self._config.max_text_characters,
                )
                if isinstance(extracted_or_failure, WebFetchFailure):
                    return extracted_or_failure
                title, text, metadata, truncated = extracted_or_failure
                return WebPageContent(
                    normalized_url=original.normalized_url,
                    final_url=current.normalized_url,
                    title=title,
                    text=text,
                    metadata=metadata,
                    content_type=media_type,
                    fetched_at=self._clock(),
                    diagnostics=WebFetchDiagnostics(
                        http_status=response.status_code,
                        redirect_count=redirect_count,
                        decoded_byte_size=len(body_or_failure),
                        text_truncated=truncated,
                    ),
                )
            finally:
                await response.aclose()

    async def _resolve_and_bind(
        self,
        target: ValidatedWebUrl,
    ) -> BoundWebTarget | WebFetchFailure:
        if target.literal_ip is not None:
            addresses: tuple[str, ...] = (target.literal_ip.compressed,)
        else:
            try:
                addresses = await self._resolver.resolve(target.hostname, target.port)
            except asyncio.CancelledError:
                raise
            except Exception:
                return WebFetchFailure.for_code(WebFetchFailureCode.DNS_FAILED)
        if not addresses:
            return WebFetchFailure.for_code(WebFetchFailureCode.DNS_FAILED)
        try:
            validated = validate_resolved_addresses(target, addresses)
            return bind_web_target(target, validated[0])
        except UrlPolicyError:
            return WebFetchFailure.for_code(WebFetchFailureCode.TARGET_BLOCKED)

    async def _send_once(
        self,
        target: BoundWebTarget,
    ) -> httpx.Response | WebFetchFailure:
        headers = {
            "Accept": "text/html, application/xhtml+xml, text/plain;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
            "Host": target.host_header,
            "User-Agent": "Shiguang-WebFetcher/0.1",
        }
        extensions: dict[str, object] = {}
        if target.sni_hostname is not None:
            extensions["sni_hostname"] = target.sni_hostname
        request = httpx.Request(
            "GET",
            target.request_url,
            headers=headers,
            extensions=extensions,
        )
        try:
            return await self._http_client.send(
                request,
                stream=True,
                auth=None,
                follow_redirects=False,
            )
        except asyncio.CancelledError:
            raise
        except httpx.DecodingError:
            return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
        except httpx.TimeoutException:
            return WebFetchFailure.for_code(WebFetchFailureCode.TIMEOUT)
        except (httpx.NetworkError, httpx.RemoteProtocolError):
            return WebFetchFailure.for_code(WebFetchFailureCode.CONNECTION_FAILED)
        except httpx.HTTPError:
            return WebFetchFailure.for_code(WebFetchFailureCode.CONNECTION_FAILED)


def _single_header(headers: httpx.Headers, name: str) -> str | None:
    values = headers.get_list(name)
    if len(values) != 1:
        return None
    value = values[0].strip()
    return value or None


def _parse_content_type(
    headers: httpx.Headers,
) -> tuple[str, str | None] | WebFetchFailure:
    content_types = headers.get_list("content-type")
    if not content_types:
        return WebFetchFailure.for_code(WebFetchFailureCode.CONTENT_TYPE_UNSUPPORTED)
    if len(content_types) != 1 or not content_types[0].strip():
        return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
    raw = content_types[0].strip()
    pieces = [piece.strip() for piece in raw.split(";")]
    media_type = pieces[0].lower()
    if media_type not in SUPPORTED_WEB_CONTENT_TYPES:
        return WebFetchFailure.for_code(WebFetchFailureCode.CONTENT_TYPE_UNSUPPORTED)
    charset: str | None = None
    for parameter in pieces[1:]:
        if not parameter:
            continue
        key, separator, value = parameter.partition("=")
        if not separator:
            return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
        if key.strip().lower() != "charset":
            continue
        candidate = value.strip().strip('"\'').lower()
        normalized = _SAFE_ENCODINGS.get(candidate)
        if normalized is None or (charset is not None and normalized != charset):
            return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
        charset = normalized
    return media_type, charset


async def _read_limited_body(
    response: httpx.Response,
    config: WebFetchConfig,
) -> bytes | WebFetchFailure:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
        if declared < 0:
            return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
        if declared > config.max_response_bytes:
            return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_TOO_LARGE)

    encodings = response.headers.get_list("content-encoding")
    encoding = "identity"
    if encodings:
        tokens = [token.strip().lower() for item in encodings for token in item.split(",")]
        if len(tokens) != 1 or tokens[0] not in {"identity", "gzip", "deflate"}:
            return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
        encoding = tokens[0]

    decompressor: _StreamingDecompressor | None = None
    if encoding == "gzip":
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif encoding == "deflate":
        decompressor = zlib.decompressobj()

    output = bytearray()
    wire_bytes = 0
    try:
        async for chunk in _raw_chunks(response):
            wire_bytes += len(chunk)
            if wire_bytes > config.max_response_bytes:
                return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_TOO_LARGE)
            if decompressor is None:
                if len(output) + len(chunk) > config.max_response_bytes:
                    return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_TOO_LARGE)
                output.extend(chunk)
                continue
            remaining = config.max_response_bytes - len(output)
            decoded = decompressor.decompress(chunk, remaining + 1)
            if len(decoded) > remaining or decompressor.unconsumed_tail:
                return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_TOO_LARGE)
            output.extend(decoded)
        if decompressor is not None:
            remaining = config.max_response_bytes - len(output)
            tail = decompressor.flush(remaining + 1)
            if len(tail) > remaining or not decompressor.eof or decompressor.unused_data:
                return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
            output.extend(tail)
    except asyncio.CancelledError:
        raise
    except (httpx.HTTPError, zlib.error):
        return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
    if not output:
        return WebFetchFailure.for_code(WebFetchFailureCode.CONTENT_UNREADABLE)
    return bytes(output)


async def _raw_chunks(response: httpx.Response) -> AsyncIterator[bytes]:
    """Support normal streaming plus MockTransport's already-buffered fixed fixtures."""

    if response.is_stream_consumed:
        yield response.content
        return
    async for chunk in response.aiter_raw():
        yield chunk


def _decode_body(
    body: bytes,
    media_type: str,
    header_charset: str | None,
) -> str | WebFetchFailure:
    bom_encoding: str | None = None
    if body.startswith(codecs.BOM_UTF8):
        bom_encoding = "utf-8-sig"
    elif body.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        bom_encoding = "utf-16"

    meta_encoding: str | None = None
    if media_type != "text/plain":
        match = _META_CHARSET.search(body[:4096])
        if match is not None:
            try:
                raw_meta = match.group(1).decode("ascii").lower()
            except UnicodeDecodeError:
                return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
            meta_encoding = _SAFE_ENCODINGS.get(raw_meta)
            if meta_encoding is None:
                return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)

    comparable_bom = "utf-8" if bom_encoding == "utf-8-sig" else bom_encoding
    declared = [value for value in (header_charset, comparable_bom, meta_encoding) if value]
    if declared and any(value != declared[0] for value in declared[1:]):
        return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
    encoding = bom_encoding or header_charset or meta_encoding or "utf-8"
    try:
        return body.decode(encoding, errors="strict")
    except (LookupError, UnicodeDecodeError):
        return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)


def _extract_content(
    decoded: str,
    *,
    media_type: str,
    final_url: str,
    max_text_characters: int,
) -> tuple[str, str, WebPageMetadata, bool] | WebFetchFailure:
    if media_type == "text/plain":
        normalized = _normalize_text(decoded)
        if not normalized:
            return WebFetchFailure.for_code(WebFetchFailureCode.CONTENT_UNREADABLE)
        text, truncated = _truncate(normalized, max_text_characters)
        return "", text, WebPageMetadata(), truncated

    try:
        soup = BeautifulSoup(decoded, "html.parser")
        for tag in soup.find_all(
            ["script", "style", "nav", "header", "footer", "aside", "noscript", "template", "svg"]
        ):
            tag.decompose()
        for tag in soup.find_all(True):
            if _is_hidden(tag):
                tag.decompose()

        title = _limited_text(soup.title.get_text(" ", strip=True) if soup.title else "", 300) or ""
        metadata = _extract_metadata(soup, final_url)
        main = soup.find("article") or soup.find("main") or soup.find(attrs={"role": "main"})
        if main is None and soup.body is None:
            for tag in soup.find_all(["head", "title", "meta", "link"]):
                tag.decompose()
        root = main or soup.body or soup
        text_value = _normalize_text(root.get_text("\n", strip=True))
    except Exception:
        return WebFetchFailure.for_code(WebFetchFailureCode.RESPONSE_MALFORMED)
    if not text_value:
        return WebFetchFailure.for_code(WebFetchFailureCode.CONTENT_UNREADABLE)
    text, truncated = _truncate(text_value, max_text_characters)
    return title, text, metadata, truncated


def _extract_metadata(soup: BeautifulSoup, final_url: str) -> WebPageMetadata:
    canonical: str | None = None
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    if isinstance(canonical_tag, Tag):
        href = canonical_tag.get("href")
        if isinstance(href, str):
            canonical = safe_canonical_url(final_url, href)
    return WebPageMetadata(
        description=_meta_content(soup, name="description", limit=1000),
        canonical_url=canonical,
        open_graph_title=_meta_content(soup, property_name="og:title", limit=300),
        open_graph_description=_meta_content(
            soup,
            property_name="og:description",
            limit=1000,
        ),
        open_graph_site_name=_meta_content(soup, property_name="og:site_name", limit=200),
    )


def _meta_content(
    soup: BeautifulSoup,
    *,
    name: str | None = None,
    property_name: str | None = None,
    limit: int,
) -> str | None:
    attrs = {"name": name} if name is not None else {"property": property_name}
    tag = soup.find("meta", attrs=attrs)
    if not isinstance(tag, Tag):
        return None
    content = tag.get("content")
    return _limited_text(content, limit) if isinstance(content, str) else None


def _is_hidden(tag: Tag) -> bool:
    if tag.has_attr("hidden") or str(tag.get("aria-hidden", "")).lower() == "true":
        return True
    style = re.sub(r"\s+", "", str(tag.get("style", "")).lower())
    return "display:none" in style or "visibility:hidden" in style


def _limited_text(value: str, limit: int) -> str | None:
    normalized = _normalize_text(value)
    return normalized[:limit] if normalized else None


def _normalize_text(value: str) -> str:
    lines: list[str] = []
    for raw_line in value.splitlines():
        line = _WHITESPACE.sub(" ", raw_line).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return "\n".join(lines)


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    return (value, False) if len(value) <= limit else (value[:limit], True)

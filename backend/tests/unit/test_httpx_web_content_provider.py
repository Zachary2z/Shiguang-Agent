from __future__ import annotations

import asyncio
import gzip
import json
import logging
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.domain.web import WebFetchFailure, WebFetchFailureCode, WebPageContent
from app.providers.web import (
    HttpxWebContentProvider,
    WebFetchConfig,
    create_web_http_client,
)

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
PUBLIC_V4 = "93.184.216.34"
SECOND_PUBLIC_V4 = "8.8.8.8"

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


class StubResolver:
    def __init__(
        self,
        answers: dict[str, tuple[str, ...] | BaseException] | None = None,
    ) -> None:
        self.answers = answers or {"example.com": (PUBLIC_V4,)}
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.calls.append((hostname, port))
        answer = self.answers.get(hostname, (PUBLIC_V4,))
        if isinstance(answer, BaseException):
            raise answer
        return answer


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connect_timeout_seconds": 0},
        {"read_timeout_seconds": float("inf")},
        {"total_timeout_seconds": 20.001},
        {"max_redirects": 6},
        {"max_redirects": True},
        {"max_response_bytes": 2_000_001},
        {"max_text_characters": 50_001},
    ],
)
def test_fetch_config_enforces_hard_upper_bounds(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WebFetchConfig(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    ["max_redirects", "max_response_bytes", "max_text_characters"],
)
@pytest.mark.parametrize(
    "value",
    [1.0, 1.5, Decimal("1"), "1", True, float("nan"), float("inf")],
)
def test_fetch_config_integer_limits_reject_non_exact_ints(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        WebFetchConfig(**{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    ["connect_timeout_seconds", "read_timeout_seconds", "total_timeout_seconds"],
)
@pytest.mark.parametrize(
    "value",
    [True, Decimal("1"), "1", float("nan"), float("inf"), float("-inf")],
)
def test_fetch_config_timeouts_reject_non_numeric_or_non_finite_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="web timeouts must be finite positive numbers"):
        WebFetchConfig(**{field: value})  # type: ignore[arg-type]


def test_fetch_config_timeouts_accept_finite_ints_and_floats() -> None:
    config = WebFetchConfig(
        connect_timeout_seconds=1,
        read_timeout_seconds=2.5,
        total_timeout_seconds=3,
    )
    assert config.connect_timeout_seconds == 1
    assert config.read_timeout_seconds == 2.5
    assert config.total_timeout_seconds == 3


async def fetch_with(
    url: str,
    handler: Handler,
    *,
    resolver: StubResolver | None = None,
    config: WebFetchConfig | None = None,
) -> tuple[WebPageContent | WebFetchFailure, StubResolver]:
    transport = httpx.MockTransport(handler)
    client = create_web_http_client(config=config, transport=transport)
    active_resolver = resolver or StubResolver()
    provider = HttpxWebContentProvider(
        http_client=client,
        resolver=active_resolver,
        config=config,
        clock=lambda: NOW,
    )
    try:
        return await provider.fetch(url), active_resolver
    finally:
        await provider.aclose()


def html_response(
    html: str | bytes,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    active_headers = {"Content-Type": "text/html; charset=utf-8"}
    if headers:
        active_headers.update(headers)
    return httpx.Response(status, headers=active_headers, content=html)


@pytest.mark.asyncio
async def test_fetches_html_metadata_and_clean_body_through_pinned_connection() -> None:
    seen: list[httpx.Request] = []
    html = """
    <html><head>
      <title>  Example article  </title>
      <meta name="description" content=" A useful description ">
      <meta property="og:title" content="Open Graph title">
      <meta property="og:description" content="Open Graph description">
      <meta property="og:site_name" content="Example Site">
      <link rel="canonical" href="../canonical">
      <meta name="arbitrary-secret" content="must not pass through">
      <script type="application/ld+json">{"secret":"not text"}</script>
    </head><body>
      <header>Header noise</header><nav>Navigation noise</nav>
      <main><h1>Main heading</h1><p>Useful body text.</p>
      <p hidden>Hidden secret</p><span style="display: none">Invisible</span></main>
      <footer>Footer noise</footer>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return html_response(html)

    result, resolver = await fetch_with("HTTPS://Example.COM./a/page?keep=1#drop", handler)

    assert isinstance(result, WebPageContent)
    assert result.normalized_url == "https://example.com/a/page?keep=1"
    assert result.final_url == result.normalized_url
    assert result.title == "Example article"
    assert result.text == "Main heading\nUseful body text."
    assert result.metadata.description == "A useful description"
    assert result.metadata.canonical_url == "https://example.com/canonical"
    assert result.metadata.open_graph_title == "Open Graph title"
    assert result.metadata.open_graph_description == "Open Graph description"
    assert result.metadata.open_graph_site_name == "Example Site"
    assert result.fetched_at == NOW
    assert result.diagnostics.redirect_count == 0
    assert resolver.calls == [("example.com", 443)]
    assert len(seen) == 1
    assert seen[0].url.host == PUBLIC_V4
    assert seen[0].headers["host"] == "example.com"
    assert seen[0].extensions["sni_hostname"] == "example.com"
    assert "authorization" not in seen[0].headers
    assert "cookie" not in seen[0].headers
    assert seen[0].headers["connection"] == "close"


@pytest.mark.asyncio
async def test_idn_and_trailing_dot_use_canonical_dns_name() -> None:
    resolver = StubResolver({"xn--fsqu00a.xn--0zwm56d": (PUBLIC_V4,)})
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return html_response("<main>地点正文</main>")

    result, _ = await fetch_with("https://例子.测试./地点", handler, resolver=resolver)
    assert isinstance(result, WebPageContent)
    assert result.normalized_url == "https://xn--fsqu00a.xn--0zwm56d/地点"
    assert resolver.calls == [("xn--fsqu00a.xn--0zwm56d", 443)]
    assert seen[0].headers["host"] == "xn--fsqu00a.xn--0zwm56d"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://example.com/file", WebFetchFailureCode.INVALID_URL),
        ("http://user:pass@example.com", WebFetchFailureCode.INVALID_URL),
        ("http://example.com:8080", WebFetchFailureCode.INVALID_URL),
        ("http://localhost", WebFetchFailureCode.TARGET_BLOCKED),
        ("http://169.254.169.254", WebFetchFailureCode.TARGET_BLOCKED),
        ("http://2130706433", WebFetchFailureCode.INVALID_URL),
    ],
)
async def test_rejects_url_before_dns_or_http(url: str, code: WebFetchFailureCode) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return html_response("unreachable")

    resolver = StubResolver()
    result, _ = await fetch_with(url, handler, resolver=resolver)
    assert isinstance(result, WebFetchFailure)
    assert result.code is code
    assert resolver.calls == []
    assert attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        ("10.0.0.1",),
        (PUBLIC_V4, "127.0.0.1"),
        ("::ffff:8.8.8.8",),
    ],
)
async def test_blocks_private_or_mixed_dns_answers_without_http(answer: tuple[str, ...]) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return html_response("unreachable")

    resolver = StubResolver({"example.com": answer})
    result, _ = await fetch_with("https://example.com", handler, resolver=resolver)
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.TARGET_BLOCKED
    assert attempts == 0


@pytest.mark.asyncio
async def test_dns_failure_is_safe_and_recoverable() -> None:
    resolver = StubResolver({"example.com": socket.gaierror("internal dns secret")})
    result, _ = await fetch_with(
        "https://example.com/?token=query-secret",
        lambda _: html_response("unreachable"),
        resolver=resolver,
    )
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.DNS_FAILED
    public = json.dumps(result.to_public_dict()) + repr(result)
    assert "query-secret" not in public
    assert "internal dns secret" not in public


@pytest.mark.asyncio
async def test_dns_rebinding_cannot_change_the_validated_connection_address() -> None:
    resolver = StubResolver({"example.com": (PUBLIC_V4, SECOND_PUBLIC_V4)})
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        assert request.url.host != "example.com"
        return html_response("<main>Safe pinned response</main>")

    result, _ = await fetch_with("https://example.com", handler, resolver=resolver)
    assert isinstance(result, WebPageContent)
    assert seen_hosts == [PUBLIC_V4]
    assert resolver.calls == [("example.com", 443)]


@pytest.mark.asyncio
async def test_follows_safe_redirects_with_full_validation_per_hop() -> None:
    resolver = StubResolver(
        {"example.com": (PUBLIC_V4,), "public.example": (SECOND_PUBLIC_V4,)}
    )
    seen: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.headers["host"], request.url.host, request.url.path))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "https://public.example/final"})
        return html_response("<article>Redirected content</article>")

    result, _ = await fetch_with("http://example.com/start", handler, resolver=resolver)
    assert isinstance(result, WebPageContent)
    assert result.final_url == "https://public.example/final"
    assert result.diagnostics.redirect_count == 1
    assert resolver.calls == [("example.com", 80), ("public.example", 443)]
    assert seen == [
        ("example.com", PUBLIC_V4, "/start"),
        ("public.example", SECOND_PUBLIC_V4, "/final"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("root_level", [logging.INFO, logging.DEBUG])
async def test_http_client_logs_hide_initial_and_redirect_queries_at_all_root_levels(
    root_level: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    initial_secret = "initial-query-secret"
    redirect_secret = "redirect-query-secret"
    body_secret = "response-body-secret"
    seen_urls: list[str] = []
    caplog.set_level(root_level)
    caplog.set_level(root_level, logger="httpx")
    caplog.set_level(root_level, logger="httpcore")

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={
                    "Location": f"https://public.example/final?token={redirect_secret}"
                },
            )
        return httpx.Response(503, text=body_secret)

    result, _ = await fetch_with(
        f"https://example.com/start?token={initial_secret}",
        handler,
        resolver=StubResolver(
            {"example.com": (PUBLIC_V4,), "public.example": (SECOND_PUBLIC_V4,)}
        ),
    )

    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.HTTP_STATUS
    assert initial_secret in seen_urls[0]
    assert redirect_secret in seen_urls[1]
    exposed = caplog.text + repr(result) + json.dumps(result.to_public_dict())
    for secret in (initial_secret, redirect_secret, body_secret):
        assert secret not in exposed
    assert getattr(result, "__context__", None) is None
    assert getattr(result, "__cause__", None) is None
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
        "https://example.com:444/path",
    ],
)
async def test_blocks_unsafe_redirect_before_second_request(location: str) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(302, headers={"Location": location})

    result, _ = await fetch_with("https://example.com/start", handler)
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.REDIRECT_BLOCKED
    assert attempts == 1


@pytest.mark.asyncio
async def test_blocks_redirect_when_dns_answer_is_private() -> None:
    resolver = StubResolver({"example.com": (PUBLIC_V4,), "private.example": ("10.0.0.1",)})

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://private.example/admin"})

    result, _ = await fetch_with("https://example.com/start", handler, resolver=resolver)
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.REDIRECT_BLOCKED


@pytest.mark.asyncio
async def test_detects_redirect_loop_and_limit() -> None:
    attempts: list[str] = []

    def loop_handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.path)
        target = "/b" if request.url.path == "/a" else "/a"
        return httpx.Response(301, headers={"Location": target})

    loop, _ = await fetch_with("https://example.com/a", loop_handler)
    assert isinstance(loop, WebFetchFailure)
    assert loop.code is WebFetchFailureCode.REDIRECT_LOOP
    assert attempts == ["/a", "/b"]

    attempts.clear()
    limited, _ = await fetch_with(
        "https://example.com/a",
        loop_handler,
        config=WebFetchConfig(max_redirects=1),
    )
    assert isinstance(limited, WebFetchFailure)
    assert limited.code is WebFetchFailureCode.REDIRECT_LIMIT
    assert attempts == ["/a", "/b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_supports_each_allowed_redirect_status(status: int) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if request.url.path == "/start":
            return httpx.Response(status, headers={"Location": "/final"})
        return html_response("<main>done</main>")

    result, _ = await fetch_with("https://example.com/start", handler)
    assert isinstance(result, WebPageContent)
    assert attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
async def test_http_error_statuses_are_safe_and_never_retried(status: int) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, content=b"body-secret")

    result, _ = await fetch_with("https://example.com/?token=query-secret", handler)
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.HTTP_STATUS
    assert result.http_status == status
    assert attempts == 1
    public = json.dumps(result.to_public_dict()) + repr(result)
    assert "body-secret" not in public
    assert "query-secret" not in public


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Content-Type": "application/octet-stream"},
        {"Content-Type": "image/png"},
        {"Content-Type": "application/pdf"},
        {"Content-Type": "application/json"},
    ],
)
async def test_rejects_missing_binary_or_unknown_content_type(headers: dict[str, str]) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, content=b"not-readable-content")

    result, _ = await fetch_with("https://example.com", handler)
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.CONTENT_TYPE_UNSUPPORTED


@pytest.mark.asyncio
async def test_conflicting_content_type_headers_are_malformed() -> None:
    result, _ = await fetch_with(
        "https://example.com",
        lambda _: httpx.Response(
            200,
            headers=[
                ("Content-Type", "text/html"),
                ("Content-Type", "text/plain"),
            ],
            content=b"body",
        ),
    )
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.RESPONSE_MALFORMED


@pytest.mark.asyncio
async def test_plain_text_and_common_charsets_are_supported() -> None:
    plain, _ = await fetch_with(
        "https://example.com/plain",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/plain; charset=windows-1252"},
            content="Café text".encode("windows-1252"),
        ),
    )
    assert isinstance(plain, WebPageContent)
    assert plain.title == ""
    assert plain.text == "Café text"

    chinese = "<html><head><meta charset='gb18030'></head><body>广州正文</body></html>"
    gb, _ = await fetch_with(
        "https://example.com/gb",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=chinese.encode("gb18030"),
        ),
    )
    assert isinstance(gb, WebPageContent)
    assert gb.text == "广州正文"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ignored_markup",
    [
        "<!-- <meta charset='gb18030'> -->",
        "<div data-charset='gb18030'>ordinary attribute</div>",
        "<script>const fake = \"<meta charset='gb18030'>\";</script>",
        "<section charset='gb18030'>not a meta element</section>",
    ],
)
async def test_charset_discovery_ignores_comments_scripts_and_pseudo_attributes(
    ignored_markup: str,
) -> None:
    html = f"<html><head>{ignored_markup}<meta charset='utf-8'></head><body>正文</body></html>"
    result, _ = await fetch_with(
        "https://example.com/charset",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=html.encode(),
        ),
    )
    assert isinstance(result, WebPageContent)
    assert result.text == "正文"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("html", "encoding", "expected"),
    [
        (
            '<html><head><META CONTENT="text/html; charset=GB18030" '
            'HTTP-EQUIV="Content-Type"></head><body>广州正文</body></html>',
            "gb18030",
            "广州正文",
        ),
        (
            "<html><head><meta data-order='first' CHARSET='UTF-8'></head>"
            "<body>深圳正文</body></html>",
            "utf-8",
            "深圳正文",
        ),
        (
            '<html><head><meta http-equiv="CONTENT-TYPE" '
            'content="text/html; CHARSET=windows-1252"></head><body>Café</body></html>',
            "windows-1252",
            "Café",
        ),
    ],
)
async def test_real_meta_charset_supports_http_equiv_case_and_attribute_order(
    html: str,
    encoding: str,
    expected: str,
) -> None:
    result, _ = await fetch_with(
        "https://example.com/meta-charset",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=html.encode(encoding),
        ),
    )
    assert isinstance(result, WebPageContent)
    assert result.text == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type",
    [
        "text/html; charset=made-up",
        "text/html; charset=utf-8; charset=gb18030",
        "text/html; broken-parameter",
    ],
)
async def test_rejects_invalid_or_conflicting_charset(content_type: str) -> None:
    result, _ = await fetch_with(
        "https://example.com",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": content_type},
            content=b"<main>body</main>",
        ),
    )
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.RESPONSE_MALFORMED


@pytest.mark.asyncio
async def test_rejects_header_and_html_charset_conflict() -> None:
    result, _ = await fetch_with(
        "https://example.com",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=b"<meta charset='gb18030'><main>body</main>",
        ),
    )
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.RESPONSE_MALFORMED


@pytest.mark.asyncio
async def test_size_limit_accepts_exact_boundary_and_rejects_one_more() -> None:
    config = WebFetchConfig(max_response_bytes=10)
    exact, _ = await fetch_with(
        "https://example.com",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            content=b"abcdefghij",
        ),
        config=config,
    )
    assert isinstance(exact, WebPageContent)
    assert exact.text == "abcdefghij"

    over, _ = await fetch_with(
        "https://example.com",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            content=b"abcdefghijk",
        ),
        config=config,
    )
    assert isinstance(over, WebFetchFailure)
    assert over.code is WebFetchFailureCode.RESPONSE_TOO_LARGE


@pytest.mark.asyncio
async def test_chunked_and_decompressed_size_boundaries() -> None:
    config = WebFetchConfig(max_response_bytes=10)
    chunked, _ = await fetch_with(
        "https://example.com/chunked",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            stream=ChunkedStream((b"abc", b"def", b"ghij")),
        ),
        config=config,
    )
    assert isinstance(chunked, WebPageContent)

    bomb_config = WebFetchConfig(max_response_bytes=100)
    compressed = gzip.compress(b"a" * 1000)
    assert len(compressed) < bomb_config.max_response_bytes
    bomb, _ = await fetch_with(
        "https://example.com/gzip",
        lambda _: httpx.Response(
            200,
            headers={
                "Content-Type": "text/plain",
                "Content-Encoding": "gzip",
            },
            content=compressed,
        ),
        config=bomb_config,
    )
    assert isinstance(bomb, WebFetchFailure)
    assert bomb.code is WebFetchFailureCode.RESPONSE_TOO_LARGE

    exact_compressed = gzip.compress(b"a" * 100)
    exact_gzip, _ = await fetch_with(
        "https://example.com/exact-gzip",
        lambda _: httpx.Response(
            200,
            headers={
                "Content-Type": "text/plain",
                "Content-Encoding": "gzip",
            },
            stream=ChunkedStream((exact_compressed[:5], exact_compressed[5:])),
        ),
        config=bomb_config,
    )
    assert isinstance(exact_gzip, WebPageContent)
    assert len(exact_gzip.text) == 100


@pytest.mark.asyncio
async def test_corrupt_compressed_response_is_malformed() -> None:
    result, _ = await fetch_with(
        "https://example.com",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
            content=b"not-gzip",
        ),
    )
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.RESPONSE_MALFORMED


@pytest.mark.asyncio
async def test_empty_title_metadata_and_body_semantics() -> None:
    readable, _ = await fetch_with(
        "https://example.com",
        lambda _: html_response("<html><head><title> </title></head><body>Body only</body></html>"),
    )
    assert isinstance(readable, WebPageContent)
    assert readable.title == ""
    assert readable.metadata.model_dump() == {
        "description": None,
        "canonical_url": None,
        "open_graph_title": None,
        "open_graph_description": None,
        "open_graph_site_name": None,
    }

    empty, _ = await fetch_with(
        "https://example.com",
        lambda _: html_response("<html><title>Title only</title><script>hidden</script></html>"),
    )
    assert isinstance(empty, WebFetchFailure)
    assert empty.code is WebFetchFailureCode.CONTENT_UNREADABLE


@pytest.mark.asyncio
async def test_nested_noise_and_hidden_parent_nodes_preserve_only_visible_siblings() -> None:
    html = """
    <html><body>
      <header><nav><span>nested navigation noise</span></nav></header>
      <main>
        <div hidden><span>hidden child</span></div>
        <p>Visible first</p>
        <section aria-hidden="true"><span>aria hidden child</span></section>
        <p>Visible second</p>
        <div style="display: none"><span>display hidden child</span></div>
        <div style="visibility: hidden"><span>visibility hidden child</span></div>
        <p>Visible third</p>
      </main>
    </body></html>
    """
    result, _ = await fetch_with(
        "https://example.com/nested",
        lambda _: html_response(html),
    )
    assert isinstance(result, WebPageContent)
    assert result.text == "Visible first\nVisible second\nVisible third"


@pytest.mark.asyncio
async def test_page_with_only_nested_hidden_content_is_unreadable() -> None:
    html = """
    <html><body>
      <header><nav><span>navigation only</span></nav></header>
      <div hidden><span>hidden child</span></div>
      <section aria-hidden="true"><span>aria hidden child</span></section>
      <div style="display:none"><span>display hidden child</span></div>
      <div style="visibility: hidden"><span>visibility hidden child</span></div>
    </body></html>
    """
    result, _ = await fetch_with(
        "https://example.com/all-hidden",
        lambda _: html_response(html),
    )
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.CONTENT_UNREADABLE


@pytest.mark.asyncio
async def test_text_length_is_deterministically_truncated() -> None:
    config = WebFetchConfig(max_text_characters=5)
    result, _ = await fetch_with(
        "https://example.com",
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            content=b"abcdefghij",
        ),
        config=config,
    )
    assert isinstance(result, WebPageContent)
    assert result.text == "abcde"
    assert result.diagnostics.text_truncated is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx.ConnectError("connect secret"), WebFetchFailureCode.CONNECTION_FAILED),
        (httpx.ReadTimeout("timeout secret"), WebFetchFailureCode.TIMEOUT),
    ],
)
async def test_transport_failures_are_safe_and_not_retried(
    exception: Exception,
    code: WebFetchFailureCode,
) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise exception

    result, _ = await fetch_with("https://example.com/?secret=query-secret", handler)
    assert isinstance(result, WebFetchFailure)
    assert result.code is code
    assert attempts == 1
    public = json.dumps(result.to_public_dict()) + repr(result)
    assert "secret" not in public


@pytest.mark.asyncio
async def test_unknown_fetch_error_uses_fixed_safe_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise RuntimeError("unknown internal fake-secret")

    result, _ = await fetch_with("https://example.com/?secret=query-secret", handler)
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.UNKNOWN
    public = json.dumps(result.to_public_dict()) + repr(result)
    assert "fake-secret" not in public
    assert "query-secret" not in public


@pytest.mark.asyncio
async def test_cancelled_error_propagates_unchanged() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await fetch_with("https://example.com", handler)


@pytest.mark.asyncio
async def test_total_timeout_is_enforced_without_retry() -> None:
    attempts = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.05)
        return html_response("late")

    result, _ = await fetch_with(
        "https://example.com",
        handler,
        config=WebFetchConfig(total_timeout_seconds=0.001),
    )
    assert isinstance(result, WebFetchFailure)
    assert result.code is WebFetchFailureCode.TIMEOUT
    assert attempts == 1


@pytest.mark.asyncio
async def test_environment_proxy_and_credentials_are_not_inherited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy-user:proxy-secret@127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy-user:proxy-secret@127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return html_response("<main>offline response</main>")

    result, _ = await fetch_with("https://example.com", handler)
    assert isinstance(result, WebPageContent)
    assert len(seen) == 1
    serialized = str(seen[0].headers).lower()
    assert "authorization" not in serialized
    assert "cookie" not in serialized
    assert "proxy-user" not in serialized
    assert "proxy-secret" not in serialized


@pytest.mark.asyncio
async def test_response_cookies_are_never_retained_sent_or_logged_across_shared_calls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cookie_secret = "response-cookie-secret"
    sent_cookie_headers: list[str | None] = []
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="httpx")
    caplog.set_level(logging.DEBUG, logger="httpcore")

    async def handler(request: httpx.Request) -> httpx.Response:
        sent_cookie_headers.append(request.headers.get("cookie"))
        await asyncio.sleep(0)
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={
                    "Location": "/redirected",
                    "Set-Cookie": f"session={cookie_secret}; Path=/; HttpOnly",
                },
            )
        return html_response(
            f"<main>{request.url.path}</main>",
            headers={"Set-Cookie": f"session={cookie_secret}; Path=/; HttpOnly"},
        )

    client = create_web_http_client(transport=httpx.MockTransport(handler))
    provider = HttpxWebContentProvider(
        http_client=client,
        resolver=StubResolver(),
        clock=lambda: NOW,
    )
    try:
        redirected = await provider.fetch("https://example.com/start")
        repeated = await provider.fetch("https://example.com/repeated")
        concurrent = await asyncio.gather(
            provider.fetch("https://example.com/one"),
            provider.fetch("https://example.com/two"),
        )
        assert isinstance(redirected, WebPageContent)
        assert isinstance(repeated, WebPageContent)
        assert all(isinstance(result, WebPageContent) for result in concurrent)
        assert len(client.cookies) == 0
    finally:
        await provider.aclose()

    assert sent_cookie_headers == [None, None, None, None, None]
    assert cookie_secret not in caplog.text
    assert cookie_secret not in repr(redirected)


@pytest.mark.asyncio
async def test_repeated_and_concurrent_calls_do_not_share_state() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        await asyncio.sleep(0)
        return html_response(f"<main>{request.url.path}</main>")

    transport = httpx.MockTransport(handler)
    client = create_web_http_client(transport=transport)
    resolver = StubResolver()
    provider = HttpxWebContentProvider(
        http_client=client,
        resolver=resolver,
        clock=lambda: NOW,
    )
    try:
        first, second, repeated = await asyncio.gather(
            provider.fetch("https://example.com/one"),
            provider.fetch("https://example.com/two"),
            provider.fetch("https://example.com/one"),
        )
    finally:
        await provider.aclose()

    assert isinstance(first, WebPageContent)
    assert isinstance(second, WebPageContent)
    assert isinstance(repeated, WebPageContent)
    assert first.text == "/one"
    assert second.text == "/two"
    assert repeated.text == "/one"
    assert sorted(seen) == ["/one", "/one", "/two"]
    assert len(resolver.calls) == 3

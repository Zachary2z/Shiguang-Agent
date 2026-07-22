from __future__ import annotations

import ipaddress

import pytest

from app.domain.web.security import (
    UrlPolicyError,
    UrlPolicyErrorCode,
    bind_web_target,
    safe_canonical_url,
    split_for_redirect,
    validate_resolved_addresses,
    validate_web_url,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("HTTP://Example.COM", "http://example.com/"),
        ("http://example.com:80/standard", "http://example.com/standard"),
        ("https://example.com:443/standard", "https://example.com/standard"),
        ("https://Example.COM./a?b=1#fragment", "https://example.com/a?b=1"),
        ("https://例子.测试/地点", "https://xn--fsqu00a.xn--0zwm56d/地点"),
        ("http://93.184.216.34/path", "http://93.184.216.34/path"),
        ("https://[2606:4700:4700::1111]/", "https://[2606:4700:4700::1111]/"),
    ],
)
def test_normalizes_public_http_urls(source: str, expected: str) -> None:
    assert validate_web_url(source).normalized_url == expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "data:text/html,hello",
        "javascript:alert(1)",
        "gopher://example.com",
        "https://user@example.com",
        "https://user:pass@example.com",
        "http://example.com:81",
        "https://example.com:444",
        "http://example.com:99999",
        "http://example.com/%ZZ",
        "http://example.com\\@127.0.0.1/",
        "http://example.com/\nsecret",
        "http://example.com/\x00secret",
        "http://exa\u200bmple.com/",
        "http:///missing-host",
        "not a url",
        "",
    ],
)
def test_rejects_invalid_or_confusing_urls(url: str) -> None:
    with pytest.raises(UrlPolicyError) as raised:
        validate_web_url(url)
    assert raised.value.code == UrlPolicyErrorCode.INVALID


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://LOCALHOST./",
        "http://sub.localhost/",
        "http://metadata.google.internal/",
        "http://instance-data/",
        "http://127.0.0.1/",
        "http://127.1.2.3/",
        "http://0.0.0.0/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[ff02::1]/",
        "http://[::]/",
        "http://[2001:db8::1]/",
        "http://240.0.0.1/",
        "http://[::ffff:127.0.0.1]/",
    ],
)
def test_rejects_literal_non_public_targets(url: str) -> None:
    with pytest.raises(UrlPolicyError) as raised:
        validate_web_url(url)
    assert raised.value.code == UrlPolicyErrorCode.BLOCKED


@pytest.mark.parametrize(
    "url",
    [
        "http://2130706433/",
        "http://017700000001/",
        "http://0x7f000001/",
        "http://127.1/",
        "http://127.0.1/",
        "http://0177.0.0.1/",
        "http://0x7f.0.0.1/",
    ],
)
def test_rejects_ambiguous_ip_notation(url: str) -> None:
    with pytest.raises(UrlPolicyError) as raised:
        validate_web_url(url)
    assert raised.value.code == UrlPolicyErrorCode.INVALID


@pytest.mark.parametrize(
    "addresses",
    [
        ("10.0.0.1",),
        ("93.184.216.34", "127.0.0.1"),
        ("::ffff:8.8.8.8",),
        ("not-an-ip",),
    ],
)
def test_rejects_any_unsafe_or_mixed_dns_answer(addresses: tuple[str, ...]) -> None:
    target = validate_web_url("https://example.com/")
    with pytest.raises(UrlPolicyError) as raised:
        validate_resolved_addresses(target, addresses)
    assert raised.value.code == UrlPolicyErrorCode.BLOCKED


def test_binds_connection_to_validated_ip_and_preserves_host_and_sni() -> None:
    logical = validate_web_url("https://Example.com/path?q=1")
    addresses = validate_resolved_addresses(logical, ("93.184.216.34", "8.8.8.8"))
    bound = bind_web_target(logical, addresses[0])

    assert bound.request_url == "https://93.184.216.34/path?q=1"
    assert bound.host_header == "example.com"
    assert bound.sni_hostname == "example.com"
    assert bound.address == ipaddress.ip_address("93.184.216.34")
    assert "q=1" not in repr(bound)


def test_canonical_is_resolved_and_unsafe_metadata_is_dropped() -> None:
    assert safe_canonical_url("https://example.com/a/b", "../canonical") == (
        "https://example.com/canonical"
    )
    assert safe_canonical_url("https://example.com/a", "http://localhost/secret") is None


def test_redirect_reference_rejects_controls_before_urljoin_can_normalize_them() -> None:
    base = validate_web_url("https://example.com/start")
    with pytest.raises(UrlPolicyError):
        split_for_redirect(base, "https://public.example/\nconfusing")

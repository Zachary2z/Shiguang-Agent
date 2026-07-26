"""Pure identity security and provider-neutral boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.identifiers import generate_user_id
from app.domain.identity import (
    BrowserSession,
    ChannelIdentity,
    SessionCredentialError,
    derive_csrf_token,
    generate_session_secret,
    hash_session_secret,
    validate_session_secret,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def test_session_secret_and_derived_csrf_are_strict_domain_separated_and_one_way() -> None:
    first = generate_session_secret()
    second = generate_session_secret()
    first_csrf = derive_csrf_token(first)
    second_csrf = derive_csrf_token(second)
    snapshot = first

    assert first != second
    assert len(first) == len(second) == len(first_csrf) == len(second_csrf) == 43
    assert validate_session_secret(first) == first
    assert validate_session_secret(first_csrf) == first_csrf
    assert first_csrf == derive_csrf_token(first)
    assert first_csrf != first
    assert first_csrf != second_csrf
    assert hash_session_secret(first) != first
    assert hash_session_secret(first) != hash_session_secret(second)
    assert len(hash_session_secret(first)) == 64
    assert first == snapshot

    for malformed in ("", "fixed-token", "a" * 42, "a" * 44, "!" * 43):
        with pytest.raises(
            SessionCredentialError,
            match="invalid session credential",
        ) as exc_info:
            validate_session_secret(malformed)
        if malformed:
            assert malformed not in repr(exc_info.value)


def test_browser_session_expiry_is_absolute_and_equal_boundary_is_expired() -> None:
    browser_session = BrowserSession(
        id="wbs_" + "1" * 32,
        user_id=generate_user_id(),
        token_hash="3" * 64,
        csrf_token_hash="4" * 64,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=2),
    )

    assert browser_session.is_active_at(NOW)
    assert browser_session.is_active_at(browser_session.expires_at - timedelta(microseconds=1))
    assert not browser_session.is_active_at(browser_session.expires_at)
    assert not browser_session.is_active_at(browser_session.expires_at + timedelta(seconds=1))
    assert "3" * 64 not in repr(browser_session)
    assert "4" * 64 not in repr(browser_session)
    assert "usr_" not in repr(browser_session)


def test_channel_identity_is_minimal_secret_safe_and_has_no_wechat_fields() -> None:
    identity = ChannelIdentity(channel="future_channel", subject="private-subject")

    assert identity.model_dump() == {
        "channel": "future_channel",
        "subject": "private-subject",
    }
    assert "private-subject" not in repr(identity)
    assert not (
        {"openid", "unionid", "oauth", "binding_code"} & set(ChannelIdentity.model_fields)
    )

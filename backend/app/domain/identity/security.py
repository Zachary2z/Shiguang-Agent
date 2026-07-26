"""Opaque browser credential generation, validation, and hashing."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from base64 import urlsafe_b64encode

SESSION_COOKIE_NAME = "shiguang_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$", flags=re.ASCII)
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$", flags=re.ASCII)
_CSRF_DERIVATION_CONTEXT = b"shiguang:web-session:csrf:v1"


class SessionCredentialError(ValueError):
    def __init__(self) -> None:
        super().__init__("invalid session credential")


def generate_session_secret() -> str:
    secret = secrets.token_urlsafe(32)
    if _SECRET_PATTERN.fullmatch(secret) is None:
        raise RuntimeError("secure token generator returned an invalid credential")
    return secret


def validate_session_secret(value: object) -> str:
    if not isinstance(value, str) or _SECRET_PATTERN.fullmatch(value) is None:
        raise SessionCredentialError
    return value


def hash_session_secret(value: str) -> str:
    secret = validate_session_secret(value)
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def derive_csrf_token(session_token: str) -> str:
    """Derive the browser CSRF proof without persisting another plaintext secret."""

    secret = validate_session_secret(session_token)
    digest = hmac.new(
        secret.encode("ascii"),
        _CSRF_DERIVATION_CONTEXT,
        hashlib.sha256,
    ).digest()
    csrf_token = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return validate_session_secret(csrf_token)


def validate_secret_hash(value: str) -> str:
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError("credential hash must be 64 lowercase hexadecimal characters")
    return value

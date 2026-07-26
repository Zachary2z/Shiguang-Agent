"""Opaque browser credential generation, validation, and hashing."""

from __future__ import annotations

import hashlib
import re
import secrets

SESSION_COOKIE_NAME = "shiguang_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$", flags=re.ASCII)
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$", flags=re.ASCII)


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


def validate_secret_hash(value: str) -> str:
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError("credential hash must be 64 lowercase hexadecimal characters")
    return value

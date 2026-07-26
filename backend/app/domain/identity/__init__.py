"""Browser identity contracts shared by API and infrastructure."""

from app.domain.identity.contracts import (
    BrowserSession,
    ChannelIdentity,
    ChannelIdentityRepository,
    CurrentPrincipal,
    PrincipalMode,
    WebSessionRepository,
)
from app.domain.identity.security import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    SessionCredentialError,
    generate_session_secret,
    hash_session_secret,
    validate_session_secret,
)

__all__ = [
    "CSRF_HEADER_NAME",
    "SESSION_COOKIE_NAME",
    "BrowserSession",
    "ChannelIdentity",
    "ChannelIdentityRepository",
    "CurrentPrincipal",
    "PrincipalMode",
    "SessionCredentialError",
    "WebSessionRepository",
    "generate_session_secret",
    "hash_session_secret",
    "validate_session_secret",
]

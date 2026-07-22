"""Shared logging boundary for HTTP clients whose URLs may contain credentials."""

from __future__ import annotations

import logging

_SENSITIVE_HTTP_LOGGERS = ("httpx", "httpcore")


def enforce_safe_http_client_logging() -> None:
    """Suppress third-party request details that may include URL queries or headers."""

    for name in _SENSITIVE_HTTP_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(max(logger.level, logging.WARNING))

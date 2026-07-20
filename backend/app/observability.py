"""Minimal request correlation and request logging."""

from __future__ import annotations

import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_request_logger = logging.getLogger("shiguang.request")


def configure_logging(level: str) -> None:
    """Configure a small, non-sensitive server log format."""

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _request_logger.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True


def normalize_request_id(candidate: str | None) -> str:
    """Preserve a safe client request ID or generate a new opaque identifier."""

    if candidate is not None and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


class RequestContextMiddleware:
    """Attach a request ID response header and log request-level metadata only."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = normalize_request_id(headers.get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = (perf_counter() - started_at) * 1000
            _request_logger.info(
                "request_completed request_id=%s method=%s path=%s status=%d duration_ms=%.2f",
                request_id,
                scope["method"],
                scope["path"],
                status_code,
                duration_ms,
            )

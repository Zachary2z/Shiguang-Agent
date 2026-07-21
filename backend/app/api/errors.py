"""Stable, secret-safe HTTP error mapping."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.dependencies import ProviderNotConfiguredError
from app.application.text_collection_workflow import (
    IdempotentRequestInProgressError,
    TextCollectionProviderError,
    TextCollectionRunError,
    TextCollectionTimeoutError,
)
from app.domain.collections import (
    IdempotencyConflictError,
    ResourceNotFoundError,
    VersionConflictError,
)


class UndoNotAvailableError(LookupError):
    """The supplied token cannot safely be used for the requested path item."""


def install_error_handlers(api: FastAPI) -> None:
    api.add_exception_handler(RequestValidationError, _request_validation_error)
    api.add_exception_handler(ValidationError, _domain_validation_error)
    api.add_exception_handler(ResourceNotFoundError, _resource_not_found)
    api.add_exception_handler(UndoNotAvailableError, _undo_not_available)
    api.add_exception_handler(IdempotencyConflictError, _idempotency_conflict)
    api.add_exception_handler(VersionConflictError, _version_conflict)
    api.add_exception_handler(
        IdempotentRequestInProgressError,
        _idempotent_request_in_progress,
    )
    api.add_exception_handler(TextCollectionProviderError, _provider_error)
    api.add_exception_handler(TextCollectionRunError, _workflow_error)
    api.add_exception_handler(TextCollectionTimeoutError, _workflow_timeout)
    api.add_exception_handler(ProviderNotConfiguredError, _provider_not_configured)


async def _request_validation_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request
    assert isinstance(exc, RequestValidationError)
    issues = tuple(
        {
            "path": ".".join(str(part) for part in error.get("loc", ()))[:160],
            "type": str(error.get("type", "invalid"))[:80],
        }
        for error in exc.errors()[:8]
    )
    return _error(422, "REQUEST_VALIDATION_ERROR", "Request validation failed.", issues=issues)


async def _domain_validation_error(request: Request, exc: Exception) -> JSONResponse:
    del request
    assert isinstance(exc, ValidationError)
    issues = tuple(
        {
            "path": ".".join(str(part) for part in error.get("loc", ()))[:160],
            "type": str(error.get("type", "invalid"))[:80],
        }
        for error in exc.errors(include_input=False, include_context=False, include_url=False)[:8]
    )
    return _error(422, "DOMAIN_VALIDATION_ERROR", "Requested values are invalid.", issues=issues)


async def _resource_not_found(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(404, "RESOURCE_NOT_FOUND", "Resource not found.")


async def _undo_not_available(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(404, "UNDO_NOT_AVAILABLE", "Undo is not available.")


async def _idempotency_conflict(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(409, "IDEMPOTENCY_CONFLICT", "Idempotency key conflicts with a request.")


async def _version_conflict(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(409, "VERSION_CONFLICT", "Collection version conflict.")


async def _idempotent_request_in_progress(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request, exc
    return _error(409, "REQUEST_IN_PROGRESS", "The idempotent request is still running.")


async def _provider_error(request: Request, exc: Exception) -> JSONResponse:
    del request
    assert isinstance(exc, TextCollectionProviderError)
    return _error(
        502,
        exc.error_code,
        "The text provider could not complete the request.",
        trace_id=exc.trace_id,
    )


async def _provider_not_configured(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(503, "PROVIDER_NOT_CONFIGURED", "Text collection is unavailable.")


async def _workflow_timeout(request: Request, exc: Exception) -> JSONResponse:
    del request
    assert isinstance(exc, TextCollectionTimeoutError)
    return _error(
        504,
        "RUN_TIMEOUT",
        "The text collection request timed out.",
        trace_id=exc.trace_id,
    )


async def _workflow_error(request: Request, exc: Exception) -> JSONResponse:
    del request
    assert isinstance(exc, TextCollectionRunError)
    return _error(
        500,
        exc.error_code,
        "The text collection request failed.",
        trace_id=exc.trace_id,
    )


def _error(
    status_code: int,
    error_code: str,
    message: str,
    *,
    trace_id: str | None = None,
    issues: tuple[dict[str, str], ...] = (),
) -> JSONResponse:
    content: dict[str, object] = {"error_code": error_code, "message": message}
    if trace_id is not None:
        content["trace_id"] = trace_id
    if issues:
        content["issues"] = issues
    return JSONResponse(status_code=status_code, content=content)

"""Stable, secret-safe HTTP error mapping."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.dependencies import (
    AuthenticationRequiredError,
    CsrfRejectedError,
    DemoNotAvailableError,
    PlanProviderNotConfiguredError,
    ProviderNotConfiguredError,
)
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
from app.domain.jobs import JobConflictError
from app.domain.memories import (
    MemoryNotFoundError,
    MemorySuggestionUnavailableError,
    MemoryVersionConflictError,
    SensitiveMemoryRejectedError,
)
from app.domain.plans import (
    PlanExecutionNotAllowedError,
    PlanFeedbackSelectionError,
    PlanNotReadyError,
    PlanVersionConflictError,
)


class UndoNotAvailableError(LookupError):
    """The supplied token cannot safely be used for the requested path item."""


def install_error_handlers(api: FastAPI) -> None:
    api.add_exception_handler(RequestValidationError, _request_validation_error)
    api.add_exception_handler(ValidationError, _domain_validation_error)
    api.add_exception_handler(ResourceNotFoundError, _resource_not_found)
    api.add_exception_handler(UndoNotAvailableError, _undo_not_available)
    api.add_exception_handler(IdempotencyConflictError, _idempotency_conflict)
    api.add_exception_handler(JobConflictError, _idempotency_conflict)
    api.add_exception_handler(VersionConflictError, _version_conflict)
    api.add_exception_handler(PlanVersionConflictError, _plan_version_conflict)
    api.add_exception_handler(PlanNotReadyError, _plan_not_ready)
    api.add_exception_handler(
        PlanExecutionNotAllowedError,
        _plan_execution_not_allowed,
    )
    api.add_exception_handler(PlanFeedbackSelectionError, _feedback_selection_error)
    api.add_exception_handler(MemoryNotFoundError, _memory_not_found)
    api.add_exception_handler(
        MemorySuggestionUnavailableError, _memory_suggestion_unavailable
    )
    api.add_exception_handler(MemoryVersionConflictError, _memory_version_conflict)
    api.add_exception_handler(SensitiveMemoryRejectedError, _sensitive_memory_rejected)
    api.add_exception_handler(
        IdempotentRequestInProgressError,
        _idempotent_request_in_progress,
    )
    api.add_exception_handler(TextCollectionProviderError, _provider_error)
    api.add_exception_handler(TextCollectionRunError, _workflow_error)
    api.add_exception_handler(TextCollectionTimeoutError, _workflow_timeout)
    api.add_exception_handler(ProviderNotConfiguredError, _provider_not_configured)
    api.add_exception_handler(
        PlanProviderNotConfiguredError,
        _plan_provider_not_configured,
    )
    api.add_exception_handler(AuthenticationRequiredError, _authentication_required)
    api.add_exception_handler(CsrfRejectedError, _csrf_rejected)
    api.add_exception_handler(DemoNotAvailableError, _demo_not_available)


async def _authentication_required(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(401, "AUTHENTICATION_REQUIRED", "Authentication is required.")


async def _csrf_rejected(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(403, "CSRF_REJECTED", "CSRF validation failed.")


async def _demo_not_available(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(503, "DEMO_NOT_AVAILABLE", "Demo is not available.")


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


async def _plan_version_conflict(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(
        409,
        "PLAN_VERSION_CONFLICT",
        "The requested plan version is no longer current.",
    )


async def _plan_not_ready(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(409, "PLAN_NOT_READY", "The plan version is not ready to confirm.")


async def _plan_execution_not_allowed(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request, exc
    return _error(
        409,
        "PLAN_NOT_CONFIRMED",
        "The plan must be explicitly confirmed before execution.",
    )


async def _feedback_selection_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request, exc
    return _error(
        422,
        "PLAN_FEEDBACK_SELECTION_INVALID",
        "The selected plan items do not match the completion status.",
    )


async def _memory_not_found(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(404, "MEMORY_NOT_FOUND", "Memory was not found.")


async def _memory_suggestion_unavailable(
    request: Request, exc: Exception
) -> JSONResponse:
    del request, exc
    return _error(
        404,
        "MEMORY_SUGGESTION_NOT_AVAILABLE",
        "Memory suggestion is not available.",
    )


async def _memory_version_conflict(
    request: Request, exc: Exception
) -> JSONResponse:
    del request, exc
    return _error(409, "MEMORY_VERSION_CONFLICT", "Memory version conflict.")


async def _sensitive_memory_rejected(
    request: Request, exc: Exception
) -> JSONResponse:
    del request, exc
    return _error(
        422,
        "SENSITIVE_MEMORY_REJECTED",
        "Only explicitly authorized coarse areas can be saved as long-term memory.",
    )


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
        "The input provider could not complete the request.",
        trace_id=exc.trace_id,
        recovery_actions=("retry_later", "supply_text"),
    )


async def _provider_not_configured(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _error(503, "PROVIDER_NOT_CONFIGURED", "Collection input is unavailable.")


async def _plan_provider_not_configured(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request, exc
    return _error(
        503,
        "PLAN_PROVIDER_NOT_CONFIGURED",
        "Plan generation is unavailable until its providers are configured.",
    )


async def _workflow_timeout(request: Request, exc: Exception) -> JSONResponse:
    del request
    assert isinstance(exc, TextCollectionTimeoutError)
    return _error(
        504,
        "RUN_TIMEOUT",
        "The collection input request timed out.",
        trace_id=exc.trace_id,
        recovery_actions=("retry_later",),
    )


async def _workflow_error(request: Request, exc: Exception) -> JSONResponse:
    del request
    assert isinstance(exc, TextCollectionRunError)
    return _error(
        500,
        exc.error_code,
        "The collection input request failed.",
        trace_id=exc.trace_id,
        recovery_actions=(
            ("reupload_image", "supply_text")
            if exc.error_code.startswith(("IMAGE_", "STORAGE_"))
            else ("retry_later",)
        ),
    )


def _error(
    status_code: int,
    error_code: str,
    message: str,
    *,
    trace_id: str | None = None,
    issues: tuple[dict[str, str], ...] = (),
    recovery_actions: tuple[str, ...] = (),
) -> JSONResponse:
    content: dict[str, object] = {"error_code": error_code, "message": message}
    if trace_id is not None:
        content["trace_id"] = trace_id
    if issues:
        content["issues"] = issues
    if recovery_actions:
        content["recovery_actions"] = recovery_actions
    return JSONResponse(status_code=status_code, content=content)

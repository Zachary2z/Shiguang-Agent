"""Single API boundary for verified browser identity, database routing, and CSRF."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.pricing import ConfiguredPricingPolicy
from app.application.text_collection_workflow import IdempotencyLockRegistry
from app.application.web_sessions import WebSessionService
from app.config import Settings
from app.domain.collections import UserMode
from app.domain.identity import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    BrowserSession,
    CurrentPrincipal,
    PrincipalMode,
    hash_session_secret,
)
from app.infrastructure.db import Database
from app.infrastructure.repositories import SqlAlchemyCollectionRepository
from app.providers.storage import StorageProvider
from app.providers.web import WebContentProvider
from nanobot_core.providers import ModelProvider

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class ProviderNotConfiguredError(RuntimeError):
    """No text provider was injected for this process."""


class PlanProviderNotConfiguredError(RuntimeError):
    """The worker cannot execute a plan with the configured provider set."""


class AuthenticationRequiredError(PermissionError):
    def __init__(self) -> None:
        super().__init__("authentication required")


class CsrfRejectedError(PermissionError):
    def __init__(self) -> None:
        super().__init__("csrf validation failed")


class DemoNotAvailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("demo is not available")


@dataclass(frozen=True)
class RequestIdentityContext:
    principal: CurrentPrincipal
    browser_session: BrowserSession
    session: AsyncSession
    database: Database


async def get_request_identity(request: Request) -> AsyncIterator[RequestIdentityContext]:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token is None:
        raise AuthenticationRequiredError

    databases: tuple[tuple[Database | None, PrincipalMode], ...] = (
        (request.app.state.demo_database, PrincipalMode.DEMO),
        (request.app.state.database, PrincipalMode.REAL),
    )
    for database, mode in databases:
        if database is None:
            continue
        async with database.session() as session:
            resolved = await WebSessionService(session=session).resolve(
                session_token=session_token,
                mode=mode,
            )
            if resolved is None:
                continue
            principal, browser_session = resolved
            user = await SqlAlchemyCollectionRepository(session).get_user(
                user_id=principal.user_id
            )
            expected_mode = UserMode.DEMO if mode is PrincipalMode.DEMO else UserMode.REAL
            if user is None or user.mode is not expected_mode:
                raise AuthenticationRequiredError
            _require_csrf_if_writing(request, browser_session)
            await session.rollback()
            yield RequestIdentityContext(
                principal=principal,
                browser_session=browser_session,
                session=session,
                database=database,
            )
            return
    raise AuthenticationRequiredError


def _require_csrf_if_writing(
    request: Request,
    browser_session: BrowserSession,
) -> None:
    if request.method in _SAFE_METHODS:
        return
    csrf_token = request.headers.get(CSRF_HEADER_NAME)
    try:
        supplied_hash = "" if csrf_token is None else hash_session_secret(csrf_token)
    except ValueError:
        supplied_hash = ""
    if not hmac.compare_digest(supplied_hash, browser_session.csrf_token_hash):
        raise CsrfRejectedError


def get_db_session(
    context: Annotated[RequestIdentityContext, Depends(get_request_identity)],
) -> AsyncSession:
    return context.session


def get_current_principal(
    context: Annotated[RequestIdentityContext, Depends(get_request_identity)],
) -> CurrentPrincipal:
    return context.principal


def get_current_user_id(
    context: Annotated[RequestIdentityContext, Depends(get_request_identity)],
) -> str:
    return context.principal.user_id


def get_current_database(
    context: Annotated[RequestIdentityContext, Depends(get_request_identity)],
) -> Database:
    return context.database


async def get_demo_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database | None = request.app.state.demo_database
    if database is None:
        raise DemoNotAvailableError
    async with database.session() as session:
        yield session


def get_text_provider(request: Request) -> ModelProvider:
    provider: ModelProvider | None = request.app.state.text_provider
    if provider is None:
        raise ProviderNotConfiguredError
    return provider


def get_web_provider(request: Request) -> WebContentProvider | None:
    provider: WebContentProvider | None = request.app.state.web_provider
    return provider


def get_storage_provider(
    request: Request,
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> StorageProvider | None:
    state_name = (
        "demo_storage_provider"
        if principal.mode is PrincipalMode.DEMO
        else "storage_provider"
    )
    provider: StorageProvider | None = getattr(request.app.state, state_name)
    return provider


def get_pricing(request: Request) -> ConfiguredPricingPolicy:
    settings: Settings = request.app.state.settings
    return ConfiguredPricingPolicy.from_settings(settings)


def get_idempotency_locks(request: Request) -> IdempotencyLockRegistry:
    locks: IdempotencyLockRegistry = request.app.state.idempotency_locks
    return locks


def get_agent_timeout_seconds(request: Request) -> float:
    settings: Settings = request.app.state.settings
    return settings.agent_timeout_seconds

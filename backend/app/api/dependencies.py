"""M0 API dependency boundaries for identity, database, and providers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.demo_sessions import DEMO_USER_ID
from app.application.pricing import ConfiguredPricingPolicy
from app.application.text_collection_workflow import IdempotencyLockRegistry
from app.config import Settings
from nanobot_core.providers import ModelProvider


class ProviderNotConfiguredError(RuntimeError):
    """No text provider was injected for this process."""


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session() as session:
        yield session


def get_current_user_id() -> str:
    """M0 uses one server-owned identity and never trusts a client user_id."""

    return DEMO_USER_ID


def get_text_provider(request: Request) -> ModelProvider:
    provider: ModelProvider | None = request.app.state.text_provider
    if provider is None:
        raise ProviderNotConfiguredError
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

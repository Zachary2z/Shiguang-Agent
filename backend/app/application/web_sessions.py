"""Creation, recovery, CSRF rotation, and revocation for the single Web Session model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity import (
    BrowserSession,
    CurrentPrincipal,
    PrincipalMode,
    generate_session_secret,
    hash_session_secret,
)
from app.domain.time import utc_now
from app.infrastructure.repositories.web_sessions import SqlAlchemyWebSessionRepository


@dataclass(frozen=True, repr=False)
class IssuedWebSession:
    browser_session: BrowserSession
    session_token: str
    csrf_token: str


class WebSessionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._repository = SqlAlchemyWebSessionRepository(session)
        self._now = now

    async def create(
        self,
        *,
        user_id: str,
        mode: PrincipalMode,
        lifetime: timedelta,
    ) -> IssuedWebSession:
        if lifetime <= timedelta(0):
            raise ValueError("web session lifetime must be positive")
        timestamp = self._now()
        token = generate_session_secret()
        csrf_token = generate_session_secret()
        browser_session = BrowserSession(
            id=f"wbs_{uuid4().hex}",
            user_id=user_id,
            token_hash=hash_session_secret(token),
            csrf_token_hash=hash_session_secret(csrf_token),
            created_at=timestamp,
            expires_at=timestamp + lifetime,
        )
        await self._repository.add(browser_session)
        return IssuedWebSession(
            browser_session=browser_session,
            session_token=token,
            csrf_token=csrf_token,
        )

    async def resolve(
        self,
        *,
        session_token: str,
        mode: PrincipalMode,
    ) -> tuple[CurrentPrincipal, BrowserSession] | None:
        try:
            token_hash = hash_session_secret(session_token)
        except ValueError:
            return None
        browser_session = await self._repository.get_by_token_hash(token_hash)
        if browser_session is None or not browser_session.is_active_at(self._now()):
            return None
        return (
            CurrentPrincipal(
                web_session_id=browser_session.id,
                user_id=browser_session.user_id,
                mode=mode,
                expires_at=browser_session.expires_at,
            ),
            browser_session,
        )

    async def rotate_credentials(self, *, session_id: str) -> IssuedWebSession | None:
        session_token = generate_session_secret()
        csrf_token = generate_session_secret()
        browser_session = await self._repository.replace_credentials(
            session_id=session_id,
            token_hash=hash_session_secret(session_token),
            csrf_token_hash=hash_session_secret(csrf_token),
        )
        if browser_session is None:
            return None
        return IssuedWebSession(
            browser_session=browser_session,
            session_token=session_token,
            csrf_token=csrf_token,
        )

    async def revoke(self, *, session_id: str) -> BrowserSession | None:
        return await self._repository.revoke(
            session_id=session_id,
            revoked_at=self._now(),
        )

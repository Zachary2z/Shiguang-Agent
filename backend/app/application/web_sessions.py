"""Creation, stable recovery, and revocation for the single Web Session model."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity import (
    BrowserSession,
    CurrentPrincipal,
    PrincipalMode,
    derive_csrf_token,
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
        at: datetime | None = None,
    ) -> IssuedWebSession:
        if lifetime <= timedelta(0):
            raise ValueError("web session lifetime must be positive")
        timestamp = at or self._now()
        token = generate_session_secret()
        csrf_token = derive_csrf_token(token)
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
        at: datetime | None = None,
    ) -> tuple[CurrentPrincipal, BrowserSession] | None:
        try:
            token_hash = hash_session_secret(session_token)
        except ValueError:
            return None
        browser_session = await self._repository.get_by_token_hash(token_hash)
        if browser_session is None or not browser_session.is_active_at(at or self._now()):
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

    async def resume(
        self,
        *,
        session_token: str,
        mode: PrincipalMode,
        at: datetime | None = None,
    ) -> tuple[CurrentPrincipal, IssuedWebSession] | None:
        resolved = await self.resolve(
            session_token=session_token,
            mode=mode,
            at=at,
        )
        if resolved is None:
            return None
        principal, browser_session = resolved
        csrf_token = derive_csrf_token(session_token)
        if not hmac.compare_digest(
            hash_session_secret(csrf_token),
            browser_session.csrf_token_hash,
        ):
            return None
        return (
            principal,
            IssuedWebSession(
                browser_session=browser_session,
                session_token=session_token,
                csrf_token=csrf_token,
            ),
        )

    async def revoke(self, *, session_id: str) -> BrowserSession | None:
        return await self._repository.revoke(
            session_id=session_id,
            revoked_at=self._now(),
        )

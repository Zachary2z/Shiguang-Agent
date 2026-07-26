"""Per-browser Demo sandbox creation and recovery in the physical Demo database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.web_sessions import WebSessionService
from app.domain.collections import (
    PlanCity,
    Session,
    SessionChannel,
    SupportedTimezone,
    User,
    UserMode,
)
from app.domain.identifiers import generate_user_id
from app.domain.identity import PrincipalMode
from app.domain.time import utc_now
from app.infrastructure.repositories import SqlAlchemyCollectionRepository


@dataclass(frozen=True, repr=False)
class DemoSessionBootstrap:
    message_session: Session
    session_token: str
    csrf_token: str
    expires_at: datetime
    resumed: bool


class DemoSessionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        lifetime: timedelta,
    ) -> None:
        self._session = session
        self._lifetime = lifetime
        self._repository = SqlAlchemyCollectionRepository(session)
        self._web_sessions = WebSessionService(session=session)

    async def start(self, *, session_token: str | None) -> DemoSessionBootstrap:
        if session_token is not None:
            resolved = await self._web_sessions.resolve(
                session_token=session_token,
                mode=PrincipalMode.DEMO,
            )
            if resolved is not None:
                principal, browser_session = resolved
                user = await self._repository.get_user(user_id=principal.user_id)
                message_sessions = await self._repository.list_sessions(
                    user_id=principal.user_id
                )
                active = next(
                    (
                        item
                        for item in message_sessions
                        if item.channel is SessionChannel.DEMO
                    ),
                    None,
                )
                if user is not None and user.mode is UserMode.DEMO and active is not None:
                    rotated = await self._web_sessions.rotate_credentials(
                        session_id=browser_session.id
                    )
                    if rotated is not None:
                        await self._session.commit()
                        return DemoSessionBootstrap(
                            message_session=active,
                            session_token=rotated.session_token,
                            csrf_token=rotated.csrf_token,
                            expires_at=rotated.browser_session.expires_at,
                            resumed=True,
                        )

        # Resolution is read-only but SQLAlchemy autobegins a transaction for it.
        # End that transaction before atomically creating a replacement sandbox.
        await self._session.rollback()
        timestamp = utc_now()
        user = User(
            id=generate_user_id(),
            mode=UserMode.DEMO,
            default_plan_city=PlanCity.SHENZHEN,
            timezone=SupportedTimezone.ASIA_SHANGHAI,
            created_at=timestamp,
        )
        message_session = Session(
            user_id=user.id,
            channel=SessionChannel.DEMO,
            created_at=timestamp,
            updated_at=timestamp,
        )
        async with self._session.begin():
            await self._repository.add_user(user_id=user.id, user=user)
            await self._repository.add_session(
                user_id=user.id,
                session=message_session,
            )
            issued = await self._web_sessions.create(
                user_id=user.id,
                mode=PrincipalMode.DEMO,
                lifetime=self._lifetime,
            )
        return DemoSessionBootstrap(
            message_session=message_session,
            session_token=issued.session_token,
            csrf_token=issued.csrf_token,
            expires_at=issued.browser_session.expires_at,
            resumed=False,
        )

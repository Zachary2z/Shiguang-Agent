"""M0-only fixed Demo identity and fresh Session creation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.collections import (
    PlanCity,
    Session,
    SessionChannel,
    SupportedTimezone,
    User,
    UserMode,
)
from app.domain.time import utc_now
from app.infrastructure.repositories import SqlAlchemyCollectionRepository

DEMO_USER_ID = "usr_b5e5b707c5d6136963dd833791d1eab4"


class DemoSessionService:
    """Ensure the server-owned Demo user and create a fresh isolated Session."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._repository = SqlAlchemyCollectionRepository(session)
        self._now = now

    async def create(self) -> Session:
        timestamp = self._now()
        demo_session = Session(
            user_id=DEMO_USER_ID,
            channel=SessionChannel.DEMO,
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            await self._create_in_transaction(demo_session, timestamp)
        except IntegrityError:
            await self._session.rollback()
            await self._create_in_transaction(demo_session, timestamp)
        return demo_session

    async def _create_in_transaction(
        self,
        demo_session: Session,
        timestamp: datetime,
    ) -> None:
        async with self._session.begin():
            user = await self._repository.get_user(user_id=DEMO_USER_ID)
            if user is None:
                await self._repository.add_user(
                    user_id=DEMO_USER_ID,
                    user=User(
                        id=DEMO_USER_ID,
                        mode=UserMode.DEMO,
                        default_plan_city=PlanCity.SHENZHEN,
                        timezone=SupportedTimezone.ASIA_SHANGHAI,
                        created_at=timestamp,
                    ),
                )
            await self._repository.add_session(
                user_id=DEMO_USER_ID,
                session=demo_session,
            )

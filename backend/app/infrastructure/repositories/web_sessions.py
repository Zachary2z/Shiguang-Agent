"""SQLAlchemy implementation of the one Web Session repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity import BrowserSession
from app.domain.time import as_utc, required_utc
from app.infrastructure.db.models.identity import BrowserSessionModel


class SqlAlchemyWebSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, browser_session: BrowserSession) -> BrowserSession:
        self._session.add(
            BrowserSessionModel(
                id=browser_session.id,
                user_id=browser_session.user_id,
                token_hash=browser_session.token_hash,
                csrf_token_hash=browser_session.csrf_token_hash,
                created_at=browser_session.created_at,
                expires_at=browser_session.expires_at,
                revoked_at=browser_session.revoked_at,
            )
        )
        await self._session.flush()
        return browser_session

    async def get_by_token_hash(self, token_hash: str) -> BrowserSession | None:
        model = await self._session.scalar(
            select(BrowserSessionModel).where(BrowserSessionModel.token_hash == token_hash)
        )
        return None if model is None else _to_domain(model)

    async def replace_credentials(
        self,
        *,
        session_id: str,
        token_hash: str,
        csrf_token_hash: str,
    ) -> BrowserSession | None:
        await self._session.execute(
            update(BrowserSessionModel)
            .where(
                BrowserSessionModel.id == session_id,
                BrowserSessionModel.revoked_at.is_(None),
            )
            .values(
                token_hash=token_hash,
                csrf_token_hash=csrf_token_hash,
            )
        )
        await self._session.flush()
        model = await self._session.get(BrowserSessionModel, session_id)
        return None if model is None or model.revoked_at is not None else _to_domain(model)

    async def revoke(
        self,
        *,
        session_id: str,
        revoked_at: datetime,
    ) -> BrowserSession | None:
        await self._session.execute(
            update(BrowserSessionModel)
            .where(
                BrowserSessionModel.id == session_id,
                BrowserSessionModel.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        await self._session.flush()
        model = await self._session.get(BrowserSessionModel, session_id)
        return None if model is None else _to_domain(model)


def _to_domain(model: BrowserSessionModel) -> BrowserSession:
    return BrowserSession(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        csrf_token_hash=model.csrf_token_hash,
        created_at=required_utc(model.created_at),
        expires_at=required_utc(model.expires_at),
        revoked_at=as_utc(model.revoked_at),
    )

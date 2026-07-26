"""Typed SQLAlchemy DML result boundary shared by repositories."""

from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Delete, Update


async def execute_dml_rowcount(
    session: AsyncSession,
    statement: Update | Delete,
) -> int:
    """Execute UPDATE/DELETE through the ORM session and return its row count."""

    result = await session.execute(statement)
    if not isinstance(result, CursorResult):
        raise RuntimeError("DML execution did not return a cursor result")
    return result.rowcount


__all__ = ["execute_dml_rowcount"]

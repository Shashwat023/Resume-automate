from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db

DbDep = AsyncIterator[AsyncSession]

__all__ = ["get_db"]

"""
All SQLAlchemy query construction for TrackedCompany lives here, following
the same repository pattern as the other aggregates. Not used by any
router today — only by the portals.yml seeding script — but the same
boundary rule applies: nowhere else should query TrackedCompany directly.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import TrackedCompany


class TrackedCompanyRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_careers_url(self, careers_url: str) -> TrackedCompany | None:
        stmt = select(TrackedCompany).where(TrackedCompany.careers_url == careers_url)
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self, name: str, careers_url: str, *, enabled: bool = True
    ) -> tuple[TrackedCompany, bool]:
        """Returns (row, was_inserted)."""
        existing = await self.get_by_careers_url(careers_url)
        if existing is not None:
            existing.name = name
            existing.enabled = enabled
            await self._db.commit()
            return existing, False

        row = TrackedCompany(name=name, careers_url=careers_url, enabled=enabled)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row, True

    async def count(self) -> int:
        stmt = select(TrackedCompany)
        result = await self._db.execute(stmt)
        return len(result.scalars().all())

    async def mark_synced(self, careers_url: str, when: datetime) -> None:
        existing = await self.get_by_careers_url(careers_url)
        if existing is not None:
            existing.last_synced_at = when
            await self._db.commit()

"""
All SQLAlchemy query construction for TrackedCompany lives here, following
the same repository pattern as the other aggregates — nowhere else should
query TrackedCompany directly. Used by the portals.yml seeding script and,
since the "sync all tracked companies" feature, by
services/scraper/bulk_sync_service.py too.
"""

from datetime import datetime

from sqlalchemy import func, or_, select
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

    async def disable_missing_from(self, current_careers_urls: set[str]) -> int:
        """
        Real bug, live-caught: `seed_portals.py`'s `seed()` only ever
        inserts/updates — a company removed from `portals.yml` stayed
        `enabled=True` in the DB forever, so deleting it from the file
        (e.g. because it's structurally unscrapable and would just burn
        tokens every week) did NOT stop the bulk sync from still picking
        it up; `next_eligible()`'s query reads this table, never the
        file directly. Disables (not deletes — keeps history, reversible
        by re-adding to the file) every currently-enabled row whose
        `careers_url` is no longer present. Returns the count disabled.
        """
        stmt = select(TrackedCompany).where(TrackedCompany.enabled.is_(True))
        rows = (await self._db.execute(stmt)).scalars().all()
        disabled = 0
        for row in rows:
            if row.careers_url not in current_careers_urls:
                row.enabled = False
                disabled += 1
        if disabled:
            await self._db.commit()
        return disabled

    def _eligible_stmt(self, cutoff: datetime):
        """enabled AND (never synced OR last synced before `cutoff`) — the
        one query both `count_eligible` and `next_eligible` share, so the
        two can never disagree about what counts as "still to do"."""
        return select(TrackedCompany).where(
            TrackedCompany.enabled.is_(True),
            or_(
                TrackedCompany.last_synced_at.is_(None),
                TrackedCompany.last_synced_at < cutoff,
            ),
        )

    async def count_eligible(self, cutoff: datetime) -> int:
        stmt = select(func.count()).select_from(self._eligible_stmt(cutoff).subquery())
        return (await self._db.execute(stmt)).scalar_one()

    async def next_eligible(self, cutoff: datetime) -> TrackedCompany | None:
        """
        The bulk sync's entire "resume where it left off" mechanism: no
        separate cursor is stored anywhere. `mark_synced` moves a company's
        `last_synced_at` to now the instant it's attempted (success or
        failure), which drops it out of this same eligibility query — so
        re-running this after a pause, a server restart, or on a fresh day
        naturally returns whatever hasn't been touched yet, in a stable,
        deterministic order.
        """
        stmt = self._eligible_stmt(cutoff).order_by(TrackedCompany.id.asc()).limit(1)
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def mark_synced(self, careers_url: str, when: datetime) -> None:
        existing = await self.get_by_careers_url(careers_url)
        if existing is not None:
            existing.last_synced_at = when
            await self._db.commit()

"""
All SQLAlchemy query construction for Job lives here. The dynamic
filter-building, count query, sort, and pagination are extracted verbatim
from what was inline in api/jobs.py's search_jobs() handler.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Job


class JobRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, job_id: int) -> Job | None:
        return await self._db.get(Job, job_id)

    async def search(
        self,
        *,
        keyword: str | None,
        company_name: str | None,
        location: str | None,
        location_type: str | None,
        ats: str | None,
        industry: str | None,
        posted_within_hours: int | None,
        page: int,
        limit: int,
        sort: str | None,
    ) -> tuple[list[Job], int]:
        stmt = select(Job)

        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(or_(Job.title.ilike(like), Job.description.ilike(like)))
        if company_name:
            stmt = stmt.where(Job.company_name.ilike(f"%{company_name}%"))
        if location:
            stmt = stmt.where(Job.location.ilike(f"%{location}%"))
        if location_type:
            stmt = stmt.where(Job.location_type == location_type)
        if ats:
            stmt = stmt.where(Job.ats == ats)
        if industry:
            stmt = stmt.where(Job.industry == industry)
        # posted_within_hours needs a real posted_date -> datetime comparison; skipped
        # for the MVP scraper which stores posted_date as free text from source sites.

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._db.execute(count_stmt)).scalar_one()

        if sort == "oldest":
            stmt = stmt.order_by(Job.created_at.asc())
        else:
            stmt = stmt.order_by(Job.created_at.desc())

        stmt = stmt.offset((page - 1) * limit).limit(limit)
        jobs = (await self._db.execute(stmt)).scalars().all()

        return list(jobs), total

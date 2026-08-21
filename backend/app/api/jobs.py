from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.db_models import Job
from app.models.schemas import JobOut, JobSearchOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/search", response_model=JobSearchOut)
async def search_jobs(
    keyword: str | None = None,
    company_name: str | None = None,
    location: str | None = None,
    location_type: str | None = None,
    ats: str | None = None,
    industry: str | None = None,
    posted_within_hours: int | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> JobSearchOut:
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
    total = (await db.execute(count_stmt)).scalar_one()

    if sort == "oldest":
        stmt = stmt.order_by(Job.created_at.asc())
    else:
        stmt = stmt.order_by(Job.created_at.desc())

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    jobs = (await db.execute(stmt)).scalars().all()

    return JobSearchOut(
        jobs=[JobOut(**{**j.__dict__, "id": str(j.id)}) for j in jobs],
        total=total,
        page=page,
        limit=limit,
    )

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_job_search_service
from app.models.schemas import JobSearchOut
from app.services.job_search_service import JobSearchService

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
    service: JobSearchService = Depends(get_job_search_service),
) -> JobSearchOut:
    return await service.search(
        keyword=keyword,
        company_name=company_name,
        location=location,
        location_type=location_type,
        ats=ats,
        industry=industry,
        posted_within_hours=posted_within_hours,
        page=page,
        limit=limit,
        sort=sort,
    )

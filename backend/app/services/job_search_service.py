"""
Job search use case. Extracted verbatim from what was inline in
api/jobs.py's search_jobs() handler — the repository owns the query,
this owns the response shaping (id-as-string, pagination envelope).
"""

from app.models.schemas import JobOut, JobSearchOut
from app.repositories.job_repository import JobRepository


class JobSearchService:
    def __init__(self, repo: JobRepository):
        self._repo = repo

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
    ) -> JobSearchOut:
        jobs, total = await self._repo.search(
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
        return JobSearchOut(
            jobs=[JobOut(**{**j.__dict__, "id": str(j.id)}) for j in jobs],
            total=total,
            page=page,
            limit=limit,
        )

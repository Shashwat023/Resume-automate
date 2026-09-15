from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import ConflictError
from app.models.schemas import (
    AdminSyncIn,
    AdminSyncOut,
    TrackedCompanySyncStatusOut,
)
from app.services.scraper import bulk_sync_service
from app.services.scraper.sync_service import sync_company

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/sync", response_model=AdminSyncOut)
async def sync_jobs(
    payload: AdminSyncIn, db: AsyncSession = Depends(get_db)
) -> AdminSyncOut:
    # Both this route and the bulk sync's own loop drive Stagehand through
    # the SAME shared "scraper" Chrome profile (sync_service.py's
    # _SCRAPER_PROFILE_KEY) — running both at once would race over that
    # one browser session, exactly the class of bug FLAGGED.md #11/#26-29
    # already fought hard to eliminate elsewhere. Blocked here rather than
    # letting the two collide.
    status = await bulk_sync_service.get_status()
    if status["status"] == "running":
        raise ConflictError(
            "A bulk sync of all tracked companies is currently running — "
            "wait for it to finish or pause it before syncing a URL manually."
        )
    result = await sync_company(payload.company_url, db)
    return AdminSyncOut(**result)


@router.post("/sync-tracked/start", response_model=TrackedCompanySyncStatusOut)
async def start_tracked_sync() -> TrackedCompanySyncStatusOut:
    """
    Starts (or resumes a paused) sync across every company in
    config/portals.yml — distinct from the manual URL-paste flow above,
    which only ever touches the one URL given to it. See
    bulk_sync_service.py's own docstring for the pause/resume design.
    """
    result = await bulk_sync_service.start_or_resume()
    return TrackedCompanySyncStatusOut(**result)


@router.post("/sync-tracked/pause", response_model=TrackedCompanySyncStatusOut)
async def pause_tracked_sync() -> TrackedCompanySyncStatusOut:
    result = await bulk_sync_service.request_pause()
    return TrackedCompanySyncStatusOut(**result)


@router.get("/sync-tracked/status", response_model=TrackedCompanySyncStatusOut)
async def get_tracked_sync_status() -> TrackedCompanySyncStatusOut:
    result = await bulk_sync_service.get_status()
    return TrackedCompanySyncStatusOut(**result)

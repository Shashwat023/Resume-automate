from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.schemas import AdminSyncIn, AdminSyncOut
from app.services.scraper.sync_service import sync_company

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/sync", response_model=AdminSyncOut)
async def sync_jobs(
    payload: AdminSyncIn, db: AsyncSession = Depends(get_db)
) -> AdminSyncOut:
    result = await sync_company(payload.company_url, db)
    return AdminSyncOut(**result)

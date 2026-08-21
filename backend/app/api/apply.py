from fastapi import APIRouter, Depends

from app.api.deps import get_apply_service
from app.models.schemas import (
    ApplyDetailsOut,
    ApplyHistoryItemOut,
    ApplyStartIn,
    ApplyStartOut,
    ApplyStatusOut,
)
from app.services.apply_service import ApplyService

router = APIRouter(prefix="/api/apply", tags=["apply"])


@router.post("/start", response_model=ApplyStartOut)
async def start_apply(
    payload: ApplyStartIn, service: ApplyService = Depends(get_apply_service)
) -> ApplyStartOut:
    application = await service.start(payload.profile_id, payload.job_id)
    return ApplyStartOut(application_id=application.id, status=application.status)


@router.get("/status/{application_id}", response_model=ApplyStatusOut)
async def get_apply_status(
    application_id: str, service: ApplyService = Depends(get_apply_service)
) -> ApplyStatusOut:
    return await service.get_status(application_id)


@router.get("/history/{profile_id}", response_model=list[ApplyHistoryItemOut])
async def get_apply_history(
    profile_id: int, service: ApplyService = Depends(get_apply_service)
) -> list[ApplyHistoryItemOut]:
    return await service.get_history(profile_id)


@router.get("/details/{application_id}", response_model=ApplyDetailsOut)
async def get_apply_details(
    application_id: str, service: ApplyService = Depends(get_apply_service)
) -> ApplyDetailsOut:
    return await service.get_details(application_id)


@router.post("/{application_id}/pause", response_model=ApplyStatusOut)
async def pause_apply(
    application_id: str, service: ApplyService = Depends(get_apply_service)
) -> ApplyStatusOut:
    return await service.pause(application_id)


@router.post("/{application_id}/resume", response_model=ApplyStatusOut)
async def resume_apply(
    application_id: str, service: ApplyService = Depends(get_apply_service)
) -> ApplyStatusOut:
    return await service.resume(application_id)


@router.post("/{application_id}/cancel", response_model=ApplyStatusOut)
async def cancel_apply(
    application_id: str, service: ApplyService = Depends(get_apply_service)
) -> ApplyStatusOut:
    return await service.cancel(application_id)

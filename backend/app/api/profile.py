from fastapi import APIRouter, Depends

from app.api.deps import get_profile_service
from app.models.schemas import DeleteOut, ProfileCreate, ProfileOut, ProfileUpdate
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("", response_model=ProfileOut)
async def create_profile(
    payload: ProfileCreate, service: ProfileService = Depends(get_profile_service)
) -> ProfileOut:
    return await service.create(payload.model_dump())


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(
    profile_id: int, service: ProfileService = Depends(get_profile_service)
) -> ProfileOut:
    return await service.get(profile_id)


@router.put("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: int,
    payload: ProfileUpdate,
    service: ProfileService = Depends(get_profile_service),
) -> ProfileOut:
    return await service.update(profile_id, payload.model_dump(exclude_unset=True))


@router.delete("/{profile_id}", response_model=DeleteOut)
async def delete_profile(
    profile_id: int, service: ProfileService = Depends(get_profile_service)
) -> DeleteOut:
    await service.delete(profile_id)
    return DeleteOut(success=True)

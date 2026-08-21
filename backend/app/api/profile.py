from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.db_models import Profile
from app.models.schemas import DeleteOut, ProfileCreate, ProfileOut, ProfileUpdate

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("", response_model=ProfileOut)
async def create_profile(payload: ProfileCreate, db: AsyncSession = Depends(get_db)) -> Profile:
    profile = Profile(**payload.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(profile_id: int, db: AsyncSession = Depends(get_db)) -> Profile:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: int, payload: ProfileUpdate, db: AsyncSession = Depends(get_db)
) -> Profile:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", response_model=DeleteOut)
async def delete_profile(profile_id: int, db: AsyncSession = Depends(get_db)) -> DeleteOut:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.delete(profile)
    await db.commit()
    return DeleteOut(success=True)


async def _profile_exists(profile_id: int, db: AsyncSession) -> bool:
    result = await db.execute(select(Profile.id).where(Profile.id == profile_id))
    return result.scalar_one_or_none() is not None

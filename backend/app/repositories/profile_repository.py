"""
All SQLAlchemy query construction for Profile lives here — nowhere else in
the codebase should import `Profile` from models.db_models and build a
query directly. Extracted verbatim from what was inline in api/profile.py.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Profile


class ProfileRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, profile_id: int) -> Profile | None:
        return await self._db.get(Profile, profile_id)

    async def create(self, data: dict) -> Profile:
        profile = Profile(**data)
        self._db.add(profile)
        await self._db.commit()
        await self._db.refresh(profile)
        return profile

    async def update(self, profile: Profile, data: dict) -> Profile:
        for field, value in data.items():
            setattr(profile, field, value)
        await self._db.commit()
        await self._db.refresh(profile)
        return profile

    async def delete(self, profile: Profile) -> None:
        await self._db.delete(profile)
        await self._db.commit()

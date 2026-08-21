"""
Profile use cases: create/get/update/delete. Extracted verbatim from what
was inline in api/profile.py, including the partial-update semantics
(`exclude_unset` merge) that were previously sitting directly in the route.
"""

from app.core.exceptions import NotFoundError
from app.models.db_models import Profile
from app.repositories.profile_repository import ProfileRepository


class ProfileService:
    def __init__(self, repo: ProfileRepository):
        self._repo = repo

    async def create(self, data: dict) -> Profile:
        return await self._repo.create(data)

    async def get(self, profile_id: int) -> Profile:
        profile = await self._repo.get(profile_id)
        if profile is None:
            raise NotFoundError("Profile not found")
        return profile

    async def update(self, profile_id: int, data: dict) -> Profile:
        profile = await self.get(profile_id)
        return await self._repo.update(profile, data)

    async def delete(self, profile_id: int) -> None:
        profile = await self.get(profile_id)
        await self._repo.delete(profile)

"""
Resume use cases: upload/get/delete. Extracted verbatim from what was
inline in api/resume.py — file I/O now goes through ports.ResumeStoragePort
instead of the route touching the filesystem directly.
"""

from app.core.exceptions import NotFoundError
from app.models.db_models import Resume
from app.ports import ResumeStoragePort
from app.repositories.profile_repository import ProfileRepository
from app.repositories.resume_repository import ResumeRepository


class ResumeService:
    def __init__(
        self,
        resume_repo: ResumeRepository,
        profile_repo: ProfileRepository,
        storage: ResumeStoragePort,
    ):
        self._resume_repo = resume_repo
        self._profile_repo = profile_repo
        self._storage = storage

    async def upload(self, profile_id: int, filename: str, contents: bytes) -> str:
        profile = await self._profile_repo.get(profile_id)
        if profile is None:
            raise NotFoundError("Profile not found")

        saved = await self._storage.save(profile_id, filename or "resume", contents)
        await self._resume_repo.upsert(profile_id, saved.file_path, saved.resume_url)
        return saved.resume_url

    async def get(self, profile_id: int) -> Resume:
        resume = await self._resume_repo.get(profile_id)
        if resume is None:
            raise NotFoundError("Resume not found")
        return resume

    async def delete(self, profile_id: int) -> None:
        resume = await self.get(profile_id)
        await self._storage.delete(resume.file_path)
        await self._resume_repo.delete(resume)

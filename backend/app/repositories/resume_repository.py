"""
All SQLAlchemy query construction for Resume lives here. Extracted
verbatim from what was inline in api/resume.py.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Resume


class ResumeRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, profile_id: int) -> Resume | None:
        return await self._db.get(Resume, profile_id)

    async def upsert(self, profile_id: int, file_path: str, resume_url: str) -> Resume:
        resume = await self.get(profile_id)
        if resume is None:
            resume = Resume(
                profile_id=profile_id, file_path=file_path, resume_url=resume_url
            )
            self._db.add(resume)
        else:
            resume.file_path = file_path
            resume.resume_url = resume_url
        await self._db.commit()
        return resume

    async def delete(self, resume: Resume) -> None:
        await self._db.delete(resume)
        await self._db.commit()

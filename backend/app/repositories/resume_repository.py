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

    async def upsert(
        self,
        profile_id: int,
        file_path: str,
        resume_url: str,
        extracted_text: str | None = None,
    ) -> Resume:
        resume = await self.get(profile_id)
        if resume is None:
            resume = Resume(
                profile_id=profile_id,
                file_path=file_path,
                resume_url=resume_url,
                extracted_text=extracted_text,
            )
            self._db.add(resume)
        else:
            resume.file_path = file_path
            resume.resume_url = resume_url
            # A re-upload replaces the old resume's text; parsed_facts was
            # derived from the old text, so it's now stale and must be
            # invalidated rather than served for a different document.
            resume.extracted_text = extracted_text
            resume.parsed_facts = None
        await self._db.commit()
        return resume

    async def set_parsed_facts(self, profile_id: int, parsed_facts: str) -> None:
        resume = await self.get(profile_id)
        if resume is not None:
            resume.parsed_facts = parsed_facts
            await self._db.commit()

    async def delete(self, resume: Resume) -> None:
        await self._db.delete(resume)
        await self._db.commit()

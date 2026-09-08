"""
All SQLAlchemy query construction for AnswerLibrary lives here, following
the same repository pattern as profile/resume/job/application.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import AnswerLibrary


class AnswerLibraryRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, profile_id: int, question_hash: str) -> AnswerLibrary | None:
        return await self._db.get(AnswerLibrary, (profile_id, question_hash))

    async def upsert(
        self,
        profile_id: int,
        question_hash: str,
        question_text: str,
        answer: str,
        *,
        source: str,
        confidence: float | None,
    ) -> AnswerLibrary:
        """
        Human answers (source='human') always overwrite whatever is stored,
        LLM or human. LLM answers (source='llm') never overwrite an
        existing human answer — the human's answer is the ground truth for
        that question going forward, per PLAN.md Part D.
        """
        existing = await self.get(profile_id, question_hash)
        if existing is not None and existing.source == "human" and source != "human":
            return existing

        if existing is None:
            existing = AnswerLibrary(profile_id=profile_id, question_hash=question_hash)
            self._db.add(existing)

        existing.question_text = question_text
        existing.answer = answer
        existing.source = source
        existing.confidence = confidence
        await self._db.commit()
        return existing

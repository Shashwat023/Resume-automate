"""
Resume use cases: upload/get/delete. Extracted verbatim from what was
inline in api/resume.py — file I/O now goes through ports.ResumeStoragePort
instead of the route touching the filesystem directly.
"""

import json

from app.core.exceptions import NotFoundError
from app.models.db_models import Resume
from app.ports import ResumeStoragePort
from app.repositories.profile_repository import ProfileRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.engine.openrouter_client import OpenRouterError
from app.services.engine.resume_parse import ResumeFacts, parse_resume_facts
from app.services.resume.extract import extract_text


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
        text = extract_text(filename or "resume", contents)
        await self._resume_repo.upsert(
            profile_id, saved.file_path, saved.resume_url, extracted_text=text
        )
        return saved.resume_url

    async def get_facts(self, profile_id: int) -> ResumeFacts:
        """
        Used by the automation engine (Tier 1), not the public API. Parses
        once per resume and caches on Resume.parsed_facts — every
        application after the first pays zero extra LLM cost for this.
        Degrades to empty facts (never raises) if there's no resume, no
        extracted text, or no OpenRouter key configured — Tier 1 keeps
        working off the profile alone in that case, same pattern as its
        own kill switch.
        """
        resume = await self._resume_repo.get(profile_id)
        if resume is None:
            return ResumeFacts()

        if resume.parsed_facts:
            return ResumeFacts.model_validate(json.loads(resume.parsed_facts))

        if not resume.extracted_text:
            return ResumeFacts()

        try:
            facts = await parse_resume_facts(resume.extracted_text)
        except OpenRouterError:
            return ResumeFacts()

        await self._resume_repo.set_parsed_facts(
            profile_id, facts.model_dump_json()
        )
        return facts

    async def get(self, profile_id: int) -> Resume:
        resume = await self._resume_repo.get(profile_id)
        if resume is None:
            raise NotFoundError("Resume not found")
        return resume

    async def delete(self, profile_id: int) -> None:
        resume = await self.get(profile_id)
        await self._storage.delete(resume.file_path)
        await self._resume_repo.delete(resume)

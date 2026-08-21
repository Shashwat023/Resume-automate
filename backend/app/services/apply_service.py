"""
Application lifecycle use cases: start/status/history/details/pause/resume/
cancel. Extracted verbatim from what was inline in api/apply.py — the
pause/resume/cancel transition VALIDITY rules now live in
domain/application_transitions.py; this orchestrates repository +
domain + queue.
"""

from datetime import datetime, timezone

from app.core.exceptions import NotFoundError
from app.domain import application_transitions as transitions
from app.domain import status as st
from app.models.db_models import Application
from app.models.schemas import (
    ApplyDetailsOut,
    ApplyHistoryItemOut,
    ApplyStatusOut,
)
from app.ports import QueuePort
from app.repositories.application_repository import ApplicationRepository
from app.repositories.job_repository import JobRepository
from app.repositories.profile_repository import ProfileRepository


class ApplyService:
    def __init__(
        self,
        application_repo: ApplicationRepository,
        profile_repo: ProfileRepository,
        job_repo: JobRepository,
        queue: QueuePort,
    ):
        self._applications = application_repo
        self._profiles = profile_repo
        self._jobs = job_repo
        self._queue = queue

    async def start(self, profile_id: int, job_id: int) -> Application:
        profile = await self._profiles.get(profile_id)
        if profile is None:
            raise NotFoundError("Profile not found")
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFoundError("Job not found")

        application = await self._applications.create(profile_id, job_id, st.QUEUED)
        await self._applications.add_event(application.id, "Application queued")
        await self._applications.commit()
        await self._applications.refresh(application)

        await self._queue.enqueue_application(application.id)
        return application

    async def get_status(self, application_id: str) -> ApplyStatusOut:
        application = await self._require(application_id)
        job = await self._jobs.get(application.job_id)
        return ApplyStatusOut(
            application_id=application.id,
            status=application.status,
            job_title=job.title if job else None,
            company=job.company_name if job else None,
            started_at=application.started_at,
            finished_at=application.finished_at,
            error=application.error,
        )

    async def get_history(self, profile_id: int) -> list[ApplyHistoryItemOut]:
        rows = await self._applications.history_with_job(profile_id)
        return [
            ApplyHistoryItemOut(
                application_id=app.id,
                company_name=job.company_name,
                job_title=job.title,
                status=app.status,
                started_at=app.started_at,
                finished_at=app.finished_at,
            )
            for app, job in rows
        ]

    async def get_details(self, application_id: str) -> ApplyDetailsOut:
        application = await self._require(application_id)
        profile = await self._profiles.get(application.profile_id)
        job = await self._jobs.get(application.job_id)
        return ApplyDetailsOut(
            application_id=application.id,
            profile={"id": profile.id, "full_name": profile.full_name}
            if profile
            else {},
            job={"id": job.id, "title": job.title, "company_name": job.company_name}
            if job
            else {},
            status=application.status,
            error=application.error,
            started_at=application.started_at,
            finished_at=application.finished_at,
        )

    async def pause(self, application_id: str) -> ApplyStatusOut:
        application = await self._require(application_id)
        transitions.ensure_can_pause(application.status)
        application.status = st.NEEDS_INPUT
        application.pause_reason = "manual_pause"
        await self._applications.add_event(application.id, "Paused by user")
        await self._applications.commit()
        return await self.get_status(application_id)

    async def resume(self, application_id: str) -> ApplyStatusOut:
        application = await self._require(application_id)
        transitions.ensure_can_resume(application.status)
        application.status = st.RUNNING
        application.pause_reason = None
        await self._applications.add_event(application.id, "Resumed by user")
        await self._applications.commit()
        await self._queue.signal_resume(application_id)
        return await self.get_status(application_id)

    async def cancel(self, application_id: str) -> ApplyStatusOut:
        application = await self._require(application_id)
        transitions.ensure_can_cancel(application.status)
        application.status = st.CANCELLED
        application.finished_at = datetime.now(timezone.utc)
        await self._applications.add_event(application.id, "Cancelled by user")
        await self._applications.commit()
        await self._queue.signal_cancel(application_id)
        return await self.get_status(application_id)

    async def _require(self, application_id: str) -> Application:
        application = await self._applications.get(application_id)
        if application is None:
            raise NotFoundError("Application not found")
        return application

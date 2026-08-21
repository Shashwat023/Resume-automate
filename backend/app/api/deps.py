"""
Dependency-injection hub. Routes depend on service classes via FastAPI's
Depends() chain; services depend on repositories and ports, never directly
on the DB session or infrastructure — that indirection is what makes the
service layer testable with fakes.
"""

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.ports import QueuePort, ResumeStoragePort
from app.repositories.application_repository import ApplicationRepository
from app.repositories.job_repository import JobRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.apply_service import ApplyService
from app.services.job_search_service import JobSearchService
from app.services.profile_service import ProfileService
from app.services.resume.storage import LocalFilesystemStorage
from app.services.resume_service import ResumeService
from app.worker import queue_runner

DbDep = AsyncIterator[AsyncSession]

__all__ = ["get_db"]


# ---- Repositories ----


def get_profile_repository(db: AsyncSession = Depends(get_db)) -> ProfileRepository:
    return ProfileRepository(db)


def get_resume_repository(db: AsyncSession = Depends(get_db)) -> ResumeRepository:
    return ResumeRepository(db)


def get_job_repository(db: AsyncSession = Depends(get_db)) -> JobRepository:
    return JobRepository(db)


def get_application_repository(
    db: AsyncSession = Depends(get_db),
) -> ApplicationRepository:
    return ApplicationRepository(db)


# ---- Ports ----


def get_queue() -> QueuePort:
    return queue_runner.queue


def get_resume_storage() -> ResumeStoragePort:
    return LocalFilesystemStorage(get_settings().resume_storage_dir)


# ---- Services ----


def get_profile_service(
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileService:
    return ProfileService(repo)


def get_resume_service(
    resume_repo: ResumeRepository = Depends(get_resume_repository),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
    storage: ResumeStoragePort = Depends(get_resume_storage),
) -> ResumeService:
    return ResumeService(resume_repo, profile_repo, storage)


def get_job_search_service(
    repo: JobRepository = Depends(get_job_repository),
) -> JobSearchService:
    return JobSearchService(repo)


def get_apply_service(
    application_repo: ApplicationRepository = Depends(get_application_repository),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
    job_repo: JobRepository = Depends(get_job_repository),
    queue: QueuePort = Depends(get_queue),
) -> ApplyService:
    return ApplyService(application_repo, profile_repo, job_repo, queue)


# Note: LiveViewService and LogStreamService (app/services/live_view_service.py,
# log_stream_service.py) are intentionally NOT wired here. Both need a
# freshly-opened, narrowly-scoped DB session per use (a long-poll loop and a
# long-lived WebSocket connection, respectively) rather than the single
# connection-lifetime session FastAPI's Depends() would give a websocket
# route — see api/ws.py, which constructs them inline for that reason.

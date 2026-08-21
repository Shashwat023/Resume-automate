"""
This is the concrete payoff of the ports.QueuePort boundary: ApplyService
is tested here with a fake queue, never touching worker/queue_runner.py or
launching a real Chrome session — impossible before the restructure, since
the router used to import queue_runner's functions directly.
"""

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.domain import status as st
from app.models.db_models import Job, Profile
from app.repositories.application_repository import ApplicationRepository
from app.repositories.job_repository import JobRepository
from app.repositories.profile_repository import ProfileRepository
from app.services.apply_service import ApplyService


class FakeQueue:
    def __init__(self):
        self.enqueued: list[str] = []
        self.resumed: list[str] = []
        self.cancelled: list[str] = []

    async def enqueue_application(self, application_id: str) -> None:
        self.enqueued.append(application_id)

    async def signal_resume(self, application_id: str) -> None:
        self.resumed.append(application_id)

    async def signal_cancel(self, application_id: str) -> None:
        self.cancelled.append(application_id)

    def is_cancelled(self, application_id: str) -> bool:
        return False

    def cleanup(self, application_id: str) -> None:
        pass


async def _make_service(async_session):
    profile_repo = ProfileRepository(async_session)
    job_repo = JobRepository(async_session)
    application_repo = ApplicationRepository(async_session)
    queue = FakeQueue()

    profile = Profile(full_name="Jordan Smith", email="j@example.com", phone="123")
    job = Job(
        title="Account Executive", company_name="Anthropic", apply_url="https://x.com/1"
    )
    async_session.add_all([profile, job])
    await async_session.commit()
    await async_session.refresh(profile)
    await async_session.refresh(job)

    service = ApplyService(application_repo, profile_repo, job_repo, queue)
    return service, queue, profile, job


async def test_start_enqueues_and_creates_application(async_session):
    service, queue, profile, job = await _make_service(async_session)

    application = await service.start(profile.id, job.id)

    assert application.status == st.QUEUED
    assert queue.enqueued == [application.id]


async def test_start_raises_not_found_for_missing_profile(async_session):
    service, _queue, _profile, job = await _make_service(async_session)

    with pytest.raises(NotFoundError, match="Profile not found"):
        await service.start(999, job.id)


async def test_start_raises_not_found_for_missing_job(async_session):
    service, _queue, profile, _job = await _make_service(async_session)

    with pytest.raises(NotFoundError, match="Job not found"):
        await service.start(profile.id, 999)


async def test_pause_then_resume_signals_queue(async_session):
    service, queue, profile, job = await _make_service(async_session)
    application = await service.start(profile.id, job.id)

    # start() leaves status QUEUED, which is not TERMINAL, so pause is valid
    paused = await service.pause(application.id)
    assert paused.status == st.NEEDS_INPUT

    resumed = await service.resume(application.id)
    assert resumed.status == st.RUNNING
    assert queue.resumed == [application.id]


async def test_resume_without_pause_is_conflict(async_session):
    service, _queue, profile, job = await _make_service(async_session)
    application = await service.start(profile.id, job.id)

    with pytest.raises(ConflictError, match="not paused"):
        await service.resume(application.id)


async def test_cancel_signals_queue_and_sets_finished_at(async_session):
    service, queue, profile, job = await _make_service(async_session)
    application = await service.start(profile.id, job.id)

    cancelled = await service.cancel(application.id)

    assert cancelled.status == st.CANCELLED
    assert queue.cancelled == [application.id]


async def test_cancel_twice_is_conflict(async_session):
    service, _queue, profile, job = await _make_service(async_session)
    application = await service.start(profile.id, job.id)
    await service.cancel(application.id)

    with pytest.raises(ConflictError, match="already finished"):
        await service.cancel(application.id)

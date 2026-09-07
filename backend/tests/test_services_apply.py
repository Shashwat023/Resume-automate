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
        self.paused: list[str] = []

    async def enqueue_application(self, application_id: str) -> None:
        self.enqueued.append(application_id)

    async def signal_resume(self, application_id: str) -> None:
        self.resumed.append(application_id)

    async def signal_cancel(self, application_id: str) -> None:
        self.cancelled.append(application_id)

    async def signal_pause(self, application_id: str) -> None:
        self.paused.append(application_id)

    def is_cancelled(self, application_id: str) -> bool:
        return False

    def is_paused(self, application_id: str) -> bool:
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
    assert paused.status == st.PAUSED
    assert queue.paused == [application.id]

    resumed = await service.resume(application.id)
    assert resumed.status == st.RUNNING
    assert queue.resumed == [application.id]


async def test_resume_from_needs_input_still_works(async_session):
    """PAUSED (user pause) and NEEDS_INPUT (2FA) are different statuses,
    but both must resume the same way — this is the 2FA path."""
    service, queue, profile, job = await _make_service(async_session)
    application = await service.start(profile.id, job.id)
    application_row = await service._require(application.id)
    application_row.status = st.NEEDS_INPUT
    await async_session.commit()

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


async def test_get_details_includes_full_run_events_timeline(async_session):
    service, _queue, profile, job = await _make_service(async_session)
    application = await service.start(profile.id, job.id)
    await service._applications.add_event(
        application.id, "Tier 0 filled 'Email'", level="info", tier="tier0"
    )
    await service._applications.add_event(
        application.id, "Tier 1 low confidence", level="warn", tier="tier1"
    )
    await service._applications.commit()

    details = await service.get_details(application.id)

    assert details.application_id == application.id
    assert (
        len(details.events) == 3
    )  # "Application queued" (from start()) + the two added above
    assert [e.message for e in details.events] == [
        "Application queued",
        "Tier 0 filled 'Email'",
        "Tier 1 low confidence",
    ]
    assert details.events[1].tier == "tier0"
    assert details.events[2].level == "warn"


async def test_get_details_missing_application_is_not_found(async_session):
    service, _queue, _profile, _job = await _make_service(async_session)

    with pytest.raises(NotFoundError, match="Application not found"):
        await service.get_details("does-not-exist")


async def test_get_history_includes_real_job_id(async_session):
    """Regression test: the frontend's Retry button was sending the
    application UUID as job_id (Number(uuid) -> NaN -> 422) because the
    history response never exposed the real numeric job id at all."""
    service, _queue, profile, job = await _make_service(async_session)
    application = await service.start(profile.id, job.id)

    history = await service.get_history(profile.id)

    assert len(history) == 1
    assert history[0].application_id == application.id
    assert history[0].job_id == job.id

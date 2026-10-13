import pytest

from app.core.exceptions import ConflictError
from app.domain import status as st
from app.models.db_models import Application, Job, Profile
from app.repositories.application_repository import ApplicationRepository
from app.services import live_view_service
from app.services.live_view_service import LiveViewService


async def test_live_view_service_refuses_without_session_or_for_queued_and_terminal(
    async_session, monkeypatch
):
    profile = Profile(full_name="Jordan", email="j@example.com", phone="1")
    job = Job(title="Role", company_name="Acme", apply_url="https://example.com")
    async_session.add_all([profile, job])
    await async_session.commit()
    await async_session.refresh(profile)
    await async_session.refresh(job)
    application = Application(profile_id=profile.id, job_id=job.id, status=st.RUNNING)
    async_session.add(application)
    await async_session.commit()

    service = LiveViewService(ApplicationRepository(async_session))
    monkeypatch.setattr(live_view_service, "get_session", lambda _key: None)
    with pytest.raises(ConflictError):
        await service.connect(application.id)

    session = object()
    monkeypatch.setattr(live_view_service, "get_session", lambda _key: session)
    for status in (st.QUEUED, st.COMPLETED):
        application.status = status
        await async_session.commit()
        with pytest.raises(ConflictError):
            await service.connect(application.id)

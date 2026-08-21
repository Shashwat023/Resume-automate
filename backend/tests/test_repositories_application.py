from app.domain import status as st
from app.models.db_models import Job, Profile
from app.repositories.application_repository import ApplicationRepository


async def _seed_profile_and_job(db):
    profile = Profile(full_name="Jordan Smith", email="j@example.com", phone="123")
    job = Job(
        title="Account Executive", company_name="Anthropic", apply_url="https://x.com/1"
    )
    db.add_all([profile, job])
    await db.commit()
    await db.refresh(profile)
    await db.refresh(job)
    return profile, job


async def test_create_and_get(async_session):
    profile, job = await _seed_profile_and_job(async_session)
    repo = ApplicationRepository(async_session)

    application = await repo.create(profile.id, job.id, st.QUEUED)
    await repo.commit()

    fetched = await repo.get(application.id)
    assert fetched is not None
    assert fetched.status == st.QUEUED
    assert fetched.profile_id == profile.id


async def test_get_missing_returns_none(async_session):
    repo = ApplicationRepository(async_session)
    assert await repo.get("nonexistent-id") is None


async def test_add_event_and_history_with_job(async_session):
    profile, job = await _seed_profile_and_job(async_session)
    repo = ApplicationRepository(async_session)
    application = await repo.create(profile.id, job.id, st.QUEUED)
    await repo.add_event(application.id, "Application queued")
    await repo.commit()

    history = await repo.history_with_job(profile.id)

    assert len(history) == 1
    fetched_app, fetched_job = history[0]
    assert fetched_app.id == application.id
    assert fetched_job.company_name == "Anthropic"


async def test_events_after_only_returns_newer_events(async_session):
    profile, job = await _seed_profile_and_job(async_session)
    repo = ApplicationRepository(async_session)
    application = await repo.create(profile.id, job.id, st.QUEUED)
    await repo.add_event(application.id, "first")
    await repo.add_event(application.id, "second")
    await repo.commit()

    all_events = await repo.events_after(application.id, last_id=0)
    assert [e.message for e in all_events] == ["first", "second"]

    newer_only = await repo.events_after(application.id, last_id=all_events[0].id)
    assert [e.message for e in newer_only] == ["second"]

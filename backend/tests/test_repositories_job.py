from app.models.db_models import Job
from app.repositories.job_repository import JobRepository


async def _seed(db, **overrides):
    defaults = dict(
        title="Software Engineer",
        company_name="Anthropic",
        location="San Francisco, CA",
        apply_url=f"https://example.com/{overrides.get('title', 'job')}-{id(overrides)}",
        ats="greenhouse",
    )
    defaults.update(overrides)
    job = Job(**defaults)
    db.add(job)
    await db.commit()
    return job


async def test_search_with_no_filters_returns_all(async_session):
    await _seed(async_session, apply_url="https://x.com/1")
    await _seed(async_session, apply_url="https://x.com/2")
    repo = JobRepository(async_session)

    jobs, total = await repo.search(
        keyword=None,
        company_name=None,
        location=None,
        location_type=None,
        ats=None,
        industry=None,
        posted_within_hours=None,
        page=1,
        limit=20,
        sort=None,
    )

    assert total == 2
    assert len(jobs) == 2


async def test_search_filters_by_keyword_in_title(async_session):
    await _seed(
        async_session,
        title="Account Executive, Public Sector",
        apply_url="https://x.com/1",
    )
    await _seed(async_session, title="Backend Engineer", apply_url="https://x.com/2")
    repo = JobRepository(async_session)

    jobs, total = await repo.search(
        keyword="Public Sector",
        company_name=None,
        location=None,
        location_type=None,
        ats=None,
        industry=None,
        posted_within_hours=None,
        page=1,
        limit=20,
        sort=None,
    )

    assert total == 1
    assert jobs[0].title == "Account Executive, Public Sector"


async def test_search_filters_by_ats(async_session):
    await _seed(async_session, ats="greenhouse", apply_url="https://x.com/1")
    await _seed(async_session, ats="lever", apply_url="https://x.com/2")
    repo = JobRepository(async_session)

    jobs, total = await repo.search(
        keyword=None,
        company_name=None,
        location=None,
        location_type=None,
        ats="lever",
        industry=None,
        posted_within_hours=None,
        page=1,
        limit=20,
        sort=None,
    )

    assert total == 1
    assert jobs[0].ats == "lever"


async def test_search_pagination(async_session):
    for i in range(5):
        await _seed(async_session, apply_url=f"https://x.com/{i}")
    repo = JobRepository(async_session)

    jobs, total = await repo.search(
        keyword=None,
        company_name=None,
        location=None,
        location_type=None,
        ats=None,
        industry=None,
        posted_within_hours=None,
        page=1,
        limit=2,
        sort=None,
    )

    assert total == 5  # total reflects the whole matching set, not just this page
    assert len(jobs) == 2


async def test_get_by_id(async_session):
    job = await _seed(async_session, apply_url="https://x.com/1")
    repo = JobRepository(async_session)

    fetched = await repo.get(job.id)

    assert fetched is not None
    assert fetched.id == job.id


async def test_get_missing_returns_none(async_session):
    repo = JobRepository(async_session)
    assert await repo.get(999) is None

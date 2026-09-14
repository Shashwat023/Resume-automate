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


async def test_search_pagination_is_stable_when_created_at_ties(async_session):
    """
    FLAGGED.md #34.8: created_at is second-granularity, so a bulk scrape
    inserting many jobs in one second gives them identical timestamps.
    Ordering on created_at alone leaves those rows in an arbitrary order,
    and LIMIT/OFFSET pagination over an arbitrary order can skip or repeat
    rows between pages. Job.id breaks the tie deterministically.
    """
    from datetime import datetime

    same_moment = datetime(2024, 1, 1, 12, 0, 0)
    for n in range(6):
        async_session.add(
            Job(
                title=f"Job {n}",
                company_name="Acme",
                apply_url=f"https://example.com/{n}",
                created_at=same_moment,
            )
        )
    await async_session.commit()

    repo = JobRepository(async_session)
    kwargs = dict(
        keyword=None,
        company_name=None,
        location=None,
        location_type=None,
        ats=None,
        industry=None,
        posted_within_hours=None,
        limit=2,
        sort=None,
    )

    seen: list[int] = []
    for page in (1, 2, 3):
        jobs, _ = await repo.search(page=page, **kwargs)
        seen.extend(j.id for j in jobs)

    # Every row appears exactly once across the three pages.
    assert sorted(seen) == sorted(set(seen))
    assert len(seen) == 6


async def test_search_sort_oldest_is_the_exact_reverse_of_default(async_session):
    from datetime import datetime

    same_moment = datetime(2024, 1, 1, 12, 0, 0)
    for n in range(4):
        async_session.add(
            Job(
                title=f"Job {n}",
                company_name="Acme",
                apply_url=f"https://example.com/{n}",
                created_at=same_moment,
            )
        )
    await async_session.commit()

    repo = JobRepository(async_session)
    kwargs = dict(
        keyword=None,
        company_name=None,
        location=None,
        location_type=None,
        ats=None,
        industry=None,
        posted_within_hours=None,
        page=1,
        limit=10,
    )

    newest, _ = await repo.search(sort=None, **kwargs)
    oldest, _ = await repo.search(sort="oldest", **kwargs)

    assert [j.id for j in oldest] == list(reversed([j.id for j in newest]))

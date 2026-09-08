from app.repositories.tracked_company_repository import TrackedCompanyRepository


async def test_upsert_inserts_new_row(async_session):
    repo = TrackedCompanyRepository(async_session)

    row, was_inserted = await repo.upsert("Acme Corp", "https://acme.com/careers")

    assert was_inserted is True
    assert row.name == "Acme Corp"
    assert row.enabled is True


async def test_upsert_is_idempotent_on_careers_url(async_session):
    repo = TrackedCompanyRepository(async_session)

    await repo.upsert("Acme Corp", "https://acme.com/careers")
    row2, was_inserted2 = await repo.upsert("Acme Corp", "https://acme.com/careers")

    assert was_inserted2 is False
    assert await repo.count() == 1
    assert row2.name == "Acme Corp"


async def test_upsert_updates_name_on_repeat(async_session):
    repo = TrackedCompanyRepository(async_session)

    await repo.upsert("Old Name", "https://acme.com/careers")
    row, _ = await repo.upsert("New Name", "https://acme.com/careers")

    assert row.name == "New Name"
    assert await repo.count() == 1


async def test_get_by_careers_url_missing_returns_none(async_session):
    repo = TrackedCompanyRepository(async_session)
    assert await repo.get_by_careers_url("https://nope.com") is None

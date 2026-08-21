from app.repositories.profile_repository import ProfileRepository


async def test_create_and_get(async_session):
    repo = ProfileRepository(async_session)
    profile = await repo.create(
        {"full_name": "Jordan Smith", "email": "j@example.com", "phone": "123"}
    )

    assert profile.id is not None
    fetched = await repo.get(profile.id)
    assert fetched is not None
    assert fetched.full_name == "Jordan Smith"


async def test_get_missing_returns_none(async_session):
    repo = ProfileRepository(async_session)
    assert await repo.get(999) is None


async def test_update_applies_partial_fields_only(async_session):
    repo = ProfileRepository(async_session)
    profile = await repo.create(
        {"full_name": "Jordan Smith", "email": "j@example.com", "phone": "123"}
    )

    updated = await repo.update(profile, {"city": "San Francisco"})

    assert updated.city == "San Francisco"
    assert updated.full_name == "Jordan Smith"  # untouched fields survive


async def test_delete_removes_profile(async_session):
    repo = ProfileRepository(async_session)
    profile = await repo.create(
        {"full_name": "Jordan Smith", "email": "j@example.com", "phone": "123"}
    )

    await repo.delete(profile)

    assert await repo.get(profile.id) is None

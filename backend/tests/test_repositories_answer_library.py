from app.models.db_models import Profile
from app.repositories.answer_library_repository import AnswerLibraryRepository


async def _seed_profile(db):
    profile = Profile(full_name="Jordan Smith", email="j@example.com", phone="123")
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def test_upsert_then_get(async_session):
    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)

    await repo.upsert(
        profile.id,
        "hash1",
        "Why Anthropic?",
        "Because AI safety matters.",
        source="llm",
        confidence=0.9,
    )

    fetched = await repo.get(profile.id, "hash1")
    assert fetched is not None
    assert fetched.answer == "Because AI safety matters."
    assert fetched.source == "llm"
    assert fetched.confidence == 0.9


async def test_get_missing_returns_none(async_session):
    repo = AnswerLibraryRepository(async_session)
    assert await repo.get(999, "nohash") is None


async def test_llm_upsert_overwrites_previous_llm_answer(async_session):
    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)

    await repo.upsert(
        profile.id,
        "hash1",
        "Why Anthropic?",
        "First guess.",
        source="llm",
        confidence=0.8,
    )
    await repo.upsert(
        profile.id,
        "hash1",
        "Why Anthropic?",
        "Second guess.",
        source="llm",
        confidence=0.85,
    )

    fetched = await repo.get(profile.id, "hash1")
    assert fetched.answer == "Second guess."


async def test_human_answer_overwrites_llm_answer(async_session):
    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)

    await repo.upsert(
        profile.id,
        "hash1",
        "Why Anthropic?",
        "LLM guess.",
        source="llm",
        confidence=0.8,
    )
    await repo.upsert(
        profile.id,
        "hash1",
        "Why Anthropic?",
        "Human's real answer.",
        source="human",
        confidence=None,
    )

    fetched = await repo.get(profile.id, "hash1")
    assert fetched.answer == "Human's real answer."
    assert fetched.source == "human"


async def test_llm_answer_does_not_overwrite_existing_human_answer(async_session):
    # This is the important safety property: once a human has answered a
    # question, a future Tier-1 run for a DIFFERENT job must not silently
    # replace it with a machine guess.
    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)

    await repo.upsert(
        profile.id,
        "hash1",
        "Why Anthropic?",
        "Human's real answer.",
        source="human",
        confidence=None,
    )
    await repo.upsert(
        profile.id,
        "hash1",
        "Why Anthropic?",
        "LLM guess.",
        source="llm",
        confidence=0.95,
    )

    fetched = await repo.get(profile.id, "hash1")
    assert fetched.answer == "Human's real answer."
    assert fetched.source == "human"


async def test_answers_are_scoped_per_profile(async_session):
    p1 = await _seed_profile(async_session)
    p2 = Profile(full_name="Alex Doe", email="a@example.com", phone="456")
    async_session.add(p2)
    await async_session.commit()
    await async_session.refresh(p2)

    repo = AnswerLibraryRepository(async_session)
    await repo.upsert(
        p1.id, "hash1", "Why Anthropic?", "P1's answer.", source="llm", confidence=0.9
    )

    assert await repo.get(p2.id, "hash1") is None
    assert (await repo.get(p1.id, "hash1")).answer == "P1's answer."

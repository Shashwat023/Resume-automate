import json

from app.models.db_models import Profile
from app.repositories.profile_repository import ProfileRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.engine import resume_parse
from app.services.engine.resume_parse import ResumeFacts
from app.services.resume_service import ResumeService


class FakeStorage:
    """Minimal ResumeStoragePort double — file I/O isn't what these tests exercise."""

    async def save(self, profile_id, filename, contents):
        from app.ports import SavedFile

        return SavedFile(file_path=f"/tmp/{filename}", resume_url=f"/storage/{filename}")

    async def delete(self, file_path):
        pass


async def _seed_profile(db) -> Profile:
    profile = Profile(full_name="Jane Doe", email="jane@example.com", phone="555-1234")
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def _service(db) -> ResumeService:
    return ResumeService(ResumeRepository(db), ProfileRepository(db), FakeStorage())


async def test_upload_extracts_and_stores_text(async_session):
    profile = await _seed_profile(async_session)
    service = _service(async_session)

    await service.upload(profile.id, "resume.txt", b"Jane Doe, Software Engineer")

    resume = await ResumeRepository(async_session).get(profile.id)
    assert resume.extracted_text == "Jane Doe, Software Engineer"


async def test_reupload_invalidates_stale_parsed_facts(async_session):
    profile = await _seed_profile(async_session)
    service = _service(async_session)
    repo = ResumeRepository(async_session)

    await service.upload(profile.id, "resume.txt", b"first version")
    await repo.set_parsed_facts(profile.id, ResumeFacts(skills=["Python"]).model_dump_json())

    await service.upload(profile.id, "resume.txt", b"second, different version")

    resume = await repo.get(profile.id)
    assert resume.extracted_text == "second, different version"
    assert resume.parsed_facts is None


async def test_get_facts_returns_empty_when_no_resume(async_session):
    profile = await _seed_profile(async_session)
    service = _service(async_session)

    facts = await service.get_facts(profile.id)

    assert facts == ResumeFacts()


async def test_get_facts_parses_once_and_caches(async_session, monkeypatch):
    profile = await _seed_profile(async_session)
    service = _service(async_session)
    await service.upload(profile.id, "resume.txt", b"Jane Doe, 10 years at Acme")

    call_count = 0

    async def _fake_parse(text):
        nonlocal call_count
        call_count += 1
        return ResumeFacts(skills=["Python"])

    monkeypatch.setattr(resume_parse, "parse_resume_facts", _fake_parse)
    # ResumeService imports the function by name, so patch it there too.
    import app.services.resume_service as resume_service_module

    monkeypatch.setattr(resume_service_module, "parse_resume_facts", _fake_parse)

    first = await service.get_facts(profile.id)
    second = await service.get_facts(profile.id)

    assert first.skills == ["Python"]
    assert second.skills == ["Python"]
    assert call_count == 1  # second call served from the cached parsed_facts column

    resume = await ResumeRepository(async_session).get(profile.id)
    assert json.loads(resume.parsed_facts)["skills"] == ["Python"]


async def test_get_facts_degrades_gracefully_on_openrouter_error(async_session, monkeypatch):
    from app.services.engine.openrouter_client import OpenRouterError

    profile = await _seed_profile(async_session)
    service = _service(async_session)
    await service.upload(profile.id, "resume.txt", b"some resume text")

    async def _boom(text):
        raise OpenRouterError("no key configured")

    import app.services.resume_service as resume_service_module

    monkeypatch.setattr(resume_service_module, "parse_resume_facts", _boom)

    facts = await service.get_facts(profile.id)

    assert facts == ResumeFacts()

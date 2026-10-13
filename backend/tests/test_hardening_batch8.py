import httpx
import pytest

from app.services.engine import openrouter_client
from app.services.engine.openrouter_client import OpenRouterError, chat_json
from app.services.resume.storage import LocalFilesystemStorage, safe_filename


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": "provider down", "code": 502}},
        {"choices": []},
        {"choices": [{"message": None}]},
    ],
)
async def test_chat_json_turns_malformed_200_into_openrouter_error(monkeypatch, body):
    def handler(_request):
        return httpx.Response(200, json=body)

    real = httpx.AsyncClient

    class _Client(real):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=httpx.MockTransport(handler), **k)

    monkeypatch.setattr(openrouter_client.httpx, "AsyncClient", _Client)

    with pytest.raises(OpenRouterError):
        await chat_json(
            [{"role": "user", "content": "x"}],
            json_schema={"type": "object"},
            schema_name="t",
            model="m",
        )


async def test_chat_json_non_json_body_is_openrouter_error(monkeypatch):
    real = httpx.AsyncClient

    class _Client(real):
        def __init__(self, *a, **k):
            super().__init__(
                *a,
                transport=httpx.MockTransport(
                    lambda _r: httpx.Response(200, content=b"<html>oops</html>")
                ),
                **k,
            )

    monkeypatch.setattr(openrouter_client.httpx, "AsyncClient", _Client)

    with pytest.raises(OpenRouterError):
        await chat_json(
            [{"role": "user", "content": "x"}],
            json_schema={"type": "object"},
            schema_name="t",
            model="m",
        )


async def test_resume_facts_validation_error_degrades_to_empty_facts(
    async_session, monkeypatch
):
    from app.models.db_models import Profile, Resume
    from app.repositories.profile_repository import ProfileRepository
    from app.repositories.resume_repository import ResumeRepository
    from app.services import resume_service
    from app.services.engine.resume_parse import ResumeFacts

    profile = Profile(full_name="A B", email="a@b.c", phone="1")
    async_session.add(profile)
    await async_session.commit()
    async_session.add(
        Resume(
            profile_id=profile.id,
            file_path="x",
            resume_url="y",
            extracted_text="some text",
        )
    )
    await async_session.commit()

    async def bad_parse(_text):
        ResumeFacts.model_validate({"employment": "not-a-list"})

    monkeypatch.setattr(resume_service, "parse_resume_facts", bad_parse)
    service = resume_service.ResumeService(
        ResumeRepository(async_session), ProfileRepository(async_session), None
    )

    facts = await service.get_facts(profile.id)

    assert facts == ResumeFacts()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("../../etc/passwd", "passwd"),
        (r"C:\Users\me\resume.pdf", "resume.pdf"),
        ("my resume (final)?.pdf", "my resume _final__.pdf"),
        ("...", "resume"),
        ("", "resume"),
    ],
)
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected


async def test_upload_cannot_escape_the_profile_directory(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "resumes")

    saved = await storage.save(7, "../../evil.pdf", b"x")

    assert (tmp_path / "evil.pdf").exists() is False
    assert saved.file_path.startswith(str(tmp_path / "resumes" / "7"))
    assert saved.resume_url == "/storage/resumes/7/evil.pdf"

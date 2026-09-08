from app.services.engine import resume_parse
from app.services.engine.resume_parse import ResumeFacts


def _fake_chat_json(response: dict):
    async def _fake(messages, *, json_schema, schema_name, model, temperature=0.0):
        return response, {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

    return _fake


async def test_parse_resume_facts_returns_validated_shape(monkeypatch):
    monkeypatch.setattr(
        resume_parse,
        "chat_json",
        _fake_chat_json(
            {
                "employment": [
                    {
                        "employer": "Acme Corp",
                        "title": "Software Engineer",
                        "start_date": "2020",
                        "end_date": "2023",
                        "description": "Built things",
                    }
                ],
                "education": [
                    {
                        "institution": "State University",
                        "degree": "BS",
                        "field_of_study": "Computer Science",
                        "graduation_year": "2020",
                    }
                ],
                "skills": ["Python", "SQL"],
                "certifications": [],
            }
        ),
    )

    facts = await resume_parse.parse_resume_facts("Jane Doe, Software Engineer...")

    assert isinstance(facts, ResumeFacts)
    assert facts.employment[0].employer == "Acme Corp"
    assert facts.education[0].institution == "State University"
    assert facts.skills == ["Python", "SQL"]
    assert facts.certifications == []


async def test_parse_resume_facts_propagates_openrouter_error(monkeypatch):
    from app.services.engine.openrouter_client import OpenRouterError

    async def _boom(*args, **kwargs):
        raise OpenRouterError("no key configured")

    monkeypatch.setattr(resume_parse, "chat_json", _boom)

    try:
        await resume_parse.parse_resume_facts("some text")
        assert False, "expected OpenRouterError"
    except OpenRouterError:
        pass

import pytest

from app.repositories.answer_library_repository import AnswerLibraryRepository
from app.services.engine import tier1_map
from app.services.engine.openrouter_client import OpenRouterError
from app.services.engine.tier0_harvest import FormField
from app.models.db_models import Profile


class FakeLocator:
    def __init__(self, calls, xpath):
        self._calls = calls
        self._xpath = xpath

    async def fill(self, value):
        self._calls.append(("fill", self._xpath, value))

    async def select_option(self, value):
        self._calls.append(("select_option", self._xpath, value))


class FakePage:
    def __init__(self):
        self.calls: list[tuple] = []

    def locator(self, xpath):
        return FakeLocator(self.calls, xpath)


async def _seed_profile(db):
    profile = Profile(full_name="Jordan Smith", email="j@example.com", phone="123")
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def _fake_chat_json(response: dict, usage: dict | None = None):
    async def _fake(messages, *, json_schema, schema_name, model, temperature=0.0):
        return response, usage or {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        }

    return _fake


async def test_answers_library_hit_skips_llm_call(async_session, monkeypatch):
    async def _boom(*args, **kwargs):
        raise AssertionError("chat_json must not be called on a library hit")

    monkeypatch.setattr(tier1_map, "chat_json", _boom)

    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)
    await repo.upsert(
        profile.id,
        tier1_map.question_hash("Why Anthropic?"),
        "Why Anthropic?",
        "Because AI safety matters.",
        source="llm",
        confidence=0.9,
    )

    field = FormField(
        node_id="1", role="textbox", label="Why Anthropic?", xpath="//textarea[1]"
    )
    page = FakePage()

    result = await tier1_map.map_fields(
        page, [field], {"full_name": "Jordan Smith"}, profile.id, repo
    )

    assert result.from_library == [("Why Anthropic?", "Because AI safety matters.")]
    assert page.calls == [("fill", "//textarea[1]", "Because AI safety matters.")]
    assert result.filled == [("Why Anthropic?", "Because AI safety matters.")]


async def test_llm_decides_textbox_value_and_caches_it(async_session, monkeypatch):
    monkeypatch.setattr(
        tier1_map,
        "chat_json",
        _fake_chat_json(
            {
                "answers": [
                    {
                        "field_id": "1",
                        "value": "Because AI safety matters.",
                        "confidence": 0.9,
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(tier1_map.settings, "openrouter_api_key", "fake-key-for-test")

    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)
    field = FormField(
        node_id="1", role="textbox", label="Why Anthropic?", xpath="//textarea[1]"
    )
    page = FakePage()

    result = await tier1_map.map_fields(
        page, [field], {"full_name": "Jordan Smith"}, profile.id, repo
    )

    assert result.filled == [("Why Anthropic?", "Because AI safety matters.")]
    assert page.calls == [("fill", "//textarea[1]", "Because AI safety matters.")]

    cached = await repo.get(profile.id, tier1_map.question_hash("Why Anthropic?"))
    assert cached is not None
    assert cached.answer == "Because AI safety matters."
    assert cached.source == "llm"


async def test_native_select_uses_select_option_not_fill(async_session, monkeypatch):
    monkeypatch.setattr(
        tier1_map,
        "chat_json",
        _fake_chat_json(
            {"answers": [{"field_id": "1", "value": "California", "confidence": 0.95}]}
        ),
    )
    monkeypatch.setattr(tier1_map.settings, "openrouter_api_key", "fake-key-for-test")

    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)
    field = FormField(
        node_id="1",
        role="combobox",
        label="State",
        xpath="//select[1]",
        options=["California", "New York"],
    )
    page = FakePage()

    result = await tier1_map.map_fields(page, [field], {}, profile.id, repo)

    assert page.calls == [("select_option", "//select[1]", "California")]
    assert result.filled == [("State", "California")]

    # Fields WITH a fixed option set are not the "novel question" case —
    # not cached in the answers library.
    assert await repo.get(profile.id, tier1_map.question_hash("State")) is None


async def test_custom_combobox_with_no_options_goes_to_tier2(
    async_session, monkeypatch
):
    monkeypatch.setattr(
        tier1_map,
        "chat_json",
        _fake_chat_json(
            {"answers": [{"field_id": "1", "value": "No", "confidence": 0.9}]}
        ),
    )
    monkeypatch.setattr(tier1_map.settings, "openrouter_api_key", "fake-key-for-test")

    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)
    field = FormField(
        node_id="1",
        role="combobox",
        label="Do you require visa sponsorship?",
        xpath="//div[1]",
        options=[],
    )
    page = FakePage()

    result = await tier1_map.map_fields(page, [field], {}, profile.id, repo)

    assert page.calls == []  # Tier 1 never touches the DOM for this field
    assert result.filled == []
    assert result.for_tier2 == [(field, "No")]

    # No fixed options -> IS the novel-question case -> cached, so a
    # repeat application skips the LLM call for the decision (Tier 2 still
    # has to execute the click every time; only the VALUE is cached).
    cached = await repo.get(
        profile.id, tier1_map.question_hash("Do you require visa sponsorship?")
    )
    assert cached is not None
    assert cached.answer == "No"


async def test_low_confidence_answer_is_filled_but_not_cached(async_session, monkeypatch):
    """
    Day 4 scope correction: Tier 1 never abstains. A low-confidence answer
    is still written to the field (accepted tradeoff, see PLAN.md) — the
    confidence threshold now only gates whether the answer is cached into
    the answers library, so a bad guess isn't replayed into future
    applications asking the same question.
    """
    monkeypatch.setattr(
        tier1_map,
        "chat_json",
        _fake_chat_json(
            {"answers": [{"field_id": "1", "value": "Guess", "confidence": 0.2}]}
        ),
    )
    monkeypatch.setattr(tier1_map.settings, "openrouter_api_key", "fake-key-for-test")

    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)
    field = FormField(
        node_id="1", role="textbox", label="Obscure question", xpath="//textarea[1]"
    )
    page = FakePage()

    result = await tier1_map.map_fields(page, [field], {}, profile.id, repo)

    assert result.low_confidence_filled == ["Obscure question"]
    assert result.filled == [("Obscure question", "Guess")]
    assert page.calls == [("fill", "//textarea[1]", "Guess")]
    assert (
        await repo.get(profile.id, tier1_map.question_hash("Obscure question")) is None
    )


async def test_no_api_key_leaves_everything_unfilled(async_session, monkeypatch):
    """
    The kill switch (no OpenRouter key) is the ONE remaining case where a
    field genuinely gets no answer — there's no LLM call to produce one at
    all, unlike a low-confidence answer which is still filled.
    """
    async def _boom(*args, **kwargs):
        raise AssertionError("chat_json must not be called when no key is configured")

    monkeypatch.setattr(tier1_map, "chat_json", _boom)
    monkeypatch.setattr(tier1_map.settings, "openrouter_api_key", None)

    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)
    field = FormField(
        node_id="1", role="textbox", label="Why Anthropic?", xpath="//textarea[1]"
    )
    page = FakePage()

    result = await tier1_map.map_fields(page, [field], {}, profile.id, repo)

    assert result.low_confidence_filled == ["Why Anthropic?"]
    assert page.calls == []


async def test_build_prompt_handles_non_json_native_profile_values():
    # Regression: runner.py builds the profile dict straight from ORM
    # column values (getattr(profile, c.name) for every column), which
    # includes real datetime objects (created_at/updated_at) — this broke
    # a live run with "Object of type datetime is not JSON serializable"
    # the first time Tier 1 actually ran end-to-end against a real form.
    import datetime

    profile = {
        "full_name": "Jordan Smith",
        "created_at": datetime.datetime(2026, 1, 1, 12, 0, 0),
        "updated_at": datetime.datetime(2026, 1, 2, 8, 30, 0),
    }
    field = FormField(
        node_id="1", role="textbox", label="Why Anthropic?", xpath="//textarea[1]"
    )

    messages = tier1_map.build_prompt(profile, [field])  # must not raise

    assert "2026-01-01 12:00:00" in messages[1]["content"]


async def test_malformed_json_retries_once_then_raises(async_session, monkeypatch):
    calls = {"n": 0}

    async def _flaky(messages, *, json_schema, schema_name, model, temperature=0.0):
        calls["n"] += 1
        raise OpenRouterError("boom")

    monkeypatch.setattr(tier1_map, "chat_json", _flaky)
    monkeypatch.setattr(tier1_map.settings, "openrouter_api_key", "fake-key-for-test")

    profile = await _seed_profile(async_session)
    repo = AnswerLibraryRepository(async_session)
    field = FormField(
        node_id="1", role="textbox", label="Why Anthropic?", xpath="//textarea[1]"
    )
    page = FakePage()

    with pytest.raises(OpenRouterError):
        await tier1_map.map_fields(page, [field], {}, profile.id, repo)

    assert calls["n"] == 2  # original attempt + one repair retry

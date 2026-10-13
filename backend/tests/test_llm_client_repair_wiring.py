from types import SimpleNamespace

from app.services.engine import llm_client


class _Params:
    system_prompt = None
    messages: list = []
    temperature = None
    stop_sequences = None
    response_format = SimpleNamespace(
        name="t",
        schema_=SimpleNamespace(
            model_dump=lambda **_k: {
                "type": "object",
                "properties": {"url": {"type": "string"}},
            }
        ),
    )


def _patch(monkeypatch, replies):
    queue = list(replies)
    calls: list[dict] = []

    async def fake_call(body):
        calls.append(body)
        return {
            "choices": [
                {"message": {"content": queue.pop(0)}, "finish_reason": "stop"}
            ],
            "usage": {},
        }

    monkeypatch.setattr(llm_client, "_call_openrouter", fake_call)
    monkeypatch.setattr(llm_client, "LLMStructuredGenerateParams", _Params)
    monkeypatch.setattr(
        llm_client,
        "FieldSchema8",
        SimpleNamespace(model_validate=lambda value: value),
    )
    monkeypatch.setattr(
        llm_client,
        "LLMStructuredGenerateResult",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    return calls


async def test_prose_reply_gets_one_reformat_request(monkeypatch):
    calls = _patch(monkeypatch, ["Sure! here you go", '{"url": "https://x.y"}'])

    result = await llm_client.openrouter_llm(_Params())

    assert result.structured_content == {"url": "https://x.y"}
    assert len(calls) == 2  # original + repair


async def test_null_for_a_string_field_is_coerced_to_empty_string(monkeypatch):
    _patch(monkeypatch, ['{"url": null}'])

    result = await llm_client.openrouter_llm(_Params())

    assert result.structured_content == {"url": ""}


async def test_unrepairable_reply_degrades_to_none_after_one_retry(monkeypatch):
    calls = _patch(monkeypatch, ["nope", "still nope"])

    result = await llm_client.openrouter_llm(_Params())

    assert result.structured_content is None
    assert len(calls) == 2

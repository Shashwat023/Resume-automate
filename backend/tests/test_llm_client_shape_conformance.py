"""
The RPC layer that dispatches our callback's return value does:
    result_model.model_validate(result, strict=True)
    .model_dump_json(by_alias=True, exclude_unset=True)
    result_model.model_validate_json(...)
(see rpc_client.py:_handle_request, mapped in PLAN.md Part C). If our
callback returns something that fails that round-trip, Tier 2 breaks on
every single call — silently until it's live. Replaying that exact
round-trip here is the cheapest way to catch a contract mistake before it
costs a real browser session and real LLM spend.
"""

import pytest
from stagehand._generated.models import (
    FieldSchema6,
    LLMJsonSchemaResponseFormat,
    LLMMessage,
    LLMMessageContentBlock,
    LLMMessageGenerateParams,
    LLMMessageGenerateResult,
    LLMRole,
    LLMStructuredGenerateParams,
    LLMStructuredGenerateResult,
    LLMTextContent,
    LLMImageContent,
)

from app.services.engine import llm_client


def _roundtrip(result_model, instance):
    """Exactly what rpc_client.py's _handle_request does to our return value."""
    validated = result_model.model_validate(instance, strict=True)
    encoded = validated.model_dump_json(
        by_alias=True, exclude_unset=True, warnings="none"
    )
    reparsed = result_model.model_validate_json(encoded, strict=True)
    return reparsed


def _fake_openai_response(content: str, finish_reason: str = "stop") -> dict:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    }


async def test_message_params_produce_a_result_that_survives_the_strict_roundtrip(
    monkeypatch,
):
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", "fake-key")

    async def fake_call(body):
        assert body["model"] == llm_client.settings.openrouter_model_tier2
        assert (
            "response_format" not in body
        )  # text variant must not send response_format
        return _fake_openai_response("The submit button is at the bottom of the form.")

    monkeypatch.setattr(llm_client, "_call_openrouter", fake_call)

    params = LLMMessageGenerateParams(
        messages=[
            LLMMessage(
                role=LLMRole.user,
                content=LLMMessageContentBlock(
                    root=LLMTextContent(type="text", text="Where is the submit button?")
                ),
            )
        ],
    )

    result = await llm_client.openrouter_llm(params)

    assert isinstance(result, LLMMessageGenerateResult)
    roundtripped = _roundtrip(LLMMessageGenerateResult, result)
    assert roundtripped.output_format == "text"
    assert roundtripped.role == LLMRole.assistant


async def test_structured_params_produce_a_result_that_survives_the_strict_roundtrip(
    monkeypatch,
):
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", "fake-key")

    async def fake_call(body):
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["name"] == "widget_choice"
        return _fake_openai_response('{"selector": "[data-testid=hybrid-option]"}')

    monkeypatch.setattr(llm_client, "_call_openrouter", fake_call)

    schema = FieldSchema6.model_validate(
        {
            "type": "object",
            "properties": {"selector": {"type": "string"}},
            "required": ["selector"],
        }
    )
    params = LLMStructuredGenerateParams(
        messages=[
            LLMMessage(
                role=LLMRole.user,
                content=LLMMessageContentBlock(
                    root=LLMTextContent(type="text", text="Find the Hybrid option")
                ),
            )
        ],
        response_format=LLMJsonSchemaResponseFormat(
            type="json_schema", name="widget_choice", schema_=schema
        ),
    )

    result = await llm_client.openrouter_llm(params)

    assert isinstance(result, LLMStructuredGenerateResult)
    roundtripped = _roundtrip(LLMStructuredGenerateResult, result)
    assert roundtripped.output_format == "json_schema"
    # structured_content is a required KEY even though its value can be
    # None — confirm we always populate it, not just sometimes.
    assert "structured_content" in result.model_fields_set
    assert roundtripped.structured_content is not None


async def test_structured_result_populates_both_content_and_structured_content(
    monkeypatch,
):
    # PLAN.md: "populate BOTH content (JSON as text) and structured_content
    # (parsed object) — the only shape satisfying every consumer."
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", "fake-key")

    async def fake_call(body):
        return _fake_openai_response('{"selector": "#foo"}')

    monkeypatch.setattr(llm_client, "_call_openrouter", fake_call)

    schema = FieldSchema6.model_validate(
        {"type": "object", "properties": {"selector": {"type": "string"}}}
    )
    params = LLMStructuredGenerateParams(
        messages=[
            LLMMessage(
                role=LLMRole.user,
                content=LLMMessageContentBlock(
                    root=LLMTextContent(type="text", text="x")
                ),
            )
        ],
        response_format=LLMJsonSchemaResponseFormat(
            type="json_schema", name="s", schema_=schema
        ),
    )

    result = await llm_client.openrouter_llm(params)

    blocks = result.content if isinstance(result.content, list) else [result.content]
    assert any(
        isinstance(b.root, LLMTextContent) and "#foo" in b.root.text for b in blocks
    )
    assert result.structured_content is not None


async def test_system_prompt_is_prepended_as_openai_system_message(monkeypatch):
    # LLMRole has no "system" value — system_prompt arrives separately and
    # must become its own message, not get dropped.
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", "fake-key")
    captured = {}

    async def fake_call(body):
        captured["messages"] = body["messages"]
        return _fake_openai_response("ok")

    monkeypatch.setattr(llm_client, "_call_openrouter", fake_call)

    params = LLMMessageGenerateParams(
        system_prompt="You are a helpful form-filling assistant.",
        messages=[
            LLMMessage(
                role=LLMRole.user,
                content=LLMMessageContentBlock(
                    root=LLMTextContent(type="text", text="hi")
                ),
            )
        ],
    )

    await llm_client.openrouter_llm(params)

    assert captured["messages"][0] == {
        "role": "system",
        "content": "You are a helpful form-filling assistant.",
    }


async def test_image_content_block_becomes_data_uri():
    block = LLMMessageContentBlock(
        root=LLMImageContent(type="image", data="aGVsbG8=", mime_type="image/png")
    )
    parts = llm_client._blocks_to_openai_content(block)
    assert parts == [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}}
    ]


async def test_content_as_single_block_not_list_is_normalized():
    # LLMMessage.content can be a single block OR a list — must not crash
    # on the single-block case.
    single = LLMMessageContentBlock(root=LLMTextContent(type="text", text="hello"))
    parts = llm_client._blocks_to_openai_content(single)
    assert parts == [{"type": "text", "text": "hello"}]


async def test_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", None)

    params = LLMMessageGenerateParams(
        messages=[
            LLMMessage(
                role=LLMRole.user,
                content=LLMMessageContentBlock(
                    root=LLMTextContent(type="text", text="hi")
                ),
            )
        ],
    )

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        await llm_client.openrouter_llm(params)


async def test_unreachable_llm_always_raises():
    with pytest.raises(RuntimeError, match="Tier 0-only run"):
        await llm_client.unreachable_llm(object())

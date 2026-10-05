"""
The custom LLM callback Stagehand.create(model=...) accepts. This is the
bridge Tier 2 uses when Stagehand itself needs an LLM (observe/act resolving
a custom widget) — Tier 1's own OpenRouter calls (tier1_map.py) never go
through this path at all; they're a separate, simpler direct HTTP call.

Contract mapped from the installed stagehand v4.0.1 package source (not
guessed — see PLAN.md Part C for the full writeup). The load-bearing facts:

- The callback receives the UNWRAPPED union member (never a RootModel
  wrapper): branch with isinstance(params, LLMStructuredGenerateParams).
- LLMMessage.content is NEVER a plain str — always an LLMMessageContentBlock
  (a RootModel — read .root) or a list of them.
- LLMRole has only user/assistant, no "system" — system_prompt arrives
  separately and must be prepended as an OpenAI-style system message.
- The JSON schema lives at params.response_format.schema_ (note the
  trailing underscore — aliased from "schema").
- Results must be REAL model instances, not dicts — the RPC layer does a
  strict=True validate -> dump -> re-validate round-trip.
- output_format is a required discriminator ("text" / "json_schema").
  structured_content has NO default on the structured result — it must be
  passed explicitly even when None.
- Exceptions raised in the callback become a JSON-RPC error surfaced by
  Stagehand, not a hang — failures are loud and safe.
"""

import json
import logging
import re

import httpx
from stagehand import LLMImageContent, LLMRole, LLMTextContent, LLMUsage
from stagehand._generated.models import (
    FieldSchema8,
    LLMMessageContentBlock,
    LLMMessageGenerateResult,
    LLMStructuredGenerateParams,
    LLMStructuredGenerateResult,
)

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


_NULLABLE_SCHEMA_KEYS = {"const", "enum"}
_DROPPED_SCHEMA_KEYS = {"default", "examples"}


def _strict_schema(node):
    """
    OpenAI (strict json_schema) rejects what Stagehand generates: objects
    whose `additionalProperties` is an untyped placeholder ("schema must
    have a 'type' key"), and properties left out of `required`. Normalize
    to what strict mode demands — every object closed and fully required,
    null-valued keys (pydantic dump artifacts) dropped. Still valid JSON
    Schema, so lenient providers (Gemini etc.) are unaffected.
    """
    if isinstance(node, list):
        return [_strict_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {
        key: _strict_schema(value)
        for key, value in node.items()
        if key not in _DROPPED_SCHEMA_KEYS
        and (value is not None or key in _NULLABLE_SCHEMA_KEYS)
    }
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list((out.get("properties") or {}).keys())
    return out


def _parse_structured_text(text: str):
    """
    Models routed through OpenRouter often wrap JSON in ```json fences or
    prepend reasoning/<think> text even under json_schema mode. Try the
    plain parse first, then fall back to the outermost {...} block.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass
    logger.warning(
        "LLM structured output was not valid JSON (finish_reason unknown to "
        "parser); raw reply (first 500 chars): %r",
        text[:500],
    )
    return None


def _blocks_to_openai_content(content) -> list[dict]:
    blocks = content if isinstance(content, list) else [content]
    parts = []
    for block in blocks:
        inner = block.root
        if isinstance(inner, LLMTextContent):
            parts.append({"type": "text", "text": inner.text})
        elif isinstance(inner, LLMImageContent):
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{inner.mime_type};base64,{inner.data}"},
                }
            )
        # LLMToolUseContent / LLMToolResultContent: only relevant to
        # tool-use/WebMCP flows, not needed for act/observe/extract — see
        # module docstring / PLAN.md, noted gap rather than silently dropped.
    return parts


def _messages_to_openai(params) -> list[dict]:
    openai_messages = []
    if params.system_prompt:
        openai_messages.append({"role": "system", "content": params.system_prompt})
    for msg in params.messages:
        openai_messages.append(
            {"role": msg.role.value, "content": _blocks_to_openai_content(msg.content)}
        )
    return openai_messages


# Set when OpenRouter answers 402 (credits / key spending limit exhausted).
# Stagehand wraps callback exceptions into its own RPCError, losing the
# type, so callers (the scraper) check this instead of parsing messages.
_credits_exhausted: str | None = None


def credits_exhausted() -> str | None:
    """OpenRouter's 402 message if the last call ran out of credits, else None."""
    return _credits_exhausted


def clear_credits_exhausted() -> None:
    global _credits_exhausted
    _credits_exhausted = None


async def _call_openrouter(body: dict) -> dict:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=body,
        )
        global _credits_exhausted
        if resp.status_code == 402:
            _credits_exhausted = resp.text[:300]
        elif not resp.is_error:
            _credits_exhausted = None
        if resp.is_error:
            # raise_for_status() alone drops OpenRouter's explanation (e.g.
            # which schema/param the model rejected) — keep it in the error.
            raise RuntimeError(
                f"OpenRouter {resp.status_code} for model {body.get('model')}: "
                f"{resp.text[:800]}"
            )
        return resp.json()


def _usage_from_openai(data: dict) -> LLMUsage:
    u = data.get("usage") or {}
    return LLMUsage(
        input_tokens=int(u.get("prompt_tokens", 0)),
        output_tokens=int(u.get("completion_tokens", 0)),
        total_tokens=int(u.get("total_tokens", 0)),
    )


def openrouter_llm_for(model: str):
    """A Stagehand model callback pinned to a specific model (the scraper's
    fallback run uses this instead of the configured Tier-2 default)."""

    async def callback(params):
        return await openrouter_llm(params, model=model)

    return callback


async def openrouter_llm(params, model: str | None = None):
    """
    Real OpenRouter-backed callback for Tier 2 (Stagehand observe/act).
    Branches on the exact param type Stagehand hands us, per the contract
    above — this isinstance check is reliable because the two param
    variants are mutually exclusive on the wire (response_format.type
    discriminates them; see PLAN.md).
    """
    openai_messages = _messages_to_openai(params)
    body = {
        "model": model or settings.openrouter_model_tier2,
        "messages": openai_messages,
        # Stagehand never sends a limit, and without one OpenRouter reserves
        # the model's full output window (65,536 for Gemini) against the
        # key's budget — live-caught as a 402 "can only afford 60166" while
        # real replies here are < ~3k tokens.
        "max_tokens": settings.openrouter_tier2_max_tokens,
    }
    if params.temperature is not None:
        body["temperature"] = params.temperature
    if params.stop_sequences:
        body["stop"] = params.stop_sequences

    is_structured = isinstance(params, LLMStructuredGenerateParams)
    if is_structured:
        schema_dict = (
            params.response_format.schema_.model_dump(mode="json", by_alias=True)
            if params.response_format.schema_ is not None
            else {}
        )
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": params.response_format.name,
                "strict": True,
                "schema": _strict_schema(schema_dict),
            },
        }

    data = await _call_openrouter(body)
    choice = data["choices"][0]
    text = choice["message"]["content"] or ""
    usage = _usage_from_openai(data)
    content_block = LLMMessageContentBlock(root=LLMTextContent(type="text", text=text))

    if is_structured:
        structured = _parse_structured_text(text)
        return LLMStructuredGenerateResult(
            role=LLMRole.assistant,
            content=[content_block],
            stop_reason=choice.get("finish_reason"),
            usage=usage,
            output_format="json_schema",
            structured_content=FieldSchema8.model_validate(structured)
            if structured is not None
            else None,
        )

    return LLMMessageGenerateResult(
        role=LLMRole.assistant,
        content=[content_block],
        stop_reason=choice.get("finish_reason"),
        usage=usage,
        output_format="text",
    )

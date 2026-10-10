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

import asyncio
import json
import logging
import re
import time

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
from app.services.engine.timeouts import describe

logger = logging.getLogger(__name__)

# Real bug, live-caught 2026-09-17: OpenRouter's `response_format: json_schema`
# is a REQUEST, not a guarantee — it silently routed z-ai/glm-4.6 to a
# provider ("Venice") that accepted the parameter without error and then
# ignored it entirely, returning free-form prose instead of JSON. Pinning a
# specific provider (`provider.order`, `require_parameters: true`) was tried
# live against the real API and did NOT fix it: Venice still won even with
# require_parameters, and explicitly excluding it left zero endpoints that
# both serve this model AND actually honor strict structured output. Since
# OpenRouter's provider routing can shift to a non-compliant provider for
# ANY model at any time, the durable fix has to be resilience in THIS
# function, not a model/provider pin that could break again the same way.
# `json.loads(text)` used to be the ONLY attempt — any prose response (the
# 100%-reproducible case here, not occasional flakiness) fell straight
# through to `structured_content=None`, which Stagehand's own extension-side
# schema then rejects with a cryptic `RPCError: invalid_type` naming a field
# ("structuredContent") our code never mentions — undiagnosable without
# reading the extension's bundled JS directly, which is what it took to
# find this. `_extract_json`/`_repair_to_json` below give two more real
# chances before actually giving up.
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> dict | list | None:
    """Best-effort recovery of JSON from a response that ignored
    response_format entirely. Tries, in order: the raw text as-is, a
    ```json ... ``` fenced block (models that DO try to comply often still
    wrap it in markdown), then the widest {...} substring (a model that
    prefaces its answer with prose before the actual JSON object)."""
    candidates = [text.strip()]
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1).strip())
    brace_start, brace_end = text.find("{"), text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidates.append(text[brace_start : brace_end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


async def _repair_to_json(body: dict, prior_text: str) -> dict | list | None:
    """One follow-up call telling the model its own prior answer wasn't
    JSON, asking it to reformat — same "one repair retry" shape as Tier 1's
    _chat_with_repair (tier1_map.py). Prompt-level reinforcement rather
    than another response_format attempt, since the provider already
    proved it ignores that parameter."""
    repair_body = {
        **body,
        "messages": [
            *body["messages"],
            {"role": "assistant", "content": prior_text},
            {
                "role": "user",
                "content": (
                    "That was not valid JSON. Reply with ONLY the JSON object "
                    "matching the requested schema — no prose, no markdown "
                    "code fences, nothing before or after the JSON."
                ),
            },
        ],
    }
    try:
        data = await _call_openrouter(repair_body)
        repaired_text = data["choices"][0]["message"]["content"] or ""
    except Exception:  # noqa: BLE001
        logger.exception("JSON repair call itself failed")
        return None
    return _extract_json(repaired_text)


def _coerce_nulls_to_schema_type(data, schema: dict):
    """
    Real bug, live-caught immediately after the fix above: getting the
    model to return actual JSON (rather than prose) surfaced a SECOND,
    narrower gap — `RPCError: invalid_type, expected 'string', path:
    ['structuredContent', 'sections', 0, 'url']`. The model filled in a
    section it couldn't find a real URL for with JSON `null` rather than
    an empty string, which is entirely reasonable model behavior but
    doesn't match a plain (non-Optional) `str` field's generated JSON
    schema — `{"type": "string"}` does not permit null, so Stagehand's
    own extension-side re-validation of whatever we hand back rejects it
    before our own Pydantic model ever sees it.

    Rather than special-case every such field by name (today it's
    ListingSection.url; anything else not `Optional` would hit the exact
    same failure tomorrow), walk the ACTUAL JSON schema the caller
    requested alongside the parsed data and replace any `None` found at
    a position schema-typed as "string" with "" — generically correct
    for any current or future non-nullable string field, not just this
    one live-caught case.
    """
    if isinstance(schema, dict) and schema.get("type") == "object":
        properties = schema.get("properties") or {}
        if isinstance(data, dict):
            for key, value in list(data.items()):
                prop_schema = properties.get(key)
                if prop_schema is None:
                    continue
                if value is None and prop_schema.get("type") == "string":
                    data[key] = ""
                else:
                    data[key] = _coerce_nulls_to_schema_type(value, prop_schema)
    elif isinstance(schema, dict) and schema.get("type") == "array":
        item_schema = schema.get("items")
        if isinstance(data, list) and item_schema is not None:
            for i, item in enumerate(data):
                data[i] = _coerce_nulls_to_schema_type(item, item_schema)
    return data


def _make_strict_compatible(schema):
    """
    Pydantic's own JSON Schema generation (what Stagehand hands us as
    `params.response_format.schema_`) is a correct, general-purpose JSON
    Schema — but OpenAI's `strict: true` structured-output mode has two
    EXTRA requirements beyond plain JSON Schema validity that Pydantic
    doesn't know or care about: every object must set
    `"additionalProperties": false` (Pydantic emits `{}`, meaning "any
    type allowed", which is valid JSON Schema but rejected by OpenAI's
    strict mode with "additionalProperties is required to be supplied
    and to be false"), and every property must appear in `"required"`
    even when it's optional/nullable (optionality is expressed via the
    property's own type, e.g. `anyOf: [{type: string}, {type: null}]`
    with a default — not by omitting it from `required`). Confirmed
    directly: OpenAI models rejected the schema as originally generated,
    same failure either param violates.

    Model-agnostic by construction — recurses through the whole schema
    fixing both, so switching `openrouter_model_tier2` to any strict-mode
    provider in the future doesn't need a matching schema change here.
    """
    if isinstance(schema, dict) and schema.get("type") == "object":
        properties = schema.get("properties") or {}
        for value in properties.values():
            _make_strict_compatible(value)
        schema["additionalProperties"] = False
        schema["required"] = list(properties.keys())
    elif isinstance(schema, dict) and schema.get("type") == "array":
        if schema.get("items") is not None:
            _make_strict_compatible(schema["items"])
    elif isinstance(schema, dict) and "anyOf" in schema:
        for sub in schema["anyOf"]:
            _make_strict_compatible(sub)
    return schema


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


# Models that answered 400 "Reasoning is mandatory" to reasoning={enabled:false}
# (e.g. Gemini): sent without the flag from then on.
_reasoning_mandatory: set[str] = set()


async def _call_openrouter(body: dict) -> dict:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    if body.get("model") in _reasoning_mandatory:
        body = {k: v for k, v in body.items() if k != "reasoning"}
    async with httpx.AsyncClient(timeout=60) as client:
        url = f"{settings.openrouter_base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code == 400 and "reasoning" in body and "easoning" in resp.text:
            _reasoning_mandatory.add(body["model"])
            body = {k: v for k, v in body.items() if k != "reasoning"}
            resp = await client.post(url, headers=headers, json=body)
        global _credits_exhausted
        # A key's own total limit answers 403 "Key limit exceeded", not 402
        # (live 2026-10-07): just as final, so it counts as out of credits.
        if resp.status_code == 402 or (
            resp.status_code == 403 and "limit exceeded" in resp.text.lower()
        ):
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


async def preflight_check(model: str | None = None, timeout: float = 30) -> str | None:
    """One tiny call to prove the configured model answers at all. Returns an
    error description, or None if healthy."""
    model = model or settings.openrouter_model_tier2
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "max_tokens": 16,
    }
    if settings.openrouter_disable_reasoning:
        body["reasoning"] = {"enabled": False}
    started = time.monotonic()
    try:
        await asyncio.wait_for(_call_openrouter(body), timeout=timeout)
    except BaseException as exc:  # noqa: BLE001
        if isinstance(exc, asyncio.CancelledError):
            raise
        return f"{model}: {describe(exc)} after {time.monotonic() - started:.1f}s"
    logger.info("LLM preflight OK: %s in %.1fs", model, time.monotonic() - started)
    return None


def _usage_from_openai(data: dict) -> LLMUsage:
    u = data.get("usage") or {}
    return LLMUsage(
        input_tokens=int(u.get("prompt_tokens", 0)),
        output_tokens=int(u.get("completion_tokens", 0)),
        total_tokens=int(u.get("total_tokens", 0)),
    )


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
    if settings.openrouter_disable_reasoning:
        body["reasoning"] = {"enabled": False}
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
        _make_strict_compatible(schema_dict)
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": params.response_format.name,
                "strict": True,
                "schema": _strict_schema(schema_dict),
            },
        }
        # Belt-and-suspenders alongside response_format above: a provider
        # that ignores response_format (see module comment) still often
        # follows an explicit in-prompt instruction — but ONLY if the
        # instruction actually states the schema. Real bug, live-caught
        # immediately after adding just the "respond with only JSON" text
        # below with no schema attached: Stagehand's own internal chunked-
        # extraction "progress" metadata call hallucinated field names
        # (`chunksSeen`, `chunksTotal`) straight out of ITS OWN system
        # prompt's natural-language description of that concept, because
        # nothing in what the model actually saw named the real expected
        # keys — response_format being ignored meant the model had NO
        # source of truth for the schema at all, structured or otherwise.
        # Inlining the literal schema JSON (not just a generic "use JSON"
        # instruction) gives every structured call a real contract to
        # follow regardless of which Stagehand-internal call it's for —
        # the assessment call, this metadata call, or any other.
        openai_messages.append(
            {
                "role": "system",
                "content": (
                    "Respond with ONLY a single JSON object matching "
                    "EXACTLY this JSON Schema — the same property names "
                    "and types, no extra or renamed fields, no prose, no "
                    "markdown code fences, nothing before or after the "
                    f"JSON:\n{json.dumps(schema_dict)}"
                ),
            }
        )

    started = time.monotonic()
    try:
        data = await _call_openrouter(body)
    except BaseException as exc:
        logger.error(
            "LLM call to %s failed after %.1fs: %s",
            body["model"],
            time.monotonic() - started,
            describe(exc),
        )
        raise
    choice = data["choices"][0]
    text = choice["message"]["content"] or ""
    usage = _usage_from_openai(data)
    logger.info(
        "LLM call to %s done in %.1fs (finish_reason=%s, out_tokens=%d, structured=%s)",
        body["model"],
        time.monotonic() - started,
        choice.get("finish_reason"),
        usage.output_tokens,
        is_structured,
    )
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

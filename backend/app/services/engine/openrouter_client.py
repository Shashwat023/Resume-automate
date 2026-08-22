"""
Direct OpenRouter chat client, used by Tier 1 (batched field mapping) and
later resume parsing. This is intentionally separate from
llm_client.py::openrouter_llm — Tier 1 makes its own HTTP calls with its own
prompt and never goes through Stagehand's LLM callback protocol at all.
Stagehand's `model=` callback is only invoked when Stagehand itself needs an
LLM, which is Tier 2 (observe/act). Keeping these two call paths separate
means Tier 1 stays simple, cheap, and independent of Stagehand's wire format.
"""

import json

import httpx

from app.core.config import get_settings

settings = get_settings()


class OpenRouterError(Exception):
    pass


async def chat_json(
    messages: list[dict],
    *,
    json_schema: dict,
    schema_name: str,
    model: str,
    temperature: float = 0.0,
) -> tuple[dict, dict]:
    """
    Calls OpenRouter's /chat/completions with response_format=json_schema,
    returns (parsed_dict, usage_dict). Raises OpenRouterError on transport
    failure or malformed JSON in the response — callers decide whether to
    retry (Tier 1 does one repair retry) rather than this module deciding.
    """
    if not settings.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured")

    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": json_schema},
        },
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json=body,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

    data = resp.json()
    text = data["choices"][0]["message"]["content"] or ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenRouterError(f"OpenRouter returned non-JSON content: {exc}") from exc

    usage = data.get("usage") or {}
    return parsed, {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }

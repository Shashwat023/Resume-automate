"""
The custom LLM callback Stagehand.create(model=...) accepts. Confirmed in the
Day-1 spike: Stagehand v4 places zero constraints on this — it's just an
async function, so OpenRouter is a plain HTTP call inside it. No ModelConfig/
base-URL plumbing needed.

Wired for real in Day 3 (Tier 1 batched mapping, Tier 2 observe/act). Tier 0
never calls this — `unreachable_llm` is passed to Stagehand.create() during
Tier 0 runs specifically so any accidental LLM invocation fails loudly
instead of silently costing money.
"""
from app.core.config import get_settings

settings = get_settings()


async def unreachable_llm(params):
    raise RuntimeError(
        "LLM callback invoked during a Tier 0-only run — Tier 0 must be "
        "purely deterministic. This indicates a bug, not a missing API key."
    )


async def openrouter_llm(params):
    """Real OpenRouter-backed callback for Tier 1/2 (Day 3)."""
    import httpx

    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    # TODO(Day 3): translate `params` (LLMMessageGenerateParams /
    # LLMStructuredGenerateParams) into an OpenRouter chat/completions call,
    # and translate the response back into LLMMessageGenerateResult /
    # LLMStructuredGenerateResult. Shape confirmed during the Day-1 spike.
    raise NotImplementedError("Tier 1/2 OpenRouter wiring lands Day 3")

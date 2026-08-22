"""
Tier 1 — one batched LLM call per page for every field Tier 0 couldn't
match. Decides a VALUE for each field using profile data (and the answers
library for fields it's already seen); does not resolve widgets itself.
Applying the decided value is a separate step:

  - textbox                    -> filled directly here (locator.fill())
  - combobox WITH tree options -> filled directly here (locator.select_option())
  - everything else (custom combobox with no known options, checkbox,
    radio) -> handed to Tier 2, which resolves the actual clickable
    element via Stagehand observe()/act() and executes using the value
    decided here.

Kept deliberately separate from Stagehand's LLM callback (llm_client.py) —
this is our own direct OpenRouter call with our own prompt, batched once
per page, never routed through Stagehand's per-action wire protocol. Tier 2
is the only tier that ever invokes Stagehand's LLM callback.
"""

import json
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError
from stagehand import Page

from app.core.config import get_settings
from app.domain.answer_key import question_hash
from app.repositories.answer_library_repository import AnswerLibraryRepository
from app.services.engine.openrouter_client import OpenRouterError, chat_json
from app.services.engine.tier0_harvest import FormField

settings = get_settings()


class FieldAnswer(BaseModel):
    field_id: str
    value: str
    confidence: float = Field(ge=0, le=1)


class TierOneResponse(BaseModel):
    answers: list[FieldAnswer]


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_id": {"type": "string"},
                    "value": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["field_id", "value", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answers"],
    "additionalProperties": False,
}


@dataclass
class Tier1Result:
    filled: list[tuple[str, str]]  # textbox/native-select fields written directly
    from_library: list[
        tuple[str, str]
    ]  # (label, answer) served from cache, no LLM call needed
    for_tier2: list[
        tuple[FormField, str]
    ]  # (field, decided value) handed off for Stagehand to execute
    low_confidence: list[str]  # left alone entirely -> Tier 3 (human)
    errored: list[tuple[str, str]]
    usage: dict


def build_prompt(profile: dict, fields: list[FormField]) -> list[dict]:
    field_payload = [
        {
            "id": f.node_id,
            "role": f.role,
            "label": f.label,
            "options": f.options or None,
        }
        for f in fields
    ]
    profile_summary = {k: v for k, v in profile.items() if v not in (None, "", [])}

    system = (
        "You are filling out a job application form on behalf of a candidate. "
        "For each field below, decide the best value using ONLY the candidate profile "
        "provided. If a field has an 'options' list, your value MUST be exactly one of "
        "those option strings, verbatim. If a field has no options (a free-text question "
        "or a custom dropdown/checkbox with unknown choices), write a concise, honest "
        "value inferred from the profile. Give a confidence from 0 to 1 for every answer: "
        "use a LOW confidence (below 0.5) whenever the profile genuinely doesn't contain "
        "the information needed — do not fabricate specifics that aren't in the profile."
    )
    # default=str: profile_summary comes straight from ORM column values
    # (runner.py builds it via `getattr(profile, c.name)` for every column),
    # so datetime/Decimal/etc need a safe stringification rather than a
    # hand-maintained field-name filter that breaks every time the schema
    # gains a new non-JSON-native column type.
    user = json.dumps(
        {"profile": profile_summary, "fields": field_payload}, default=str
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def map_fields(
    page: Page,
    fields: list[FormField],
    profile: dict,
    profile_id: int,
    answer_repo: AnswerLibraryRepository,
) -> Tier1Result:
    filled: list[tuple[str, str]] = []
    from_library: list[tuple[str, str]] = []
    for_tier2: list[tuple[FormField, str]] = []
    low_confidence: list[str] = []
    errored: list[tuple[str, str]] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # 1. Answers library first — free, no LLM call. Only fields with no
    #    fixed option set are cacheable this way (see module docstring).
    remaining: list[FormField] = []
    for f in fields:
        if not f.options:
            cached = await answer_repo.get(profile_id, question_hash(f.label))
            if cached is not None:
                from_library.append((f.label, cached.answer))
                await _apply(page, f, cached.answer, filled, for_tier2, errored)
                continue
        remaining.append(f)

    if not remaining:
        return Tier1Result(
            filled, from_library, for_tier2, low_confidence, errored, usage
        )

    if not settings.openrouter_api_key:
        # Kill switch: no key configured -> the app must stay runnable
        # without one. Everything left over falls through to Tier 3.
        low_confidence.extend(f.label for f in remaining)
        return Tier1Result(
            filled, from_library, for_tier2, low_confidence, errored, usage
        )

    messages = build_prompt(profile, remaining)
    parsed, call_usage = await _chat_with_repair(messages)
    usage = call_usage

    by_id = {f.node_id: f for f in remaining}
    for answer in parsed.answers:
        field = by_id.get(answer.field_id)
        if field is None:
            continue
        if answer.confidence < settings.tier1_confidence_threshold:
            low_confidence.append(field.label)
            continue

        await _apply(page, field, answer.value, filled, for_tier2, errored)

        if not field.options:
            # Cache free-text / unknown-option answers only — this is the
            # "novel question" case the answers library exists for.
            await answer_repo.upsert(
                profile_id,
                question_hash(field.label),
                field.label,
                answer.value,
                source="llm",
                confidence=answer.confidence,
            )

    return Tier1Result(filled, from_library, for_tier2, low_confidence, errored, usage)


async def _apply(
    page: Page,
    field: FormField,
    value: str,
    filled: list[tuple[str, str]],
    for_tier2: list[tuple[FormField, str]],
    errored: list[tuple[str, str]],
) -> None:
    if field.xpath is None:
        errored.append((field.label, "no xpath available"))
        return

    try:
        if field.role == "textbox":
            await page.locator(field.xpath).fill(value)
            filled.append((field.label, value))
        elif field.is_native_select:
            await page.locator(field.xpath).select_option(value)
            filled.append((field.label, value))
        else:
            # Custom combobox with no known options, checkbox, or radio —
            # Tier 2's job to resolve the real clickable element and execute.
            for_tier2.append((field, value))
    except Exception as exc:  # noqa: BLE001
        errored.append((field.label, str(exc)))


async def _chat_with_repair(messages: list[dict]) -> tuple[TierOneResponse, dict]:
    """One repair retry on malformed JSON before giving up entirely."""
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw, usage = await chat_json(
                messages,
                json_schema=_RESPONSE_SCHEMA,
                schema_name="tier1_field_answers",
                model=settings.openrouter_model_tier1,
            )
            return TierOneResponse.model_validate(raw), usage
        except (OpenRouterError, ValidationError) as exc:
            last_error = exc
            if attempt == 0:
                messages = messages + [
                    {
                        "role": "user",
                        "content": f"Your previous response was invalid: {exc}. Return ONLY valid JSON matching the schema.",
                    }
                ]
                continue
    raise OpenRouterError(f"Tier 1 response invalid after repair retry: {last_error}")

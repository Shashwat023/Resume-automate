"""
Tier 0 — deterministic harvest. No LLM. Pulls Stagehand's accessibility-tree
snapshot of the current page, extracts textbox fields with their accessible
names, matches against the semantic dictionary, and fills the matches.

Only `textbox` roles are handled here — combobox/checkbox/radio and any
free-text judgment question fall through unmatched, which is correct: those
are Tier 1 (batched LLM) / Tier 2 (Stagehand observe/act) / Tier 3 (human)
territory per PLAN.md's tier boundaries. Tier 0's job is the ~70-80% of
fields that don't need any of that.
"""

import re
from dataclasses import dataclass

from stagehand import Page

from app.domain.semantic_dictionary import match_field, resolve_value

_TEXTBOX_LINE = re.compile(r"^\s*\[([\w-]+)\]\s+textbox:\s*(.+?)\s*$")


@dataclass
class HarvestResult:
    filled: list[tuple[str, str]]  # (label, value) actually written
    unmatched: list[str]  # labels with no semantic dictionary match
    errored: list[
        tuple[str, str]
    ]  # (label, error) - matched but the fill itself failed


async def harvest_and_fill(page: Page, profile: dict) -> HarvestResult:
    snapshot = await page.snapshot()
    filled: list[tuple[str, str]] = []
    unmatched: list[str] = []
    errored: list[tuple[str, str]] = []

    for line in snapshot.formatted_tree.splitlines():
        m = _TEXTBOX_LINE.match(line)
        if not m:
            continue
        node_id, label = m.group(1), m.group(2)

        match = match_field(label)
        if match is None:
            unmatched.append(label)
            continue

        value = resolve_value(profile, match)
        if not value:
            unmatched.append(label)
            continue

        xpath = snapshot.xpath_map.get(node_id)
        if xpath is None:
            unmatched.append(label)
            continue

        try:
            # A field earlier in this loop may have reflowed the DOM enough
            # to invalidate this xpath even though it came from the same
            # snapshot — one bad field must not abort the rest of the fill.
            await page.locator(xpath).fill(value)
            filled.append((label, value))
        except Exception as exc:  # noqa: BLE001
            errored.append((label, str(exc)))

    return HarvestResult(filled=filled, unmatched=unmatched, errored=errored)

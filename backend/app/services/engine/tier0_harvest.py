"""
Tier 0 — deterministic harvest. No LLM. Pulls Stagehand's accessibility-tree
snapshot of the current page, extracts ALL interactive form fields
(textbox, combobox, checkbox, radio), and fills the ones the semantic
dictionary can match with high confidence — textboxes only.

Split into two phases (`collect_fields` / `fill_deterministic`) rather than
the original single `harvest_and_fill`, because Tier 1 and Tier 2 both need
the full field inventory — including the combobox/checkbox/radio fields
Tier 0 itself never touches — not just the textboxes Tier 0 fills.

Confirmed against a real Anthropic Greenhouse form (see PLAN.md): comboboxes
render as custom React-select widgets with ZERO children in the accessibility
tree — no visible `option:` rows — until the widget is opened. A native
`<select>` DOES expose its `option:` children directly in the tree. That
distinction is exactly the Tier 1 vs Tier 2 boundary:
  - combobox WITH options in the tree -> Tier 1 can pick a value and call
    `locator.select_option(value)`.
  - combobox with NO options in the tree -> genuinely can't be driven by
    select_option (Playwright-style label/index lookups aren't even
    available on Stagehand's Locator — values only). That's Tier 2's job:
    `observe()` returns a real resolvable selector for the actual clickable
    element, not a screen coordinate — the fix this whole rebuild exists for.
"""

import re
from dataclasses import dataclass, field

from stagehand import Page

from app.domain.semantic_dictionary import match_field, resolve_value

# Role is a single bare word in every case observed in the real tree
# (StaticText/ListMarker/etc use the same shape). Label is everything after
# the colon; roles with no name (body, main, div, scrollable, html, ...)
# have no colon at all and are simply skipped by TARGET_ROLES filtering.
_FIELD_LINE = re.compile(
    r"^(?P<indent>\s*)\[(?P<id>[\w-]+)\]\s+(?P<role>[A-Za-z]+)(?::\s*(?P<label>.*?))?\s*$"
)

TARGET_ROLES = {"textbox", "combobox", "checkbox", "radio"}


@dataclass
class FormField:
    node_id: str
    role: str  # textbox | combobox | checkbox | radio
    label: str
    xpath: str | None
    options: list[str] = field(
        default_factory=list
    )  # only populated if the tree exposes option: children

    @property
    def is_native_select(self) -> bool:
        """A combobox is only select_option()-able if the tree actually exposed its options."""
        return self.role == "combobox" and bool(self.options)


@dataclass
class HarvestResult:
    filled: list[tuple[str, str]]  # (label, value) actually written
    unmatched: list[str]  # labels with no semantic dictionary match
    errored: list[
        tuple[str, str]
    ]  # (label, error) - matched but the fill itself failed


def collect_fields(formatted_tree: str, xpath_map: dict[str, str]) -> list[FormField]:
    """
    Parses every line into (indent_length, node_id, role, label), then for
    each target-role node walks forward collecting `option:` children —
    any subsequent line whose indent is strictly greater belongs to that
    node's subtree; a line at indent <= the field's own indent closes it.

    Uses raw indentation character count for the nesting comparison, not a
    normalized depth (spaces-per-level is NOT constant in the real tree —
    confirmed empirically: sibling fields on the same real form differ by
    2, 4, 6+ spaces depending on how many wrapper divs each one has). Only
    relative nesting matters here, so raw length comparison is correct and
    doesn't depend on that assumption.
    """
    nodes: list[tuple[int, str, str, str]] = []
    for line in formatted_tree.splitlines():
        m = _FIELD_LINE.match(line)
        if not m:
            continue
        nodes.append(
            (
                len(m.group("indent")),
                m.group("id"),
                m.group("role"),
                (m.group("label") or "").strip(),
            )
        )

    fields: list[FormField] = []
    n = len(nodes)
    for i, (indent, node_id, role, label) in enumerate(nodes):
        if role not in TARGET_ROLES:
            continue

        options: list[str] = []
        j = i + 1
        while j < n and nodes[j][0] > indent:
            if nodes[j][2] == "option":
                options.append(nodes[j][3])
            j += 1

        fields.append(
            FormField(
                node_id=node_id,
                role=role,
                label=label,
                xpath=xpath_map.get(node_id),
                options=options,
            )
        )

    return fields


async def fill_deterministic(
    page: Page, fields: list[FormField], profile: dict
) -> HarvestResult:
    """
    Textbox fields only — the exact behavior of the original single-phase
    harvest_and_fill, now operating on an already-collected field list
    instead of re-parsing the tree itself. Combobox/checkbox/radio fields
    are left entirely alone here; they're Tier 1/2 territory.
    """
    filled: list[tuple[str, str]] = []
    unmatched: list[str] = []
    errored: list[tuple[str, str]] = []

    for f in fields:
        if f.role != "textbox":
            continue

        match = match_field(f.label)
        if match is None:
            unmatched.append(f.label)
            continue

        value = resolve_value(profile, match)
        if not value:
            unmatched.append(f.label)
            continue

        if f.xpath is None:
            unmatched.append(f.label)
            continue

        try:
            # A field earlier in this loop may have reflowed the DOM enough
            # to invalidate this xpath even though it came from the same
            # snapshot — one bad field must not abort the rest of the fill.
            await page.locator(f.xpath).fill(value)
            filled.append((f.label, value))
        except Exception as exc:  # noqa: BLE001
            errored.append((f.label, str(exc)))

    return HarvestResult(filled=filled, unmatched=unmatched, errored=errored)


async def harvest_and_fill(page: Page, profile: dict) -> HarvestResult:
    """Convenience wrapper: snapshot + collect + fill in one call (Tier-0-only callers)."""
    snapshot = await page.snapshot()
    fields = collect_fields(snapshot.formatted_tree, snapshot.xpath_map)
    return await fill_deterministic(page, fields, profile)

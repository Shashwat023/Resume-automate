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

import phonenumbers
from stagehand import Page

from app.domain.semantic_dictionary import match_field, resolve_value
from app.services.engine.field_fill import fill_textbox
from app.services.engine.timeouts import with_timeout

# Role is USUALLY a single bare word (StaticText/ListMarker/textbox/...),
# but the file-upload control on a real Greenhouse form renders as a
# comma-joined role: `[3-78] input, file: Attach` (confirmed live — see
# PLAN.md Day 4 recon notes). The role group accepts that comma-separated
# form generally rather than special-casing "file" in the regex itself.
# Label is everything after the colon; roles with no name (body, main, div,
# scrollable, html, ...) have no colon at all and are simply skipped by
# TARGET_ROLES filtering.
_FIELD_LINE = re.compile(
    r"^(?P<indent>\s*)\[(?P<id>[\w-]+)\]\s+"
    r"(?P<role>[A-Za-z]+(?:,\s*[A-Za-z]+)*)(?::\s*(?P<label>.*?))?\s*$"
)

TARGET_ROLES = {"textbox", "combobox", "checkbox", "radio", "file"}

# The only grouping construct confirmed to carry a required-field marker on
# a real form: `[id] group: Resume/CV*` — the enclosing group's OWN label
# ends in "*", not the input's. Only this one pattern is implemented; a
# required marker attached some other way (e.g. a sibling "*" StaticText
# with no enclosing group) would not be caught — flagged as a known gap
# rather than guessed at without live confirmation.
_GROUP_ROLE = "group"

# A real form can have more than one file input (confirmed live: Resume/CV
# AND Cover Letter as separate fields, see PLAN.md Day 4 recon notes). The
# stored resume must only be attached to the one that's actually asking for
# a resume/CV — attaching it everywhere would silently submit it as a cover
# letter too.
_RESUME_FIELD_LABEL = re.compile(r"resum[eé]|\bcv\b", re.I)

# Real bug found live: a form can split phone entry into a separate
# Country/dial-code selector PLUS a plain Phone field. The profile stores
# the phone number WITH its country code (e.g. "+918303545027"), which is
# correct for a single combined phone field — but on a split form it
# duplicates the code, since the Country dropdown already supplies it.
# Only strip when a sibling selector actually exists on the page (checked
# where this is used) — a form with one combined field legitimately needs
# the full number.
#
# A SECOND real bug was found fixing the first one: a naive regex
# (`^\+\d{1,4}[\s\-]*`, greedily eating up to 4 digits) doesn't know where
# the country code actually ends — calling codes are 1-3 digits and
# genuinely ambiguous from the digit string alone (+1 is 1 digit, +91 is
# 2, +971 is 3). Live-confirmed: it ate "+9183" instead of "+91" from
# "+918303545027", leaving the mangled "03545027" as the "phone number".
# `phonenumbers` (Google's libphonenumber) parses against the real ITU
# calling-code table instead of guessing.
def strip_country_code(value: str) -> str:
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException:
        return value
    return str(parsed.national_number)


@dataclass
class FormField:
    node_id: str
    role: str  # textbox | combobox | checkbox | radio | file
    label: str
    xpath: str | None
    options: list[str] = field(
        default_factory=list
    )  # only populated if the tree exposes option: children
    required: bool = False

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
        # role_tokens: "input, file" -> {"input", "file"}; "textbox" -> {"textbox"}.
        role_tokens = {r.strip() for r in m.group("role").split(",")}
        nodes.append(
            (
                len(m.group("indent")),
                m.group("id"),
                _effective_role(role_tokens),
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

        group_label, required = _enclosing_group(nodes, i, indent)
        # The file input's own label ("Attach") isn't meaningful for
        # matching or for disambiguating multiple file fields on one form
        # (e.g. "Resume/CV" vs "Cover Letter") — the enclosing group's
        # label is the real field name. Other roles keep their own label
        # unchanged (verified Day 3 matching behavior, not touched here).
        effective_label = group_label if (role == "file" and group_label) else label

        fields.append(
            FormField(
                node_id=node_id,
                role=role,
                label=effective_label,
                xpath=xpath_map.get(node_id),
                options=options,
                required=required,
            )
        )

    return fields


def _effective_role(role_tokens: set[str]) -> str:
    """A comma-joined role (`input, file`) collapses to whichever token is
    an actual target role; anything else keeps its first token so non-field
    lines (StaticText, div, ...) are unaffected and still filtered out by
    TARGET_ROLES."""
    for token in role_tokens:
        if token in TARGET_ROLES:
            return token
    return next(iter(role_tokens))


def _enclosing_group(
    nodes: list[tuple[int, str, str, str]], index: int, indent: int
) -> tuple[str | None, bool]:
    """Walks backward to the nearest preceding node at a smaller indent
    whose role is `group` — the only confirmed carrier of both the real
    field label and the required-field `*` marker (see module docstring)."""
    for j in range(index - 1, -1, -1):
        node_indent, _node_id, node_role, node_label = nodes[j]
        if node_indent >= indent:
            continue
        if node_role == _GROUP_ROLE:
            required = node_label.endswith("*")
            clean_label = node_label[:-1].strip() if required else node_label
            return clean_label or None, required
        indent = node_indent  # keep climbing past this ancestor too
    return None, False


async def fill_deterministic(
    page: Page,
    fields: list[FormField],
    profile: dict,
    resume_file_path: str | None = None,
) -> HarvestResult:
    """
    Textbox fields via the semantic dictionary (unchanged Day 3 behavior),
    plus file-upload fields (Day 4) — attaching the candidate's stored
    resume needs no LLM call and no widget resolution, so it belongs here
    rather than Tier 1/2, same reasoning as textbox matching. Combobox/
    checkbox/radio fields are left entirely alone; they're Tier 1/2
    territory.
    """
    filled: list[tuple[str, str]] = []
    unmatched: list[str] = []
    errored: list[tuple[str, str]] = []

    for f in fields:
        if f.role == "file":
            if not _RESUME_FIELD_LABEL.search(f.label):
                # A non-resume file field (Cover Letter, "Other Documents",
                # ...) — deliberately left alone. Attaching the resume here
                # too would misrepresent it as a different document.
                unmatched.append(f.label)
                continue
            if resume_file_path is None or f.xpath is None:
                unmatched.append(f.label)
                continue
            try:
                await page.locator(f.xpath).set_input_files(resume_file_path)
                # Confirmed live (see FLAGGED.md): Greenhouse's own widget
                # does an async upload after the file is set — a progress
                # bar, then "resume.pdf" + "Remove file" once it settles,
                # roughly ~1s in practice. A short wait here is cheap
                # insurance against later steps (Tier 1/2, or a fast
                # submit) racing ahead of that settling.
                await page.wait_for_timeout(1500)
                filled.append((f.label, resume_file_path))
            except Exception as exc:  # noqa: BLE001
                errored.append((f.label, str(exc)))
            continue

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

        if match.profile_attr == "phone" and value.startswith("+"):
            has_country_selector = any(
                other.role == "combobox" and "country" in other.label.lower()
                for other in fields
            )
            if has_country_selector:
                value = strip_country_code(value)

        if f.xpath is None:
            unmatched.append(f.label)
            continue

        try:
            # A field earlier in this loop may have reflowed the DOM enough
            # to invalidate this xpath even though it came from the same
            # snapshot — one bad field must not abort the rest of the fill.
            await fill_textbox(page, f.xpath, value)
            filled.append((f.label, value))
        except Exception as exc:  # noqa: BLE001
            errored.append((f.label, str(exc)))

    return HarvestResult(filled=filled, unmatched=unmatched, errored=errored)


async def harvest_and_fill(
    page: Page, profile: dict, resume_file_path: str | None = None
) -> HarvestResult:
    """Convenience wrapper: snapshot + collect + fill in one call (Tier-0-only callers)."""
    snapshot = await with_timeout(page.snapshot(), what="page.snapshot")
    fields = collect_fields(snapshot.formatted_tree, snapshot.xpath_map)
    return await fill_deterministic(page, fields, profile, resume_file_path)

"""
Submission: find the real Submit control and click it, then read the
resulting page to tell success from a validation error. Deterministic,
Tier-0 style (regex over the accessibility tree text) for both halves —
no LLM needed to recognize "Submit Application" or "Thank you for
applying."

Gated by settings.submit_enabled (default False) everywhere it's called
from runner.py — this module itself has no opinion on that flag; it just
implements what happens when submission is allowed to actually happen.
"""

import re
from dataclasses import dataclass

from stagehand import Page

from app.services.engine.tier0_harvest import _FIELD_LINE, _GROUP_ROLE, TARGET_ROLES

_SUBMIT_BUTTON = re.compile(
    r"^\s*\[([\w-]+)\]\s+button:\s*"
    r"(Submit(?:\s+Application)?|Send Application|Apply Now)\s*$",
    # re.M is the actual fix here: without it, ^/$ only anchor to the whole
    # STRING's start/end, not each line — meaning this could basically
    # never match a real (multi-line) accessibility tree except in the
    # degenerate case where the button happened to be the very first or
    # very last line. Confirmed live: this is exactly why real submission
    # failed with "submit button not found" even though the real button
    # ("Submit application") was right there in the tree. Single-line test
    # fixtures had masked this — see tests/test_engine_submit.py.
    re.I | re.M,
)

# Confirmation-page phrasing is fairly conventional across ATS providers.
_CONFIRMATION_PATTERN = re.compile(
    r"thank you for (?:your interest|applying)|application (?:has been |was )?"
    r"(?:submitted|received)|we('ve| have) received your application|"
    r"your application (?:has been |was )?submitted",
    re.I,
)

# Deliberately narrower than a bare "required"/"error" match — those words
# appear in ordinary form copy too (e.g. "* indicates a required field").
# This targets phrasing that only appears in an actual validation failure.
_VALIDATION_ERROR_PATTERN = re.compile(
    r"this field is required|please (?:fill|complete|correct|enter)|"
    r"is a required field|please fix the (?:error|following)|"
    r"invalid (?:email|phone|value|entry)",
    re.I,
)


@dataclass
class SubmitResult:
    outcome: str  # "no_button_found" | "completed" | "validation_error" | "unknown"
    detail: str = ""


def find_submit_button(formatted_tree: str, xpath_map: dict[str, str]) -> str | None:
    for match in _SUBMIT_BUTTON.finditer(formatted_tree):
        xpath = xpath_map.get(match.group(1))
        if xpath:
            return xpath
    return None


def read_outcome(formatted_tree: str) -> SubmitResult:
    conf = _CONFIRMATION_PATTERN.search(formatted_tree)
    if conf:
        return SubmitResult(outcome="completed", detail=conf.group(0))

    err = _VALIDATION_ERROR_PATTERN.search(formatted_tree)
    if err:
        return SubmitResult(outcome="validation_error", detail=err.group(0))

    return SubmitResult(outcome="unknown")


async def click_submit(page: Page, xpath: str) -> None:
    await page.locator(xpath).click()


def find_invalid_field_labels(formatted_tree: str) -> list[str]:
    """
    Real gap found live, across several runs: `read_outcome()` only
    detects that A validation error exists somewhere on the page — it has
    no idea WHICH field. Repair was instead targeted using Tier 2's own
    resolved/errored bookkeeping (`_unhandled_labels` in runner.py), which
    proved unreliable in practice: several real runs ended with "0 still
    unhandled" by that accounting, yet still failed with the SAME generic
    "This field is required" on every retry — meaning at least one field
    Tier 2 believed it had resolved was never actually accepted by the
    real ATS (regex-based description parsing catching one false-success
    wording at a time, see FLAGGED.md #17-19, is inherently open-ended).
    Reading the error directly off the page is the only fully reliable
    signal available; everything else is inference from our own actions.

    Confirmed live (Greenhouse): the error text renders as a plain text
    node immediately following the invalid field's own label/group in the
    tree, not tagged with the field's id in any structured way. Scan every
    line; on a validation-error match, attribute it to the most recently
    seen field label above it — the same "nearest preceding label" shape
    tier0_harvest.py's own `_enclosing_group` walk relies on, simplified
    since only the label (not the full FormField) is needed here.

    Real bug found live: an earlier version tracked ANY labeled line,
    which included a dropdown's own `button: Toggle flyout` child —
    "Toggle flyout" isn't a real field, so it was wrongly reported as the
    invalid one when it happened to sit closer to the error text than the
    actual field's own group label. Only lines whose role is one of
    tier0_harvest's own TARGET_ROLES (the actual fillable field types) or
    a `group` (the enclosing label tier0_harvest's own `_enclosing_group`
    treats as authoritative) are tracked as candidate labels now.
    """
    last_label: str | None = None
    labels: list[str] = []
    for line in formatted_tree.splitlines():
        m = _FIELD_LINE.match(line)
        label_here = (m.group("label") or "").strip() if m else None
        role_tokens = (
            {r.strip() for r in m.group("role").split(",")} if m else set()
        )
        is_candidate_label = bool(role_tokens & TARGET_ROLES) or _GROUP_ROLE in role_tokens
        # A validation-error TEXT node itself can match _FIELD_LINE (it's
        # just another `[id] role: text` line) — don't let it overwrite
        # the real field label sitting right above it.
        if (
            label_here
            and is_candidate_label
            and not _VALIDATION_ERROR_PATTERN.search(label_here)
        ):
            last_label = label_here.rstrip("*").strip()

        if _VALIDATION_ERROR_PATTERN.search(line) and last_label:
            labels.append(last_label)

    seen: set[str] = set()
    deduped: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            deduped.append(label)
    return deduped

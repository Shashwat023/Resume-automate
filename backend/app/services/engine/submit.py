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

_SUBMIT_BUTTON = re.compile(
    r"^\s*\[([\w-]+)\]\s+button:\s*"
    r"(Submit(?:\s+Application)?|Send Application|Apply Now)\s*$",
    re.I,
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

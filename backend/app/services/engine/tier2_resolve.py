"""
Tier 2 — Stagehand observe() -> act() for widgets Tier 0/1 can't drive
directly: custom comboboxes with no options exposed in the accessibility
tree, checkboxes, and radios. Tier 1 already decided WHAT value each field
should have; this tier's only job is finding and executing the click.

This is the direct fix for the coordinate-clicking bug the whole rebuild
exists for: observe() returns real, resolvable element references
(Action.selector — a CSS or XPath selector) it can then act() on directly,
never a screen coordinate that can drift the instant the page reflows.

observe()/act() live on Stagehand, not Page — target a page via page=.
Passing the Action straight from observe() into act() skips re-planning
and just executes against that resolved element (confirmed against the
installed package source, see PLAN.md Part C).
"""

import re
from dataclasses import dataclass
from typing import Any, Coroutine

from stagehand import Stagehand

from app.services.engine.tier0_harvest import FormField
from app.services.engine.timeouts import (
    LLM_CALL_TIMEOUT_SECONDS,
    describe as _describe,
    with_timeout,
)

# Real, live-caught bug: NOTHING bounded how long an observe()/act() call
# could take. One real run hung indefinitely on a single field (no
# exception, no timeout, no log line — just silence) after a CDP-level
# error (`-32602 Invalid mouse button`) on the previous action, leaving
# the whole application — and its Chrome session — stuck forever with no
# way to recover short of killing the process. The bound now lives in
# timeouts.py, shared with every other unbounded browser await in the
# engine (page.snapshot, goto, wait_for_load_state), because this was
# never a Tier-2-specific bug — Tier 2 is just where it was first hit.


async def _with_timeout(coro: Coroutine[Any, Any, Any]) -> Any:
    return await with_timeout(coro, LLM_CALL_TIMEOUT_SECONDS, "observe()/act()")


# Real, live-caught bug (FLAGGED.md #16/#17): a real run hit
# `-32602 Invalid mouse button` from the CDP layer on 9 separate act()
# calls across one application, including on 'Country' and 'Agreement to
# Arbitrate' — both times as a normal act() RETURN (success=False,
# message containing the CDP error), not a raised exception. Root cause
# not isolated (working theory: Qwen-specific action-generation
# occasionally proposing a malformed click parameter), but it was
# observed to be transient: the SAME resolved Action, re-dispatched a
# moment later, has succeeded on retry in live testing. One bounded retry
# — not a loop — since this is a best-effort mitigation for an
# unconfirmed root cause, not a fix for it.
_TRANSIENT_ACT_ERROR = re.compile(r"invalid mouse button", re.I)


@dataclass
class _SyntheticActResultData:
    success: bool
    message: str = ""
    action_description: str = ""


@dataclass
class _SyntheticActResult:
    data: _SyntheticActResultData


async def _act_with_retry(sh: Stagehand, page, action):
    """
    Real, live-caught finding: `-32602 Invalid mouse button` is Chrome's
    CDP layer REJECTING the trusted synthetic click `act()` dispatches via
    `Input.dispatchMouseEvent` — it never reaches the page's own JS at
    all. `Locator.send_click_event()` (Stagehand) is a structurally
    different mechanism: it dispatches a real DOM `MouseEvent` via JS
    directly against the resolved element, entirely bypassing that CDP
    input pipeline. That makes it a genuine alternative path, not just
    another attempt at the one that already failed — exactly the
    "custom widgets that listen for synthetic DOM events rather than
    trusted clicks" fallback PLAN.md anticipated. Tried BEFORE a second
    plain act() retry, since re-sending the identical CDP call the
    browser just rejected is less likely to succeed than switching
    mechanisms. Reported live as non-deterministic (same field fails in
    one run, succeeds in another with the SAME question) — consistent
    with a CDP-input-pipeline-level flakiness that a different dispatch
    path is well-suited to route around.
    """
    result = await _with_timeout(sh.act(action, page=page))
    if result.data.success or not _TRANSIENT_ACT_ERROR.search(
        result.data.message or ""
    ):
        return result

    selector = getattr(action, "selector", None)
    if selector:
        try:
            await _with_timeout(page.locator(selector).send_click_event())
            return _SyntheticActResult(
                data=_SyntheticActResultData(
                    success=True,
                    action_description=(
                        f"Clicked via send_click_event fallback after a CDP "
                        f"'Invalid mouse button' rejection (selector: {selector})"
                    ),
                )
            )
        except Exception:  # noqa: BLE001 - fall through to the plain retry below
            pass

    await page.wait_for_timeout(500)
    return await _with_timeout(sh.act(action, page=page))


# Real, live-caught bug (see FLAGGED.md): `act()`'s own `success=True` only
# means the click executed — it does NOT mean the widget's value actually
# changed. One real submission had "Agreement to Arbitrate" logged as
# resolved with `act()` reporting success, while its own action_description
# literally read "...currently showing 'Select...' option" — the
# unselected placeholder. The dropdown was still empty; nothing caught it.
#
# A first fix tried reading the value back from the real DOM
# (`page.locator(field.xpath).inner_text()`) — live-tested and found to be
# WORSE than the bug it fixed: on this exact widget shape (an ARIA
# `role="combobox"` `<input>` used only for keyboard/search, with the
# VISIBLE selected value rendered by separate SIBLING elements outside
# that input's own subtree), both `inner_text()` and `input_value()` on
# `field.xpath` are structurally always empty, selected or not — a 100%
# false-negative rate confirmed live, actively blocking a submission that
# `act()` had genuinely completed correctly. The reliable signal was
# always the one from the original finding: the model's own description
# text literally NAMING the placeholder it's looking at. Check that
# instead of a DOM query whose target element varies by site.
_PLACEHOLDER_TEXTS = {"select...", "select", "choose...", "choose"}
_QUOTED_TEXT = re.compile(r"'([^']*)'")

# Second real false-success shape (FLAGGED.md #13, "one new minor edge
# case"): the closest-match fallback reported `resolved` for a field whose
# own description explicitly said no match existed — "The '1-2 years'
# option was not found in the dropdown... There is no '1-2 years' option
# visible." `act()` still returned success=True (SOMETHING was clicked)
# and the description quotes no literal placeholder, so the placeholder
# check above can't catch it. This is a distinct signal: the model
# narrating a failure to find, rather than narrating a placeholder.
_NO_MATCH_PHRASES = re.compile(
    r"\b(?:was |is |were |are )?not (?:found|available|present|visible)\b"
    r"|\bthere (?:is|are|was|were) no\b"
    r"|\bcould not (?:find|locate|select)\b"
    r"|\bno (?:matching|such|suitable) option\b"
    r"|\bnone of the (?:options|available)\b",
    re.I,
)

# Real false-POSITIVE this introduced, found live: the closest-match
# fallback instruction (see the fallback_instruction below) deliberately
# ASKS the model to explain when the exact wording isn't present before
# naming the option it picked instead — "...that specific option is not
# present in the accessibility tree. The closest matching option that is
# visible and available for selection is 'Less than 5 years'." That's a
# genuine SUCCESS narrative following the fallback instruction correctly,
# not the original bug (a description with NO resolution at all — see
# FLAGGED.md #13). Without this carve-out, _NO_MATCH_PHRASES flags the
# fallback's own explanatory reasoning as a failure on nearly every
# closest-match resolution, needlessly spending an extra repair pass each
# time. Checked first: if the description also names a specific option it
# resolved TO, it's not the "nothing selected" failure shape.
_CLOSEST_MATCH_RESOLVED = re.compile(
    r"closest[^.]{0,80}\b(?:option|match)\b[^.]{0,40}\bis\b"
    r"|selected the closest|clicked the closest|closest reasonable match",
    re.I,
)

# Third real false-success shape, found live: the SELECT step's own
# act() reported success with a description that narrates re-clicking
# the OPEN/toggle control itself, not an actual option — "Toggle flyout
# button for the '...' dropdown, which when clicked will open the
# dropdown to reveal options including 'I agree'." The dropdown's real
# value never changed; it just got toggled again. Only ever checked
# against the SELECT step's description (never the OPEN step's, where
# this language is expected and correct), so a legitimate "opened the
# dropdown" from the open step is never at risk of matching this.
_TOGGLE_NOT_SELECT_PHRASES = re.compile(
    r"\btoggle\b|\bwhich when clicked will open\b|\breveal options\b"
    r"|\bopen(?:s|ed|ing)? the dropdown\b|\bto open it\b|\band see the options\b",
    re.I,
)

# Fourth real false-success shape, found live on the SAME Figma "Location
# (City)" typeahead field: act() reported success with a description that
# only narrates the dropdown's own generic UI hint text — "...currently
# open, with instructions indicating options can be navigated with
# keyboard" — never naming an actual selected value at all. Distinct from
# the toggle/placeholder/no-match shapes above (none of those patterns
# matched this wording), so it slipped through as "resolved" while the
# field's real value stayed empty (confirmed by the ATS's own "Please
# enter" rejection on the very next submit).
_GENERIC_INSTRUCTIONS_NOT_SELECTION = re.compile(
    r"\bcan be navigated\b|\binstructions indicating\b|\buse (?:arrow|the arrow) keys\b",
    re.I,
)


@dataclass
class Tier2Result:
    resolved: list[tuple[str, str]]  # (label, action_description) successfully executed
    errored: list[tuple[str, str]]


async def resolve_and_execute(
    sh: Stagehand, page, fields: list[tuple[FormField, str]]
) -> Tier2Result:
    resolved: list[tuple[str, str]] = []
    errored: list[tuple[str, str]] = []

    for field, value in fields:
        if field.role == "combobox":
            outcome = await _resolve_combobox(sh, page, field, value)
        else:
            outcome = await _resolve_single_step(
                sh, page, build_instruction(field, value)
            )

        if outcome.startswith("ERROR:"):
            errored.append((field.label, outcome.removeprefix("ERROR:")))
        else:
            resolved.append((field.label, outcome))

    return Tier2Result(resolved=resolved, errored=errored)


async def _resolve_single_step(sh: Stagehand, page, instruction: str) -> str:
    """Checkbox/radio: a single click is the whole interaction."""
    try:
        obs = await _with_timeout(sh.observe(instruction, page=page))
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:observe() failed: {_describe(exc)}"

    if not obs.data:
        return "ERROR:observe() found no matching element"

    try:
        act_result = await _act_with_retry(sh, page, obs.data[0])
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:act() failed: {_describe(exc)}"

    if not act_result.data.success:
        return f"ERROR:{act_result.data.message}"

    return act_result.data.action_description


async def _type_then_reobserve_select(sh: Stagehand, page, field: FormField, value: str):
    """
    Last-resort recovery for a TYPEAHEAD-filtered combobox (a
    Google-Places-style city picker, confirmed live on Figma's Greenhouse
    "Location (City)" field): its option list is only populated once
    something is typed, so an exact-match AND a closest-match select
    attempt against the just-opened, still-empty list both legitimately
    find nothing — there was never anything to click. Type the value into
    the combobox's own input, then retry the select once more against
    whatever that filtering reveals. Best-effort: returns None on any
    failure so the caller falls through to its normal "nothing found"
    error rather than raising.
    """
    type_instruction = (
        f"Type '{value}' into the '{field.label}' dropdown's own text/search input"
    )
    try:
        obs_type = await _with_timeout(sh.observe(type_instruction, page=page))
    except Exception:  # noqa: BLE001
        return None
    if not obs_type.data:
        return None

    try:
        await _act_with_retry(sh, page, obs_type.data[0])
    except Exception:  # noqa: BLE001
        return None

    await page.wait_for_timeout(500)  # let the filtered list render

    select_instruction = (
        f"Click the option '{value}' that is now visible in the open "
        f"'{field.label}' dropdown"
    )
    try:
        return await _with_timeout(sh.observe(select_instruction, page=page))
    except Exception:  # noqa: BLE001
        return None


async def _resolve_combobox(sh: Stagehand, page, field: FormField, value: str) -> str:
    """
    Custom comboboxes are genuinely two DOM states, not one: the option
    elements don't exist in the tree until the dropdown is opened (confirmed
    empirically — see tier0_harvest.py's module docstring). A single
    observe() against the closed state can physically never resolve an
    option that doesn't exist yet. Open first, THEN observe again against
    the now-open state to find the specific option.

    This was found by live-verifying against a real form: a single-step
    version of this function reported success (the open-click genuinely
    executed) while the field's actual value stayed empty — success meant
    "the click happened," not "the field now holds the right value."
    """
    open_instruction = f"Click to open the '{field.label}' dropdown"
    try:
        obs_open = await _with_timeout(sh.observe(open_instruction, page=page))
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:observe() (open step) failed: {_describe(exc)}"

    if not obs_open.data:
        return "ERROR:observe() found no dropdown to open"

    try:
        open_result = await _act_with_retry(sh, page, obs_open.data[0])
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:act() (open step) failed: {_describe(exc)}"

    if not open_result.data.success:
        return f"ERROR:failed to open dropdown: {open_result.data.message}"

    await page.wait_for_timeout(400)  # let the flyout actually render its options

    select_instruction = f"Click the option '{value}' that is now visible in the open '{field.label}' dropdown"
    try:
        obs_select = await _with_timeout(sh.observe(select_instruction, page=page))
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:observe() (select step) failed: {_describe(exc)}"

    if not obs_select.data:
        # Real, live-caught gap: Tier 1 decides a value BEFORE the dropdown
        # is ever opened (it has to — the real options aren't in the tree
        # until then, see tier0_harvest.py), so it's often a paraphrase —
        # "1-2 years" vs the ATS's actual "Less than 5 years" bucket. An
        # exact-wording instruction then finds nothing and the field is
        # left blank. Accepted tradeoff (PLAN.md Day 4): an approximate
        # answer beats a blank required field on a fully-automated
        # submission — retry once, explicitly permitting the closest
        # available option instead of an exact match.
        fallback_instruction = (
            f"None of the options in this now-open '{field.label}' dropdown "
            f"are worded exactly as '{value}'. Click whichever option is the "
            f"closest reasonable match for that answer — you must select one "
            f"of the options actually shown, never leave the dropdown unset."
        )
        try:
            obs_select = await _with_timeout(sh.observe(fallback_instruction, page=page))
        except Exception as exc:  # noqa: BLE001
            return f"ERROR:observe() (fallback select step) failed: {_describe(exc)}"

        if not obs_select.data:
            # Real, live-caught gap: BOTH exact and closest-match found
            # ZERO options on every attempt for Figma's Greenhouse
            # "Location (City)" field, across two full runs — because it's
            # a TYPEAHEAD-filtered combobox (Google-Places-style): the
            # option list is only populated once something is typed, so
            # there was never anything to click in the first place. Last
            # resort before giving up: type the value into the combobox's
            # own input, then retry the select once more against whatever
            # that filtering reveals.
            obs_select = await _type_then_reobserve_select(sh, page, field, value)
            if obs_select is None or not obs_select.data:
                return (
                    f"ERROR:dropdown opened but no option matching '{value}' "
                    "was found (closest-match fallback and typeahead retry "
                    "also found nothing)"
                )

    try:
        select_result = await _act_with_retry(sh, page, obs_select.data[0])
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:act() (select step) failed: {_describe(exc)}"

    if not select_result.data.success:
        return f"ERROR:dropdown opened but selecting '{value}' failed: {select_result.data.message}"

    verification_error = _check_description_for_failure(
        field, select_result.data.action_description
    )
    if verification_error is not None:
        return f"ERROR:{verification_error}"

    return select_result.data.action_description


def _check_description_for_failure(field: FormField, description: str) -> str | None:
    """
    Catches BOTH real false-success shapes (see module docstring and
    FLAGGED.md #13) without a DOM query, since `act()`'s own success flag
    only means "a click executed":

      1. the description QUOTES a placeholder — "...currently showing
         'Select...' option" — so the click didn't land on a real option;
      2. the description NARRATES not finding anything — "There is no
         '1-2 years' option visible" — which the quoted-placeholder check
         above structurally cannot see.

    (1) only checks quoted substrings, not the whole description, so
    ordinary phrases like "Select the option" (which legitimately contains
    the word "select") don't false-positive.

      3. the description narrates re-clicking the OPEN/toggle control
         itself, not an option — "Toggle flyout button... which when
         clicked will open the dropdown to reveal options including 'I
         agree'." The value never actually changed; only checked here
         (never against the OPEN step's own description, where this
         language is expected and correct).
    """
    if _NO_MATCH_PHRASES.search(description or "") and not _CLOSEST_MATCH_RESOLVED.search(
        description or ""
    ):
        return (
            f"selection reported success but its own description says no "
            f"matching option was found for '{field.label}': {description}"
        )

    if _TOGGLE_NOT_SELECT_PHRASES.search(description or ""):
        return (
            f"selection reported success but its own description narrates "
            f"re-opening/toggling the dropdown, not picking an option, for "
            f"'{field.label}': {description}"
        )

    if _GENERIC_INSTRUCTIONS_NOT_SELECTION.search(
        description or ""
    ) and not _CLOSEST_MATCH_RESOLVED.search(description or ""):
        return (
            f"selection reported success but its own description only "
            f"narrates the dropdown's generic UI hint text, not an actual "
            f"selected value, for '{field.label}': {description}"
        )

    for quoted in _QUOTED_TEXT.findall(description or ""):
        if quoted.strip().lower() in _PLACEHOLDER_TEXTS:
            return (
                f"selection reported success but its own description still "
                f"quotes the placeholder ('{quoted}') for '{field.label}'"
            )
    return None


def build_instruction(field: FormField, value: str) -> str:
    if field.role == "checkbox":
        want_checked = value.strip().lower() in ("yes", "true", "1", "checked")
        state = "checked" if want_checked else "unchecked"
        return f"Set the checkbox for '{field.label}' to {state}"
    if field.role == "radio":
        return (
            f"Select the radio button option '{value}' for the question '{field.label}'"
        )
    # Custom combobox with no options exposed in the tree.
    return f"In the '{field.label}' dropdown, open it and select the option that best matches: {value}"

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

from dataclasses import dataclass

from stagehand import Stagehand

from app.services.engine.tier0_harvest import FormField


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
        obs = await sh.observe(instruction, page=page)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:observe() failed: {exc}"

    if not obs.data:
        return "ERROR:observe() found no matching element"

    try:
        act_result = await sh.act(obs.data[0], page=page)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:act() failed: {exc}"

    if not act_result.data.success:
        return f"ERROR:{act_result.data.message}"

    return act_result.data.action_description


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
        obs_open = await sh.observe(open_instruction, page=page)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:observe() (open step) failed: {exc}"

    if not obs_open.data:
        return "ERROR:observe() found no dropdown to open"

    try:
        open_result = await sh.act(obs_open.data[0], page=page)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:act() (open step) failed: {exc}"

    if not open_result.data.success:
        return f"ERROR:failed to open dropdown: {open_result.data.message}"

    await page.wait_for_timeout(400)  # let the flyout actually render its options

    select_instruction = f"Click the option '{value}' that is now visible in the open '{field.label}' dropdown"
    try:
        obs_select = await sh.observe(select_instruction, page=page)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:observe() (select step) failed: {exc}"

    if not obs_select.data:
        return f"ERROR:dropdown opened but no option matching '{value}' was found"

    try:
        select_result = await sh.act(obs_select.data[0], page=page)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR:act() (select step) failed: {exc}"

    if not select_result.data.success:
        return f"ERROR:dropdown opened but selecting '{value}' failed: {select_result.data.message}"

    return select_result.data.action_description


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

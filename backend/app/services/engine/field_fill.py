"""
Shared textbox-fill helper for Tier 0 (tier0_harvest.py) and Tier 1
(tier1_map.py, including its repair pass). Real, live-caught bug this
exists to fix: Figma's Greenhouse "Location (City)" field was flagged
invalid by the ATS on submit in two consecutive live runs, despite the
box visibly showing the right text both times (once from Tier 0's first
pass, once from Tier 1's repair pass) — the SAME failure both times, from
two different tiers, means it isn't a mapping/value problem, it's the
FILL MECHANISM itself.

Root cause: a plain `locator.fill()` sets the input's DOM value directly
via CDP, without firing the per-keystroke input/keydown events a real
typeahead widget listens for. Greenhouse's city field is commonly backed
by exactly such a widget (a Google-Places-style autocomplete) — its own
"a real place was selected" state never gets set, so the ATS's client-side
validation still sees the field as unanswered even though it looks filled.

Fix: after clearing, re-type the value character-by-character (fires real
events) via `.type()`, then select the first suggestion if a listbox
opened because of it. A plain (non-autocomplete) textbox has no such
listbox — nothing else happens, and it ends up with the same value either
way, so this is safe as the default fill path rather than only for
fields known in advance to be autocomplete-backed (there's no reliable
way to tell from the accessibility tree alone; both render as a plain
`textbox` role).
"""

_SUGGESTION_SELECTOR = (
    '[role="option"], li[role="option"], .pac-item, [data-testid*="option" i]'
)
_SUGGESTION_WAIT_MS = 400


async def fill_textbox(page, xpath: str, value: str) -> None:
    locator = page.locator(xpath)
    await locator.fill("")
    await locator.type(value, delay=20)
    await page.wait_for_timeout(_SUGGESTION_WAIT_MS)

    suggestion = page.locator(_SUGGESTION_SELECTOR).first()
    try:
        if not await suggestion.is_visible():
            return
        # Real regression this guards against: clicking the first visible
        # [role="option"]-shaped element ANYWHERE on the page is unsafe —
        # if some unrelated dropdown/listbox happens to be open elsewhere
        # at the same moment (e.g. a previous field's widget that hasn't
        # closed yet), this could mis-click it instead of the actual
        # autocomplete suggestion THIS textbox opened. Only click if the
        # suggestion's own text plausibly matches what was just typed.
        text = await suggestion.inner_text()
        if value.strip().lower() in (text or "").lower():
            await suggestion.click()
    except Exception:  # noqa: BLE001
        # Best-effort only — a plain textbox with no such widget, or one
        # whose suggestion selector doesn't match ours, still has the
        # typed value from above; nothing to recover from here.
        pass

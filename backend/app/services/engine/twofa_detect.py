"""
2FA detection. Deterministic, no LLM — same philosophy as Tier 0: the
accessibility tree's text is enough, no page.evaluate() or DOM attribute
access needed. Per the Day-4 scope correction this is the ONLY thing that
still triggers needs_input; everything else (form-fill, CAPTCHA, submit) is
now fully automated.

Because a match here PAUSES the application and waits for a human
indefinitely, a false positive is expensive — it looks exactly like a
freeze from the UI, and the per-profile lock means it also blocks every
later application for that profile. The original version scanned EVERY
line of the whole page tree, so any prose containing the trigger words
would strand a run: a security-role job description mentioning "two-factor
authentication", a privacy footer about "verification codes", a cookie
banner. Detection is therefore scoped to lines that are actual interactive
INPUT FIELDS or headings — the only places a real challenge can present
itself. Body prose is ignored.

No live-form confirmation of this exact pattern yet (unlike Tier 0's
textbox/combobox patterns, which were captured from a real form) — no 2FA
challenge was encountered during Day 1-4 live testing. Flagged in
FLAGGED.md rather than presented as proven.
"""

import re

_LABEL_PATTERN = re.compile(
    r"verification code|one[- ]time (?:passcode|code)|\bOTP\b|authenticator (?:app|code)|"
    r"security code|\b2FA\b|two[- ]factor",
    re.I,
)

# Same line shape Tier 0 parses (`[id] role: label`). Only these roles can
# BE a 2FA challenge: something the user types a code into, or the heading
# announcing it. Deliberately excludes StaticText/paragraph/link/listitem,
# which is where every false-positive source lives.
_CHALLENGE_LINE = re.compile(
    r"^\s*\[[\w-]+\]\s+"
    r"(?P<role>textbox|input|heading|dialog|alertdialog)\b[^:]*:\s*(?P<label>.+)$",
    re.I,
)


def detect_2fa(formatted_tree: str) -> bool:
    for line in formatted_tree.splitlines():
        m = _CHALLENGE_LINE.match(line)
        if m and _LABEL_PATTERN.search(m.group("label")):
            return True
    return False

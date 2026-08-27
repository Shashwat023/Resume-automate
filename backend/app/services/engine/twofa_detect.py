"""
2FA detection. Deterministic, no LLM — same philosophy as Tier 0: the
accessibility tree's text is enough, no page.evaluate() or DOM attribute
access needed. Per the Day-4 scope correction this is the ONLY thing that
still triggers needs_input; everything else (form-fill, CAPTCHA, submit) is
now fully automated.

Two independent signals, either one is sufficient:
  - a textbox labeled with common one-time-code phrasing
  - page-level heading/text naming the challenge explicitly

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


def detect_2fa(formatted_tree: str) -> bool:
    for line in formatted_tree.splitlines():
        if _LABEL_PATTERN.search(line):
            return True
    return False

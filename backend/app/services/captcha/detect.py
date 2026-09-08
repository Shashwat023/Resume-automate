"""
CAPTCHA detection. Deterministic, no LLM — scans the page's iframe sources
for the known reCAPTCHA/hCaptcha embed URL shapes, exactly the way a real
Greenhouse form renders one (confirmed live during Day 4 recon: an
invisible reCAPTCHA Enterprise iframe with the sitekey right there in the
`k=` query param — see PLAN.md). No DOM attribute access needed; the
sitekey is public by design (it identifies the site to Google/hCaptcha, not
a secret), so pulling it out of the iframe URL is the standard technique.
"""

import re
from dataclasses import dataclass

from stagehand import Page

# Both google.com/recaptcha and the recaptcha.net mirror are seen in
# practice (recaptcha.net exists specifically for regions where
# google.com is blocked). /api2/ is the classic form, /enterprise/ is the
# variant confirmed live on a real Greenhouse form.
_RECAPTCHA_IFRAME = re.compile(
    r"(?:google\.com|recaptcha\.net)/recaptcha/(?:api2|enterprise)/(?:anchor|bframe)\?.*[?&]k=([\w-]+)"
)
_HCAPTCHA_IFRAME = re.compile(r"hcaptcha\.com/captcha/v1/.*[?&]sitekey=([\w-]+)")


@dataclass
class CaptchaChallenge:
    kind: str  # "recaptcha" | "hcaptcha"
    sitekey: str
    enterprise: bool = False
    invisible: bool = False
    action: str | None = None


# Real bug this fixes: Enterprise reCAPTCHA binds every token to an
# `action` name the SITE'S OWN JS passes to `execute(sitekey, {action})`
# (e.g. "submit", "apply") — Google's server-side assessment compares it,
# and a missing/wrong action is grounds for rejection on its own,
# independent of anything else. That action isn't in the iframe URL; it
# only exists in the page's own inline JS, so it has to be scraped out of
# script text. Best-effort — falls back to None (2captcha's own default,
# "verify") if no matching call is found.
_ACTION_IN_JS = re.compile(
    r"""(?:grecaptcha(?:\.enterprise)?\.execute|execute)\s*\([^)]*action\s*:\s*['"]([\w/-]+)['"]"""
)


async def _extract_action(page: Page) -> str | None:
    scripts = await page.evaluate(
        "Array.from(document.scripts).map(s => s.textContent || '').join('\\n')"
    )
    m = _ACTION_IN_JS.search(scripts or "")
    return m.group(1) if m else None


async def detect_captcha(page: Page) -> CaptchaChallenge | None:
    iframe_srcs = await page.evaluate(
        "Array.from(document.querySelectorAll('iframe')).map(f => f.src)"
    )
    for src in iframe_srcs or []:
        m = _RECAPTCHA_IFRAME.search(src)
        if m:
            enterprise = "/enterprise/" in src
            invisible = "size=invisible" in src
            action = await _extract_action(page) if enterprise else None
            return CaptchaChallenge(
                kind="recaptcha",
                sitekey=m.group(1),
                enterprise=enterprise,
                invisible=invisible,
                action=action,
            )
        m = _HCAPTCHA_IFRAME.search(src)
        if m:
            return CaptchaChallenge(kind="hcaptcha", sitekey=m.group(1))
    return None

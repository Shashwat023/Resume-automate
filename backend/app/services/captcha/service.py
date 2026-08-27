"""
CAPTCHA orchestration: detect -> solve -> inject the token into the page,
one retry on failure. Kept separate from detect.py/solver.py so each stays
independently unit-testable (detection is pure regex over iframe URLs,
solving is a thin wrapper over the 2captcha SDK, this module is the glue
plus the one policy decision — what to do when solving fails twice).
"""

import json
from dataclasses import dataclass

from stagehand import Page

from app.core.config import get_settings
from app.services.captcha.detect import CaptchaChallenge, detect_captcha
from app.services.captcha.solver import CaptchaError, solve

settings = get_settings()

# Standard DOM response-field names both providers' own widget JS reads
# from on submit. Injecting here plus firing input/change is the common
# technique for headless-solved tokens — it's a best-effort, not a
# universal guarantee (a site with additional custom JS validation on top
# of the standard widget could still reject it). Flagged as a known
# boundary, same spirit as the scraper's WebSearch fallback.
_RESPONSE_FIELD = {
    "recaptcha": "g-recaptcha-response",
    "hcaptcha": "h-captcha-response",
}


@dataclass
class CaptchaOutcome:
    status: str  # "not_present" | "solved" | "no_key" | "failed_escalate" | "failed_hard"
    detail: str = ""


async def resolve_captcha(page: Page) -> CaptchaOutcome:
    challenge = await detect_captcha(page)
    if challenge is None:
        return CaptchaOutcome(status="not_present")

    if not settings.twocaptcha_api_key:
        return CaptchaOutcome(
            status="no_key",
            detail=f"{challenge.kind} detected but TWOCAPTCHA_API_KEY is not configured",
        )

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            token = await solve(challenge, page.url)
            await _inject_token(page, challenge, token)
            return CaptchaOutcome(status="solved", detail=challenge.kind)
        except CaptchaError as exc:
            last_error = exc

    status = "failed_escalate" if settings.captcha_failure_escalates else "failed_hard"
    return CaptchaOutcome(status=status, detail=str(last_error))


async def _inject_token(page: Page, challenge: CaptchaChallenge, token: str) -> None:
    field_name = _RESPONSE_FIELD[challenge.kind]
    await page.evaluate(
        f"""(() => {{
            const token = {json.dumps(token)};
            let fields = document.querySelectorAll('[name="{field_name}"]');
            if (fields.length === 0) {{
                // Some widgets render the response field lazily; create
                // the standard one if the site's own JS hasn't yet.
                const el = document.createElement('textarea');
                el.name = '{field_name}';
                el.id = '{field_name}';
                el.style.display = 'none';
                document.body.appendChild(el);
                fields = [el];
            }}
            fields.forEach(el => {{
                el.value = token;
                el.innerHTML = token;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }});
            return fields.length;
        }})()"""
    )

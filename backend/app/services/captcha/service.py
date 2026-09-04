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
            # Page.url is an ASYNC METHOD on Stagehand's Page, not a plain
            # property (`async def url(self) -> str`) — a real bug this
            # fixed: `page.url` alone evaluates to the bound method object
            # itself, not a string, which 2captcha's API correctly rejected
            # as an invalid page URL (ApiException: ERROR_PAGEURL), caught
            # live during Day 5 verification.
            token = await solve(challenge, await page.url())
            await _inject_token(page, challenge, token)
            return CaptchaOutcome(status="solved", detail=challenge.kind)
        except CaptchaError as exc:
            last_error = exc

    status = "failed_escalate" if settings.captcha_failure_escalates else "failed_hard"
    return CaptchaOutcome(status=status, detail=str(last_error))


async def _inject_token(page: Page, challenge: CaptchaChallenge, token: str) -> None:
    """
    Real bug found live: writing the solved token into the hidden
    `g-recaptcha-response` textarea (below) is the standard technique for
    a CLASSIC visible reCAPTCHA v2 checkbox — the site's own JS typically
    polls or reads that field on submit. It does NOT work for an
    invisible/Enterprise widget (confirmed live: Anthropic's Greenhouse
    form rejected a real, successfully-2captcha-solved token with "Please
    complete the reCAPTCHA and resubmit your application"). An invisible
    widget's "has the user completed the challenge" state lives in
    Google's own JS, set only when ITS registered callback fires — which
    normally happens only after a real widget interaction. Writing to the
    DOM field alone never touches that internal state, so the site's own
    submit-gate still thinks nothing happened.

    Fix: ALSO locate the widget's real callback via `___grecaptcha_cfg`
    (the internal registry `grecaptcha`/`grecaptcha.enterprise` both share
    — Enterprise is built on the same client-registration mechanism) and
    invoke it directly with the token, exactly as Google's own widget
    would after a real solve. This is a best-effort technique reverse
    engineered from Google's own (versioned, lightly obfuscated) internal
    structure — not officially documented, so kept as an ADDITION to the
    DOM-field write, never a replacement, since a classic non-Enterprise
    widget may still only need the field.
    """
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

            // Invisible/Enterprise fallback: find and invoke the widget's
            // own registered callback so Google's internal "solved" state
            // actually gets set, not just the DOM mirror of it.
            let callbacksInvoked = 0;
            try {{
                const cfg = window.___grecaptcha_cfg;
                if (cfg && cfg.clients) {{
                    for (const client of Object.values(cfg.clients)) {{
                        // The callback lives at an unpredictable, versioned
                        // nesting depth inside each client object — walk
                        // every nested object looking for a function
                        // property named 'callback' (v2) or found under a
                        // 'promise-callback'-shaped key (enterprise/v3),
                        // rather than hardcoding a specific path that
                        // breaks on the next Google API revision.
                        const seen = new Set();
                        const stack = [client];
                        while (stack.length) {{
                            const obj = stack.pop();
                            if (!obj || typeof obj !== 'object' || seen.has(obj)) continue;
                            seen.add(obj);
                            for (const [key, value] of Object.entries(obj)) {{
                                if (typeof value === 'function' && /callback/i.test(key)) {{
                                    try {{
                                        value(token);
                                        callbacksInvoked++;
                                    }} catch (e) {{ /* try the next candidate */ }}
                                }} else if (value && typeof value === 'object') {{
                                    stack.push(value);
                                }}
                            }}
                        }}
                    }}
                }}
            }} catch (e) {{ /* best-effort only — DOM field write above still stands */ }}

            return {{ fieldsFilled: fields.length, callbacksInvoked }};
        }})()"""
    )

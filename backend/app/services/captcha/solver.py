"""
2captcha client. The `2captcha-python` package is synchronous (blocking
HTTP + polling sleep internally) — run off the event loop via
asyncio.to_thread rather than blocking the whole automation engine while
2captcha's workers solve the challenge (can take up to its 600s default
timeout).
"""

import asyncio

from twocaptcha import TwoCaptcha
from twocaptcha.solver import SolverExceptions

from app.core.config import get_settings
from app.services.captcha.detect import CaptchaChallenge

settings = get_settings()


class CaptchaError(Exception):
    pass


def _client() -> TwoCaptcha:
    if not settings.twocaptcha_api_key:
        raise CaptchaError("TWOCAPTCHA_API_KEY is not configured")
    return TwoCaptcha(settings.twocaptcha_api_key)


async def solve(challenge: CaptchaChallenge, page_url: str) -> str:
    """Returns the solved token (the value to inject into the page)."""
    solver = _client()
    try:
        if challenge.kind == "recaptcha":
            result = await asyncio.to_thread(
                solver.recaptcha,
                sitekey=challenge.sitekey,
                url=page_url,
                enterprise=1 if challenge.enterprise else 0,
                invisible=1 if challenge.invisible else 0,
            )
        elif challenge.kind == "hcaptcha":
            result = await asyncio.to_thread(
                solver.hcaptcha, sitekey=challenge.sitekey, url=page_url
            )
        else:
            raise CaptchaError(f"Unknown captcha kind: {challenge.kind}")
    except SolverExceptions as exc:
        raise CaptchaError(str(exc)) from exc

    return result["code"]

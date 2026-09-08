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

# Real, live-caught bug: `2captcha-python` has TWO SEPARATE exception
# hierarchies that happen to share the class name `ApiException` —
# `twocaptcha.exceptions.solver.ApiException` (a SolverExceptions
# subclass, what solver.py's own high-level methods raise) and
# `twocaptcha.exceptions.api.ApiException` (a bare `Exception` subclass,
# raised from the lower-level HTTP layer in api.py and left to propagate
# up through solver.py uncaught). A real failure — `ERROR_CAPTCHA_UNSOLVABLE`
# — came from the SECOND one. Since it isn't a SolverExceptions subclass,
# `except SolverExceptions` never caught it, so it propagated all the way
# to the top-level handler as a raw, unwrapped exception — completely
# bypassing `captcha_failure_escalates`'s human-handoff fallback the whole
# retry loop exists to provide. Caught explicitly here too.
from twocaptcha.exceptions.api import ApiException as _ApiLayerException
from twocaptcha.exceptions.api import NetworkException as _NetworkLayerException

from app.core.config import get_settings
from app.services.captcha.detect import CaptchaChallenge
from app.services.captcha.proxy import parse_proxy_url

settings = get_settings()


class CaptchaError(Exception):
    pass


def _client() -> TwoCaptcha:
    if not settings.twocaptcha_api_key:
        raise CaptchaError("TWOCAPTCHA_API_KEY is not configured")
    # The SDK's own defaults (recaptchaTimeout=600, defaultTimeout=120,
    # pollingInterval=10) were being inherited silently. Because the call
    # runs under `asyncio.to_thread` — which cannot be cancelled — those
    # defaults were a hard, unbreakable ~10-minute-per-attempt block on the
    # whole application, twice over with service.py's retry. Passed
    # explicitly so the bound is ours and is visible in config.
    return TwoCaptcha(
        settings.twocaptcha_api_key,
        defaultTimeout=settings.captcha_solve_timeout_seconds,
        recaptchaTimeout=settings.captcha_solve_timeout_seconds,
        pollingInterval=settings.captcha_polling_interval_seconds,
    )


async def solve(challenge: CaptchaChallenge, page_url: str) -> str:
    """Returns the solved token (the value to inject into the page)."""
    solver = _client()

    if challenge.kind == "recaptcha":
        extra_kwargs: dict = {}
        if challenge.action:
            extra_kwargs["action"] = challenge.action
        if settings.captcha_proxy_url:
            # Root-cause fix for a live rejection despite a "solved" token:
            # without this, 2captcha's worker solves from ITS OWN IP, but
            # our browser submits from a DIFFERENT one — Google's
            # Enterprise assessment sees the mismatch and rejects. Must be
            # the SAME proxy chrome_launcher.py routes the browser through.
            extra_kwargs["proxy"] = parse_proxy_url(
                settings.captcha_proxy_url
            ).twocaptcha_proxy
        call = asyncio.to_thread(
            solver.recaptcha,
            sitekey=challenge.sitekey,
            url=page_url,
            enterprise=1 if challenge.enterprise else 0,
            invisible=1 if challenge.invisible else 0,
            **extra_kwargs,
        )
    elif challenge.kind == "hcaptcha":
        call = asyncio.to_thread(
            solver.hcaptcha, sitekey=challenge.sitekey, url=page_url
        )
    else:
        raise CaptchaError(f"Unknown captcha kind: {challenge.kind}")

    try:
        # Backstop above the SDK's own (now explicit) polling timeout: that
        # timeout only bounds the POLLING loop, not a single wedged HTTP
        # request, which has no socket timeout of its own. Caveat kept
        # honest: `to_thread` can't actually be cancelled, so the worker
        # thread may outlive this — but the automation stops waiting on it
        # and the application fails cleanly instead of hanging forever,
        # which is the whole point (see FLAGGED.md #15).
        result = await asyncio.wait_for(
            call, timeout=settings.captcha_solve_timeout_seconds + 30
        )
    except TimeoutError as exc:
        raise CaptchaError(
            f"2captcha did not return a solution within "
            f"{settings.captcha_solve_timeout_seconds + 30}s"
        ) from exc
    except (SolverExceptions, _ApiLayerException, _NetworkLayerException) as exc:
        raise CaptchaError(str(exc)) from exc

    return result["code"]

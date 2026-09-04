import pytest

from app.services.captcha import solver
from app.services.captcha.detect import CaptchaChallenge
from app.services.captcha.solver import CaptchaError


async def test_solve_raises_when_no_api_key_configured(monkeypatch):
    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", None)
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")

    with pytest.raises(CaptchaError, match="not configured"):
        await solver.solve(challenge, "https://example.com")


async def test_solve_recaptcha_returns_token(monkeypatch):
    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def recaptcha(self, sitekey, url, enterprise, invisible):
            assert sitekey == "abc"
            assert enterprise == 1
            assert invisible == 1
            return {"code": "solved-token-123"}

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(
        kind="recaptcha", sitekey="abc", enterprise=True, invisible=True
    )

    token = await solver.solve(challenge, "https://example.com/apply")

    assert token == "solved-token-123"


async def test_solve_hcaptcha_returns_token(monkeypatch):
    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def hcaptcha(self, sitekey, url):
            return {"code": "hcaptcha-token"}

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(kind="hcaptcha", sitekey="xyz")

    token = await solver.solve(challenge, "https://example.com/apply")

    assert token == "hcaptcha-token"


async def test_solve_wraps_solver_exceptions(monkeypatch):
    from twocaptcha.solver import TimeoutException

    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def recaptcha(self, **kwargs):
            raise TimeoutException("timed out waiting for solution")

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")

    with pytest.raises(CaptchaError, match="timed out"):
        await solver.solve(challenge, "https://example.com")


async def test_solver_is_constructed_with_explicit_timeouts_not_sdk_defaults(monkeypatch):
    # The single biggest latent freeze before this fix: the SDK's own
    # defaults are recaptchaTimeout=600 / defaultTimeout=120, and the call
    # runs under `asyncio.to_thread`, which CANNOT be cancelled — so a slow
    # solve blocked the whole application for up to 10 minutes per attempt,
    # twice over (service.py retries once). Inheriting those defaults
    # silently is the bug; this asserts we pass our own.
    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")
    monkeypatch.setattr(solver.settings, "captcha_solve_timeout_seconds", 42)
    captured = {}

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            captured.update(kwargs)

        def hcaptcha(self, sitekey, url):
            return {"code": "t"}

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)

    await solver.solve(CaptchaChallenge(kind="hcaptcha", sitekey="x"), "https://e.com")

    assert captured["recaptchaTimeout"] == 42
    assert captured["defaultTimeout"] == 42


async def test_a_solve_that_never_returns_fails_instead_of_hanging(monkeypatch):
    # Backstop above the SDK's own polling timeout, which only bounds the
    # POLLING loop — not a single wedged HTTP request, which has no socket
    # timeout of its own.
    import time

    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")
    monkeypatch.setattr(solver.settings, "captcha_solve_timeout_seconds", -29)  # +30 => 1s

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def hcaptcha(self, sitekey, url):
            # 3s, not 30: `to_thread` can't be cancelled, so the orphaned
            # worker still runs to completion before the process exits — the
            # documented caveat of this backstop, visible right here.
            time.sleep(3)
            return {"code": "never"}

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)

    with pytest.raises(CaptchaError, match="did not return a solution"):
        await solver.solve(CaptchaChallenge(kind="hcaptcha", sitekey="x"), "https://e.com")


async def test_solve_passes_action_through_for_enterprise_challenges(monkeypatch):
    # Real bug this covers: Enterprise reCAPTCHA binds the token to an
    # `action` name — omitting it is grounds for Google to reject the
    # token independent of whether it was otherwise validly solved.
    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")
    captured = {}

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def recaptcha(self, **kwargs):
            captured.update(kwargs)
            return {"code": "t"}

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(
        kind="recaptcha", sitekey="abc", enterprise=True, action="submit"
    )

    await solver.solve(challenge, "https://example.com")

    assert captured["action"] == "submit"


async def test_solve_omits_action_kwarg_when_none_detected(monkeypatch):
    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")
    captured = {}

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def recaptcha(self, **kwargs):
            captured.update(kwargs)
            return {"code": "t"}

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")

    await solver.solve(challenge, "https://example.com")

    assert "action" not in captured


async def test_solve_routes_through_configured_proxy(monkeypatch):
    # Root-cause fix for a live rejection despite a "solved" token:
    # 2captcha must solve from the SAME IP the browser submits from.
    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")
    monkeypatch.setattr(
        solver.settings, "captcha_proxy_url", "http://user:pass@proxy.example.com:8080"
    )
    captured = {}

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def recaptcha(self, **kwargs):
            captured.update(kwargs)
            return {"code": "t"}

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")

    await solver.solve(challenge, "https://example.com")

    assert captured["proxy"] == {
        "type": "HTTP",
        "uri": "user:pass@proxy.example.com:8080",
    }


async def test_solve_omits_proxy_kwarg_when_not_configured(monkeypatch):
    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")
    monkeypatch.setattr(solver.settings, "captcha_proxy_url", None)
    captured = {}

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def recaptcha(self, **kwargs):
            captured.update(kwargs)
            return {"code": "t"}

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")

    await solver.solve(challenge, "https://example.com")

    assert "proxy" not in captured


async def test_api_layer_exception_is_also_wrapped_not_left_raw(monkeypatch):
    # Real bug found live: `2captcha-python` has TWO separate exception
    # hierarchies sharing the class name `ApiException` —
    # `twocaptcha.exceptions.solver.ApiException` (a SolverExceptions
    # subclass) and `twocaptcha.exceptions.api.ApiException` (a bare
    # Exception subclass, raised from the lower HTTP layer). A real
    # failure (`ERROR_CAPTCHA_UNSOLVABLE`) came from the second one and
    # was NOT caught by `except SolverExceptions`, so it propagated raw
    # all the way past the entire captcha_failure_escalates fallback.
    from twocaptcha.exceptions.api import ApiException as ApiLayerException

    monkeypatch.setattr(solver.settings, "twocaptcha_api_key", "fake-key")

    class FakeSolver:
        def __init__(self, api_key, **kwargs):
            pass

        def recaptcha(self, sitekey, url, enterprise, invisible):
            raise ApiLayerException("ERROR_CAPTCHA_UNSOLVABLE")

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")

    with pytest.raises(CaptchaError, match="ERROR_CAPTCHA_UNSOLVABLE"):
        await solver.solve(challenge, "https://example.com")

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
        def __init__(self, api_key):
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
        def __init__(self, api_key):
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
        def __init__(self, api_key):
            pass

        def recaptcha(self, **kwargs):
            raise TimeoutException("timed out waiting for solution")

    monkeypatch.setattr(solver, "TwoCaptcha", FakeSolver)
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")

    with pytest.raises(CaptchaError, match="timed out"):
        await solver.solve(challenge, "https://example.com")

from app.services.captcha import service
from app.services.captcha.detect import CaptchaChallenge
from app.services.captcha.solver import CaptchaError


class FakePage:
    def __init__(self, url="https://example.com/apply"):
        self.url = url
        self.evaluated: list[str] = []

    async def evaluate(self, expression):
        self.evaluated.append(expression)
        return None


async def test_no_captcha_present_is_a_noop(monkeypatch):
    monkeypatch.setattr(service, "detect_captcha", _fake_detect(None))
    page = FakePage()

    outcome = await service.resolve_captcha(page)

    assert outcome.status == "not_present"
    assert page.evaluated == []


async def test_captcha_present_but_no_key_configured(monkeypatch):
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")
    monkeypatch.setattr(service, "detect_captcha", _fake_detect(challenge))
    monkeypatch.setattr(service.settings, "twocaptcha_api_key", None)
    page = FakePage()

    outcome = await service.resolve_captcha(page)

    assert outcome.status == "no_key"
    assert page.evaluated == []


async def test_solved_captcha_injects_token(monkeypatch):
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")
    monkeypatch.setattr(service, "detect_captcha", _fake_detect(challenge))
    monkeypatch.setattr(service.settings, "twocaptcha_api_key", "fake-key")

    async def _fake_solve(challenge, page_url):
        return "the-solved-token"

    monkeypatch.setattr(service, "solve", _fake_solve)
    page = FakePage()

    outcome = await service.resolve_captcha(page)

    assert outcome.status == "solved"
    assert len(page.evaluated) == 1
    assert "the-solved-token" in page.evaluated[0]
    assert "g-recaptcha-response" in page.evaluated[0]


async def test_hcaptcha_injects_into_h_captcha_response_field(monkeypatch):
    challenge = CaptchaChallenge(kind="hcaptcha", sitekey="xyz")
    monkeypatch.setattr(service, "detect_captcha", _fake_detect(challenge))
    monkeypatch.setattr(service.settings, "twocaptcha_api_key", "fake-key")

    async def _fake_solve(challenge, page_url):
        return "hcaptcha-token"

    monkeypatch.setattr(service, "solve", _fake_solve)
    page = FakePage()

    outcome = await service.resolve_captcha(page)

    assert outcome.status == "solved"
    assert "h-captcha-response" in page.evaluated[0]


async def test_failure_retries_once_then_escalates_by_default(monkeypatch):
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")
    monkeypatch.setattr(service, "detect_captcha", _fake_detect(challenge))
    monkeypatch.setattr(service.settings, "twocaptcha_api_key", "fake-key")
    monkeypatch.setattr(service.settings, "captcha_failure_escalates", True)

    call_count = 0

    async def _fake_solve(challenge, page_url):
        nonlocal call_count
        call_count += 1
        raise CaptchaError("2captcha timed out")

    monkeypatch.setattr(service, "solve", _fake_solve)
    page = FakePage()

    outcome = await service.resolve_captcha(page)

    assert call_count == 2  # one retry
    assert outcome.status == "failed_escalate"
    assert "timed out" in outcome.detail


async def test_failure_hard_fails_when_escalation_disabled(monkeypatch):
    challenge = CaptchaChallenge(kind="recaptcha", sitekey="abc")
    monkeypatch.setattr(service, "detect_captcha", _fake_detect(challenge))
    monkeypatch.setattr(service.settings, "twocaptcha_api_key", "fake-key")
    monkeypatch.setattr(service.settings, "captcha_failure_escalates", False)

    async def _fake_solve(challenge, page_url):
        raise CaptchaError("balance too low")

    monkeypatch.setattr(service, "solve", _fake_solve)
    page = FakePage()

    outcome = await service.resolve_captcha(page)

    assert outcome.status == "failed_hard"


def _fake_detect(challenge):
    async def _detect(page):
        return challenge

    return _detect

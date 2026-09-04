from app.services.captcha.detect import detect_captcha


class FakePage:
    def __init__(self, iframe_srcs, url="https://example.com/apply"):
        self._iframe_srcs = iframe_srcs
        self.url = url

    async def evaluate(self, expression):
        return self._iframe_srcs


async def test_detects_recaptcha_enterprise_invisible():
    # Real iframe src captured live from Anthropic's Greenhouse form
    # (see PLAN.md Day 4 recon notes).
    page = FakePage(
        [
            "https://www.recaptcha.net/recaptcha/enterprise/anchor?ar=1&k=6LfmcbcpAAAAAChNTbhUShzUOAMj_wY9LQIvLFX0&co=aHR0cHM6Ly9qb2ItYm9hcmRzLmdyZWVuaG91c2UuaW8&size=invisible",
        ]
    )

    challenge = await detect_captcha(page)

    assert challenge is not None
    assert challenge.kind == "recaptcha"
    assert challenge.sitekey == "6LfmcbcpAAAAAChNTbhUShzUOAMj_wY9LQIvLFX0"
    assert challenge.enterprise is True
    assert challenge.invisible is True


async def test_detects_classic_recaptcha_v2():
    page = FakePage(
        [
            "https://www.google.com/recaptcha/api2/anchor?ar=1&k=6LdAbcdEAAAAABsitekey123&co=x",
        ]
    )

    challenge = await detect_captcha(page)

    assert challenge.kind == "recaptcha"
    assert challenge.enterprise is False
    assert challenge.invisible is False


async def test_detects_hcaptcha():
    page = FakePage(
        ["https://newassets.hcaptcha.com/captcha/v1/abc123/static/hcaptcha.html?sitekey=my-hcaptcha-sitekey&host=example.com"]
    )

    challenge = await detect_captcha(page)

    assert challenge.kind == "hcaptcha"
    assert challenge.sitekey == "my-hcaptcha-sitekey"


async def test_no_captcha_returns_none():
    page = FakePage([])
    assert await detect_captcha(page) is None


async def test_unrelated_iframes_are_ignored():
    page = FakePage(
        [
            "https://www.google.com/recaptcha/enterprise/anchor?ar=1&k=6LfmcbcpAAAAAChNTbhUShzUOAMj_wY9LQIvLFX0",
            "https://content.googleapis.com/static/proxy.html?usegapi=1",
        ]
    )

    # first matching iframe wins
    challenge = await detect_captcha(page)
    assert challenge.kind == "recaptcha"


async def test_evaluate_returning_none_does_not_crash():
    page = FakePage(None)
    assert await detect_captcha(page) is None

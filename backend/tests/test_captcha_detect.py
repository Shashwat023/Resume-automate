from app.services.captcha.detect import detect_captcha


class FakePage:
    def __init__(self, iframe_srcs, url="https://example.com/apply", scripts_text=""):
        self._iframe_srcs = iframe_srcs
        self.url = url
        self._scripts_text = scripts_text

    async def evaluate(self, expression):
        # Two different evaluate() calls now happen for an enterprise
        # match (iframe srcs, then the action-scraping script scan) —
        # route by what the expression actually asks for rather than
        # always returning the iframe fixture.
        if "scripts" in expression:
            return self._scripts_text
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


async def test_enterprise_challenge_extracts_action_from_page_js():
    # Real bug this covers: Enterprise reCAPTCHA binds the token to an
    # `action` name passed to execute() in the SITE'S OWN JS — a
    # missing/wrong action gets a token rejected independent of validity.
    page = FakePage(
        [
            "https://www.recaptcha.net/recaptcha/enterprise/anchor?ar=1&k=6LfmcbcpAAAAAChNTbhUShzUOAMj_wY9LQIvLFX0&size=invisible",
        ],
        scripts_text="grecaptcha.enterprise.execute('6Lfmcbcp...', {action: 'submit'}).then(...)",
    )

    challenge = await detect_captcha(page)

    assert challenge.action == "submit"


async def test_enterprise_challenge_with_no_action_in_js_falls_back_to_none():
    page = FakePage(
        [
            "https://www.recaptcha.net/recaptcha/enterprise/anchor?ar=1&k=6LfmcbcpAAAAAChNTbhUShzUOAMj_wY9LQIvLFX0&size=invisible",
        ],
        scripts_text="some unrelated inline script",
    )

    challenge = await detect_captcha(page)

    assert challenge.action is None


async def test_classic_v2_challenge_never_extracts_action():
    # Action-scraping is Enterprise-specific; a classic v2 checkbox has no
    # such concept, so the extra evaluate() call should not even happen.
    page = FakePage(
        [
            "https://www.google.com/recaptcha/api2/anchor?ar=1&k=6LdAbcdEAAAAABsitekey123&co=x",
        ],
        scripts_text="grecaptcha.enterprise.execute('x', {action: 'should_not_be_read'})",
    )

    challenge = await detect_captcha(page)

    assert challenge.action is None

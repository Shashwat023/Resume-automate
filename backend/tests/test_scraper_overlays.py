"""
Runs the scraper's real _DISMISS_OVERLAYS_JS in the Chrome-for-Testing build
against local pages, so the cookie-banner policy (always reject, never accept)
is tested in a browser and not just by reading the script.
"""
import os

import pytest

from app.core.config import get_settings
from app.services.scraper import sync_service

sync_api = pytest.importorskip("playwright.sync_api")

CHROME = get_settings().chrome_executable_path
pytestmark = pytest.mark.skipif(
    not os.path.exists(CHROME), reason="Chrome for Testing build not installed"
)

BOX = "position:fixed;bottom:0;left:0;width:420px;height:120px;background:#222;color:#fff"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True)
        yield b
        b.close()


def _run(browser, html):
    page = browser.new_page()
    try:
        page.set_content(html)
        result = page.evaluate(sync_service._DISMISS_OVERLAYS_JS)
        clicked = page.evaluate("window.__clicked || ''")
        return result, clicked, page
    except Exception:
        page.close()
        raise


def test_rejects_an_evidon_banner(browser):
    result, clicked, page = _run(browser, f"""
        <div id="_evidon_banner" class="evidon-banner" style="{BOX}">
          We use cookies to personalize your experience.
          <button onclick="window.__clicked='accept'">Accept</button>
          <button id="_evidon-decline-button" onclick="window.__clicked='decline'">Decline</button>
        </div>""")
    page.close()
    assert result == "rejected:#_evidon-decline-button"
    assert clicked == "decline"


def test_rejects_a_banner_from_a_platform_it_has_never_seen(browser):
    result, clicked, page = _run(browser, f"""
        <div id="x1" class="box" style="{BOX}">
          We use cookies on this site.
          <button class="b2" onclick="window.__clicked='accept'">Accept</button>
          <button class="b1" onclick="window.__clicked='decline'">Decline</button>
        </div>""")
    page.close()
    assert result == "rejected:Decline"
    assert clicked == "decline"


def test_hides_but_never_accepts_a_banner_with_no_reject_button(browser):
    result, clicked, page = _run(browser, f"""
        <div id="x1" class="box" style="{BOX}">
          We use cookies on this site.
          <button onclick="window.__clicked='accept'">Accept</button>
        </div>""")
    hidden = page.evaluate("getComputedStyle(document.getElementById('x1')).display")
    page.close()
    assert result.startswith("hid-consent")
    assert clicked == ""
    assert hidden == "none"


def test_leaves_a_decline_button_that_is_not_a_cookie_banner_alone(browser):
    result, clicked, page = _run(browser, """
        <main><p>You have been invited to join the team.</p>
        <button onclick="window.__clicked='decline'">Decline</button></main>""")
    page.close()
    assert result == ""
    assert clicked == ""


def _next_link(browser, html, url="https://careers.example.com/jobs/page/1"):
    page = browser.new_page()
    try:
        page.route("**/*", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.goto(url)
        return page.evaluate(sync_service._NEXT_LINK_JS)
    finally:
        page.close()


def test_next_link_finds_a_plain_next_page_link(browser):
    url = _next_link(browser, """
        <nav><a href="/jobs/page/1">1</a><a href="/jobs/page/2">2</a>
        <a href="/jobs/page/2">Next Page</a><a href="/jobs/page/207">Last page</a></nav>""")
    assert url == "https://careers.example.com/jobs/page/2"


def test_next_link_ignores_a_next_button_and_unrelated_links(browser):
    assert _next_link(browser, """
        <button aria-label="Next">›</button>
        <a href="/blog/next-steps">Next steps for your career</a>
        <a href="https://other.example.org/jobs/2">Next</a>
        <a href="#">Next</a>""") is None


def test_still_rejects_a_known_platform_by_its_own_button(browser):
    result, clicked, page = _run(browser, f"""
        <div id="onetrust-banner-sdk" style="{BOX}">
          We use cookies.
          <button id="onetrust-reject-all-handler" onclick="window.__clicked='decline'">Reject All</button>
        </div>""")
    page.close()
    assert result == "rejected:#onetrust-reject-all-handler"
    assert clicked == "decline"


def test_next_link_accepts_a_next_label_with_arrows(browser):
    url = _next_link(browser, """
        <a href="/en_US/careers/SearchJobs/?jobOffset=25">Next &gt;&gt;</a>""")
    assert url == "https://careers.example.com/en_US/careers/SearchJobs/?jobOffset=25"

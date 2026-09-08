import httpx
import pytest

from app.services.browser import chrome_launcher


_RealAsyncClient = httpx.AsyncClient


def _client_factory(handler):
    def factory(*args, **kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(handler))

    return factory


async def test_discover_extension_id_finds_the_service_worker_target(monkeypatch):
    # Real, live-caught technique: Stagehand's own error message for a
    # Chrome build without Extensions.loadUnpacked support literally says
    # "Launch with --load-extension and connect using extension_id
    # instead." An unpacked extension loaded that way registers a
    # service-worker target whose URL is `chrome-extension://<id>/...` —
    # this discovers that id from Chrome's own DevTools HTTP API instead
    # of requiring a manual chrome://extensions lookup.
    def handler(request):
        assert request.url.path == "/json/list"
        return httpx.Response(
            200,
            json=[
                {"type": "page", "url": "https://example.com"},
                {
                    "type": "service_worker",
                    "url": "chrome-extension://abcdefghijklmnop/service-worker.js",
                },
            ],
        )

    monkeypatch.setattr(chrome_launcher.httpx, "AsyncClient", _client_factory(handler))

    extension_id = await chrome_launcher._discover_extension_id(9999)

    assert extension_id == "abcdefghijklmnop"


async def test_discover_extension_id_ignores_non_service_worker_targets(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            # First poll: extension hasn't registered yet.
            return httpx.Response(
                200, json=[{"type": "page", "url": "https://example.com"}]
            )
        return httpx.Response(
            200,
            json=[
                {
                    "type": "service_worker",
                    "url": "chrome-extension://readyid1234567890/service-worker.js",
                }
            ],
        )

    monkeypatch.setattr(chrome_launcher.httpx, "AsyncClient", _client_factory(handler))
    monkeypatch.setattr(chrome_launcher, "_EXTENSION_POLL_INTERVAL_SECONDS", 0)

    extension_id = await chrome_launcher._discover_extension_id(9999)

    assert extension_id == "readyid1234567890"
    assert calls["n"] >= 2  # actually polled, not just took the first response


async def test_discover_extension_id_times_out_if_extension_never_registers(
    monkeypatch,
):
    def handler(request):
        return httpx.Response(
            200, json=[{"type": "page", "url": "https://example.com"}]
        )

    monkeypatch.setattr(chrome_launcher.httpx, "AsyncClient", _client_factory(handler))
    monkeypatch.setattr(chrome_launcher, "_EXTENSION_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(chrome_launcher, "_EXTENSION_READY_TIMEOUT_SECONDS", 0)

    with pytest.raises(RuntimeError, match="never registered"):
        await chrome_launcher._discover_extension_id(9999)


def test_find_real_chrome_path_prefers_explicit_setting(monkeypatch):
    monkeypatch.setattr(
        chrome_launcher.settings, "real_chrome_executable_path", "C:/custom/chrome.exe"
    )
    assert chrome_launcher._find_real_chrome_path() == "C:/custom/chrome.exe"


def test_find_real_chrome_path_raises_a_clear_error_when_not_found(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(chrome_launcher.settings, "real_chrome_executable_path", None)
    monkeypatch.setattr(chrome_launcher.sys, "platform", "win32")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "nonexistent1"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "nonexistent2"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "nonexistent3"))

    with pytest.raises(RuntimeError, match="auto-detect"):
        chrome_launcher._find_real_chrome_path()


class _FakeBrowser:
    def __init__(self, closed=False):
        self._closed = closed

    @property
    def closed(self):
        return self._closed


async def test_get_or_launch_reuses_the_cached_session_while_still_open(monkeypatch):
    # This is what lets live_view_service.py attach a second, independent
    # CDP client to an application's browser WHILE it's still actively
    # running (mid-pause, 2FA, manual-field escalation) — get_or_launch
    # must return the SAME session, not relaunch, as long as it's open.
    chrome_launcher._sessions.clear()

    launch_calls = []
    browser = _FakeBrowser(closed=False)

    async def _fake_launch(**kwargs):
        launch_calls.append(kwargs)
        return browser

    async def _fake_discover_extension_id(port):
        return "abcextensionid"

    monkeypatch.setattr(chrome_launcher.local_browser, "launch", _fake_launch)
    monkeypatch.setattr(
        chrome_launcher, "_discover_extension_id", _fake_discover_extension_id
    )

    first_session = await chrome_launcher.get_or_launch("1")
    second_session = await chrome_launcher.get_or_launch("1")

    assert second_session is first_session
    assert len(launch_calls) == 1

    chrome_launcher._sessions.clear()


async def test_get_or_launch_relaunches_fresh_once_the_session_is_closed(monkeypatch):
    # Real, live-caught constraint, confirmed against the Stagehand
    # extension's own bundled service-worker JS: its runtime state
    # machine is `created -> initialized -> closed`, ONE WAY, with no
    # reset — a second Stagehand.create() against the SAME long-lived
    # extension instance always fails with "Stagehand has already been
    # initialized", reproduced live on the very next application for a
    # profile, success or failure of the prior one alike. A brand-new
    # Chrome process (fresh extension load) is the only way to get a
    # fresh "created" state — runner.py's run_application now closes its
    # own session unconditionally at the end of every application for
    # exactly this reason. Once closed, get_or_launch must relaunch.
    chrome_launcher._sessions.clear()

    launch_calls = []
    first_browser = _FakeBrowser(closed=False)
    second_browser = _FakeBrowser(closed=False)
    browsers = iter([first_browser, second_browser])

    async def _fake_launch(**kwargs):
        launch_calls.append(kwargs)
        return next(browsers)

    async def _fake_discover_extension_id(port):
        return "abcextensionid"

    monkeypatch.setattr(chrome_launcher.local_browser, "launch", _fake_launch)
    monkeypatch.setattr(
        chrome_launcher, "_discover_extension_id", _fake_discover_extension_id
    )

    first_session = await chrome_launcher.get_or_launch("1")
    first_browser._closed = True  # simulate close_session() having run

    second_session = await chrome_launcher.get_or_launch("1")

    assert second_session is not first_session
    assert second_session.browser is second_browser
    assert len(launch_calls) == 2

    chrome_launcher._sessions.clear()

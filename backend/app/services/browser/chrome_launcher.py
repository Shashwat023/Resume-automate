"""
Chrome launcher: WE own the browser's lifecycle (port, profile dir,
keep_alive), so a second independent CDP client (the live-view proxy) can
attach to the exact same running browser, and the browser survives
pause/resume regardless of what Stagehand itself is doing. Two CDP clients,
one Chrome — see PLAN.md "The key trick".

Two launch paths, selected by settings.use_real_chrome:

- Default (False): goes through stagehand.local_browser.launch() against a
  "Chrome for Testing" build, which Stagehand v4's local mode depends on to
  bootstrap its companion extension via the CDP `Extensions.loadUnpacked`
  method — a method NOT supported by consumer Chrome Stable (confirmed
  empirically, Day-1 spike). local_browser.launch() handles that bootstrap
  correctly instead of us reimplementing it.

- Opt-in (True): real, live-caught bug — a real submission was rejected
  with "Please complete the reCAPTCHA and resubmit your application"
  despite a genuinely 2captcha-solved token; manual testing of the SAME
  form showed no captcha challenge at all, meaning Google's risk-based
  (not puzzle-based) reCAPTCHA Enterprise scored the automated session too
  low to accept ANY token. A fresh "Chrome for Testing" profile with
  `navigator.webdriver=true` and zero browsing history is plausibly a
  large part of that signal. This path launches REAL consumer Chrome
  ourselves (`--load-extension` is a normal Chrome command-line flag that
  works on any build — unlike the CDP method above) against a PERSISTENT
  profile directory that accumulates real history/cookies across runs,
  discovers the resulting extension id from its own CDP target list (no
  manual chrome://extensions step needed), then has Stagehand `connect()`
  to that already-running browser instead of launching+bootstrapping a
  throwaway instance itself.
"""

import asyncio
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from stagehand import StagehandBrowser, local_browser

from app.core.config import get_settings
from app.services.captcha.proxy import parse_proxy_url

settings = get_settings()

_sessions: dict[str, "ChromeSession"] = {}

_EXTENSION_READY_TIMEOUT_SECONDS = 30
_EXTENSION_POLL_INTERVAL_SECONDS = 0.5


@dataclass
class ChromeSession:
    profile_key: str
    port: int
    browser: (
        StagehandBrowser  # pass this into Stagehand.create(browser=...) for automation
    )
    process: subprocess.Popen | None = None  # only set for the real-Chrome path
    extension_id: str | None = None

    @property
    def cdp_url(self) -> str:
        return f"http://localhost:{self.port}"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _find_real_chrome_path() -> str:
    if settings.real_chrome_executable_path:
        return settings.real_chrome_executable_path

    if sys.platform == "win32":
        import os

        roots = filter(
            None,
            (
                os.environ.get("PROGRAMFILES"),
                os.environ.get("PROGRAMFILES(X86)"),
                os.environ.get("LOCALAPPDATA"),
            ),
        )
        candidates = [
            str(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
            for root in roots
        ]
    elif sys.platform == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        candidates = ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]

    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate

    raise RuntimeError(
        "Could not auto-detect a real Chrome install for use_real_chrome=True. "
        "Set REAL_CHROME_EXECUTABLE_PATH explicitly."
    )


def _extension_directory() -> str:
    from stagehand.extension_assets import extension_directory

    return str(extension_directory())


async def _wait_for_cdp_ready(port: int) -> None:
    deadline = asyncio.get_event_loop().time() + _EXTENSION_READY_TIMEOUT_SECONDS
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(
                    f"http://localhost:{port}/json/version", timeout=2
                )
                if resp.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if asyncio.get_event_loop().time() >= deadline:
                raise RuntimeError(
                    f"Real Chrome did not expose its CDP endpoint on port {port} "
                    f"within {_EXTENSION_READY_TIMEOUT_SECONDS}s"
                )
            await asyncio.sleep(_EXTENSION_POLL_INTERVAL_SECONDS)


async def _discover_extension_id(port: int) -> str:
    """
    Confirmed live (Stagehand's own cdp_client.py source, see module
    docstring): a Chrome build that doesn't support `Extensions.loadUnpacked`
    is meant to be launched with `--load-extension=<dir>` instead, then
    connected to via a KNOWN extension_id — Stagehand's own error message
    for this exact case literally says "Launch with --load-extension and
    connect using extension_id instead." We discover that id ourselves via
    Chrome's DevTools HTTP API rather than requiring a manual
    chrome://extensions lookup: an unpacked extension loaded via
    --load-extension registers a service-worker target whose URL is
    `chrome-extension://<id>/...` — poll `/json/list` for it.
    """
    deadline = asyncio.get_event_loop().time() + _EXTENSION_READY_TIMEOUT_SECONDS
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(f"http://localhost:{port}/json/list", timeout=2)
                if resp.status_code == 200:
                    for target in resp.json():
                        url = target.get("url", "")
                        if target.get("type") == "service_worker" and url.startswith(
                            "chrome-extension://"
                        ):
                            extension_id, _, rest = url.removeprefix(
                                "chrome-extension://"
                            ).partition("/")
                            if extension_id and rest:
                                return extension_id
            except httpx.HTTPError:
                pass
            if asyncio.get_event_loop().time() >= deadline:
                raise RuntimeError(
                    f"Stagehand's companion extension never registered a service "
                    f"worker within {_EXTENSION_READY_TIMEOUT_SECONDS}s — "
                    f"--load-extension may have been rejected by this Chrome build"
                )
            await asyncio.sleep(_EXTENSION_POLL_INTERVAL_SECONDS)


async def _launch_real_chrome_and_connect(profile_key: str, port: int) -> ChromeSession:
    chrome_path = _find_real_chrome_path()
    user_data_dir = settings.real_chrome_profiles_dir / profile_key
    user_data_dir.mkdir(parents=True, exist_ok=True)

    process = subprocess.Popen(
        [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            f"--load-extension={_extension_directory()}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        await _wait_for_cdp_ready(port)
        extension_id = await _discover_extension_id(port)
        browser = await local_browser.connect(
            cdp_url=f"http://localhost:{port}", extension_id=extension_id
        )
    except BaseException:
        process.terminate()
        raise

    return ChromeSession(
        profile_key=profile_key,
        port=port,
        browser=browser,
        process=process,
        extension_id=extension_id,
    )


async def get_or_launch(profile_key: str) -> ChromeSession:
    """
    profile_key is typically f"{profile_id}". Returns the SAME cached
    session while one is live and not yet closed — this is what lets
    live_view_service.py attach a second, independent CDP client to an
    application's browser WHILE it's still actively running (mid-pause,
    2FA, manual-field escalation), and what lets one application's own
    internal flow keep reusing its one browser throughout its lifetime.
    Falls through to a genuinely fresh launch once the cached session is
    closed.

    Real, live-caught constraint, confirmed against the Stagehand
    extension's own bundled service-worker JS: its runtime state machine
    is `created -> initialized -> closed`, ONE WAY, with no reset. A
    SECOND `Stagehand.create()` against the SAME long-lived extension
    instance always fails with "Stagehand has already been initialized"
    — reconnecting via a brand-new, unclaimed `StagehandBrowser` wrapper
    was tried first (see FLAGGED.md #26) and does NOT help, since the
    constraint lives in the extension's own persistent JS state, not in
    which Python wrapper object is attached to it. The extension only
    resets to "created" when the Chrome PROCESS itself restarts (a fresh
    extension load). This is exactly why `run_application` (runner.py)
    now unconditionally closes its own session at the end of every
    application, regardless of outcome — see that function's own
    comment — so THIS function's "reuse while not closed" check
    correctly falls through to a fresh launch for the next application,
    rather than ever handing back an extension that can never initialize
    again. Cookie/login continuity across a profile's applications comes
    from reusing the same `user_data_dir` below, not from keeping one
    Chrome process alive across different applications.
    """
    existing = _sessions.get(profile_key)
    if existing is not None and not existing.browser.closed:
        return existing

    port = _free_port()

    if settings.use_real_chrome:
        session = await _launch_real_chrome_and_connect(profile_key, port)
    else:
        user_data_dir = settings.chrome_profiles_dir / profile_key
        user_data_dir.mkdir(parents=True, exist_ok=True)

        proxy_kwargs: dict = {}
        if settings.captcha_proxy_url:
            # Same proxy the 2captcha solve call uses (solver.py) — so the
            # IP that solves the challenge matches the IP that submits the
            # token. See config.py's captcha_proxy_url docstring.
            proxy = parse_proxy_url(settings.captcha_proxy_url)
            proxy_kwargs = {
                "proxy_server": proxy.server_url,
                "proxy_username": proxy.username,
                "proxy_password": proxy.password,
            }

        browser = await local_browser.launch(
            executable_path=settings.chrome_executable_path,
            port=port,
            user_data_dir=str(user_data_dir),
            headless=False,
            # Default False per user direction (was True). Note: `sh.close()`
            # (called at the end of every application, see runner.py) never
            # touches this flag either way — it only detaches the Stagehand
            # wrapper, never the underlying browser/Chrome process — so this
            # change alone does NOT stop Chrome processes from piling up;
            # nothing currently calls `chrome_launcher.close_session()`
            # (the one path that would actually honor this and terminate
            # the process). Flagged in FLAGGED.md as the real remaining gap.
            keep_alive=False,
            # Layer 2 (best-effort bot-detection mitigation, not a
            # guaranteed bypass — see FLAGGED.md): removes the
            # `navigator.webdriver=true` signal Chrome sets under CDP
            # control. The real fix for risk-based reCAPTCHA Enterprise
            # scoring is Layer 1's proxy (captcha_proxy_url) matching the
            # browser's egress IP to the solving IP — this flag is a
            # cheap, low-maintenance supplement to that, not a
            # replacement. The persistent per-profile user_data_dir above
            # already accumulates real cookies/history across runs.
            args=["--disable-blink-features=AutomationControlled"],
            **proxy_kwargs,
        )
        # Discovered the same way as the real-Chrome `--load-extension`
        # path above (Stagehand's own `Extensions.loadUnpacked` bootstrap
        # registers a service worker the same way) — not currently reused
        # anywhere since every application gets a fresh Chrome process
        # (see this function's own docstring), but harmless to keep on
        # the session for now.
        extension_id = await _discover_extension_id(port)
        session = ChromeSession(
            profile_key=profile_key,
            port=port,
            browser=browser,
            extension_id=extension_id,
        )

    _sessions[profile_key] = session
    return session


async def close_session(profile_key: str) -> None:
    session = _sessions.pop(profile_key, None)
    if session is None:
        return
    await session.browser.close()
    if session.process is not None:
        session.process.terminate()

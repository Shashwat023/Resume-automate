"""
Chrome launcher: WE own the browser's lifecycle (port, profile dir,
keep_alive), so a second independent CDP client (the live-view proxy) can
attach to the exact same running browser, and the browser survives
pause/resume regardless of what Stagehand itself is doing. Two CDP clients,
one Chrome — see PLAN.md "The key trick".

Mechanically this goes through stagehand.local_browser.launch() rather than
a raw subprocess.Popen, because Stagehand v4's local mode depends on
bootstrapping a companion browser extension via the CDP `Extensions.loadUnpacked`
method — a method NOT supported by consumer Chrome Stable (confirmed
empirically in the Day-1 spike), only by "Chrome for Testing" builds. We
still control port/user_data_dir/keep_alive, which is what the architecture
actually needs; local_browser.launch() just handles the extension bootstrap
correctly instead of us reimplementing it.
"""

import socket
from dataclasses import dataclass

from stagehand import StagehandBrowser, local_browser

from app.core.config import get_settings

settings = get_settings()

_sessions: dict[str, "ChromeSession"] = {}


@dataclass
class ChromeSession:
    profile_key: str
    port: int
    browser: (
        StagehandBrowser  # pass this into Stagehand.create(browser=...) for automation
    )

    @property
    def cdp_url(self) -> str:
        return f"http://localhost:{self.port}"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


async def get_or_launch(profile_key: str) -> ChromeSession:
    """
    profile_key is typically f"{profile_id}", so cookies/login state persist
    across a profile's applications and across pause/resume.
    """
    existing = _sessions.get(profile_key)
    if existing is not None and not existing.browser.closed:
        return existing

    user_data_dir = settings.chrome_profiles_dir / profile_key
    user_data_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()

    browser = await local_browser.launch(
        executable_path=settings.chrome_executable_path,
        port=port,
        user_data_dir=str(user_data_dir),
        headless=False,
        keep_alive=True,  # survives Stagehand.close() / pause
    )

    session = ChromeSession(profile_key=profile_key, port=port, browser=browser)
    _sessions[profile_key] = session
    return session


async def close_session(profile_key: str) -> None:
    session = _sessions.pop(profile_key, None)
    if session is None:
        return
    await session.browser.close()

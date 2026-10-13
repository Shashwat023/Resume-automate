import asyncio
import json
import re

import pytest

from app.services.browser import chrome_launcher


def _write_prefs(profile_dir, **profile):
    prefs = profile_dir / "Default" / "Preferences"
    prefs.parent.mkdir(parents=True)
    prefs.write_text(json.dumps({"profile": profile, "other": 1}), encoding="utf-8")
    return prefs


def test_ephemeral_profile_is_wiped_so_no_stale_state_survives(tmp_path):
    profile_dir = tmp_path / "scraper"
    _write_prefs(profile_dir, exit_type="Crashed")
    (profile_dir / "Default" / "Cookies").write_text("stale", encoding="utf-8")

    chrome_launcher._prepare_profile_dir(profile_dir, ephemeral=True)

    assert profile_dir.is_dir()
    assert list(profile_dir.iterdir()) == []


def test_persistent_profile_keeps_cookies_but_is_marked_cleanly_exited(tmp_path):
    profile_dir = tmp_path / "42"
    prefs = _write_prefs(profile_dir, exit_type="Crashed", exited_cleanly=False)
    cookies = profile_dir / "Default" / "Cookies"
    cookies.write_text("login", encoding="utf-8")

    chrome_launcher._prepare_profile_dir(profile_dir, ephemeral=False)

    data = json.loads(prefs.read_text(encoding="utf-8"))
    assert data["profile"]["exit_type"] == "Normal"
    assert data["profile"]["exited_cleanly"] is True
    assert data["other"] == 1
    assert cookies.read_text(encoding="utf-8") == "login"


def test_missing_profile_dir_is_created_without_error(tmp_path):
    profile_dir = tmp_path / "new"

    chrome_launcher._prepare_profile_dir(profile_dir, ephemeral=False)

    assert profile_dir.is_dir()


def test_only_the_scraper_profile_is_ephemeral():
    assert chrome_launcher.EPHEMERAL_PROFILE_KEYS == {"scraper"}


def test_profile_cmdline_pattern_does_not_match_profile_prefixes(tmp_path):
    profile = tmp_path / ".chrome-profiles" / "1"
    pattern = chrome_launcher.profile_cmdline_pattern(profile)

    assert re.search(pattern, f"--user-data-dir={profile}")
    assert re.search(pattern, f'"--user-data-dir={profile}"')
    assert re.search(pattern, f"--user-data-dir={profile} --foo")
    assert not re.search(pattern, f"--user-data-dir={profile}0")
    assert not re.search(pattern, f"--user-data-dir={profile}00")
    assert "[[:space:]]" in chrome_launcher.profile_cmdline_pattern(profile, "ere")


@pytest.mark.parametrize(
    "suffix, matches",
    [
        ("", True),
        ('"', True),
        (" --foo", True),
        ("\t--foo", True),
        ("0", False),
        ("00", False),
        ("x", False),
        (".bak", False),
        ("/child", False),
        ("-copy", False),
    ],
)
def test_profile_cmdline_pattern_has_an_exact_directory_boundary(
    tmp_path, suffix, matches
):
    profile = tmp_path / ".chrome-profiles" / "1"
    found = bool(
        re.search(
            chrome_launcher.profile_cmdline_pattern(profile),
            f"--user-data-dir={profile}{suffix}",
        )
    )
    assert found is matches


def test_get_session_never_launches_and_rejects_closed_sessions(monkeypatch):
    chrome_launcher._sessions.clear()
    assert chrome_launcher.get_session("missing") is None
    closed = type("Session", (), {"browser": type("Browser", (), {"closed": True})()})()
    chrome_launcher._sessions["closed"] = closed
    assert chrome_launcher.get_session("closed") is None


async def test_get_or_launch_serializes_concurrent_callers(monkeypatch, tmp_path):
    key = "concurrent-profile"
    launches = []

    class Browser:
        closed = False

    async def launch(**_kwargs):
        launches.append(True)
        await asyncio.sleep(0.05)
        return Browser()

    async def extension(*_args):
        return "ext"

    monkeypatch.setattr(chrome_launcher.local_browser, "launch", launch)
    monkeypatch.setattr(chrome_launcher, "_discover_extension_id", extension)
    monkeypatch.setattr(chrome_launcher, "_kill_profile_chrome", lambda *_args: None)
    monkeypatch.setattr(chrome_launcher, "_prepare_profile_dir", lambda *_args: None)
    monkeypatch.setattr(chrome_launcher, "_free_port", lambda: 9999)
    monkeypatch.setattr(chrome_launcher.settings, "use_real_chrome", False)
    monkeypatch.setattr(chrome_launcher.settings, "chrome_profiles_dir", tmp_path)
    try:
        first, second = await asyncio.gather(
            chrome_launcher.get_or_launch(key), chrome_launcher.get_or_launch(key)
        )
        assert len(launches) == 1 and first is second
    finally:
        chrome_launcher._sessions.pop(key, None)

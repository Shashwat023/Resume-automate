import asyncio

import pytest

from app.worker import queue_runner as qr


@pytest.fixture(autouse=True)
def _isolated_events():
    """Each test gets its own application_id via a random-ish suffix isn't
    needed — clear the module-level dicts before/after so tests can't leak
    state into each other (these are module globals, not fixtures)."""
    yield
    qr._cancel_events.clear()
    qr._resume_events.clear()
    qr._pause_events.clear()


async def _seed(app_id: str) -> None:
    qr._cancel_events[app_id] = asyncio.Event()
    qr._resume_events[app_id] = asyncio.Event()
    qr._pause_events[app_id] = asyncio.Event()


async def test_signal_pause_sets_is_paused():
    await _seed("app-1")
    assert qr.is_paused("app-1") is False

    await qr.signal_pause("app-1")

    assert qr.is_paused("app-1") is True


async def test_signal_resume_clears_pause_flag():
    await _seed("app-1")
    await qr.signal_pause("app-1")
    assert qr.is_paused("app-1") is True

    await qr.signal_resume("app-1")

    assert qr.is_paused("app-1") is False


async def test_wait_for_resume_or_cancel_returns_resumed():
    await _seed("app-1")

    async def _resume_soon():
        await asyncio.sleep(0.01)
        await qr.signal_resume("app-1")

    asyncio.create_task(_resume_soon())
    result = await qr.wait_for_resume_or_cancel("app-1")

    assert result == "resumed"


async def test_wait_for_resume_or_cancel_returns_cancelled():
    await _seed("app-1")

    async def _cancel_soon():
        await asyncio.sleep(0.01)
        await qr.signal_cancel("app-1")

    asyncio.create_task(_cancel_soon())
    result = await qr.wait_for_resume_or_cancel("app-1")

    assert result == "cancelled"


async def test_wait_for_resume_or_cancel_cancels_the_losing_task():
    # Whichever event does NOT fire, its waiting task must be cancelled,
    # not left running — otherwise every pause point leaks a task. Resume
    # must be signalled AFTER the wait starts (matching real usage: the
    # runner blocks first, an external API call signals second) — signalling
    # before entry gets wiped by wait_for_resume_or_cancel's own
    # clear-stale-flag step, same as the plain wait_for_resume contract.
    await _seed("app-1")

    async def _resume_soon():
        await asyncio.sleep(0.01)
        await qr.signal_resume("app-1")

    before = len(asyncio.all_tasks())
    asyncio.create_task(_resume_soon())
    result = await qr.wait_for_resume_or_cancel("app-1")
    await asyncio.sleep(0.02)  # let cancellation of the losing task propagate
    after = len(asyncio.all_tasks())

    assert result == "resumed"
    assert after <= before + 1  # no net task leak beyond the resume helper itself
    assert qr._cancel_events["app-1"].is_set() is False


async def test_wait_for_resume_or_cancel_times_out_when_nothing_fires():
    # Exists for 2FA polling (runner.py's _handle_2fa_if_present): a run
    # must periodically check whether the challenge cleared on its own,
    # rather than block on a human clicking Resume forever.
    await _seed("app-1")

    result = await qr.wait_for_resume_or_cancel("app-1", timeout=0.01)

    assert result == "timeout"


async def test_wait_for_resume_or_cancel_with_timeout_still_returns_resumed_if_signalled_first():
    await _seed("app-1")

    async def _resume_soon():
        await asyncio.sleep(0.01)
        await qr.signal_resume("app-1")

    asyncio.create_task(_resume_soon())
    result = await qr.wait_for_resume_or_cancel("app-1", timeout=5)

    assert result == "resumed"


async def test_is_paused_false_for_unknown_application():
    assert qr.is_paused("never-seen") is False


async def test_enqueue_application_creates_all_three_events(monkeypatch):
    calls = []

    async def _fake_run(app_id):
        calls.append(app_id)

    qr.set_run_fn(_fake_run)
    try:
        await qr.enqueue_application("app-2")
        await asyncio.sleep(0)  # let the created task run

        assert "app-2" in qr._cancel_events
        assert "app-2" in qr._resume_events
        assert "app-2" in qr._pause_events
        assert calls == ["app-2"]
    finally:
        qr.set_run_fn(None)
        qr._cancel_events.pop("app-2", None)
        qr._resume_events.pop("app-2", None)
        qr._pause_events.pop("app-2", None)


def test_cleanup_removes_all_three_events():
    qr._cancel_events["app-3"] = asyncio.Event()
    qr._resume_events["app-3"] = asyncio.Event()
    qr._pause_events["app-3"] = asyncio.Event()

    qr.cleanup("app-3")

    assert "app-3" not in qr._cancel_events
    assert "app-3" not in qr._resume_events
    assert "app-3" not in qr._pause_events


async def test_get_profile_lock_returns_same_lock_for_same_profile():
    lock1 = qr.get_profile_lock("profile-1")
    lock2 = qr.get_profile_lock("profile-1")

    assert lock1 is lock2

    qr._profile_locks.pop("profile-1", None)


async def test_get_profile_lock_isolates_different_profiles():
    lock_a = qr.get_profile_lock("profile-a")
    lock_b = qr.get_profile_lock("profile-b")

    assert lock_a is not lock_b

    qr._profile_locks.pop("profile-a", None)
    qr._profile_locks.pop("profile-b", None)


async def test_get_profile_lock_serializes_concurrent_access():
    # This is the actual bug: two "applications" for the same profile must
    # not run their critical section concurrently.
    order: list[str] = []

    async def _worker(name: str, delay: float):
        async with qr.get_profile_lock("profile-serial"):
            order.append(f"{name}-start")
            await asyncio.sleep(delay)
            order.append(f"{name}-end")

    try:
        await asyncio.gather(_worker("A", 0.02), _worker("B", 0.0))
        # Whichever ran first must fully finish before the other starts —
        # no interleaving of start/end pairs.
        assert order in (
            ["A-start", "A-end", "B-start", "B-end"],
            ["B-start", "B-end", "A-start", "A-end"],
        )
    finally:
        qr._profile_locks.pop("profile-serial", None)


async def test_profile_session_acquires_and_releases_like_the_bare_lock():
    async with qr.profile_session("profile-session-basic"):
        assert qr.get_profile_lock("profile-session-basic").locked()

    assert not qr.get_profile_lock("profile-session-basic").locked()
    qr._profile_locks.pop("profile-session-basic", None)


async def test_profile_session_times_out_instead_of_waiting_forever(monkeypatch):
    # FLAGGED.md freeze-scan fix: a run holds this lock for its entire
    # Chrome-touching portion, including while paused for 2FA — so one
    # genuinely stuck run must not block every later application for that
    # profile forever with zero visible error. profile_session bounds the
    # ACQUIRE only; release behavior of an already-held lock is unchanged.
    monkeypatch.setattr(qr, "PROFILE_LOCK_TIMEOUT_SECONDS", 0.05)

    held_lock = qr.get_profile_lock("profile-session-timeout")
    await held_lock.acquire()
    try:
        with pytest.raises(qr.ProfileBusyError):
            async with qr.profile_session("profile-session-timeout"):
                pass
    finally:
        held_lock.release()
        qr._profile_locks.pop("profile-session-timeout", None)

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.domain import status as st
from sqlalchemy import select
from sqlalchemy import create_engine, inspect, text

from app.core import db as core_db
from app.models.db_models import Application, RunEvent
from app.services import apply_recovery
from app.services.engine import runner
from app.worker import queue_runner, watchdog


class _CtxWrapper:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def test_additive_migration_adds_application_activity_columns():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE applications (id TEXT PRIMARY KEY, profile_id INTEGER NOT NULL, "
                    "job_id INTEGER NOT NULL, status TEXT NOT NULL, pause_reason TEXT, error TEXT, "
                    "started_at DATETIME, finished_at DATETIME, created_at DATETIME)"
                )
            )
            core_db._add_missing_columns(conn)
            names = {
                column["name"] for column in inspect(conn).get_columns("applications")
            }
        assert {"current_step", "last_activity_at"} <= names
    finally:
        engine.dispose()


async def _application(session, application_id: str, status: str, **values):
    app = Application(
        id=application_id,
        profile_id=1,
        job_id=1,
        status=status,
        **values,
    )
    session.add(app)
    await session.commit()
    return app


async def test_log_updates_activity_and_current_step(async_session, monkeypatch):
    await _application(async_session, "heartbeat", st.RUNNING)
    monkeypatch.setattr(
        runner, "async_session_factory", lambda: _CtxWrapper(async_session)
    )

    await runner._log("heartbeat", "launching", step="Launching Chrome")

    app = await async_session.get(Application, "heartbeat")
    assert app.current_step == "Launching Chrome"
    assert app.last_activity_at is not None


async def test_watchdog_fails_only_stalled_running_application(
    async_session, monkeypatch
):
    stale = datetime.now(timezone.utc) - timedelta(minutes=20)
    await _application(
        async_session,
        "stalled",
        st.RUNNING,
        started_at=stale,
        last_activity_at=stale,
        current_step="Tier 2: Country",
    )
    for status in (st.QUEUED, st.PAUSED, st.NEEDS_INPUT, st.COMPLETED):
        await _application(
            async_session, f"untouched-{status}", status, started_at=stale
        )
    monkeypatch.setattr(
        watchdog, "async_session_factory", lambda: _CtxWrapper(async_session)
    )
    monkeypatch.setattr(
        watchdog,
        "get_settings",
        lambda: SimpleNamespace(application_stall_timeout_seconds=60),
    )
    cancelled = []
    monkeypatch.setattr(watchdog, "cancel_task", cancelled.append)

    assert await watchdog.run_watchdog_once() == ["stalled"]
    stalled = await async_session.get(Application, "stalled")
    assert stalled.status == st.FAILED
    assert "Tier 2: Country" in stalled.error
    assert cancelled == ["stalled"]
    assert (
        await async_session.get(Application, "untouched-queued")
    ).status == st.QUEUED
    assert (
        await async_session.get(Application, "untouched-paused")
    ).status == st.PAUSED
    assert (
        await async_session.get(Application, "untouched-needs_input")
    ).status == st.NEEDS_INPUT
    assert (
        await async_session.get(Application, "untouched-completed")
    ).status == st.COMPLETED
    events = (await async_session.scalars(select(RunEvent))).all()
    assert any(event.tier == "watchdog" for event in events)


async def test_startup_recovery_marks_orphans_and_preserves_terminal_rows(
    async_session, monkeypatch
):
    for status in (st.QUEUED, st.RUNNING, st.PAUSED, st.NEEDS_INPUT):
        await _application(async_session, f"orphan-{status}", status)
    await _application(
        async_session, "uncertain", st.RUNNING, current_step="Submitting"
    )
    await _application(async_session, "terminal", st.COMPLETED)
    monkeypatch.setattr(
        apply_recovery, "async_session_factory", lambda: _CtxWrapper(async_session)
    )
    monkeypatch.setattr(
        apply_recovery,
        "get_settings",
        lambda: SimpleNamespace(use_real_chrome=False, chrome_profiles_dir=None),
    )
    monkeypatch.setattr(apply_recovery, "_kill_profile_chrome", lambda _path: None)

    await apply_recovery.recover_orphaned_applications()

    assert (await async_session.get(Application, "orphan-queued")).status == st.FAILED
    assert (await async_session.get(Application, "orphan-running")).status == st.FAILED
    assert (await async_session.get(Application, "orphan-paused")).status == st.FAILED
    assert (
        await async_session.get(Application, "orphan-needs_input")
    ).status == st.FAILED
    uncertain = await async_session.get(Application, "uncertain")
    assert uncertain.status == st.NEEDS_REVIEW
    assert "verify" in uncertain.error
    assert (await async_session.get(Application, "terminal")).status == st.COMPLETED


async def test_application_lock_wait_has_no_timeout_but_unscoped_wait_does(monkeypatch):
    key = "watchdog-lock-wait"
    lock = queue_runner.get_profile_lock(key)
    await lock.acquire()
    monkeypatch.setattr(queue_runner, "PROFILE_LOCK_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(queue_runner, "LOCK_WAIT_LOG_INTERVAL_SECONDS", 0.01)
    try:
        entered = []

        async def waiter():
            async with queue_runner.profile_session(key, "application-waiter"):
                entered.append(True)

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.02)
        lock.release()
        await task
        assert entered == [True]

        await lock.acquire()
        with pytest.raises(queue_runner.ProfileBusyError):
            async with queue_runner.profile_session(key):
                pass
    finally:
        if lock.locked():
            lock.release()
        queue_runner._profile_locks.pop(key, None)


async def test_watchdog_loop_survives_an_iteration_exception(monkeypatch):
    stop = asyncio.Event()
    calls = 0

    async def _run_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database error")
        stop.set()

    monkeypatch.setattr(watchdog, "run_watchdog_once", _run_once)
    monkeypatch.setattr(
        watchdog, "get_settings", lambda: SimpleNamespace(watchdog_interval_seconds=0)
    )

    await watchdog.watchdog_loop(stop)

    assert calls == 2

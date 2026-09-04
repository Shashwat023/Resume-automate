"""
In-process asyncio worker. Browser automation is stateful and serial per
profile, so this is a simple task-per-application queue with DB-row status
as the source of truth (no Celery/Redis needed for this scope).

pause/resume/cancel are implemented as asyncio.Event flags keyed by
application_id, checked by the running automation loop between actions.

Day 4 Part H: `wait_for_resume_or_cancel` exists because a job paused (user
pause OR 2FA OR CAPTCHA-escalation) is blocked awaiting the resume event —
a cancel signalled while blocked would previously never be observed, since
nothing was listening for it during the wait. Every blocking wait in the
runner now uses this instead of the plain resume-only wait.

`get_profile_lock`: the "serial per profile" claim in this module's own
docstring was never actually enforced until this was added — every queued
application spawned its own task immediately with nothing stopping two
applications for the SAME profile from running concurrently, both driving
the SAME shared Chrome session (chrome_launcher.get_or_launch is keyed by
profile, one browser per profile, reused). Concurrently: two Stagehand
instances fighting over the same pages/frames, causing exactly the kind of
"Frame with the given frameId is not found" CDP errors and instant/timeout
failures this was added to fix. The runner now acquires this lock around
the entire Chrome-touching portion of a run, so a second application for
the same profile genuinely waits its turn instead of racing.
"""

import asyncio
from contextlib import asynccontextmanager

from app.ports import RunnerPort

_cancel_events: dict[str, asyncio.Event] = {}
_resume_events: dict[str, asyncio.Event] = {}
_pause_events: dict[str, asyncio.Event] = {}
_profile_locks: dict[str, asyncio.Lock] = {}
_run_fn: RunnerPort | None = None


# A run holds the profile lock for its ENTIRE Chrome-touching portion,
# deliberately including while it is paused for 2FA. That is correct — a
# paused run still owns the browser's current state — but it means one
# stuck run silently blocks every later application for that profile,
# forever, with those applications showing no error at all: they simply
# never start. This is the "everything froze" symptom one level up from
# the Tier 2 hang in FLAGGED.md #15, and it deserves its own bound. 30
# minutes is far longer than any legitimate run (the longest real run
# observed is a few minutes) while still guaranteeing the queue drains.
PROFILE_LOCK_TIMEOUT_SECONDS = 30 * 60


class ProfileBusyError(RuntimeError):
    """A run waited past PROFILE_LOCK_TIMEOUT_SECONDS for the profile's
    browser session and gave up. Surfaced as a normal application failure
    with a clear message rather than an invisible indefinite wait."""


def get_profile_lock(profile_key: str) -> asyncio.Lock:
    lock = _profile_locks.get(profile_key)
    if lock is None:
        lock = asyncio.Lock()
        _profile_locks[profile_key] = lock
    return lock


@asynccontextmanager
async def profile_session(profile_key: str):
    """`get_profile_lock` with a bound on the ACQUIRE. Release is unchanged
    — once held, the lock is held for as long as the run needs it."""
    lock = get_profile_lock(profile_key)
    try:
        await asyncio.wait_for(lock.acquire(), timeout=PROFILE_LOCK_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise ProfileBusyError(
            f"another application for this profile has held the browser "
            f"session for over {PROFILE_LOCK_TIMEOUT_SECONDS // 60} minutes "
            f"— giving up rather than waiting indefinitely"
        ) from exc
    try:
        yield
    finally:
        lock.release()


def set_run_fn(fn: RunnerPort) -> None:
    """Wired up at startup to app.services.engine.runner.run_application,
    avoiding a circular import between the worker and the engine."""
    global _run_fn
    _run_fn = fn


async def enqueue_application(application_id: str) -> None:
    _cancel_events[application_id] = asyncio.Event()
    _resume_events[application_id] = asyncio.Event()
    _pause_events[application_id] = asyncio.Event()
    if _run_fn is not None:
        asyncio.create_task(_run_fn(application_id))


async def signal_resume(application_id: str) -> None:
    event = _resume_events.get(application_id)
    if event is not None:
        event.set()
    # A resume always clears any pending pause flag too — resuming an
    # application that was user-paused must not have the next checkpoint
    # immediately re-pause it.
    pause_event = _pause_events.get(application_id)
    if pause_event is not None:
        pause_event.clear()


async def signal_cancel(application_id: str) -> None:
    event = _cancel_events.get(application_id)
    if event is not None:
        event.set()


async def signal_pause(application_id: str) -> None:
    event = _pause_events.get(application_id)
    if event is not None:
        event.set()


def is_cancelled(application_id: str) -> bool:
    event = _cancel_events.get(application_id)
    return event is not None and event.is_set()


def is_paused(application_id: str) -> bool:
    event = _pause_events.get(application_id)
    return event is not None and event.is_set()


async def wait_for_resume(application_id: str) -> None:
    event = _resume_events.setdefault(application_id, asyncio.Event())
    event.clear()
    await event.wait()


async def wait_for_resume_or_cancel(application_id: str) -> str:
    """Returns "resumed" or "cancelled" — whichever fires first. Use this
    (not the plain wait_for_resume) at every blocking pause point, so a
    cancel signalled while an application is paused (2FA, CAPTCHA
    escalation, or a user pause) is actually observed instead of leaving
    the task — and its Chrome session — blocked forever."""
    resume_event = _resume_events.setdefault(application_id, asyncio.Event())
    cancel_event = _cancel_events.setdefault(application_id, asyncio.Event())
    resume_event.clear()

    resume_task = asyncio.create_task(resume_event.wait())
    cancel_task = asyncio.create_task(cancel_event.wait())
    try:
        done, pending = await asyncio.wait(
            {resume_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        for task in (resume_task, cancel_task):
            if not task.done():
                task.cancel()

    return "cancelled" if cancel_task in done else "resumed"


def cleanup(application_id: str) -> None:
    _cancel_events.pop(application_id, None)
    _resume_events.pop(application_id, None)
    _pause_events.pop(application_id, None)


class InProcessQueue:
    """
    Adapter exposing this module's free functions as a ports.QueuePort
    implementation, so services can depend on the QueuePort contract
    (constructor-injected, fakeable in tests) instead of importing this
    module's functions directly. The functions above are unchanged and
    still the actual implementation — this just wraps them for DI.
    """

    async def enqueue_application(self, application_id: str) -> None:
        await enqueue_application(application_id)

    async def signal_resume(self, application_id: str) -> None:
        await signal_resume(application_id)

    async def signal_cancel(self, application_id: str) -> None:
        await signal_cancel(application_id)

    async def signal_pause(self, application_id: str) -> None:
        await signal_pause(application_id)

    def is_cancelled(self, application_id: str) -> bool:
        return is_cancelled(application_id)

    def is_paused(self, application_id: str) -> bool:
        return is_paused(application_id)

    def cleanup(self, application_id: str) -> None:
        cleanup(application_id)


queue = InProcessQueue()

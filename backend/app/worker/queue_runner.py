"""
In-process asyncio worker. Browser automation is stateful and serial per
profile, so this is a simple task-per-application queue with DB-row status
as the source of truth (no Celery/Redis needed for this scope).

pause/resume/cancel are implemented as asyncio.Event flags keyed by
application_id, checked by the running automation loop between actions.
"""
import asyncio
from collections.abc import Awaitable, Callable

_cancel_events: dict[str, asyncio.Event] = {}
_resume_events: dict[str, asyncio.Event] = {}
_run_fn: Callable[[str], Awaitable[None]] | None = None


def set_run_fn(fn: Callable[[str], Awaitable[None]]) -> None:
    """Wired up at startup to app.services.engine.runner.run_application,
    avoiding a circular import between the worker and the engine."""
    global _run_fn
    _run_fn = fn


async def enqueue_application(application_id: str) -> None:
    _cancel_events[application_id] = asyncio.Event()
    _resume_events[application_id] = asyncio.Event()
    if _run_fn is not None:
        asyncio.create_task(_run_fn(application_id))


async def signal_resume(application_id: str) -> None:
    event = _resume_events.get(application_id)
    if event is not None:
        event.set()


async def signal_cancel(application_id: str) -> None:
    event = _cancel_events.get(application_id)
    if event is not None:
        event.set()


def is_cancelled(application_id: str) -> bool:
    event = _cancel_events.get(application_id)
    return event is not None and event.is_set()


async def wait_for_resume(application_id: str) -> None:
    event = _resume_events.setdefault(application_id, asyncio.Event())
    event.clear()
    await event.wait()


def cleanup(application_id: str) -> None:
    _cancel_events.pop(application_id, None)
    _resume_events.pop(application_id, None)

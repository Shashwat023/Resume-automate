"""Detect automation tasks that stopped making progress without touching waits."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.domain import status as st
from app.models.db_models import Application, RunEvent
from app.worker.queue_runner import cancel_task

logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def run_watchdog_once() -> list[str]:
    """Fail stale running rows and cancel their in-process task, if any."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    stalled: list[str] = []
    async with async_session_factory() as db:
        rows = (
            await db.scalars(
                select(Application).where(Application.status == st.RUNNING)
            )
        ).all()
        for application in rows:
            reference = application.last_activity_at or application.started_at
            if reference is None:
                continue
            elapsed_seconds = (now - _utc(reference)).total_seconds()
            if elapsed_seconds < settings.application_stall_timeout_seconds:
                continue
            minutes = max(1, int(elapsed_seconds // 60))
            step = application.current_step or "unknown step"
            application.status = st.FAILED
            application.error = (
                f"Stalled: no activity for {minutes} min at step '{step}'"
            )
            application.finished_at = now
            db.add(
                RunEvent(
                    application_id=application.id,
                    message=application.error,
                    level="error",
                    tier="watchdog",
                )
            )
            stalled.append(application.id)
        await db.commit()
    for application_id in stalled:
        cancel_task(application_id)
    return stalled


async def watchdog_loop(stop_event: asyncio.Event) -> None:
    """Run until shutdown; one bad iteration must not kill the watchdog."""
    settings = get_settings()
    while not stop_event.is_set():
        try:
            await run_watchdog_once()
        except Exception:  # noqa: BLE001 - a later interval can recover
            logger.exception("Application stall watchdog iteration failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(), settings.watchdog_interval_seconds
            )
        except TimeoutError:
            pass

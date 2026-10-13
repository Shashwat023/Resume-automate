"""Reconcile application rows which cannot have a surviving worker after restart."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.domain import status as st
from app.models.db_models import Application, RunEvent
from app.services.browser.chrome_launcher import _kill_profile_chrome

logger = logging.getLogger(__name__)

VERIFY_BEFORE_RETRY = (
    "Submission may have gone through — verify in your email/ATS before retrying"
)


async def recover_orphaned_applications() -> list[str]:
    """Terminally mark rows abandoned by a process restart and release Chrome."""
    now = datetime.now(timezone.utc)
    affected: list[tuple[str, int]] = []
    active = (st.QUEUED, st.RUNNING, st.NEEDS_INPUT, st.PAUSED)
    async with async_session_factory() as db:
        rows = (
            await db.scalars(select(Application).where(Application.status.in_(active)))
        ).all()
        for application in rows:
            uncertain = (application.current_step or "").startswith(
                ("Submitting", "Verifying")
            )
            application.status = st.NEEDS_REVIEW if uncertain else st.FAILED
            application.error = (
                VERIFY_BEFORE_RETRY
                if uncertain
                else "Interrupted by server restart — re-queue to retry"
            )
            application.finished_at = now
            db.add(
                RunEvent(
                    application_id=application.id,
                    message=application.error,
                    level="warn" if uncertain else "error",
                    tier="recovery",
                )
            )
            affected.append((application.id, application.profile_id))
        await db.commit()

    settings = get_settings()
    profile_root = (
        settings.real_chrome_profiles_dir
        if settings.use_real_chrome
        else settings.chrome_profiles_dir
    )
    for _application_id, profile_id in affected:
        try:
            await asyncio.to_thread(
                _kill_profile_chrome, profile_root / str(profile_id)
            )
        except Exception:  # noqa: BLE001 - recovery must not fail on cleanup
            logger.warning(
                "Could not clean up Chrome for profile %s", profile_id, exc_info=True
            )
    return [application_id for application_id, _profile_id in affected]

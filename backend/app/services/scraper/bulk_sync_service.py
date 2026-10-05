"""
"Sync all tracked companies" — a separate button from the manual
paste-a-URL sync (api/admin.py's plain `/sync` route, untouched by this
module). Per direct user direction:

  - operates on config/portals.yml's tracked_companies list, not a
    user-supplied URL (that's what the manual flow is for)
  - pausable and resumable, including across a server restart — a full
    pass over 400+ companies is realistically a multi-hour, possibly
    multi-day operation
  - a company already synced within `settings.tracked_company_resync_hours`
    is skipped, so a same-day re-click (or the next day's click) doesn't
    re-spend on companies that were just covered — new jobs still get
    picked up via the ordinary insert-vs-update upsert every sync already
    does (TrackedCompanySyncState itself has no dedup logic of its own;
    it only decides WHICH company to visit next)

State lives in one persisted, singleton `TrackedCompanySyncState` row
(id=1) rather than the in-memory asyncio.Event flags
worker/queue_runner.py uses for a single application's pause/resume —
those are correctly scoped to one process's lifetime; this explicitly
needs to survive longer than that.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.models.db_models import TrackedCompanySyncState
from app.repositories.tracked_company_repository import TrackedCompanyRepository
from app.scripts.seed_portals import seed as seed_tracked_companies
from app.services.engine.llm_client import clear_credits_exhausted
from app.services.scraper.sync_service import sync_company

logger = logging.getLogger(__name__)

_STATE_ID = 1

# In-memory only — deliberately NOT persisted. This is checked WITHIN the
# same process the background loop is running in, purely to let Pause take
# effect between companies without waiting for the current one to finish.
# The persisted `status` column is the actual source of truth for
# "is a pass in progress" across restarts; this flag means nothing once
# the process that set it is gone (which is exactly when a fresh "running"
# status found at startup gets reset to "paused" — see main.py's lifespan).
_pause_requested = asyncio.Event()
_active_task: asyncio.Task | None = None


async def _get_or_create_state(db) -> TrackedCompanySyncState:
    state = await db.get(TrackedCompanySyncState, _STATE_ID)
    if state is None:
        state = TrackedCompanySyncState(id=_STATE_ID)
        db.add(state)
        await _commit_state(db, state)
    return state


async def _commit_state(db, state: TrackedCompanySyncState) -> None:
    """
    `updated_at` uses `onupdate=func.now()` — a DB-computed value the ORM
    object doesn't know until it's re-read, so SQLAlchemy marks it
    "expired" after commit regardless of `expire_on_commit`. An explicit
    refresh right here, still inside the same async call that just
    committed, reads it back deterministically instead of leaving a later,
    unrelated call to trigger an implicit lazy-load — which depends on
    still being inside the async context that first loaded the object,
    and isn't guaranteed once that call has returned.
    """
    await db.commit()
    await db.refresh(state)


async def get_status() -> dict:
    async with async_session_factory() as db:
        state = await _get_or_create_state(db)
        return _to_dict(state)


def _to_dict(state: TrackedCompanySyncState) -> dict:
    return {
        "status": state.status,
        "total_eligible": state.total_eligible,
        "processed": state.processed,
        "jobs_inserted": state.jobs_inserted,
        "jobs_updated": state.jobs_updated,
        "companies_failed": state.companies_failed,
        "current_company_name": state.current_company_name,
        "started_at": state.started_at,
        "updated_at": state.updated_at,
    }


def _resync_cutoff() -> datetime:
    hours = get_settings().tracked_company_resync_hours
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)


async def start_or_resume() -> dict:
    """
    One entry point for both "Start" and "Resume" — they're the same
    action here. If a fresh pass is starting (status is "idle" or a PRIOR
    pass fully "completed"), total_eligible/processed/the counters reset
    for the new pass; resuming a "paused" pass keeps them, since nothing
    about what's already been done should be forgotten.
    """
    global _active_task

    if _active_task is not None and not _active_task.done():
        return await get_status()  # already running in this process — no-op

    # Keeps TrackedCompany rows in sync with the current portals.yml
    # before computing what's eligible — a company added to the file
    # since the last seed must be picked up, not silently skipped because
    # it doesn't exist in the table yet. Cheap and idempotent either way.
    await seed_tracked_companies()

    async with async_session_factory() as db:
        state = await _get_or_create_state(db)
        if state.status == "running":
            # Persisted state says running but no live task in THIS
            # process owns it — either another worker/process claimed it
            # (this app is single-process, so this shouldn't happen in
            # practice) or main.py's startup reset was somehow bypassed.
            # Treat as safe to take over rather than refuse forever.
            pass
        if state.status in ("idle", "completed"):
            repo = TrackedCompanyRepository(db)
            state.total_eligible = await repo.count_eligible(_resync_cutoff())
            state.processed = 0
            state.jobs_inserted = 0
            state.jobs_updated = 0
            state.companies_failed = 0
            state.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        state.status = "running"
        state.current_company_name = None
        state.last_company_error = None
        await _commit_state(db, state)
        result = _to_dict(state)

    _pause_requested.clear()
    clear_credits_exhausted()  # the user topped up (or is retrying) — try again
    _active_task = asyncio.create_task(_run_loop())
    return result


async def request_pause() -> dict:
    _pause_requested.set()
    return await get_status()


async def recover_stale_running_state_on_startup() -> None:
    """
    Called once from main.py's lifespan. A `status="running"` row found at
    boot is necessarily a crash artifact — no asyncio task from a previous
    process survives a restart — so it's reset to "paused" rather than
    left claiming a run is active that nothing is actually driving. The
    next Start click resumes it cleanly (see start_or_resume's docstring):
    nothing here needs to know how far it got, since TrackedCompany's own
    last_synced_at values already reflect exactly that.
    """
    async with async_session_factory() as db:
        state = await _get_or_create_state(db)
        if state.status == "running":
            state.status = "paused"
            await _commit_state(db, state)


async def _run_loop() -> None:
    try:
        while True:
            if _pause_requested.is_set():
                async with async_session_factory() as db:
                    state = await _get_or_create_state(db)
                    state.status = "paused"
                    state.current_company_name = None
                    await _commit_state(db, state)
                return

            async with async_session_factory() as db:
                repo = TrackedCompanyRepository(db)
                company = await repo.next_eligible(_resync_cutoff())
                if company is None:
                    state = await _get_or_create_state(db)
                    state.status = "completed"
                    state.current_company_name = None
                    await _commit_state(db, state)
                    return
                careers_url = company.careers_url
                company_name = company.name

                state = await _get_or_create_state(db)
                state.current_company_name = company_name
                await _commit_state(db, state)

            # A fresh session held open for exactly this one call, since
            # sync_company() does its own job upserts inline as it finds
            # them and can legitimately run for several minutes (real
            # Chrome navigation + LLM calls) — same session lifetime the
            # manual single-URL endpoint already gives it via
            # Depends(get_db), just opened explicitly here instead of
            # coming from a request.
            try:
                async with async_session_factory() as db:
                    result = await sync_company(careers_url, db)
            except Exception:  # noqa: BLE001
                # sync_company() already logs (and swallows) failures from
                # its own three sync paths — reaching here means something
                # escaped ALL of them (e.g. a DB error unrelated to
                # scraping), which is exactly the case with the least
                # visibility otherwise, so it gets logged here too.
                logger.exception(
                    "sync_company raised outside its own handling for %s",
                    careers_url,
                )
                result = {
                    "success": False,
                    "jobs_inserted": 0,
                    "jobs_updated": 0,
                    "failed": 1,
                }

            if result.get("out_of_credits"):
                # Don't mark this company synced or count it — every company
                # after it would fail the same way. Pause so Resume (after
                # topping up the OpenRouter key) retries this same company.
                async with async_session_factory() as db:
                    state = await _get_or_create_state(db)
                    state.status = "paused"
                    state.current_company_name = None
                    state.last_company_error = (
                        "OpenRouter credits / API key limit exhausted — top up or "
                        f"raise the key limit, then Resume. Stopped at: {company_name}"
                    )
                    await _commit_state(db, state)
                logger.error("Bulk sync paused: OpenRouter credits exhausted at %s", careers_url)
                return

            async with async_session_factory() as db:
                repo = TrackedCompanyRepository(db)
                await repo.mark_synced(
                    careers_url, datetime.now(timezone.utc).replace(tzinfo=None)
                )

                state = await _get_or_create_state(db)
                state.processed += 1
                state.jobs_inserted += result["jobs_inserted"]
                state.jobs_updated += result["jobs_updated"]
                if not result["success"]:
                    state.companies_failed += 1
                await _commit_state(db, state)
    except asyncio.CancelledError:
        # Server shutting down mid-loop — leave status as "running"; the
        # next boot's recover_stale_running_state_on_startup() resets it
        # to "paused", same as any other crash-in-progress.
        raise

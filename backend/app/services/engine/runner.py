"""
Automation engine entrypoint. Day 2 scope: real Chrome + real navigation +
Tier 0 deterministic fill. Tier 1 (batched LLM), Tier 2 (Stagehand
observe/act), and Tier 3 (human escalation on low confidence) land Day 3-4
per PLAN.md. Every application currently ends in needs_input regardless of
Tier 0's result — Tier 0 alone can't safely decide "this application is
complete," only the higher tiers plus the final-review gate can, so that's
an honest place to stop until those exist.
"""
import re
from datetime import datetime, timezone

from stagehand import Stagehand

from app.core import status as st
from app.core.db import async_session_factory
from app.models.db_models import Application, Job, Profile, RunEvent
from app.services.browser.chrome_launcher import get_or_launch
from app.services.engine.llm_client import unreachable_llm
from app.services.engine.tier0_harvest import harvest_and_fill
from app.worker.queue_runner import cleanup, is_cancelled

_APPLY_BUTTON = re.compile(r"^\s*\[([\w-]+)\]\s+button:\s*(Apply|Apply Now|Apply for this job)\s*$", re.I)


async def run_application(application_id: str) -> None:
    async with async_session_factory() as db:
        application = await db.get(Application, application_id)
        if application is None:
            return
        profile = await db.get(Profile, application.profile_id)
        job = await db.get(Job, application.job_id)
        if profile is None or job is None:
            application.status = st.FAILED
            application.error = "Profile or job not found"
            await db.commit()
            cleanup(application_id)
            return

        profile_dict = {c.name: getattr(profile, c.name) for c in profile.__table__.columns}

        application.status = st.RUNNING
        application.started_at = datetime.now(timezone.utc)
        db.add(RunEvent(application_id=application_id, message="Automation started"))
        await db.commit()

        if is_cancelled(application_id):
            cleanup(application_id)
            return

    try:
        session = await get_or_launch(str(profile.id))
        sh = await Stagehand.create(browser=session.browser, model=unreachable_llm)
        page = await sh.browser.context.active_page() or await sh.browser.context.new_page()

        await _log(application_id, f"Navigating to {job.apply_url}")
        await page.goto(job.apply_url)
        await page.wait_for_load_state("load")
        # snapshot()'s xpaths are only valid for the DOM shape at that instant;
        # many ATS pages (Greenhouse included) still hydrate/reflow briefly
        # after `load` fires, which is exactly what broke this the first time
        # this ran against a real form (snapshot taken too early -> stale xpath).
        await page.wait_for_timeout(1500)

        clicked_apply = await _click_apply_if_present(page)
        if clicked_apply:
            await _log(application_id, "Clicked an 'Apply' button to reveal the application form")
            await page.wait_for_timeout(1500)

        result = await harvest_and_fill(page, profile_dict)
        for label, value in result.filled:
            await _log(application_id, f"Tier 0 filled '{label}'", tier="tier0")
        for label, err in result.errored:
            await _log(application_id, f"Tier 0 matched '{label}' but fill failed: {err}", level="warn", tier="tier0")
        if result.unmatched:
            await _log(
                application_id,
                f"Tier 0 left {len(result.unmatched)} field(s) unmatched: "
                + ", ".join(result.unmatched[:10])
                + (" ..." if len(result.unmatched) > 10 else ""),
                level="warn",
                tier="tier0",
            )

        await sh.close()

        async with async_session_factory() as db:
            application = await db.get(Application, application_id)
            application.status = st.NEEDS_INPUT
            application.pause_reason = "tier1_2_3_not_implemented_yet"
            db.add(
                RunEvent(
                    application_id=application_id,
                    message=(
                        f"Tier 0 complete: {len(result.filled)} field(s) filled, "
                        f"{len(result.errored)} matched-but-failed, "
                        f"{len(result.unmatched)} unmatched. Higher tiers and the "
                        "final-review gate land Day 3-5 — review and submit manually "
                        "via live view for now."
                    ),
                    level="warn",
                )
            )
            await db.commit()

    except Exception as exc:  # noqa: BLE001 - report to the application record, don't crash the worker
        async with async_session_factory() as db:
            application = await db.get(Application, application_id)
            if application is not None:
                application.status = st.FAILED
                application.error = str(exc)
                application.finished_at = datetime.now(timezone.utc)
                db.add(RunEvent(application_id=application_id, message=f"Failed: {exc}", level="error"))
                await db.commit()

    cleanup(application_id)


async def _click_apply_if_present(page) -> bool:
    """
    Heuristic, not universal: many ATS (Greenhouse among them) gate the
    actual form behind an "Apply" button on a job-description landing page.
    This is a cheap, deterministic, common-case check — the general "find
    and click the right control on an arbitrary page" problem is Tier 2's
    job (Stagehand observe/act), not Tier 0's.

    One retry with a fresh snapshot: a snapshot's xpaths are a point-in-time
    read, and a page that's still settling can invalidate them between the
    snapshot and the click (observed against a real Greenhouse form).
    """
    for attempt in range(2):
        snapshot = await page.snapshot()
        match = _APPLY_BUTTON.search(snapshot.formatted_tree)
        if not match:
            return False
        xpath = snapshot.xpath_map.get(match.group(1))
        if not xpath:
            return False
        try:
            await page.locator(xpath).click()
            return True
        except Exception:
            if attempt == 0:
                await page.wait_for_timeout(1000)
                continue
            raise
    return False


async def _log(application_id: str, message: str, *, level: str = "info", tier: str | None = None) -> None:
    async with async_session_factory() as db:
        db.add(RunEvent(application_id=application_id, message=message, level=level, tier=tier))
        await db.commit()

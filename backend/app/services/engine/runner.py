"""
Automation engine entrypoint. Day 3 scope: real Chrome + real navigation +
the full Tier 0 -> Tier 1 -> Tier 2 cascade.

  Tier 0 (deterministic, free)      -> textbox fields the semantic
                                        dictionary can match with certainty.
  Tier 1 (one batched LLM call)     -> decides a VALUE for everything else,
                                        using the profile + the answers
                                        library; fills textboxes/native
                                        selects directly.
  Tier 2 (Stagehand observe/act)    -> resolves and executes the fields
                                        Tier 1 could only decide a value for
                                        but not click itself (custom
                                        comboboxes, checkboxes, radios).

Every application still ends in needs_input regardless of how much got
filled — Tier 3 (human escalation) and the final-review-before-submit gate
land Day 4-5, so that remains the honest place to stop.
"""

import re
from datetime import datetime, timezone

from stagehand import Stagehand

from app.core.db import async_session_factory
from app.domain import status as st
from app.models.db_models import Application, Job, Profile, RunEvent
from app.repositories.answer_library_repository import AnswerLibraryRepository
from app.services.browser.chrome_launcher import get_or_launch
from app.services.engine.llm_client import openrouter_llm
from app.services.engine.tier0_harvest import collect_fields, fill_deterministic
from app.services.engine.tier1_map import map_fields
from app.services.engine.tier2_resolve import resolve_and_execute
from app.worker.queue_runner import cleanup, is_cancelled

_APPLY_BUTTON = re.compile(
    r"^\s*\[([\w-]+)\]\s+button:\s*(Apply|Apply Now|Apply for this job)\s*$", re.I
)


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

        profile_dict = {
            c.name: getattr(profile, c.name) for c in profile.__table__.columns
        }
        profile_id = profile.id

        application.status = st.RUNNING
        application.started_at = datetime.now(timezone.utc)
        db.add(RunEvent(application_id=application_id, message="Automation started"))
        await db.commit()

        if is_cancelled(application_id):
            cleanup(application_id)
            return

    try:
        session = await get_or_launch(str(profile_id))
        # openrouter_llm handles the "no key configured" case itself (a
        # clear RuntimeError) and Tier 1's own kill switch guarantees Tier 2
        # never has anything queued when no key is set, so this callback is
        # simply never invoked in that case — no separate guard needed here.
        sh = await Stagehand.create(browser=session.browser, model=openrouter_llm)
        page = (
            await sh.browser.context.active_page()
            or await sh.browser.context.new_page()
        )

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
            await _log(
                application_id,
                "Clicked an 'Apply' button to reveal the application form",
            )
            await page.wait_for_timeout(1500)

        # ---- Tier 0: deterministic harvest + fill ----
        snapshot = await page.snapshot()
        fields = collect_fields(snapshot.formatted_tree, snapshot.xpath_map)
        tier0 = await fill_deterministic(page, fields, profile_dict)

        for label, value in tier0.filled:
            await _log(application_id, f"Tier 0 filled '{label}'", tier="tier0")
        for label, err in tier0.errored:
            await _log(
                application_id,
                f"Tier 0 matched '{label}' but fill failed: {err}",
                level="warn",
                tier="tier0",
            )

        tier0_filled_labels = {label for label, _ in tier0.filled}
        remaining_fields = [
            f
            for f in fields
            if not (f.role == "textbox" and f.label in tier0_filled_labels)
        ]

        # ---- Tier 1: batched LLM field mapping ----
        async with async_session_factory() as db:
            answer_repo = AnswerLibraryRepository(db)
            tier1 = await map_fields(
                page, remaining_fields, profile_dict, profile_id, answer_repo
            )

        for label, value in tier1.filled:
            await _log(application_id, f"Tier 1 filled '{label}'", tier="tier1")
        for label, value in tier1.from_library:
            await _log(
                application_id,
                f"Tier 1 used a cached answer for '{label}'",
                tier="tier1",
            )
        for label, err in tier1.errored:
            await _log(
                application_id,
                f"Tier 1 decided '{label}' but apply failed: {err}",
                level="warn",
                tier="tier1",
            )
        if tier1.low_confidence:
            await _log(
                application_id,
                f"Tier 1 left {len(tier1.low_confidence)} field(s) low-confidence: "
                + ", ".join(tier1.low_confidence[:10])
                + (" ..." if len(tier1.low_confidence) > 10 else ""),
                level="warn",
                tier="tier1",
            )
        if tier1.usage.get("total_tokens"):
            await _log(
                application_id,
                f"Tier 1 cost: {tier1.usage['total_tokens']} tokens "
                f"({tier1.usage['input_tokens']} in / {tier1.usage['output_tokens']} out)",
                tier="tier1",
            )

        # ---- Tier 2: Stagehand observe/act for custom widgets ----
        tier2 = await resolve_and_execute(sh, page, tier1.for_tier2)
        for label, description in tier2.resolved:
            await _log(
                application_id,
                f"Tier 2 resolved '{label}': {description}",
                tier="tier2",
            )
        for label, err in tier2.errored:
            await _log(
                application_id,
                f"Tier 2 failed to resolve '{label}': {err}",
                level="warn",
                tier="tier2",
            )

        all_labels = {f.label for f in fields}
        handled_labels = (
            tier0_filled_labels
            | {label for label, _ in tier1.filled}
            | {label for label, _ in tier1.from_library}
            | {label for label, _ in tier2.resolved}
        )
        still_unhandled = sorted(all_labels - handled_labels)

        await sh.close()

        async with async_session_factory() as db:
            application = await db.get(Application, application_id)
            application.status = st.NEEDS_INPUT
            application.pause_reason = "tier3_and_final_review_not_implemented_yet"
            db.add(
                RunEvent(
                    application_id=application_id,
                    message=(
                        f"Automation pass complete — Tier 0: {len(tier0.filled)}, "
                        f"Tier 1: {len(tier1.filled) + len(tier1.from_library)}, "
                        f"Tier 2: {len(tier2.resolved)} field(s) handled; "
                        f"{len(still_unhandled)} still unhandled. Human-in-the-loop "
                        "(Tier 3) and the final-review gate land Day 4-5 — review and "
                        "submit manually via live view for now."
                    ),
                    level="warn",
                )
            )
            await db.commit()

    except Exception as exc:  # noqa: BLE001 - report to the application record, don't crash the worker
        detail = (
            f"{type(exc).__name__}: {exc}"
            if str(exc)
            else f"{type(exc).__name__} (no message)"
        )
        async with async_session_factory() as db:
            application = await db.get(Application, application_id)
            if application is not None:
                application.status = st.FAILED
                application.error = detail
                application.finished_at = datetime.now(timezone.utc)
                db.add(
                    RunEvent(
                        application_id=application_id,
                        message=f"Failed: {detail}",
                        level="error",
                    )
                )
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


async def _log(
    application_id: str, message: str, *, level: str = "info", tier: str | None = None
) -> None:
    async with async_session_factory() as db:
        db.add(
            RunEvent(
                application_id=application_id, message=message, level=level, tier=tier
            )
        )
        await db.commit()

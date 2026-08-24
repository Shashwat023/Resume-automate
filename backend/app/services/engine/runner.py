"""
Automation engine entrypoint. Day 4 scope: real Chrome + real navigation +
the full Tier 0 -> Tier 1 -> Tier 2 cascade, plus CAPTCHA solving, 2FA
pause/resume, and automated submission with verification.

  Tier 0 (deterministic, free)      -> textbox/file fields matched with
                                        certainty (semantic dictionary,
                                        resume attachment).
  Tier 1 (one batched LLM call)     -> decides a VALUE for everything else,
                                        using the profile + resume facts +
                                        the answers library; fills
                                        textboxes/native selects directly.
                                        Always answers — never abstains
                                        (Day 4 scope correction, see
                                        PLAN.md).
  Tier 2 (Stagehand observe/act)    -> resolves and executes the fields
                                        Tier 1 could only decide a value for
                                        but not click itself (custom
                                        comboboxes, checkboxes, radios).

Per the Day-4 scope correction, `needs_input` now has exactly two causes:
2FA, and a CAPTCHA that failed twice (a deliberate, flagged deviation —
see FLAGGED.md). Everything else — form-fill, CAPTCHA, submission — is
fully automated; a run ends in `completed` or `failed`, not a permanent
needs_input parking state.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from stagehand import Stagehand

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.domain import status as st
from app.models.db_models import Application, Job, Profile, RunEvent
from app.repositories.answer_library_repository import AnswerLibraryRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.browser.chrome_launcher import get_or_launch
from app.services.captcha.service import resolve_captcha
from app.services.engine.llm_client import openrouter_llm
from app.services.engine.submit import (
    SubmitResult,
    click_submit,
    find_submit_button,
    read_outcome,
)
from app.services.engine.tier0_harvest import (
    FormField,
    HarvestResult,
    collect_fields,
    fill_deterministic,
)
from app.services.engine.tier1_map import Tier1Result, map_fields
from app.services.engine.tier2_resolve import Tier2Result, resolve_and_execute
from app.services.engine.twofa_detect import detect_2fa
from app.services.resume.storage import LocalFilesystemStorage
from app.services.resume_service import ResumeService
from app.worker.queue_runner import cleanup, is_cancelled, wait_for_resume

_APPLY_BUTTON = re.compile(
    r"^\s*\[([\w-]+)\]\s+button:\s*(Apply|Apply Now|Apply for this job)\s*$", re.I
)


@dataclass
class FillCascadeResult:
    fields: list[FormField]
    tier0: HarvestResult
    tier1: Tier1Result
    tier2: Tier2Result


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
        resume = await ResumeRepository(db).get(profile_id)
        resume_file_path = resume.file_path if resume is not None else None

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

        # CAPTCHA/2FA can gate the form itself, not just the final submit —
        # check before the fill cascade as well as around submission below.
        await _resolve_captcha_if_present(application_id, page)
        await _handle_2fa_if_present(application_id, page)

        cascade = await _run_fill_cascade(
            application_id, sh, page, profile_dict, profile_id, resume_file_path
        )

        if get_settings().submit_enabled:
            submit_result = await _submit_and_verify(
                application_id,
                sh,
                page,
                profile_dict,
                profile_id,
                resume_file_path,
                cascade,
            )
        else:
            await _log(
                application_id,
                "Submission skipped — SUBMIT_ENABLED is False (dev safety). "
                "Form left filled, unsubmitted.",
            )
            submit_result = SubmitResult(outcome="skipped")

        await sh.close()

        async with async_session_factory() as db:
            application = await db.get(Application, application_id)
            all_labels = {f.label for f in cascade.fields}
            handled_labels = (
                {label for label, _ in cascade.tier0.filled}
                | {label for label, _ in cascade.tier1.filled}
                | {label for label, _ in cascade.tier1.from_library}
                | {label for label, _ in cascade.tier2.resolved}
            )
            still_unhandled = sorted(all_labels - handled_labels)

            if submit_result.outcome in ("completed", "skipped"):
                application.status = st.COMPLETED
            else:
                application.status = st.FAILED
                application.error = submit_result.detail or submit_result.outcome
            application.finished_at = datetime.now(timezone.utc)
            db.add(
                RunEvent(
                    application_id=application_id,
                    message=(
                        f"Automation pass complete — Tier 0: {len(cascade.tier0.filled)}, "
                        f"Tier 1: {len(cascade.tier1.filled) + len(cascade.tier1.from_library)}, "
                        f"Tier 2: {len(cascade.tier2.resolved)} field(s) handled; "
                        f"{len(still_unhandled)} still unhandled. "
                        f"Submission: {submit_result.outcome}"
                        + (f" ({submit_result.detail})" if submit_result.detail else "")
                        + "."
                    ),
                    level="warn" if still_unhandled else "info",
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


async def _run_fill_cascade(
    application_id: str,
    sh,
    page,
    profile_dict: dict,
    profile_id: int,
    resume_file_path: str | None,
) -> FillCascadeResult:
    """Tier 0 -> Tier 1 -> Tier 2, one full pass. Extracted so the submit
    repair pass (a validation error after a first submit attempt) can rerun
    exactly this cascade against the corrected page state, instead of
    duplicating it."""
    # ---- Tier 0: deterministic harvest + fill ----
    snapshot = await page.snapshot()
    fields = collect_fields(snapshot.formatted_tree, snapshot.xpath_map)
    tier0 = await fill_deterministic(page, fields, profile_dict, resume_file_path)

    for label, value in tier0.filled:
        await _log(application_id, f"Tier 0 filled '{label}'", tier="tier0")
    for label, err in tier0.errored:
        await _log(
            application_id,
            f"Tier 0 matched '{label}' but fill failed: {err}",
            level="warn",
            tier="tier0",
        )
    file_field_labels = {f.label for f in fields if f.role == "file"}
    for label in tier0.unmatched:
        if label in file_field_labels:
            # File fields never go to Tier 1/2 (see remaining_fields
            # below), so an unattached one is otherwise silent — this
            # is the only place it becomes visible.
            await _log(
                application_id,
                f"Tier 0 could not attach '{label}' — no resume on file",
                level="warn",
                tier="tier0",
            )

    tier0_filled_labels = {label for label, _ in tier0.filled}
    # File fields never go to Tier 1/2 regardless of outcome — attaching
    # a resume is exclusively Tier 0's job (deterministic, no value to
    # "decide"); if it wasn't filled here (no resume on file), there's
    # nothing an LLM guess or a widget click could contribute.
    remaining_fields = [
        f
        for f in fields
        if f.role != "file"
        and not (f.role == "textbox" and f.label in tier0_filled_labels)
    ]

    # ---- Tier 1: batched LLM field mapping ----
    async with async_session_factory() as db:
        resume_repo = ResumeRepository(db)
        profile_repo = ProfileRepository(db)
        storage = LocalFilesystemStorage(get_settings().resume_storage_dir)
        resume_facts = await ResumeService(
            resume_repo, profile_repo, storage
        ).get_facts(profile_id)

        answer_repo = AnswerLibraryRepository(db)
        tier1 = await map_fields(
            page,
            remaining_fields,
            profile_dict,
            profile_id,
            answer_repo,
            resume_facts,
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
    if tier1.low_confidence_filled:
        await _log(
            application_id,
            f"Tier 1 filled {len(tier1.low_confidence_filled)} field(s) at low "
            "confidence (used but not cached): "
            + ", ".join(tier1.low_confidence_filled[:10])
            + (" ..." if len(tier1.low_confidence_filled) > 10 else ""),
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

    return FillCascadeResult(fields=fields, tier0=tier0, tier1=tier1, tier2=tier2)


async def _submit_and_verify(
    application_id: str,
    sh,
    page,
    profile_dict: dict,
    profile_id: int,
    resume_file_path: str | None,
    cascade: FillCascadeResult,
) -> SubmitResult:
    """
    Clicks the real submit control and reads the result. One bounded
    repair attempt on a validation error: reruns the SAME fill cascade
    against the corrected page state (not per-field-error targeting —
    a deliberate simplification of the fuller design in PLAN.md, flagged
    there) and retries submit once more.
    """
    for attempt in range(2):
        # Invisible reCAPTCHA/hCaptcha frequently only renders once a
        # submit is actually attempted — check again right before clicking,
        # not just once at page load.
        await _resolve_captcha_if_present(application_id, page)

        snapshot = await page.snapshot()
        xpath = find_submit_button(snapshot.formatted_tree, snapshot.xpath_map)
        if xpath is None:
            return SubmitResult(outcome="unknown", detail="submit button not found")

        await click_submit(page, xpath)
        await page.wait_for_timeout(2000)

        # A challenge can appear only after submission (e.g. email-based
        # verification triggered by the attempt itself).
        await _handle_2fa_if_present(application_id, page)

        snapshot2 = await page.snapshot()
        result = read_outcome(snapshot2.formatted_tree)

        if result.outcome == "completed":
            await _log(
                application_id,
                f"Submission confirmed: {result.detail}",
                tier="submit",
            )
            return result

        if result.outcome == "validation_error" and attempt == 0:
            await _log(
                application_id,
                f"Validation error after submit: {result.detail} — running one "
                "repair pass and retrying",
                level="warn",
                tier="submit",
            )
            cascade = await _run_fill_cascade(
                application_id, sh, page, profile_dict, profile_id, resume_file_path
            )
            continue

        await _log(
            application_id,
            f"Submission outcome unclear after clicking submit "
            f"(result: {result.outcome}{': ' + result.detail if result.detail else ''})",
            level="warn",
            tier="submit",
        )
        return result

    return SubmitResult(outcome="unknown", detail="exhausted submit retries")


async def _resolve_captcha_if_present(application_id: str, page) -> None:
    outcome = await resolve_captcha(page)
    if outcome.status == "not_present":
        return
    if outcome.status == "solved":
        await _log(
            application_id, f"CAPTCHA solved ({outcome.detail})", tier="captcha"
        )
        return
    if outcome.status == "no_key":
        await _log(
            application_id,
            f"CAPTCHA detected but TWOCAPTCHA_API_KEY is not configured — "
            "left unsolved",
            level="warn",
            tier="captcha",
        )
        return
    if outcome.status == "failed_hard":
        raise RuntimeError(f"CAPTCHA solving failed: {outcome.detail}")

    # failed_escalate: deliberate, flagged deviation from "CAPTCHA is fully
    # automated" — see FLAGGED.md. The browser is already open; escalating
    # beats failing the whole application outright.
    await _log(
        application_id,
        f"CAPTCHA solving failed twice ({outcome.detail}) — escalating for "
        "manual solve via live view",
        level="warn",
        tier="captcha",
    )
    await _pause_for_input(application_id, "captcha_failed")
    await wait_for_resume(application_id)
    await _resume_from_pause(application_id)
    await _log(application_id, "Resumed after manual CAPTCHA handling")


async def _handle_2fa_if_present(application_id: str, page) -> None:
    snapshot = await page.snapshot()
    if not detect_2fa(snapshot.formatted_tree):
        return

    await _log(
        application_id,
        "2FA challenge detected — pausing for human input via live view",
        level="warn",
    )
    await _pause_for_input(application_id, "2fa_required")
    await wait_for_resume(application_id)
    await _resume_from_pause(application_id)
    await _log(application_id, "Resumed after 2FA")


async def _pause_for_input(application_id: str, pause_reason: str) -> None:
    async with async_session_factory() as db:
        application = await db.get(Application, application_id)
        if application is not None:
            application.status = st.NEEDS_INPUT
            application.pause_reason = pause_reason
            await db.commit()


async def _resume_from_pause(application_id: str) -> None:
    async with async_session_factory() as db:
        application = await db.get(Application, application_id)
        if application is not None:
            application.status = st.RUNNING
            application.pause_reason = None
            await db.commit()


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

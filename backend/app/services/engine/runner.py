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
from app.services.browser.chrome_launcher import close_session, get_or_launch
from app.services.captcha.service import resolve_captcha
from app.services.engine.llm_client import openrouter_llm
from app.services.engine.submit import (
    SubmitResult,
    click_submit,
    find_invalid_field_labels,
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
from app.services.engine.timeouts import with_timeout
from app.services.engine.twofa_detect import detect_2fa
from app.services.resume.storage import LocalFilesystemStorage
from app.services.resume_service import ResumeService
from app.worker.queue_runner import (
    cleanup,
    is_cancelled,
    is_paused,
    profile_session,
    wait_for_resume_or_cancel,
)

_APPLY_BUTTON = re.compile(
    # re.M: without it, ^/$ only anchor to the whole tree STRING's
    # start/end, not each line, so this could basically never match a real
    # multi-line tree — same bug as submit.py's _SUBMIT_BUTTON (see there
    # for the full story). Silently masked here because the URLs tested
    # throughout this project (job-boards.greenhouse.io/.../jobs/{id})
    # show the form directly with no landing-page Apply click needed, so
    # this path's return value never actually mattered until now.
    r"^\s*\[([\w-]+)\]\s+button:\s*(Apply|Apply Now|Apply for this job)\s*$",
    re.I | re.M,
)


class ApplicationCancelled(Exception):
    """Raised out of a pause-wait when the user cancels while the
    application was blocked (user-paused, 2FA, or CAPTCHA escalation) —
    `apply_service.cancel()` already set status=CANCELLED directly via the
    API call, so this just unwinds the runner cleanly without the generic
    except-block overwriting that with FAILED."""


class TwoFactorTimeout(Exception):
    """Raised when a 2FA challenge is still present after
    TWOFA_TIMEOUT_SECONDS of polling with no manual resume either. Real
    gap this fixes: the original `_handle_2fa_if_present` paused and
    blocked on `wait_for_resume_or_cancel` with NO timeout and NO
    re-checking of the page — a 2FA challenge nobody ever resolves (no one
    watching Live View, or the app itself never sends a code) strands the
    run — and, via the per-profile lock, every later application for that
    profile — forever. Raising here lets the existing top-level
    `except Exception` in run_application mark the application FAILED,
    log it, release the profile lock, and let the queue advance — the same
    "fail cleanly instead of hanging forever" contract every other bounded
    wait in this engine already provides (see timeouts.py)."""


@dataclass
class FillCascadeResult:
    fields: list[FormField]
    tier0: HarvestResult
    tier1: Tier1Result
    tier2: Tier2Result


async def run_application(application_id: str) -> None:
    profile_id: int | None = None
    # Real, live-caught bug: enqueue_application() (queue_runner.py) fires
    # this off via a bare `asyncio.create_task` — nothing awaits or tracks
    # it. The lookup block right below THIS point used to sit entirely
    # OUTSIDE any exception handling (only the block further down was
    # covered — see that fix's own comment, kept below). A DB error here
    # (SQLite write contention from two applications committing around the
    # same moment is the likely real-world trigger, given aiosqlite) killed
    # the task with an unretrieved exception: no FAILED status, no error
    # logged, no cleanup() — so `_cancel_events`/`_resume_events`/
    # `_pause_events` never got popped for this application_id, and if it
    # had already acquired the per-profile lock (queue_runner.py's
    # `profile_session`), that lock's own `finally` still releases it
    # correctly — but a NEXT queued application for a DIFFERENT profile
    # was never blocked by this in the first place, since each
    # application is its own independent task. What WAS actually blocked,
    # confirmed live: a second application queued around the same time
    # looked like it "never even tried to run" — consistent with ITS OWN
    # task also hitting this exact same unhandled-crash class independently
    # (both committing near-simultaneously against one SQLite file), not
    # one job blocking another. Wrapping the whole function in one
    # try/except/finally — so every application, whatever fails, always
    # ends in a visible FAILED status and always runs cleanup() — removes
    # that failure mode entirely instead of only half-covering it.
    try:
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
                return

            profile_dict = {
                c.name: getattr(profile, c.name) for c in profile.__table__.columns
            }
            profile_id = profile.id

        async with async_session_factory() as db:
            resume = await ResumeRepository(db).get(profile_id)
            resume_file_path = resume.file_path if resume is not None else None

            application = await db.get(Application, application_id)
            application.status = st.RUNNING
            application.started_at = datetime.now(timezone.utc)
            db.add(
                RunEvent(application_id=application_id, message="Automation started")
            )
            await db.commit()

        if is_cancelled(application_id):
            return

        # Pause-before-start: a job paused the instant it was queued (before
        # this task even got to run) must cost nothing — no browser launch,
        # no LLM call. `apply_service.pause()` already set status=PAUSED;
        # this is just the runner honouring that before doing anything.
        await _check_paused_and_wait(application_id)

        # Serialize per profile: chrome_launcher.get_or_launch reuses ONE
        # shared Chrome session per profile (deliberate — cookies/login
        # persist across a profile's applications). Without this lock, two
        # applications for the same profile queued close together would
        # both drive that same session concurrently — two Stagehand
        # instances racing over the same pages/frames, which is exactly
        # what produced "Frame with the given frameId is not found" CDP
        # errors and instant/timeout failures in practice. Held for the
        # entire Chrome-touching portion of the run, including while
        # paused/2FA/CAPTCHA-blocked — a paused application still "owns"
        # that page's current state; a second application must not jump in
        # and start navigating the same browser while the first is merely
        # paused, not finished.
        async with profile_session(str(profile_id)):
            session = await with_timeout(
                get_or_launch(str(profile_id)), what="Chrome launch"
            )
            # Real, live-caught RACE: `close_session()` below must run
            # while THIS application still holds the per-profile lock
            # (i.e. before `async with profile_session(...)` exits) — it
            # used to live in the function's outer `finally`, which only
            # runs AFTER that lock is released. A second application for
            # the same profile, already blocked waiting on the lock,
            # could acquire it and call `get_or_launch()` BEFORE this
            # close actually completed, reconnecting to a browser this
            # application hadn't finished tearing down — reproducing the
            # exact "already attached"/"already initialized" failure this
            # exists to prevent. Wraps EVERYTHING from here on, including
            # `Stagehand.create()` itself, so a session is discarded even
            # if create() fails before `sh` exists at all.
            try:
                # openrouter_llm handles the "no key configured" case itself (a
                # clear RuntimeError) and Tier 1's own kill switch guarantees Tier 2
                # never has anything queued when no key is set, so this callback is
                # simply never invoked in that case — no separate guard needed here.
                sh = await with_timeout(
                    Stagehand.create(browser=session.browser, model=openrouter_llm),
                    what="Stagehand init",
                )
                try:
                    page = (
                        await sh.browser.context.active_page()
                        or await sh.browser.context.new_page()
                    )

                    await _log(application_id, f"Navigating to {job.apply_url}")
                    await with_timeout(page.goto(job.apply_url), what="page.goto")
                    await with_timeout(
                        page.wait_for_load_state("load"), what="wait_for_load_state"
                    )
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

                    # Proactive self-check before ever attempting submit — not just
                    # reactively after a validation error. Targeted at ONLY the
                    # fields nothing handled in the first pass (never re-touches an
                    # already-succeeded field: re-clicking an already-set checkbox
                    # or dropdown risks toggling it back off).
                    if _unhandled_labels(cascade):
                        cascade = await _repair_unhandled_fields(
                            application_id,
                            sh,
                            page,
                            profile_dict,
                            profile_id,
                            cascade,
                        )

                    await _escalate_unhandled_fields_if_any(application_id, cascade)

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
                finally:
                    await sh.close()
            finally:
                await close_session(str(profile_id))

        async with async_session_factory() as db:
            application = await db.get(Application, application_id)
            still_unhandled = sorted(_unhandled_labels(cascade))

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

    except ApplicationCancelled:
        pass  # status already set to CANCELLED by apply_service.cancel()

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

    finally:
        # Real, live-caught bug, corrected THREE times over (see
        # FLAGGED.md #26/#27/#28): the Chrome session this application
        # used is now closed from INSIDE the `async with
        # profile_session(...)` block above (wrapping `Stagehand.create()`
        # itself, so it runs even if create() fails before `sh` exists) —
        # deliberately NOT here. Closing it only after that block exits
        # would run after the per-profile lock is already released, and a
        # second application already waiting on that lock could acquire
        # it and call `get_or_launch()` before this application's own
        # close had actually completed — reconnecting to a browser that
        # hadn't finished tearing down and reproducing the exact
        # "already attached"/"already initialized" failure this whole
        # chain of fixes exists to prevent. `profile_id` is otherwise
        # unused in this outer finally now — kept as a guard variable, not
        # a leftover.
        # Guaranteed to run on every exit path — including a crash in the
        # lookup block above the try, which was previously uncovered and
        # could leak this application_id's queue-runner event entries
        # forever with no FAILED status at all (see this function's own
        # opening comment). One place, always reached.
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
    await _check_paused_and_wait(application_id)

    # ---- Tier 0: deterministic harvest + fill ----
    snapshot = await with_timeout(page.snapshot(), what="page.snapshot")
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

    await _check_paused_and_wait(application_id)

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
    if tier1.unanswered:
        # Genuinely blank after a targeted repair retry — not a confidence
        # decision (those are low_confidence_filled, above), an actual
        # omission from the LLM's response. Worth its own loud line: a
        # required field ending up here is the exact bug class this
        # detection exists to surface instead of silently submitting blank.
        await _log(
            application_id,
            f"Tier 1 could not get an answer for {len(tier1.unanswered)} "
            "field(s), even after a repair retry: " + ", ".join(tier1.unanswered),
            level="error",
            tier="tier1",
        )
    if tier1.usage.get("total_tokens"):
        await _log(
            application_id,
            f"Tier 1 cost: {tier1.usage['total_tokens']} tokens "
            f"({tier1.usage['input_tokens']} in / {tier1.usage['output_tokens']} out)",
            tier="tier1",
        )

    await _check_paused_and_wait(application_id)

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


def _unhandled_labels(cascade: FillCascadeResult) -> set[str]:
    """
    Real bug found live (FLAGGED.md): `tier1.from_library` is populated
    the moment a cached ANSWER exists for a label (tier1_map.py's
    map_fields, unconditionally, before it even knows whether that field
    is a direct textbox/select fill or a for_tier2 custom widget). That is
    correct for its own purpose — it's an audit trail of "this value came
    from cache, not a fresh LLM call" — but treating it as `handled` here
    is wrong for any label that ALSO needed Tier 2 to actually execute the
    click: Tier 1 having *decided a value* is not the same as Tier 2
    having *applied* it. A live run had Tier 2 explicitly log failures for
    'Country' and 'Agreement to Arbitrate' (both cached answers) in the
    SAME pass, yet this function still reported "0 still unhandled" and
    skipped BOTH the pre-submit repair pass and the post-validation-error
    repair — because `from_library` alone made every one of them count as
    handled regardless of Tier 2's real outcome. That's why a validation
    error ("This field is required") only ever surfaced at the very last
    step, after a needless second full-cascade re-run.

    `tier1.filled` already covers every field that was genuinely applied
    without needing Tier 2 (a direct `.fill()`/`.select_option()`, cached
    answer or not) — `from_library` adds no additional TRUE completions on
    top of that, only false ones for for_tier2-bound fields. Dropped
    entirely rather than patched with a for_tier2 lookup, since it can
    never legitimately contribute a label `tier1.filled`/`tier2.resolved`
    doesn't already have.
    """
    all_labels = {f.label for f in cascade.fields}
    handled_labels = (
        {label for label, _ in cascade.tier0.filled}
        | {label for label, _ in cascade.tier1.filled}
        | {label for label, _ in cascade.tier2.resolved}
    )
    return all_labels - handled_labels


async def _repair_unhandled_fields(
    application_id: str,
    sh,
    page,
    profile_dict: dict,
    profile_id: int,
    cascade: FillCascadeResult,
    also_target: set[str] | None = None,
) -> FillCascadeResult:
    """
    One targeted pass over the fields the first pass left unhandled —
    re-collected fresh (xpaths may have drifted since the original
    snapshot), scoped by label to just that subset. Deliberately narrower
    than a full cascade re-run: re-running Tier 1+2 on already-succeeded
    fields would re-execute their clicks too, and a checkbox/dropdown
    "set" action isn't guaranteed idempotent — re-clicking an
    already-checked box can toggle it back off. Never touches a field that
    already has a result, UNLESS named in `also_target`.

    `also_target` exists because our own success bookkeeping
    (`_unhandled_labels`) has repeatedly proven unreliable in live testing
    — several real runs reported "0 still unhandled" yet still failed
    submission with the SAME validation error, meaning at least one field
    Tier 2 believed it had resolved was never actually accepted by the
    real ATS. The caller (`_submit_and_verify`) reads the validation
    error's field association directly off the page
    (`find_invalid_field_labels`) and passes it here — the ATS's own
    "This field is required" is a strictly more reliable signal than our
    own click-success tracking, so it forces a re-target even when
    `_unhandled_labels` disagrees.
    """
    unhandled = _unhandled_labels(cascade) | (also_target or set())
    await _log(
        application_id,
        f"Re-checking {len(unhandled)} field(s) left unhandled after the "
        "first pass: " + ", ".join(sorted(unhandled)),
        level="warn",
    )

    snapshot = await with_timeout(page.snapshot(), what="page.snapshot")
    fresh_fields = collect_fields(snapshot.formatted_tree, snapshot.xpath_map)
    targets = [f for f in fresh_fields if f.label in unhandled]
    if not targets:
        # The fields are simply gone from the tree now (page state moved
        # on) — nothing left to target, cascade stands as-is.
        return cascade

    async with async_session_factory() as db:
        resume_repo = ResumeRepository(db)
        profile_repo = ProfileRepository(db)
        storage = LocalFilesystemStorage(get_settings().resume_storage_dir)
        resume_facts = await ResumeService(
            resume_repo, profile_repo, storage
        ).get_facts(profile_id)
        answer_repo = AnswerLibraryRepository(db)
        tier1_extra = await map_fields(
            page, targets, profile_dict, profile_id, answer_repo, resume_facts
        )

    for label, value in tier1_extra.filled:
        await _log(
            application_id, f"Tier 1 filled '{label}' (repair pass)", tier="tier1"
        )
    for label, value in tier1_extra.from_library:
        await _log(
            application_id,
            f"Tier 1 used a cached answer for '{label}' (repair pass)",
            tier="tier1",
        )

    tier2_extra = await resolve_and_execute(sh, page, tier1_extra.for_tier2)
    for label, description in tier2_extra.resolved:
        await _log(
            application_id,
            f"Tier 2 resolved '{label}' (repair pass): {description}",
            tier="tier2",
        )
    for label, err in tier2_extra.errored:
        await _log(
            application_id,
            f"Tier 2 still could not resolve '{label}' after repair: {err}",
            level="warn",
            tier="tier2",
        )

    merged_tier1 = Tier1Result(
        filled=cascade.tier1.filled + tier1_extra.filled,
        from_library=cascade.tier1.from_library + tier1_extra.from_library,
        for_tier2=[],  # already consumed into tier2_extra above
        low_confidence_filled=cascade.tier1.low_confidence_filled
        + tier1_extra.low_confidence_filled,
        unanswered=tier1_extra.unanswered,
        errored=cascade.tier1.errored + tier1_extra.errored,
        usage={
            k: cascade.tier1.usage[k] + tier1_extra.usage[k]
            for k in cascade.tier1.usage
        },
    )
    merged_tier2 = Tier2Result(
        resolved=cascade.tier2.resolved + tier2_extra.resolved,
        errored=cascade.tier2.errored + tier2_extra.errored,
    )
    return FillCascadeResult(
        fields=cascade.fields,
        tier0=cascade.tier0,
        tier1=merged_tier1,
        tier2=merged_tier2,
    )


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
    repair attempt on a validation error: re-checks ONLY the fields
    `_unhandled_labels` says are still unhandled (the same targeted
    `_repair_unhandled_fields` the pre-submit checkpoint already uses) and
    retries submit once more.

    Previously this reran the ENTIRE fill cascade — every field, including
    the ones that had already succeeded — which was the single largest
    cost in a live run: ~19 Tier 2 widgets x 2 observe()/act() round trips
    each x 15-80s per call is 10-25 minutes on its own, spent almost
    entirely re-confirming fields that were already correct. Combined with
    the `_unhandled_labels` accounting bug fixed alongside this (which
    caused the PRE-submit repair to never even fire, deferring all repair
    work to this much more expensive post-submit path), that's a large
    share of a real run's ~47-minute total. Targeted repair here is the
    same trade already accepted for the pre-submit checkpoint: never
    re-touches an already-succeeded field, since re-clicking an
    already-set checkbox/dropdown isn't guaranteed idempotent.
    """
    # Real gap reported live: on the FINAL attempt, a validation error (or
    # any non-"completed" outcome) used to just return FAILED outright —
    # the escalation below only ever ran on attempt 0. Per the user's own
    # framing ("in any case the agent never fails and stops working on
    # its own"), the automation must never give up silently while a human
    # fix is still on the table. Three attempts now: attempt 0 is the
    # original automated repair pass; attempt 1, if STILL not resolved,
    # broadens escalation to EVERY unhandled field (not just ones we
    # guessed were required) as the last chance before the final attempt;
    # attempt 2 is that human-assisted final try. Only after a genuine
    # human-assisted attempt still fails does this actually give up —
    # not an infinite loop, a bounded one extra step.
    MAX_SUBMIT_ATTEMPTS = 3
    for attempt in range(MAX_SUBMIT_ATTEMPTS):
        # Invisible reCAPTCHA/hCaptcha frequently only renders once a
        # submit is actually attempted — check again right before clicking,
        # not just once at page load.
        await _resolve_captcha_if_present(application_id, page)

        # Reset scroll position before the final look at the page. The
        # accessibility-tree snapshot itself isn't scroll-dependent, but a
        # fresh snapshot here — after however far the fill cascade's own
        # actions left the viewport — is the closest thing to a full,
        # deliberate top-to-bottom re-check of the page immediately before
        # the irreversible click, not a leftover mid-scroll state.
        try:
            await page.evaluate("window.scrollTo(0, 0)")
        except Exception:  # noqa: BLE001 - purely cosmetic, never block on it
            pass
        await page.wait_for_timeout(300)

        snapshot = await with_timeout(page.snapshot(), what="page.snapshot")
        xpath = find_submit_button(snapshot.formatted_tree, snapshot.xpath_map)
        if xpath is None:
            return SubmitResult(outcome="unknown", detail="submit button not found")

        # Hard rule (PLAN.md Day 4 Part H): a paused job never submits. This
        # is the closest-to-the-click checkpoint achievable — right before
        # the action that makes the application irreversible.
        await _check_paused_and_wait(application_id)

        await click_submit(page, xpath)
        await page.wait_for_timeout(2000)

        # A challenge can appear only after submission (e.g. email-based
        # verification triggered by the attempt itself).
        handled_2fa = await _handle_2fa_if_present(application_id, page)

        if handled_2fa:
            # Real, live-caught bug: the ORIGINAL submit click only
            # TRIGGERED the challenge (confirmed live on Figma: an
            # email-OTP step) — it did not finalize the application.
            # Entering the code alone isn't enough; the ATS's own form
            # still needs an explicit second submit/verify click. Without
            # this, the very next read_outcome() below sees neither a
            # confirmation nor a validation error (the code was accepted,
            # nothing is "wrong") and reports a false "unknown" outcome
            # while the application never actually completes. Scoped to
            # ONLY the post-2FA path — an ordinary no-2FA submit must
            # never risk clicking Submit twice.
            post_2fa_snapshot = await with_timeout(
                page.snapshot(), what="page.snapshot"
            )
            post_2fa_submit_xpath = find_submit_button(
                post_2fa_snapshot.formatted_tree, post_2fa_snapshot.xpath_map
            )
            if post_2fa_submit_xpath:
                await _log(
                    application_id,
                    "Clicking submit again after 2FA/verification",
                    tier="submit",
                )
                await click_submit(page, post_2fa_submit_xpath)
                await page.wait_for_timeout(2000)

        snapshot2 = await with_timeout(page.snapshot(), what="page.snapshot")
        result = read_outcome(snapshot2.formatted_tree)

        if result.outcome == "completed":
            await _log(
                application_id,
                f"Submission confirmed: {result.detail}",
                tier="submit",
            )
            return result

        # The ATS's own error location beats our own click-success
        # bookkeeping — see _repair_unhandled_fields's `also_target`
        # docstring for why this exists: `_unhandled_labels` alone has
        # repeatedly reported "0 unhandled" on runs that still failed
        # this exact validation error. Read regardless of outcome type
        # (validation_error specifically names fields; other non-complete
        # outcomes may not, but an empty set here is harmless).
        page_reported_invalid = set(find_invalid_field_labels(snapshot2.formatted_tree))
        if page_reported_invalid:
            await _log(
                application_id,
                "ATS flagged these field(s) as invalid directly on the "
                "page: " + ", ".join(sorted(page_reported_invalid)),
                level="warn",
                tier="submit",
            )

        is_last_attempt = attempt == MAX_SUBMIT_ATTEMPTS - 1
        if is_last_attempt:
            await _log(
                application_id,
                f"Submission outcome unclear after clicking submit "
                f"(result: {result.outcome}{': ' + result.detail if result.detail else ''})",
                level="warn",
                tier="submit",
            )
            return result

        await _log(
            application_id,
            f"{result.outcome} after submit: {result.detail or 'no confirmation seen'} "
            "— running one targeted repair pass and retrying",
            level="warn",
            tier="submit",
        )
        if _unhandled_labels(cascade) or page_reported_invalid:
            cascade = await _repair_unhandled_fields(
                application_id,
                sh,
                page,
                profile_dict,
                profile_id,
                cascade,
                also_target=page_reported_invalid,
            )

        # One attempt left after this one: broaden escalation to EVERY
        # still-unhandled field, not just ones flagged required — this is
        # the last chance before a fully-automated give-up, and the ATS
        # is what actually decides whether the application goes through,
        # not our own guess about which fields matter.
        is_last_chance_before_final_attempt = attempt == MAX_SUBMIT_ATTEMPTS - 2
        escalate_target = page_reported_invalid | (
            _unhandled_labels(cascade) if is_last_chance_before_final_attempt else set()
        )
        await _escalate_unhandled_fields_if_any(
            application_id, cascade, also_target=escalate_target
        )
        continue

    # Defensive only — the loop's `is_last_attempt` branch always returns
    # on its final iteration, so this is never actually reached; kept as
    # a safety net rather than relying on that being provably exhaustive.
    return SubmitResult(outcome="unknown", detail="exhausted submit retries")


async def _resolve_captcha_if_present(application_id: str, page) -> None:
    outcome = await resolve_captcha(page)
    if outcome.status == "not_present":
        return
    if outcome.status == "solved":
        await _log(application_id, f"CAPTCHA solved ({outcome.detail})", tier="captcha")
        return
    if outcome.status == "no_key":
        await _log(
            application_id,
            "CAPTCHA detected but TWOCAPTCHA_API_KEY is not configured — left unsolved",
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
    if await wait_for_resume_or_cancel(application_id) == "cancelled":
        raise ApplicationCancelled
    await _resume_from_pause(application_id)
    await _log(application_id, "Resumed after manual CAPTCHA handling")


TWOFA_POLL_INTERVAL_SECONDS = 5
TWOFA_TIMEOUT_SECONDS = 10 * 60


async def _handle_2fa_if_present(application_id: str, page) -> bool:
    """
    Real gap this fixes: this used to pause and block on
    `wait_for_resume_or_cancel` with NO timeout and NO re-checking of the
    page — a completely silent, indefinite hang if nobody ever resolves
    the challenge (or if the ATS clears it on its own, e.g. a code sent by
    SMS/email that the applicant answers outside this browser entirely).
    Polls instead: every TWOFA_POLL_INTERVAL_SECONDS, check the resume/
    cancel events; on each poll tick with neither fired, re-snapshot the
    page and re-run detect_2fa — if the challenge is GONE, auto-resume
    without waiting for a human at all. A manual Resume via Live View
    still works at any point (checked every poll tick, not just at the
    deadline). If the challenge is still present after
    TWOFA_TIMEOUT_SECONDS with no manual resume either, raise
    TwoFactorTimeout so the run fails cleanly and the queue advances
    instead of being stranded forever — see that exception's own
    docstring.

    Returns whether a challenge was actually found and handled (True) vs
    a no-op (False) — the pre-submit caller (`_submit_and_verify`) uses
    this to decide whether the ORIGINAL submit click only triggered the
    challenge rather than finalizing anything, in which case a real
    ATS flow (confirmed live: Figma's own OTP-by-email step) needs an
    EXPLICIT second submit click after the code is entered. Scoped to
    True-only so an ordinary no-2FA submit never risks a double-click.
    """
    snapshot = await with_timeout(page.snapshot(), what="page.snapshot")
    if not detect_2fa(snapshot.formatted_tree):
        return False

    await _log(
        application_id,
        "2FA challenge detected — pausing for human input via live view "
        f"(auto-resuming if it clears on its own, checked every "
        f"{TWOFA_POLL_INTERVAL_SECONDS}s; giving up after "
        f"{TWOFA_TIMEOUT_SECONDS // 60} min)",
        level="warn",
    )
    await _pause_for_input(application_id, "2fa_required")

    elapsed = 0
    while True:
        outcome = await wait_for_resume_or_cancel(
            application_id, timeout=TWOFA_POLL_INTERVAL_SECONDS
        )
        if outcome == "cancelled":
            raise ApplicationCancelled
        if outcome == "resumed":
            await _resume_from_pause(application_id)
            await _log(application_id, "Resumed after 2FA")
            return True

        # outcome == "timeout" (a poll tick, not a failure) — check
        # whether the challenge cleared on its own.
        elapsed += TWOFA_POLL_INTERVAL_SECONDS
        snapshot = await with_timeout(page.snapshot(), what="page.snapshot")
        if not detect_2fa(snapshot.formatted_tree):
            await _resume_from_pause(application_id)
            await _log(application_id, "2FA challenge cleared — resuming automatically")
            return True

        if elapsed >= TWOFA_TIMEOUT_SECONDS:
            await _log(
                application_id,
                f"2FA challenge still present after {TWOFA_TIMEOUT_SECONDS // 60} "
                "min with no resume — giving up",
                level="error",
            )
            raise TwoFactorTimeout(
                f"2FA challenge unresolved after {TWOFA_TIMEOUT_SECONDS}s"
            )


async def _check_paused_and_wait(application_id: str) -> None:
    """User-pause checkpoint (Day 4 Part H). Unlike the 2FA/CAPTCHA pauses
    above, `apply_service.pause()` already set status=PAUSED itself via the
    API call that triggered this — the runner's only job here is to notice
    and block, not to set status."""
    if not is_paused(application_id):
        return
    await _log(application_id, "Paused by user — waiting to resume", level="warn")
    if await wait_for_resume_or_cancel(application_id) == "cancelled":
        raise ApplicationCancelled
    await _log(application_id, "Resumed by user")


async def _escalate_unhandled_fields_if_any(
    application_id: str,
    cascade: "FillCascadeResult",
    also_target: set[str] | None = None,
) -> None:
    """
    Real gap reported live, twice over:

    1. Some required fields are genuinely outside this pipeline's scope —
       e.g. 'Please read the arbitration agreement below', which asks the
       applicant to read an embedded legal document before answering, not
       just pick from options a model can infer from profile/resume data.
       No amount of retrying observe()/act() fixes that; it's a
       comprehension task, not a widget-resolution task.
    2. Widget SHAPES this pipeline doesn't have a strategy for at all —
       e.g. a typeahead-filtered combobox before the typeahead fallback
       existed, or whatever the next unmodeled shape turns out to be. The
       user's own framing: "today this textbox+dropdown was the reason
       the agent failed, tomorrow it'll be some other column" — rather
       than chase every individual widget shape as it's discovered, ANY
       field the automation genuinely cannot resolve after every strategy
       has been tried gets the same fallback CAPTCHA-escalation and 2FA
       already use: pause (NEEDS_INPUT) and hand the page to the user via
       Live View, instead of failing the whole application outright.

    `also_target` exists for the case our own `required` guess isn't the
    authoritative signal — most importantly, a field the ATS's OWN
    validation error is blocking submission on (`find_invalid_field_labels`
    in submit.py), regardless of whether we internally marked it required,
    and (on the last chance before a final give-up attempt) EVERY still-
    unhandled field regardless of required — the ATS is what decides
    whether the application actually goes through, not our own heuristic
    about which fields matter. Without `also_target`, only fields flagged
    `required` (`FormField.required`, set from the ATS's own '*' marker)
    trigger this — an unresolved OPTIONAL field with no other signal is
    left blank exactly as Tier 1/2 already leaves genuinely low-confidence
    fields, no need to interrupt a human for those.
    """
    unhandled = _unhandled_labels(cascade)
    required_unhandled = {f.label for f in cascade.fields if f.required and f.label in unhandled}
    escalate_labels = sorted(required_unhandled | (also_target or set()))
    if not escalate_labels:
        return

    await _log(
        application_id,
        f"{len(escalate_labels)} field(s) still unresolved after automated "
        "repair — pausing for manual input via live view: "
        + ", ".join(escalate_labels),
        level="warn",
    )
    await _pause_for_input(application_id, "manual_fields_required")
    if await wait_for_resume_or_cancel(application_id) == "cancelled":
        raise ApplicationCancelled
    await _resume_from_pause(application_id)
    await _log(application_id, "Resumed after manual field entry")


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
        snapshot = await with_timeout(page.snapshot(), what="page.snapshot")
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

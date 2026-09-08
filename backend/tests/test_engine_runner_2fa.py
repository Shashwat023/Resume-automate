import pytest

from app.domain import status as st
from app.models.db_models import Application, Job, Profile
from app.services.engine import runner


class FakePage:
    """snapshot() returns a fresh formatted_tree each call, taken in order
    from `trees` — lets a test script "2FA present" -> "2FA cleared"
    across the poll loop's repeated re-snapshots."""

    def __init__(self, trees: list[str]):
        self._trees = trees
        self.snapshot_calls = 0

    async def snapshot(self):
        tree = self._trees[min(self.snapshot_calls, len(self._trees) - 1)]
        self.snapshot_calls += 1
        return type("Snapshot", (), {"formatted_tree": tree})()


_TWOFA_TREE = "[1] textbox: Enter your one-time passcode\n"
_CLEAR_TREE = "[1] textbox: First Name\n"


async def _seed(async_session, monkeypatch):
    profile = Profile(full_name="Jordan Smith", email="j@example.com", phone="123")
    async_session.add(profile)
    await async_session.commit()
    await async_session.refresh(profile)

    job = Job(
        title="Engineer",
        company_name="Acme",
        location="Remote",
        status="active",
        apply_url="https://example.com/apply",
    )
    async_session.add(job)
    await async_session.commit()
    await async_session.refresh(job)

    application = Application(profile_id=profile.id, job_id=job.id, status=st.RUNNING)
    async_session.add(application)
    await async_session.commit()
    await async_session.refresh(application)

    class _CtxWrapper:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(runner, "async_session_factory", lambda: _CtxWrapper())
    return application


async def test_no_2fa_detected_is_a_noop(async_session, monkeypatch):
    application = await _seed(async_session, monkeypatch)
    page = FakePage([_CLEAR_TREE])

    handled = await runner._handle_2fa_if_present(application.id, page)

    await async_session.refresh(application)
    assert handled is False
    assert application.status == st.RUNNING
    assert page.snapshot_calls == 1


async def test_2fa_auto_resumes_when_challenge_clears_on_a_poll_tick(
    async_session, monkeypatch
):
    # Real gap this fixes: the old version blocked on a human forever —
    # this must notice the challenge is GONE (e.g. resolved via an SMS
    # code answered outside this browser) and continue on its own.
    application = await _seed(async_session, monkeypatch)
    page = FakePage([_TWOFA_TREE, _TWOFA_TREE, _CLEAR_TREE])

    calls = []

    async def _fake_wait(app_id, timeout=None):
        calls.append(timeout)
        return "timeout"  # every poll tick is a timeout — never a manual resume

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", _fake_wait)

    handled = await runner._handle_2fa_if_present(application.id, page)

    await async_session.refresh(application)
    assert handled is True
    assert application.status == st.RUNNING
    assert application.pause_reason is None
    assert len(calls) == 2  # two poll ticks before the third snapshot cleared
    assert page.snapshot_calls == 3  # initial detect + 2 poll re-checks


async def test_2fa_resumes_immediately_on_manual_resume(async_session, monkeypatch):
    application = await _seed(async_session, monkeypatch)
    page = FakePage([_TWOFA_TREE])

    async def _fake_wait(app_id, timeout=None):
        return "resumed"

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", _fake_wait)

    handled = await runner._handle_2fa_if_present(application.id, page)

    await async_session.refresh(application)
    assert handled is True
    assert application.status == st.RUNNING
    assert application.pause_reason is None
    # Manual resume must not re-snapshot to check whether it cleared —
    # the human already confirmed it by resuming.
    assert page.snapshot_calls == 1


async def test_2fa_cancellation_raises_application_cancelled(
    async_session, monkeypatch
):
    application = await _seed(async_session, monkeypatch)
    page = FakePage([_TWOFA_TREE])

    async def _fake_wait(app_id, timeout=None):
        return "cancelled"

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", _fake_wait)

    with pytest.raises(runner.ApplicationCancelled):
        await runner._handle_2fa_if_present(application.id, page)


async def test_2fa_raises_timeout_after_deadline_with_challenge_still_present(
    async_session, monkeypatch
):
    # Real gap this fixes: a 2FA challenge nobody ever resolves used to
    # strand the run (and, via the per-profile lock, every later
    # application for that profile) forever. Must fail cleanly instead.
    application = await _seed(async_session, monkeypatch)
    page = FakePage([_TWOFA_TREE])  # never clears
    monkeypatch.setattr(runner, "TWOFA_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(runner, "TWOFA_POLL_INTERVAL_SECONDS", 5)

    async def _fake_wait(app_id, timeout=None):
        return "timeout"

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", _fake_wait)

    with pytest.raises(runner.TwoFactorTimeout):
        await runner._handle_2fa_if_present(application.id, page)

    await async_session.refresh(application)
    # Left in NEEDS_INPUT here — the top-level except Exception in
    # run_application (not exercised by this unit test) is what marks it
    # FAILED and releases the profile lock.
    assert application.status == st.NEEDS_INPUT


# ---- _submit_and_verify: re-click submit after a 2FA challenge resolves ----


class FakeSubmitPage:
    """snapshot() returns trees (and matching xpath_maps) from a fixed
    sequence, one per call — models the real ordering inside
    _submit_and_verify's loop: initial find-submit snapshot, then
    _handle_2fa_if_present's own detect snapshot, then (if a challenge was
    handled) the post-2FA re-check snapshot, then the final read_outcome
    snapshot."""

    def __init__(self, trees_and_maps: list[tuple[str, dict]]):
        self._sequence = trees_and_maps
        self._index = 0
        self.click_calls: list[str] = []

    async def snapshot(self):
        tree, xmap = self._sequence[min(self._index, len(self._sequence) - 1)]
        self._index += 1
        return type("Snapshot", (), {"formatted_tree": tree, "xpath_map": xmap})()

    async def evaluate(self, expression):
        pass

    async def wait_for_timeout(self, ms):
        pass

    def locator(self, xpath):
        page = self

        class _Locator:
            async def click(self):
                page.click_calls.append(xpath)

        return _Locator()


_SUBMIT_TREE_1 = "[1] button: Submit Application\n"
_OTP_TREE = "[2] textbox: Enter your one-time passcode\n"
_SUBMIT_TREE_2 = "[3] button: Submit Application\n"
_CONFIRMATION_TREE = "[4] StaticText: Thank you for applying\n"


async def _seed_with_job_and_cascade(async_session, monkeypatch):
    from app.services.engine.tier0_harvest import HarvestResult
    from app.services.engine.tier1_map import Tier1Result
    from app.services.engine.tier2_resolve import Tier2Result
    from app.services.engine.runner import FillCascadeResult

    application = await _seed(async_session, monkeypatch)
    cascade = FillCascadeResult(
        fields=[],
        tier0=HarvestResult(filled=[], unmatched=[], errored=[]),
        tier1=Tier1Result(
            filled=[],
            from_library=[],
            for_tier2=[],
            low_confidence_filled=[],
            unanswered=[],
            errored=[],
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        ),
        tier2=Tier2Result(resolved=[], errored=[]),
    )
    return application, cascade


async def test_submit_clicks_again_after_2fa_resolves_before_reading_outcome(
    async_session, monkeypatch
):
    # Real, live-caught bug: Figma's own email-OTP step only gets
    # TRIGGERED by the original submit click — it doesn't finalize
    # anything. Entering the code (2FA resumed) isn't enough; the ATS's
    # form still needs an explicit second submit click. Without the fix,
    # read_outcome() sees neither a confirmation nor a validation error
    # here and the run ends with a false "unknown" while never actually
    # completing.
    application, cascade = await _seed_with_job_and_cascade(async_session, monkeypatch)
    page = FakeSubmitPage(
        [
            (_SUBMIT_TREE_1, {"1": "//button[@id='submit-1']"}),  # find submit (1st)
            (_OTP_TREE, {}),  # _handle_2fa_if_present's own detect snapshot
            (_SUBMIT_TREE_2, {"3": "//button[@id='submit-2']"}),  # post-2FA re-check
            (_CONFIRMATION_TREE, {}),  # final read_outcome
        ]
    )

    async def _fake_resolve_captcha(page):
        from app.services.captcha.service import CaptchaOutcome

        return CaptchaOutcome(status="not_present")

    async def _fake_wait(app_id, timeout=None):
        return "resumed"

    monkeypatch.setattr(runner, "resolve_captcha", _fake_resolve_captcha)
    monkeypatch.setattr(runner, "is_paused", lambda app_id: False)
    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", _fake_wait)

    result = await runner._submit_and_verify(
        application.id,
        sh=None,
        page=page,
        profile_dict={},
        profile_id=1,
        resume_file_path=None,
        cascade=cascade,
    )

    assert result.outcome == "completed"
    # Both the original AND the post-2FA submit buttons must have been
    # clicked, in order.
    assert page.click_calls == ["//button[@id='submit-1']", "//button[@id='submit-2']"]


async def test_submit_does_not_reclick_when_no_2fa_challenge_appears(
    async_session, monkeypatch
):
    # Guard against a regression in the other direction: an ordinary,
    # no-2FA submit must NEVER click Submit twice.
    application, cascade = await _seed_with_job_and_cascade(async_session, monkeypatch)
    page = FakeSubmitPage(
        [
            (_SUBMIT_TREE_1, {"1": "//button[@id='submit-1']"}),  # find submit
            (_CONFIRMATION_TREE, {}),  # _handle_2fa_if_present's detect: no 2FA
            (_CONFIRMATION_TREE, {}),  # final read_outcome
        ]
    )

    async def _fake_resolve_captcha(page):
        from app.services.captcha.service import CaptchaOutcome

        return CaptchaOutcome(status="not_present")

    monkeypatch.setattr(runner, "resolve_captcha", _fake_resolve_captcha)
    monkeypatch.setattr(runner, "is_paused", lambda app_id: False)

    result = await runner._submit_and_verify(
        application.id,
        sh=None,
        page=page,
        profile_dict={},
        profile_id=1,
        resume_file_path=None,
        cascade=cascade,
    )

    assert result.outcome == "completed"
    assert page.click_calls == ["//button[@id='submit-1']"]


# ---- submit escalation: never give up without a human-assisted final try ----


_VALIDATION_TREE = "[2] StaticText: Please enter a value\n"


async def test_final_submit_attempt_is_human_assisted_before_giving_up(
    async_session, monkeypatch
):
    # Real gap this fixes: an OPTIONAL field ("Location (City)") that
    # nothing in the pipeline could resolve used to be silently left
    # blank forever — the automated repair pass on attempt 0 only
    # escalates fields flagged `required`, and the final attempt used to
    # give up outright with no escalation at all. Per the user's own
    # framing, the agent must never fail and stop on its own while a
    # human fix is still possible: the second-to-last attempt now
    # broadens escalation to EVERY unhandled field regardless of the
    # required flag, and only a genuinely human-assisted final attempt
    # that STILL fails ends the run.
    from app.services.engine.tier0_harvest import FormField, HarvestResult
    from app.services.engine.tier1_map import Tier1Result
    from app.services.engine.tier2_resolve import Tier2Result
    from app.services.engine.runner import FillCascadeResult

    application = await _seed(async_session, monkeypatch)
    unresolved_field = FormField(
        node_id="9",
        role="combobox",
        label="Location (City)",
        xpath=None,
        required=False,
    )
    cascade = FillCascadeResult(
        fields=[unresolved_field],
        tier0=HarvestResult(filled=[], unmatched=[], errored=[]),
        tier1=Tier1Result(
            filled=[],
            from_library=[],
            for_tier2=[],
            low_confidence_filled=[],
            unanswered=[],
            errored=[],
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        ),
        tier2=Tier2Result(
            resolved=[], errored=[("Location (City)", "no working strategy")]
        ),
    )

    page = FakeSubmitPage(
        [
            (_SUBMIT_TREE_1, {"1": "//button[@id='submit']"}),  # attempt 0: find submit
            (_VALIDATION_TREE, {}),  # attempt 0: 2fa-detect (none)
            (_VALIDATION_TREE, {}),  # attempt 0: read_outcome -> validation_error
            (_SUBMIT_TREE_1, {"1": "//button[@id='submit']"}),  # attempt 1: find submit
            (_VALIDATION_TREE, {}),  # attempt 1: 2fa-detect (none)
            (_VALIDATION_TREE, {}),  # attempt 1: read_outcome -> validation_error again
            (_SUBMIT_TREE_1, {"1": "//button[@id='submit']"}),  # attempt 2: find submit
            (_CONFIRMATION_TREE, {}),  # attempt 2: 2fa-detect (none)
            (_CONFIRMATION_TREE, {}),  # attempt 2: read_outcome -> completed
        ]
    )

    async def _fake_resolve_captcha(page):
        from app.services.captcha.service import CaptchaOutcome

        return CaptchaOutcome(status="not_present")

    async def _fake_repair(
        app_id, sh, page, profile_dict, profile_id, cascade, also_target=None
    ):
        return cascade  # no-op: nothing new gets resolved by repair either

    escalation_pauses: list[set] = []

    async def _fake_wait(app_id, timeout=None):
        return "resumed"

    real_escalate = runner._escalate_unhandled_fields_if_any

    async def _spying_escalate(app_id, cascade, also_target=None):
        escalation_pauses.append(also_target or set())
        await real_escalate(app_id, cascade, also_target=also_target)

    monkeypatch.setattr(runner, "resolve_captcha", _fake_resolve_captcha)
    monkeypatch.setattr(runner, "is_paused", lambda app_id: False)
    monkeypatch.setattr(runner, "_repair_unhandled_fields", _fake_repair)
    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", _fake_wait)
    monkeypatch.setattr(runner, "_escalate_unhandled_fields_if_any", _spying_escalate)

    result = await runner._submit_and_verify(
        application.id,
        sh=None,
        page=page,
        profile_dict={},
        profile_id=1,
        resume_file_path=None,
        cascade=cascade,
    )

    assert result.outcome == "completed"
    # Attempt 0's escalation call must NOT have targeted the unresolved
    # optional field (not required, no ATS-reported invalid label yet).
    assert "Location (City)" not in escalation_pauses[0]
    # Attempt 1 (the last chance before the final attempt) must have
    # broadened escalation to include it regardless of required.
    assert "Location (City)" in escalation_pauses[1]


async def test_final_attempt_still_failing_after_human_help_truly_gives_up(
    async_session, monkeypatch
):
    # Must not loop forever: a human-assisted final attempt that STILL
    # doesn't complete ends the run with the real failing result.
    application, cascade = await _seed_with_job_and_cascade(async_session, monkeypatch)
    page = FakeSubmitPage(
        [
            (_SUBMIT_TREE_1, {"1": "//button[@id='submit']"}),
            (_VALIDATION_TREE, {}),
            (_VALIDATION_TREE, {}),
            (_SUBMIT_TREE_1, {"1": "//button[@id='submit']"}),
            (_VALIDATION_TREE, {}),
            (_VALIDATION_TREE, {}),
            (_SUBMIT_TREE_1, {"1": "//button[@id='submit']"}),
            (_VALIDATION_TREE, {}),
            (_VALIDATION_TREE, {}),  # STILL validation_error on the final attempt
        ]
    )

    async def _fake_resolve_captcha(page):
        from app.services.captcha.service import CaptchaOutcome

        return CaptchaOutcome(status="not_present")

    async def _fake_repair(
        app_id, sh, page, profile_dict, profile_id, cascade, also_target=None
    ):
        return cascade

    async def _fake_wait(app_id, timeout=None):
        return "resumed"

    monkeypatch.setattr(runner, "resolve_captcha", _fake_resolve_captcha)
    monkeypatch.setattr(runner, "is_paused", lambda app_id: False)
    monkeypatch.setattr(runner, "_repair_unhandled_fields", _fake_repair)
    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", _fake_wait)

    result = await runner._submit_and_verify(
        application.id,
        sh=None,
        page=page,
        profile_dict={},
        profile_id=1,
        resume_file_path=None,
        cascade=cascade,
    )

    assert result.outcome == "validation_error"
    # Exactly 3 attempts (9 snapshots) — no infinite retrying.
    assert page._index == 9


# ---- every run closes its browser session, unconditionally ----
#
# Real, live-caught bug, corrected TWICE: first thought this only needed
# to apply to FAILED/CANCELLED runs — live-tested and found wrong.
# Confirmed against the Stagehand extension's own bundled service-worker
# JS: its runtime state machine is `created -> initialized -> closed`, ONE
# WAY, no reset — ANY application that reached Stagehand.create()
# permanently spends that Chrome process's extension for future use,
# success or failure alike. A cleanly COMPLETED run reproduced the exact
# same "Stagehand has already been initialized" failure on the very next
# application for that profile as a failed one did.


class _FakeChromeSession:
    browser = object()


async def test_failed_run_closes_the_browser_session(async_session, monkeypatch):
    application = await _seed(async_session, monkeypatch)

    class _CtxWrapper:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(runner, "async_session_factory", lambda: _CtxWrapper())

    async def _fake_get_or_launch(profile_key):
        return _FakeChromeSession()

    class _FakeStagehand:
        @staticmethod
        async def create(*, browser, model):
            raise RuntimeError("boom mid-run")

    close_calls = []

    async def _fake_close_session(profile_key):
        close_calls.append(profile_key)

    monkeypatch.setattr(runner, "get_or_launch", _fake_get_or_launch)
    monkeypatch.setattr(runner, "Stagehand", _FakeStagehand)
    monkeypatch.setattr(runner, "close_session", _fake_close_session)

    await runner.run_application(application.id)

    await async_session.refresh(application)
    assert application.status == "failed"
    # Closed while a session actually existed — not just called blindly
    # when get_or_launch() itself never returned one.
    assert close_calls == [str(application.profile_id)]


async def test_completed_run_also_closes_the_browser_session(
    async_session, monkeypatch
):
    # The corrected behavior, opposite of what an earlier version of this
    # test asserted: a cleanly completed run must ALSO close its session
    # — chrome_launcher.py's next `get_or_launch()` call for this profile
    # relaunches a genuinely fresh Chrome process regardless (see that
    # function's own docstring), so there's nothing to preserve here;
    # cookie/login continuity comes from reusing the same `user_data_dir`
    # on that fresh launch, not from keeping this process alive.
    application = await _seed(async_session, monkeypatch)

    class _CtxWrapper:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(runner, "async_session_factory", lambda: _CtxWrapper())

    close_calls = []

    async def _fake_close_session(profile_key):
        close_calls.append(profile_key)

    async def _fake_get_or_launch(profile_key):
        return _FakeChromeSession()

    class _FakeStagehand:
        @staticmethod
        async def create(*, browser, model):
            # Short-circuit the run to a clean "success" by marking the
            # application COMPLETED directly (as a real successful run
            # would have, deep inside the Chrome-touching block this test
            # doesn't need to fully drive) and raising a benign stop.
            application.status = "completed"
            await async_session.commit()
            raise runner.ApplicationCancelled

    monkeypatch.setattr(runner, "get_or_launch", _fake_get_or_launch)
    monkeypatch.setattr(runner, "Stagehand", _FakeStagehand)
    monkeypatch.setattr(runner, "close_session", _fake_close_session)

    await runner.run_application(application.id)

    await async_session.refresh(application)
    assert application.status == "completed"
    assert close_calls == [str(application.profile_id)]


async def test_session_is_closed_before_the_profile_lock_releases(
    async_session, monkeypatch
):
    # Real, live-caught RACE: an earlier version of this fix closed the
    # session in the function's OUTER finally, which only runs after
    # `async with profile_session(...)` has already exited and released
    # the per-profile lock. A second application already waiting on that
    # lock could acquire it and call get_or_launch() BEFORE this close
    # actually completed — reproducing the exact "already
    # attached"/"already initialized" failure the whole fix chain exists
    # to prevent. close_session() must run while the lock is STILL held.
    from app.worker.queue_runner import get_profile_lock

    application = await _seed(async_session, monkeypatch)

    class _CtxWrapper:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(runner, "async_session_factory", lambda: _CtxWrapper())

    async def _fake_get_or_launch(profile_key):
        return _FakeChromeSession()

    lock_state_at_close: list[bool] = []

    async def _fake_close_session(profile_key):
        lock_state_at_close.append(get_profile_lock(profile_key).locked())

    class _FakeStagehand:
        @staticmethod
        async def create(*, browser, model):
            raise RuntimeError("boom mid-run")

    monkeypatch.setattr(runner, "get_or_launch", _fake_get_or_launch)
    monkeypatch.setattr(runner, "Stagehand", _FakeStagehand)
    monkeypatch.setattr(runner, "close_session", _fake_close_session)

    await runner.run_application(application.id)

    assert lock_state_at_close == [True]
    assert get_profile_lock(str(application.profile_id)).locked() is False

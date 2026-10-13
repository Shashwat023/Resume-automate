"""Batch 6: human pauses must not wait for a manual Resume when the page
has already cleared, and must not trigger when nothing needs a human."""

import pytest

from app.services.engine import runner
from app.services.engine.tier0_harvest import FormField, HarvestResult
from app.services.engine.tier1_map import Tier1Result
from app.services.engine.tier2_resolve import Tier2Result


class _Page:
    """Scripted snapshots; `evaluate` returns the scripted DOM answer."""

    def __init__(
        self, trees, evaluate_result=False, values=None, url="https://x.test/a"
    ):
        self._trees = trees
        self._i = 0
        self.evaluate_result = evaluate_result
        self.evaluate_scripts: list[str] = []
        self.values = values or {}
        self._url = url

    async def snapshot(self):
        tree, xmap = self._trees[min(self._i, len(self._trees) - 1)]
        self._i += 1
        return type("S", (), {"formatted_tree": tree, "xpath_map": xmap})()

    async def evaluate(self, script):
        self.evaluate_scripts.append(script)
        return self.evaluate_result

    async def url(self):
        return self._url

    async def wait_for_timeout(self, _ms):
        pass

    def locator(self, xpath):
        page = self

        class _L:
            async def input_value(self):
                return page.values.get(xpath, "")

        return _L()


@pytest.fixture
def pause_env(monkeypatch):
    log: list[str] = []
    state = {"resumed": 0}

    async def noop_input(*_a, **_k):
        return None

    async def resume(_id):
        state["resumed"] += 1

    async def fake_log(_id, message, **_k):
        log.append(message)

    monkeypatch.setattr(runner, "_pause_for_input", noop_input)
    monkeypatch.setattr(runner, "_resume_from_pause", resume)
    monkeypatch.setattr(runner, "_log", fake_log)
    return log, state


# ---- _pause_for_human ----


async def test_human_pause_auto_resumes_when_condition_clears(monkeypatch, pause_env):
    log, state = pause_env
    waits: list[dict] = []

    async def fake_wait(_id, timeout=None):
        waits.append({"timeout": timeout})
        return "timeout"

    answers = iter([False, True])

    async def cleared():
        return next(answers)

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", fake_wait)

    await runner._pause_for_human(
        "a", "manual_fields_required", "Resumed", page=object(), cleared=cleared
    )

    assert len(waits) == 2
    assert all(w["timeout"] == runner.HUMAN_POLL_SECONDS for w in waits)
    assert state["resumed"] == 1
    assert any("cleared on its own" in m for m in log)


async def test_human_pause_without_cleared_callback_keeps_waiting(
    monkeypatch, pause_env
):
    log, state = pause_env
    calls: list[dict] = []

    async def fake_wait(_id, **kwargs):
        calls.append(kwargs)
        return "resumed"

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", fake_wait)

    await runner._pause_for_human("a", "x", "Resumed by user")

    assert calls == [{}]  # indefinite wait: no timeout argument
    assert state["resumed"] == 1
    assert log == ["Resumed by user"]


async def test_cancel_during_auto_resume_poll_raises_application_cancelled(
    monkeypatch, pause_env
):
    async def fake_wait(_id, timeout=None):
        return "cancelled"

    async def cleared():
        raise AssertionError("must not poll after cancel")

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", fake_wait)

    with pytest.raises(runner.ApplicationCancelled):
        await runner._pause_for_human("a", "x", "m", page=object(), cleared=cleared)


async def test_cleared_callback_errors_keep_the_handoff(monkeypatch, pause_env):
    _log, state = pause_env
    outcomes = iter(["timeout", "resumed"])

    async def fake_wait(_id, timeout=None):
        return next(outcomes)

    async def cleared():
        raise RuntimeError("page gone")

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", fake_wait)

    await runner._pause_for_human("a", "x", "m", page=object(), cleared=cleared)

    assert state["resumed"] == 1  # only the explicit resume ended the pause


# ---- cleared predicates ----


async def test_manual_navigation_pause_auto_resumes_when_fingerprint_changes():
    empty = "[1] heading: Loading\n"
    paused_fp = runner._page_fingerprint("https://x.test/a", empty)

    still_empty = _Page([(empty, {})])
    assert await runner._navigation_pause_cleared(still_empty, paused_fp) is False

    new_page = _Page(
        [("[1] heading: My Information\n[2] textbox: First Name\n", {"2": "//f"})]
    )
    assert await runner._navigation_pause_cleared(new_page, paused_fp) is True


async def test_account_gate_pause_auto_resumes_when_gate_disappears():
    gate = "[3] heading: Create Account\n[4] textbox: Password\n"
    page = _Page([(gate, {}), ("[1] textbox: First Name\n", {})], evaluate_result=False)

    assert await runner._account_gate_cleared(page) is False
    assert await runner._account_gate_cleared(page) is True


async def test_captcha_cleared_uses_page_level_detection(monkeypatch):
    async def none_found(_page):
        return None

    monkeypatch.setattr(runner, "detect_captcha", none_found)
    assert await runner._captcha_cleared(object()) is True

    async def found(_page):
        return object()

    monkeypatch.setattr(runner, "detect_captcha", found)
    assert await runner._captcha_cleared(object()) is False


# ---- transient empty page ----


async def test_empty_page_is_retried_before_pausing_for_navigation(
    monkeypatch, pause_env
):
    log, _ = pause_env
    monkeypatch.setattr(runner, "EMPTY_PAGE_RETRY_MS", 0)
    page = _Page(
        [
            ("[1] heading: Loading\n", {}),
            ("[2] textbox: First Name\n", {"2": "//first"}),
        ]
    )

    result = await runner._retry_empty_page("a", page)

    assert result is not None
    _snapshot, fields, submit = result
    assert [f.label for f in fields] == ["First Name"]
    assert submit is None
    assert any("Page looked empty" in m for m in log)


async def test_empty_page_that_stays_empty_still_pauses(monkeypatch, pause_env):
    monkeypatch.setattr(runner, "EMPTY_PAGE_RETRY_MS", 0)
    page = _Page([("[1] heading: Loading\n", {})])

    assert await runner._retry_empty_page("a", page) is None
    assert page._i == runner.EMPTY_PAGE_RETRIES


# ---- escalation verifies real field state ----


def _cascade(fields):
    return runner.FillCascadeResult(
        fields=fields,
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


async def test_escalation_skips_fields_that_already_have_a_value(
    monkeypatch, pause_env
):
    paused: list[str] = []

    async def fake_pause(_id, reason, _m, **_k):
        paused.append(reason)

    monkeypatch.setattr(runner, "_pause_for_human", fake_pause)
    field = FormField("1", "textbox", "Preferred Name", "//pref", required=True)
    page = _Page([("", {})], values={"//pref": "Jordan"})

    await runner._escalate_unhandled_fields_if_any("a", _cascade([field]), page=page)

    assert paused == []


async def test_escalation_still_pauses_when_a_required_field_is_really_empty(
    monkeypatch, pause_env
):
    paused: list[str] = []

    async def fake_pause(_id, reason, _m, **_k):
        paused.append(reason)

    monkeypatch.setattr(runner, "_pause_for_human", fake_pause)
    field = FormField("1", "textbox", "Preferred Name", "//pref", required=True)
    page = _Page([("", {})], values={"//pref": ""})

    await runner._escalate_unhandled_fields_if_any("a", _cascade([field]), page=page)

    assert paused == ["manual_fields_required"]


# ---- account gate false positives ----


async def test_account_gate_ignores_hidden_password_input_and_header_sign_in_link():
    tree = "[1] link: Sign In\n[2] textbox: First Name\n"
    page = _Page([(tree, {})], evaluate_result=False)

    assert await runner._account_gate_present(page, tree) is False
    script = page.evaluate_scripts[0]
    assert "offsetParent" in script
    assert "closest('form,[role=dialog]')" in script
    assert "aria-hidden" in script


async def test_account_gate_still_detected_for_visible_create_account_form():
    tree = "[3] heading: Create Account\n[4] textbox: Password\n"
    page = _Page([(tree, {})])

    assert await runner._account_gate_present(page, tree) is True

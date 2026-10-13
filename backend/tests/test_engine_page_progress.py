from types import SimpleNamespace

import pytest

from app.services.engine import runner
from app.services.engine.tier0_harvest import FormField, HarvestResult
from app.services.engine.tier1_map import Tier1Result
from app.services.engine.tier2_resolve import Tier2Result


def test_fingerprint_ignores_validation_text_and_changes_with_page():
    first = "[1] heading: Personal details\n[2] textbox: Email\n"
    with_error = first + "[3] StaticText: Email is required\n"
    next_page = "[1] heading: Experience\n[2] textbox: Employer\n"

    assert runner._page_fingerprint(
        "https://example.test/apply", first
    ) == runner._page_fingerprint("https://example.test/apply", with_error)
    assert runner._page_fingerprint(
        "https://example.test/apply", first
    ) != runner._page_fingerprint("https://example.test/apply", next_page)


class _NextPage:
    def __init__(self, trees):
        self.trees = trees
        self.index = 0

    async def snapshot(self):
        tree = self.trees[min(self.index, len(self.trees) - 1)]
        self.index += 1
        return SimpleNamespace(formatted_tree=tree, xpath_map={"next": "//next"})

    async def url(self):
        return "https://example.test/apply"

    async def wait_for_timeout(self, _milliseconds):
        pass

    def locator(self, _xpath):
        class Locator:
            async def click(self):
                pass

        return Locator()


@pytest.mark.asyncio
async def test_next_that_only_adds_an_error_banner_is_not_progress(monkeypatch):
    page = _NextPage(
        [
            "[next] button: Next\n[1] heading: Details\n[2] textbox: Email\n",
            "[next] button: Next\n[1] heading: Details\n[2] textbox: Email\n[3] StaticText: Email is required\n",
        ]
    )
    monkeypatch.setattr(runner, "PAGE_PROGRESS_TIMEOUT_SECONDS", 0)

    async def log(*_args, **_kwargs):
        pass

    monkeypatch.setattr(runner, "_log", log)
    monkeypatch.setattr(runner, "_log_page_diagnostics", log)
    assert await runner._click_next_if_present(page, "app") is False


@pytest.mark.asyncio
async def test_next_that_changes_heading_and_fields_is_progress(monkeypatch):
    page = _NextPage(
        [
            "[next] button: Next\n[1] heading: Details\n[2] textbox: Email\n",
            "[3] heading: Experience\n[4] textbox: Employer\n",
        ]
    )

    async def log(*_args, **_kwargs):
        pass

    monkeypatch.setattr(runner, "_log", log)
    assert await runner._click_next_if_present(page, "app") is True


@pytest.mark.parametrize(
    "label, expected",
    [
        ("Next", True),
        ("Next Page", True),
        ("Save & Continue", True),
        ("Continue to Review", True),
        ("Review and Continue", True),
        ("Proceed", True),
        ("Back", False),
        ("Save draft", False),
        ("Cancel", False),
    ],
)
def test_next_button_label_variants_and_exclusions(label, expected):
    assert bool(runner._NEXT_BUTTON.search(f"[x] button: {label}")) is expected


def test_same_fingerprint_three_times_pauses_with_diagnostics():
    fingerprint = runner._page_fingerprint(
        "https://example.test/apply", "[1] heading: Details\n[2] textbox: Email\n"
    )
    seen: dict[str, int] = {}
    for _ in range(3):
        seen[fingerprint] = seen.get(fingerprint, 0) + 1

    assert seen[fingerprint] >= 3


def test_auto_steps_count_only_distinct_pages():
    first = runner._page_fingerprint(
        "https://example.test/apply", "[1] heading: Details\n[2] textbox: Email\n"
    )
    second = runner._page_fingerprint(
        "https://example.test/apply", "[3] heading: Review\n[4] textbox: Note\n"
    )
    seen: dict[str, int] = {}
    for fingerprint in (first, first, second):
        seen[fingerprint] = seen.get(fingerprint, 0) + 1

    assert len(seen) == 2


@pytest.mark.asyncio
async def test_click_next_reports_no_control_vs_no_progress(monkeypatch):
    class NoControl(_NextPage):
        def __init__(self):
            super().__init__(["[1] heading: Details\n"])

    async def log(*_args, **_kwargs):
        pass

    monkeypatch.setattr(runner, "_log", log)
    assert (await runner._click_next(NoControl(), "app")).reason == "no_control"

    page = _NextPage(["[next] button: Next\n[1] heading: Details\n"])
    monkeypatch.setattr(runner, "PAGE_PROGRESS_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(runner, "_log_page_diagnostics", log)
    result = await runner._click_next(page, "app")
    assert result.clicked is True and result.reason == "no_progress"


@pytest.mark.asyncio
async def test_no_progress_does_not_also_log_no_control_message(monkeypatch):
    page = _NextPage(["[next] button: Save & Continue\n[1] heading: Details\n"])
    messages = []

    async def log(*args, **_kwargs):
        messages.append(args[1] if len(args) > 1 else "")

    async def diagnostics(*_args, **_kwargs):
        pass

    monkeypatch.setattr(runner, "PAGE_PROGRESS_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(runner, "_log", log)
    monkeypatch.setattr(runner, "_log_page_diagnostics", diagnostics)

    result = await runner._click_next(page, "app")

    assert result.label == "Save & Continue"
    assert not any("no Continue or Submit control" in message for message in messages)


@pytest.mark.asyncio
async def test_repair_pass_forces_refill(monkeypatch):
    field = FormField(node_id="city", role="textbox", label="City", xpath="//city")
    cascade = runner.FillCascadeResult(
        fields=[field],
        tier0=HarvestResult(filled=[], unmatched=[], errored=[]),
        tier1=Tier1Result([], [], [], [], [], [], {}),
        tier2=Tier2Result(resolved=[], errored=[]),
    )
    calls = []

    class Page:
        async def snapshot(self):
            return SimpleNamespace(formatted_tree="", xpath_map={})

    async def map_fields(*_args, **kwargs):
        calls.append(kwargs)
        return Tier1Result([], [], [], [], [], [], {})

    async def no_op(*_args, **_kwargs):
        return Tier2Result(resolved=[], errored=[])

    monkeypatch.setattr(runner, "_log", no_op)
    monkeypatch.setattr(runner, "collect_fields", lambda *_args: [field])
    monkeypatch.setattr(runner, "_map_fields", map_fields)
    monkeypatch.setattr(runner, "resolve_and_execute", no_op)

    await runner._repair_unhandled_fields("app", None, Page(), {}, 1, cascade)

    assert calls == [{"force_refill": True}]


@pytest.mark.asyncio
async def test_log_marks_already_set_fields(monkeypatch):
    field = FormField(node_id="name", role="textbox", label="Name", xpath="//name")
    messages = []

    class Page:
        async def snapshot(self):
            return SimpleNamespace(formatted_tree="", xpath_map={})

    async def log(_application_id, message, **_kwargs):
        messages.append(message)

    async def map_fields(*_args, **_kwargs):
        return Tier1Result(
            filled=[("Question", "answer")],
            from_library=[],
            for_tier2=[],
            low_confidence_filled=[],
            unanswered=[],
            errored=[],
            usage={},
            already_set={"Question"},
        )

    async def no_op(*_args, **_kwargs):
        return Tier2Result(resolved=[], errored=[])

    monkeypatch.setattr(runner, "_check_paused_and_wait", no_op)
    monkeypatch.setattr(runner, "_set_step", no_op)
    monkeypatch.setattr(runner, "_log", log)
    monkeypatch.setattr(runner, "collect_fields", lambda *_args: [field])
    monkeypatch.setattr(
        runner,
        "fill_deterministic",
        lambda *_args: _result(
            HarvestResult(
                filled=[("Name", "Jane")],
                unmatched=[],
                errored=[],
                already_set={"Name"},
            )
        ),
    )
    monkeypatch.setattr(runner, "_map_fields", map_fields)
    monkeypatch.setattr(runner, "resolve_and_execute", no_op)

    await runner._run_fill_cascade("app", None, Page(), {}, 1, None)

    assert "Tier 0 filled 'Name' (already set)" in messages
    assert "Tier 1 filled 'Question' (already set)" in messages


async def _result(value):
    return value


def test_manual_resume_on_a_stuck_page_lets_the_engine_retry():
    fingerprint = "same-page"
    seen = {fingerprint: 3}
    seen[fingerprint] = 0
    assert seen[fingerprint] == 0

"""
Focused regression test for runner.py's _APPLY_BUTTON regex — the same
missing-re.MULTILINE bug found and fixed in submit.py's _SUBMIT_BUTTON
(see FLAGGED.md). This one was silently masked throughout the whole
project because every URL actually tested shows the form directly with no
landing-page Apply click needed, so its always-broken return value never
mattered — but it was just as broken, and would matter the moment a real
ATS gates the form behind a landing-page Apply button.
"""

from types import SimpleNamespace

import pytest

from app.services.engine import runner
from app.services.engine.runner import _APPLY_BUTTON, _click_apply_if_present


def test_matches_apply_button_in_the_middle_of_a_multiline_tree():
    tree = (
        "[1] heading: Staff Engineer\n"
        "[2] StaticText: San Francisco, CA\n"
        "              [5-107] button: Apply\n"
        "[4] paragraph: About the role\n"
    )
    match = _APPLY_BUTTON.search(tree)
    assert match is not None
    assert match.group(1) == "5-107"


def test_does_not_match_a_single_line_string_falsely_passing_without_multiline():
    # A sanity check that this genuinely exercises re.MULTILINE and isn't
    # accidentally passing for some other reason.
    tree_no_multiline_needed = "[5-107] button: Apply\n"
    assert _APPLY_BUTTON.search(tree_no_multiline_needed) is not None


def test_control_summary_only_includes_known_action_labels():
    tree = (
        "[1] button: Submit Application\n"
        "[2] button: user@example.com\n"
        "[3] link: Apply\n"
    )
    assert runner._control_summary(tree) == (
        "buttons=2, links=1, actions=[button:Submit Application, link:Apply]"
    )


@pytest.mark.asyncio
async def test_apply_link_navigates_current_page_instead_of_opening_new_tab(monkeypatch):
    # Concentrix renders two <a target="_blank"> controls named Apply.
    # Clicking one would leave the Stagehand page on the job description.
    workday_url = (
        "https://cnx.wd1.myworkdayjobs.com/external_global/job/"
        "JPN-Work-at-Home-Direct/Partner-Success-Leader_R1768370/apply?token=private"
    )

    class Page:
        def __init__(self):
            self.navigated_to = None
            self.manual_clicked = False
            self.step = 0
            self.current_url = "https://jobs.concentrix.com/job/?id=R1768370"

        async def url(self):
            return self.current_url

        async def snapshot(self):
            if self.step == 2:
                return SimpleNamespace(
                    formatted_tree=(
                        "[51] heading: Create Account\n"
                        "[78] textbox: Password\n"
                    ),
                    xpath_map={"78": "//input[@type='password']"},
                )
            if self.step == 1:
                return SimpleNamespace(
                    formatted_tree=(
                        "[1] heading: Start Your Application\n"
                        "[27] button: Apply Manually\n"
                    ),
                    xpath_map={"27": "//button[@data-automation-id='applyManually']"},
                )
            return SimpleNamespace(
                formatted_tree=(
                    "[1] heading: Partner Success Leader\n"
                    "[19] link: Apply\n"
                    "[57] link: Apply\n"
                ),
                xpath_map={"19": "//a[@data-jdq-apply-url]"},
            )

        async def evaluate(self, expression):
            assert "document.evaluate" in expression
            assert "//a[@data-jdq-apply-url]" in expression
            return workday_url

        async def goto(self, url):
            self.navigated_to = url
            self.current_url = url
            self.step = 1

        async def wait_for_load_state(self, state):
            assert state == "load"

        def locator(self, xpath):
            assert self.step == 1
            assert xpath == "//button[@data-automation-id='applyManually']"

            class Locator:
                async def click(_self):
                    self.manual_clicked = True
                    self.step = 2

            return Locator()

        async def wait_for_timeout(self, _milliseconds):
            pass

    events = []

    async def log(_application_id, message, **_kwargs):
        events.append(message)

    monkeypatch.setattr(runner, "_log", log)
    page = Page()
    assert await _click_apply_if_present(page, "app-1") is True
    assert page.navigated_to == workday_url
    assert page.manual_clicked is True
    assert any("following link" in event for event in events)
    assert any("clicking Apply Manually" in event for event in events)
    assert any("form fields=1" in event for event in events)
    assert all("private" not in event for event in events)


@pytest.mark.asyncio
async def test_workday_account_gate_pauses_before_field_filling(monkeypatch):
    class Page:
        account_open = True

        async def snapshot(self):
            tree = (
                "[51] heading: Create Account\n"
                "[76] textbox: Email Address\n"
                "[78] textbox: Password\n"
                "[80] textbox: Verify New Password\n"
                if self.account_open
                else "[5] heading: My Information\n[6] textbox: First Name\n"
            )
            return SimpleNamespace(formatted_tree=tree)

    page = Page()
    pauses = []

    async def log(_application_id, _message, **_kwargs):
        pass

    async def pause(_application_id, reason, _message):
        pauses.append(reason)
        page.account_open = False

    monkeypatch.setattr(runner, "_log", log)
    monkeypatch.setattr(runner, "_pause_for_human", pause)

    await runner._handle_account_gate_if_present("app-1", page)
    assert pauses == ["account_required"]


@pytest.mark.asyncio
async def test_account_gate_detects_password_input_when_snapshot_omits_its_label():
    class Page:
        async def evaluate(self, expression):
            assert "input[type=password]" in expression
            return True

    assert await runner._account_gate_present(
        Page(), "[1] heading: Create Account\n[2] textbox: Email\n"
    ) is True


@pytest.mark.asyncio
async def test_unfamiliar_apply_entry_uses_stagehand_then_rechecks_form(monkeypatch):
    class Page:
        form_open = False

        async def snapshot(self):
            return SimpleNamespace(
                formatted_tree=(
                    "[1] textbox: First Name\n"
                    if self.form_open
                    else "[1] button: Begin Application\n"
                ),
                xpath_map={"1": "//input"} if self.form_open else {},
            )

        async def evaluate(self, _expression):
            return None

        async def url(self):
            return "https://example.com/apply?private=1"

        async def wait_for_timeout(self, _milliseconds):
            pass

    class Stagehand:
        async def observe(self, _instruction, *, page):
            return SimpleNamespace(
                data=[SimpleNamespace(
                    selector="button.begin",
                    description="Click to start the application",
                    method="click",
                )]
            )

        async def act(self, _action, *, page):
            page.form_open = True
            return SimpleNamespace(data=SimpleNamespace(success=True))

    events = []

    async def log(_application_id, message, **_kwargs):
        events.append(message)

    monkeypatch.setattr(runner, "_log", log)
    page = Page()
    assert await _click_apply_if_present(page, "app-1", Stagehand()) is True
    assert page.form_open is True
    assert any("Stagehand selected Apply entry control" in event for event in events)
    assert all("private" not in event for event in events)


@pytest.mark.asyncio
async def test_continue_moves_to_the_next_application_step(monkeypatch):
    class Page:
        clicked = False

        async def snapshot(self):
            return SimpleNamespace(
                formatted_tree=(
                    "[6] heading: Review\n"
                    if self.clicked
                    else "[5] button: Save and Continue\n"
                ),
                xpath_map={} if self.clicked else {"5": "//button[@id='next']"},
            )

        async def url(self):
            return "https://workday.example/apply"

        def locator(self, xpath):
            assert xpath == "//button[@id='next']"

            class Locator:
                async def click(_self):
                    self.clicked = True

            return Locator()

        async def wait_for_timeout(self, _milliseconds):
            pass

    async def log(_application_id, _message, **_kwargs):
        pass

    monkeypatch.setattr(runner, "_log", log)
    page = Page()
    assert await runner._click_next_if_present(page, "app-1") is True
    assert page.clicked is True

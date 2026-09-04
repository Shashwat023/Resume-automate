from dataclasses import dataclass

from app.services.engine.tier0_harvest import FormField
from app.services.engine.tier2_resolve import build_instruction, resolve_and_execute


@dataclass
class FakeAction:
    selector: str = "//div[1]"


@dataclass
class FakeObserveResult:
    data: list


@dataclass
class FakeActResultData:
    success: bool
    message: str = ""
    action_description: str = "Clicked the option"


@dataclass
class FakeActResult:
    data: FakeActResultData


class FakeStagehand:
    """
    Records every observe()/act() call and returns scripted responses in
    call order. Combobox fields drive TWO observe->act pairs (open, then
    select); checkbox/radio fields drive ONE — see tier2_resolve.py's
    module docstring for why comboboxes need the extra step.
    """

    def __init__(self, observe_results: list, act_results: list):
        self.observe_calls: list[tuple[str, object]] = []
        self.act_calls: list[tuple[object, object]] = []
        self._observe_results = observe_results
        self._act_results = act_results

    async def observe(self, instruction, *, page=None):
        self.observe_calls.append((instruction, page))
        result = self._observe_results[len(self.observe_calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result

    async def act(self, action, *, page=None):
        self.act_calls.append((action, page))
        result = self._act_results[len(self.act_calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result


class FakeSendClickEventLocator:
    def __init__(self, page, selector):
        self._page = page
        self._selector = selector

    async def send_click_event(self):
        self._page.send_click_event_calls.append(self._selector)
        if self._page.send_click_event_should_fail:
            raise RuntimeError("send_click_event not supported on this element")


class FakePage:
    def __init__(self, send_click_event_should_fail: bool = False):
        self.send_click_event_calls: list[str] = []
        self.send_click_event_should_fail = send_click_event_should_fail

    async def wait_for_timeout(self, ms):
        pass

    def locator(self, selector):
        return FakeSendClickEventLocator(self, selector)


# ---- checkbox/radio: single-step ----


async def test_checkbox_is_a_single_observe_act_pair():
    action = FakeAction(selector="//input[@type='checkbox']")
    sh = FakeStagehand(
        observe_results=[FakeObserveResult(data=[action])],
        act_results=[
            FakeActResult(
                data=FakeActResultData(
                    success=True, action_description="Checked the box"
                )
            )
        ],
    )
    field = FormField(
        node_id="1", role="checkbox", label="I agree to relocate", xpath=None
    )

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "Yes")])

    assert result.resolved == [("I agree to relocate", "Checked the box")]
    assert len(sh.observe_calls) == 1
    assert len(sh.act_calls) == 1


async def test_checkbox_act_failure_is_captured():
    action = FakeAction()
    sh = FakeStagehand(
        observe_results=[FakeObserveResult(data=[action])],
        act_results=[
            FakeActResult(
                data=FakeActResultData(success=False, message="Element not clickable")
            )
        ],
    )
    field = FormField(node_id="1", role="checkbox", label="Terms agreement", xpath=None)

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "Yes")])

    assert result.resolved == []
    assert result.errored == [("Terms agreement", "Element not clickable")]


# ---- combobox: two-step (open, then select) ----


async def test_combobox_is_a_two_step_open_then_select():
    # Regression: this is the exact bug found live-verifying against a real
    # Anthropic Greenhouse form — a single observe+act reported success
    # (it genuinely opened the dropdown) but the field's real value stayed
    # empty, because the option element doesn't exist in the tree until
    # AFTER the dropdown is open. Confirmed via raw CDP accessibility-tree
    # inspection against the live page, not assumed.
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='option-no']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(
                data=FakeActResultData(
                    success=True, action_description="Opened the dropdown"
                )
            ),
            FakeActResult(
                data=FakeActResultData(success=True, action_description="Selected 'No'")
            ),
        ],
    )
    field = FormField(
        node_id="1",
        role="combobox",
        label="Do you require visa sponsorship?",
        xpath=None,
    )

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "No")])

    assert result.resolved == [("Do you require visa sponsorship?", "Selected 'No'")]
    assert len(sh.observe_calls) == 2
    assert len(sh.act_calls) == 2
    # The SECOND act() must use the SECOND observe()'s result, not the first
    assert sh.act_calls[0][0] is open_action
    assert sh.act_calls[1][0] is select_action


async def test_combobox_description_quoting_placeholder_is_an_error():
    # The actual bug found live: act() reported success=True for the select
    # step, but its OWN description text still quoted "Select..." — the
    # click executed but nothing was actually selected. Must NOT be
    # reported as resolved.
    #
    # (A DOM-based version of this check was tried first and found WORSE
    # than this bug: on a real ARIA role="combobox" <input> — a common
    # widget shape — the value is rendered by sibling elements outside the
    # input's own subtree, so both inner_text() and input_value() on
    # field.xpath are structurally always empty, a 100% false-negative
    # rate confirmed live. See FLAGGED.md. The model's own description
    # text is the only reliable signal here.)
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='option']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description="Dropdown now showing 'Select...' option",
                )
            ),
        ],
    )
    field = FormField(
        node_id="1", role="combobox", label="Agreement to Arbitrate", xpath=None
    )

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "I agree")])

    assert result.resolved == []
    assert len(result.errored) == 1
    label, detail = result.errored[0]
    assert label == "Agreement to Arbitrate"
    assert "placeholder" in detail


async def test_combobox_description_naming_the_real_value_is_resolved():
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='option']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(success=True, action_description="Selected 'No'")
            ),
        ],
    )
    field = FormField(
        node_id="1", role="combobox", label="Do you require visa sponsorship?", xpath=None
    )

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "No")])

    assert result.resolved == [("Do you require visa sponsorship?", "Selected 'No'")]
    assert result.errored == []


async def test_ordinary_phrase_containing_the_word_select_is_not_a_false_positive():
    # "Select the option" is completely ordinary description language and
    # must not trip the placeholder check just because it contains the
    # word "select" — only a QUOTED placeholder phrase should.
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='option']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description="Select the option 'No' in the dropdown",
                )
            ),
        ],
    )
    field = FormField(
        node_id="1", role="combobox", label="Do you require visa sponsorship?", xpath=None
    )

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "No")])

    assert result.resolved == [
        ("Do you require visa sponsorship?", "Select the option 'No' in the dropdown")
    ]


async def test_combobox_open_step_failing_never_attempts_select_step():
    open_action = FakeAction()
    sh = FakeStagehand(
        observe_results=[FakeObserveResult(data=[open_action])],
        act_results=[
            FakeActResult(
                data=FakeActResultData(success=False, message="Toggle not found")
            )
        ],
    )
    field = FormField(node_id="1", role="combobox", label="Country", xpath=None)

    result = await resolve_and_execute(
        sh, page=FakePage(), fields=[(field, "United States")]
    )

    assert result.resolved == []
    assert "Toggle not found" in result.errored[0][1]
    assert len(sh.observe_calls) == 1  # never got to the select-step observe()


async def test_combobox_opens_but_no_matching_option_found_even_after_fallback():
    open_action = FakeAction()
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[]),  # exact-value select observe() finds nothing
            FakeObserveResult(data=[]),  # closest-match fallback ALSO finds nothing
            FakeObserveResult(data=[]),  # typeahead recovery's own type-target observe() ALSO finds nothing
        ],
        act_results=[FakeActResult(data=FakeActResultData(success=True))],
    )
    field = FormField(node_id="1", role="combobox", label="Gender", xpath=None)

    result = await resolve_and_execute(
        sh, page=FakePage(), fields=[(field, "Prefer not to say")]
    )

    assert result.resolved == []
    assert "no option matching" in result.errored[0][1]
    assert "fallback" in result.errored[0][1]
    assert "typeahead" in result.errored[0][1]
    assert len(sh.observe_calls) == 4
    assert len(sh.act_calls) == 1  # only the open-step act() ran


async def test_combobox_typeahead_recovery_finds_the_option_after_typing():
    # Real, live-caught bug: Figma's Greenhouse "Location (City)" field is
    # a TYPEAHEAD-filtered combobox — its option list is only populated
    # once something is typed, so an exact AND closest-match select
    # attempt against the just-opened, still-empty list both legitimately
    # find nothing. Typing the value first, then retrying the select,
    # should recover an option that genuinely exists once filtered in.
    open_action = FakeAction(selector="//div[@class='toggle']")
    type_action = FakeAction(selector="//input[@class='city-search']")
    select_action = FakeAction(selector="//li[@data-city='bangalore']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[]),  # exact-value select finds nothing (empty list)
            FakeObserveResult(data=[]),  # closest-match fallback ALSO finds nothing
            FakeObserveResult(data=[type_action]),  # typeahead recovery finds the input
            FakeObserveResult(data=[select_action]),  # re-select after typing succeeds
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),  # open
            FakeActResult(data=FakeActResultData(success=True)),  # type
            FakeActResult(
                data=FakeActResultData(
                    success=True, action_description="Selected 'Bangalore'"
                )
            ),
        ],
    )
    field = FormField(
        node_id="1", role="combobox", label="Location (City)", xpath=None
    )

    result = await resolve_and_execute(
        sh, page=FakePage(), fields=[(field, "Bangalore")]
    )

    assert result.resolved == [("Location (City)", "Selected 'Bangalore'")]
    assert len(sh.observe_calls) == 5
    assert len(sh.act_calls) == 3
    assert sh.act_calls[1][0] is type_action
    assert sh.act_calls[2][0] is select_action


async def test_combobox_falls_back_to_closest_match_when_exact_wording_not_found():
    # The real bug this fixes: Tier 1 decides "1-2 years" before the
    # dropdown is ever opened, but the ATS's real option reads "Less than 5
    # years" — an exact-wording instruction finds nothing. The fallback
    # instruction, with no literal value to match against, should still
    # find and click SOME option.
    open_action = FakeAction(selector="//div[@class='toggle']")
    fallback_action = FakeAction(selector="//div[@class='closest-option']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[]),  # exact-value select observe() finds nothing
            FakeObserveResult(data=[fallback_action]),  # fallback finds one
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True, action_description="Selected 'Less than 5 years'"
                )
            ),
        ],
    )
    field = FormField(
        node_id="1",
        role="combobox",
        label="Years of experience",
        xpath="//div[@id='years']",
    )

    result = await resolve_and_execute(
        sh, page=FakePage(), fields=[(field, "1-2 years")]
    )

    assert result.resolved == [("Years of experience", "Selected 'Less than 5 years'")]
    assert len(sh.observe_calls) == 3
    # The fallback observe()'s result must be what gets act()-ed on.
    assert sh.act_calls[1][0] is fallback_action


async def test_combobox_select_step_failure_is_captured():
    open_action = FakeAction()
    select_action = FakeAction()
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(success=False, message="Option not clickable")
            ),
        ],
    )
    field = FormField(node_id="1", role="combobox", label="Veteran Status", xpath=None)

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "No")])

    assert result.resolved == []
    assert "Option not clickable" in result.errored[0][1]


async def test_multiple_fields_processed_independently():
    action = FakeAction()
    sh = FakeStagehand(
        observe_results=[
            RuntimeError("network blip"),  # field A (checkbox): observe fails
            FakeObserveResult(data=[action]),  # field B open step
            FakeObserveResult(data=[action]),  # field B select step
        ],
        act_results=[
            FakeActResult(
                data=FakeActResultData(success=True, action_description="opened")
            ),
            FakeActResult(
                data=FakeActResultData(
                    success=True, action_description="Selected 'Yes'"
                )
            ),
        ],
    )
    field_a = FormField(node_id="1", role="checkbox", label="Field A", xpath=None)
    field_b = FormField(node_id="2", role="combobox", label="Field B", xpath=None)

    result = await resolve_and_execute(
        sh, page=FakePage(), fields=[(field_a, "x"), (field_b, "Yes")]
    )

    # Error text carries the exception TYPE too — a TimeoutError's str() is
    # empty, so without the type name a real timeout logs as
    # "observe() failed: " with nothing after it (see _describe).
    assert result.errored == [("Field A", "observe() failed: RuntimeError: network blip")]
    assert result.resolved == [("Field B", "Selected 'Yes'")]


# ---- instruction text (unchanged behavior for checkbox/radio) ----


def test_checkbox_instruction_reflects_yes_no_semantics():
    field = FormField(
        node_id="1", role="checkbox", label="I agree to relocate", xpath=None
    )
    assert "checked" in build_instruction(field, "Yes")
    assert "unchecked" in build_instruction(field, "No")


def test_radio_instruction_names_the_option():
    field = FormField(
        node_id="1", role="radio", label="Preferred contact method", xpath=None
    )
    instruction = build_instruction(field, "Email")
    assert "Email" in instruction
    assert "Preferred contact method" in instruction


def test_combobox_instruction_names_dropdown_and_target_value():
    field = FormField(
        node_id="1",
        role="combobox",
        label="Are you open to relocation for this role?",
        xpath=None,
    )
    instruction = build_instruction(field, "No")
    assert "Are you open to relocation for this role?" in instruction
    assert "No" in instruction


async def test_observe_that_never_returns_times_out_instead_of_hanging_forever(monkeypatch):
    # The actual bug this fixes: a real run hung indefinitely on a single
    # field (no exception, no log line) after a CDP-level error on the
    # previous action. Nothing bounded how long observe()/act() could take.
    import asyncio

    from app.services.engine import tier2_resolve

    monkeypatch.setattr(tier2_resolve, "LLM_CALL_TIMEOUT_SECONDS", 0.05)

    class HangingStagehand:
        async def observe(self, instruction, *, page=None):
            await asyncio.sleep(10)  # would hang the whole test suite without the timeout
            return FakeObserveResult(data=[FakeAction()])

    field = FormField(node_id="1", role="checkbox", label="I agree", xpath=None)

    result = await resolve_and_execute(
        HangingStagehand(), page=FakePage(), fields=[(field, "Yes")]
    )

    assert result.resolved == []
    assert len(result.errored) == 1
    label, detail = result.errored[0]
    assert label == "I agree"
    assert "observe() failed" in detail


async def test_description_narrating_no_match_is_not_reported_as_resolved():
    # FLAGGED.md #13's remaining edge case, now fixed. The closest-match
    # fallback reported `resolved` for a field whose own description
    # explicitly said no match existed — act() still returned success=True
    # (SOMETHING was clicked) and the description quotes no literal
    # placeholder, so the quoted-placeholder check structurally cannot see
    # it. This is the real description text from the live run.
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[FakeAction()]),
            FakeObserveResult(data=[FakeAction()]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description=(
                        "The '1-2 years' option was not found in the dropdown. "
                        "There is no '1-2 years' option visible."
                    ),
                )
            ),
        ],
    )
    field = FormField(
        node_id="1",
        role="combobox",
        label="Years of experience",
        xpath="//div[@id='years']",
    )

    result = await resolve_and_execute(
        sh, page=FakePage(), fields=[(field, "1-2 years")]
    )

    assert result.resolved == []
    assert len(result.errored) == 1
    assert "no matching option was found" in result.errored[0][1]


async def test_a_genuine_selection_description_is_still_accepted():
    # The guard above must not reject real successes — a description
    # naming the option it actually selected has to pass.
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[FakeAction()]),
            FakeObserveResult(data=[FakeAction()]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description="Selected the option '3-5 years' from the dropdown",
                )
            ),
        ],
    )
    field = FormField(
        node_id="1", role="combobox", label="Years of experience", xpath="//div[@id='y']"
    )

    result = await resolve_and_execute(
        sh, page=FakePage(), fields=[(field, "3-5 years")]
    )

    assert result.errored == []
    assert result.resolved == [
        ("Years of experience", "Selected the option '3-5 years' from the dropdown")
    ]


async def test_transient_invalid_mouse_button_error_is_retried_once():
    # Real bug found live (FLAGGED.md #16/#17): act() returned normally
    # (success=False) with a CDP-level "-32602 Invalid mouse button"
    # message on 9 separate calls across one real run, including on
    # 'Country'. Confirmed live that a retry of the SAME resolved Action
    # can succeed a moment later. One bounded retry, not a loop.
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='option']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),  # open succeeds
            FakeActResult(
                data=FakeActResultData(
                    success=False, message="Failed to perform act: -32602 Invalid mouse button"
                )
            ),  # select fails transiently
            FakeActResult(
                data=FakeActResultData(success=True, action_description="Selected 'India'")
            ),  # select succeeds on retry
        ],
    )
    field = FormField(node_id="1", role="combobox", label="Country", xpath="//div[@id='country']")
    # send_click_event fails here too, so this test exercises the FURTHER
    # fallback: a second plain act() retry (see
    # test_invalid_mouse_button_falls_back_to_send_click_event for the
    # send_click_event path itself, tested separately).
    page = FakePage(send_click_event_should_fail=True)

    result = await resolve_and_execute(sh, page=page, fields=[(field, "India")])

    assert result.resolved == [("Country", "Selected 'India'")]
    assert result.errored == []
    assert len(sh.act_calls) == 3
    # The retry must re-dispatch the SAME resolved Action, not re-observe.
    assert sh.act_calls[1][0] is select_action
    assert sh.act_calls[2][0] is select_action


async def test_only_one_retry_is_attempted_not_a_loop():
    action = FakeAction()
    sh = FakeStagehand(
        observe_results=[FakeObserveResult(data=[action])],
        act_results=[
            FakeActResult(
                data=FakeActResultData(
                    success=False, message="-32602 Invalid mouse button"
                )
            ),
            FakeActResult(
                data=FakeActResultData(
                    success=False, message="-32602 Invalid mouse button"
                )
            ),
        ],
    )
    field = FormField(node_id="1", role="checkbox", label="I agree", xpath=None)
    page = FakePage(send_click_event_should_fail=True)

    result = await resolve_and_execute(sh, page=page, fields=[(field, "Yes")])

    assert len(sh.act_calls) == 2  # one original + one plain retry, no more
    assert result.errored == [("I agree", "-32602 Invalid mouse button")]


async def test_a_non_transient_act_failure_is_not_retried():
    action = FakeAction()
    sh = FakeStagehand(
        observe_results=[FakeObserveResult(data=[action])],
        act_results=[
            FakeActResult(data=FakeActResultData(success=False, message="element not visible")),
        ],
    )
    field = FormField(node_id="1", role="checkbox", label="I agree", xpath=None)

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "Yes")])

    assert len(sh.act_calls) == 1  # no retry for an unrelated failure
    assert result.errored == [("I agree", "element not visible")]


async def test_invalid_mouse_button_falls_back_to_send_click_event():
    # Real, live-caught fix: -32602 is Chrome's CDP layer rejecting the
    # trusted synthetic click act() dispatches via
    # Input.dispatchMouseEvent — it never reaches the page's JS.
    # Locator.send_click_event() dispatches a real DOM MouseEvent directly,
    # bypassing that CDP pipeline entirely, and is tried BEFORE a second
    # plain act() retry.
    action = FakeAction(selector="//div[@id='country-option-india']")
    sh = FakeStagehand(
        observe_results=[FakeObserveResult(data=[action])],
        act_results=[
            FakeActResult(
                data=FakeActResultData(
                    success=False, message="Failed to perform act: -32602 Invalid mouse button"
                )
            ),
        ],
    )
    page = FakePage()
    field = FormField(node_id="1", role="checkbox", label="I agree", xpath=None)

    result = await resolve_and_execute(sh, page=page, fields=[(field, "Yes")])

    assert result.resolved == [
        (
            "I agree",
            "Clicked via send_click_event fallback after a CDP 'Invalid mouse "
            "button' rejection (selector: //div[@id='country-option-india'])",
        )
    ]
    assert page.send_click_event_calls == ["//div[@id='country-option-india']"]
    assert len(sh.act_calls) == 1  # send_click_event succeeded — no plain-act retry needed


async def test_send_click_event_failure_falls_through_to_plain_retry():
    action = FakeAction(selector="//div[1]")
    sh = FakeStagehand(
        observe_results=[FakeObserveResult(data=[action])],
        act_results=[
            FakeActResult(
                data=FakeActResultData(
                    success=False, message="-32602 Invalid mouse button"
                )
            ),
            FakeActResult(
                data=FakeActResultData(success=True, action_description="Checked the box")
            ),
        ],
    )
    page = FakePage(send_click_event_should_fail=True)
    field = FormField(node_id="1", role="checkbox", label="I agree", xpath=None)

    result = await resolve_and_execute(sh, page=page, fields=[(field, "Yes")])

    assert result.resolved == [("I agree", "Checked the box")]
    assert page.send_click_event_calls == ["//div[1]"]
    assert len(sh.act_calls) == 2  # original + plain retry, after send_click_event also failed


async def test_select_step_describing_a_toggle_reopen_is_not_reported_as_resolved():
    # Real bug found live: the repair pass's select step reported
    # success=True with a description narrating re-clicking the
    # OPEN/toggle control itself, not an option — the dropdown's real
    # value never changed. Neither the quoted-placeholder nor the
    # no-match-phrase check catches this: it doesn't quote a placeholder
    # and doesn't say anything wasn't found — it just describes the wrong
    # kind of click entirely.
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='toggle']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description=(
                        "Toggle flyout button for the 'Please read the arbitration "
                        "agreement below' dropdown, which when clicked will open "
                        "the dropdown to reveal options including 'I agree'."
                    ),
                )
            ),
        ],
    )
    field = FormField(
        node_id="1", role="combobox", label="Please read the arbitration agreement below", xpath=None
    )

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "I agree")])

    assert result.resolved == []
    assert len(result.errored) == 1
    label, detail = result.errored[0]
    assert label == "Please read the arbitration agreement below"
    assert "toggling" in detail


async def test_genuine_open_dropdown_phrasing_in_a_select_description_still_passes():
    # Must not false-positive on ordinary successful phrasings that happen
    # to mention "open dropdown" without "the" (the real shape seen live
    # for genuine successes).
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='option-no']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description="Click the 'No' option in the open dropdown for 'Do you require visa sponsorship?'",
                )
            ),
        ],
    )
    field = FormField(node_id="1", role="combobox", label="Do you require visa sponsorship?", xpath=None)

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "No")])

    assert result.errored == []
    assert len(result.resolved) == 1


async def test_closest_match_fallback_explaining_its_own_reasoning_is_still_resolved():
    # Real false-positive found live: the closest-match fallback
    # instruction deliberately asks the model to explain WHY the exact
    # wording isn't present before naming the option it picked instead —
    # this is the real description text from a live run. Without the
    # closest-match carve-out, _NO_MATCH_PHRASES flagged this genuine
    # success as a failure on nearly every closest-match resolution.
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[FakeAction()]),
            FakeObserveResult(data=[FakeAction()]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description=(
                        "Option 'Less than 5 years' in the listbox for the question "
                        "'How many years of professional software engineering "
                        "experience do you have?'. The instruction asks for "
                        "'1-2 years', but that specific option is not present in "
                        "the accessibility tree. The closest matching option that "
                        "is visible and available for selection is 'Less than 5 years'."
                    ),
                )
            ),
        ],
    )
    field = FormField(
        node_id="1",
        role="combobox",
        label="How many years of professional software engineering experience do you have?",
        xpath="//div[@id='years']",
    )

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "1-2 years")])

    assert result.errored == []
    assert len(result.resolved) == 1


async def test_select_step_describing_open_it_and_see_options_is_not_reported_as_resolved():
    # Real bug found live, the SAME "described the open, not the select"
    # false-success shape (see test_select_step_describing_a_toggle_reopen)
    # but with different phrasing that slipped past the first fix — this
    # is the real description text from a live run's 'Agreement to
    # Arbitrate' field, which is very likely why every submission attempt
    # in that run still failed with "This field is required" despite the
    # run's own summary claiming 0 unhandled fields.
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='toggle']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description="Click on the 'Agreement to Arbitrate' dropdown to open it and see the options.",
                )
            ),
        ],
    )
    field = FormField(node_id="1", role="combobox", label="Agreement to Arbitrate", xpath=None)

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "I agree to arbitrate")])

    assert result.resolved == []
    assert len(result.errored) == 1


async def test_select_step_describing_generic_keyboard_instructions_is_not_reported_as_resolved():
    # Real, live-caught bug on the SAME Figma "Location (City)" field: a
    # repair pass's select step reported success=True with a description
    # that only narrates the dropdown's own generic UI hint text —
    # "...currently open, with instructions indicating options can be
    # navigated with keyboard" — never naming an actual selected value.
    # None of the toggle/placeholder/no-match checks catch this wording;
    # the field's real value stayed empty, confirmed by the ATS's own
    # "Please enter" rejection on the very next submit.
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='toggle']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description=(
                        "combobox dropdown for Location (City) field, which is "
                        "currently open, with instructions indicating options "
                        "can be navigated with keyboard"
                    ),
                )
            ),
        ],
    )
    field = FormField(node_id="1", role="combobox", label="Location (City)", xpath=None)

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "Bangalore")])

    assert result.resolved == []
    assert len(result.errored) == 1
    label, detail = result.errored[0]
    assert label == "Location (City)"
    assert "generic UI hint text" in detail


async def test_closest_match_description_mentioning_keyboard_navigation_still_passes():
    # Must not false-positive: the closest-match fallback's OWN
    # explanatory reasoning can legitimately mention navigation while
    # still naming the option it actually resolved to.
    open_action = FakeAction(selector="//div[@class='toggle']")
    select_action = FakeAction(selector="//div[@class='option-sf']")
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[select_action]),
        ],
        act_results=[
            FakeActResult(data=FakeActResultData(success=True)),
            FakeActResult(
                data=FakeActResultData(
                    success=True,
                    action_description=(
                        "That exact city is not present, so after navigating "
                        "with arrow keys the closest reasonable match is "
                        "'San Francisco'."
                    ),
                )
            ),
        ],
    )
    field = FormField(node_id="1", role="combobox", label="Location (City)", xpath=None)

    result = await resolve_and_execute(sh, page=FakePage(), fields=[(field, "SF")])

    assert result.errored == []
    assert len(result.resolved) == 1

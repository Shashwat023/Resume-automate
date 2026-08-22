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


class FakePage:
    async def wait_for_timeout(self, ms):
        pass


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


async def test_combobox_opens_but_no_matching_option_found():
    open_action = FakeAction()
    sh = FakeStagehand(
        observe_results=[
            FakeObserveResult(data=[open_action]),
            FakeObserveResult(data=[]),  # select-step observe() finds nothing
        ],
        act_results=[FakeActResult(data=FakeActResultData(success=True))],
    )
    field = FormField(node_id="1", role="combobox", label="Gender", xpath=None)

    result = await resolve_and_execute(
        sh, page=FakePage(), fields=[(field, "Prefer not to say")]
    )

    assert result.resolved == []
    assert "no option matching" in result.errored[0][1]
    assert len(sh.act_calls) == 1  # only the open-step act() ran


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

    assert result.errored == [("Field A", "observe() failed: network blip")]
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

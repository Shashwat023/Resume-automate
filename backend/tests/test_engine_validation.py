from types import SimpleNamespace

from app.services.engine import runner, validation
from app.services.engine.submit import find_invalid_field_labels
from app.services.engine.tier0_harvest import collect_fields


def test_find_page_validation_issues_attributes_error_to_preceding_label():
    tree = "[1] textbox: Country\n[2] text: The field X is required and must have a value\n[3] combobox: Race\n[4] text: Please select\n[5] text: Errors Found\n"
    assert validation.find_page_validation_issues(tree) == ["Country", "Race"]


def test_find_invalid_field_labels_behavior_unchanged():
    assert find_invalid_field_labels(
        "[1] textbox: Email\n[2] text: This field is required\n"
    ) == ["Email"]


async def test_dom_invalid_labels_script_is_an_invoked_expression():
    seen = []

    class Page:
        async def evaluate(self, script):
            seen.append(script)
            return ["Country", "Country", " "]

    assert await validation.collect_invalid_labels_from_dom(Page()) == ["Country"]
    assert seen[0].endswith(")()")


async def test_dom_invalid_labels_swallow_errors():
    class Page:
        async def evaluate(self, _script):
            raise RuntimeError("no page")

    assert await validation.collect_invalid_labels_from_dom(Page()) == []


def test_button_dropdown_collected_as_combobox_but_file_buttons_are_not():
    fields = collect_fields(
        "[1] button: Candidate type Select One Required*\n[2] button: Select File\n[3] button: Upload document\n",
        {"1": "//candidate", "2": "//file", "3": "//upload"},
    )
    assert [(field.role, field.label, field.required) for field in fields] == [
        ("combobox", "Candidate type", True)
    ]


class _BlockingPage:
    def __init__(self, tree, xpath_map):
        self.tree = tree
        self.xpath_map = xpath_map
        self.selected = []

    async def snapshot(self):
        return SimpleNamespace(formatted_tree=self.tree, xpath_map=self.xpath_map)

    async def evaluate(self, _script):
        return []

    async def wait_for_timeout(self, _milliseconds):
        pass

    def locator(self, xpath):
        page = self

        class Locator:
            async def select_option(self, option):
                page.selected.append((xpath, option))

        return Locator()


async def _quiet_log(*_args, **_kwargs):
    pass


async def test_native_select_any_option_skips_placeholder_and_uses_no_llm(monkeypatch):
    page = _BlockingPage(
        "[1] combobox: Device Type\n  [2] option: Select One\n  [3] option: Option A\n"
        "[4] text: The field Device Type is required and must have a value\n",
        {"1": "//device"},
    )
    monkeypatch.setattr(runner, "_log", _quiet_log)

    class Stagehand:
        async def observe(self, *_args, **_kwargs):
            raise AssertionError("native selects must not use observe")

    result = await runner._resolve_blocking_fields(
        "app", Stagehand(), page, {}, 1, None
    )

    assert result.acted is True
    assert page.selected == [("//device", "Option A")]
    assert result.picks == [("Device Type", "Option A")]


async def test_sensitive_label_is_escalated_not_guessed(monkeypatch):
    label = "Are you legally authorized to work in the US?"
    page = _BlockingPage(
        f"[1] textbox: {label}\n[2] text: {label} is required\n", {"1": "//auth"}
    )
    monkeypatch.setattr(runner, "_map_fields", lambda *_args, **_kwargs: None)

    result = await runner._resolve_blocking_fields("app", None, page, {}, 1, None)

    assert result.acted is False
    assert result.escalated == [label]


async def test_password_field_is_escalated_never_auto_filled(monkeypatch):
    page = _BlockingPage(
        "[1] textbox: Password\n[2] text: Password must be at least 8 characters\n",
        {"1": "//password"},
    )

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("credential fields must not be resolved")

    monkeypatch.setattr(runner, "_map_fields", unexpected)
    monkeypatch.setattr(runner, "resolve_any_option", unexpected)

    result = await runner._resolve_blocking_fields("app", None, page, {}, 1, None)

    assert result.acted is False
    assert result.escalated == ["Password"]


async def test_eeo_label_prefers_decline_option(monkeypatch):
    page = _BlockingPage(
        "[1] combobox: Gender\n  [2] option: Female\n"
        "  [3] option: I don't wish to answer\n[4] text: Please select\n",
        {"1": "//gender"},
    )
    monkeypatch.setattr(runner, "_log", _quiet_log)

    result = await runner._resolve_blocking_fields("app", None, page, {}, 1, None)

    assert result.acted is True
    assert page.selected == [("//gender", "I don't wish to answer")]

    instructions = []

    async def fake_step(_sh, _page, instruction):
        instructions.append(instruction)
        return "opened"

    monkeypatch.setattr(
        "app.services.engine.tier2_resolve._resolve_single_step", fake_step
    )

    class Stagehand:
        async def observe(self, instruction, **_kwargs):
            instructions.append(instruction)
            return SimpleNamespace(data=[])

    from app.services.engine.tier0_harvest import FormField
    from app.services.engine.tier2_resolve import resolve_any_option

    assert (
        await resolve_any_option(
            Stagehand(), page, FormField("x", "combobox", "Gender", "//gender"), True
        )
    ).startswith("ERROR:")
    assert "Prefer decline" in instructions[-1]


async def test_any_option_choice_is_logged_with_label_and_option(monkeypatch):
    page = _BlockingPage(
        "[1] combobox: Device Type\n  [2] option: Option A\n[3] text: Please select\n",
        {"1": "//device"},
    )
    events = []

    async def log(*args, **kwargs):
        events.append((args[1], kwargs))

    monkeypatch.setattr(runner, "_log", log)
    await runner._resolve_blocking_fields("app", None, page, {}, 1, None)

    assert events == [
        (
            "Any option selected for 'Device Type': Option A",
            {"level": "warn", "tier": "tier2"},
        )
    ]


async def test_blocking_resolution_limited_to_two_rounds_per_page():
    rounds = {}
    fingerprint = "same"
    for _ in range(3):
        if rounds.get(fingerprint, 0) >= 2:
            break
        rounds[fingerprint] = rounds.get(fingerprint, 0) + 1
    assert rounds[fingerprint] == 2


async def test_unresolvable_blocking_fields_pause_with_labels_listed(monkeypatch):
    page = _BlockingPage(
        "[1] textbox: Password\n[2] text: Password is required\n", {"1": "//password"}
    )
    result = await runner._resolve_blocking_fields("app", None, page, {}, 1, None)
    event = f"Blocking fields: [Password]; needs you: [{', '.join(result.escalated)}]"
    assert "Password" in event and result.escalated == ["Password"]


def test_button_dropdown_count_event_logged_once_per_page():
    fields = collect_fields(
        "[1] button: Candidate type Select One\n", {"1": "//candidate"}
    )
    fingerprint = "page"
    logged = set()
    count = sum(field.from_button for field in fields)
    events = [count] if count and fingerprint not in logged else []
    logged.add(fingerprint)
    events += [count] if count and fingerprint not in logged else []
    assert events == [1]

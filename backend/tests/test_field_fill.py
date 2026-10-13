from app.services.engine.field_fill import fill_textbox


class _Suggestion:
    async def is_visible(self):
        return False


class _Locator:
    def __init__(self, value="", input_error=False):
        self.value = value
        self.input_error = input_error
        self.calls = []

    async def input_value(self):
        if self.input_error:
            raise RuntimeError("unreadable")
        return self.value

    async def fill(self, value):
        self.calls.append(("fill", value))

    async def type(self, value, delay=0):
        self.calls.append(("type", value, delay))


class _Page:
    def __init__(self, locator):
        self.field = locator

    def locator(self, xpath):
        if xpath.startswith("//field"):
            return self.field
        return type("Suggestions", (), {"first": lambda _self: _Suggestion()})()

    async def wait_for_timeout(self, _milliseconds):
        pass


async def test_fill_textbox_skips_when_value_already_equal():
    locator = _Locator("  same value ")
    assert await fill_textbox(_Page(locator), "//field", "same value") is False
    assert locator.calls == []


async def test_fill_textbox_falls_back_when_input_value_fails():
    locator = _Locator(input_error=True)
    assert await fill_textbox(_Page(locator), "//field", "new value") is True
    assert [call[0] for call in locator.calls] == ["fill", "type"]


async def test_unchanged_fields_are_not_retyped_on_a_second_pass():
    locator = _Locator("")
    page = _Page(locator)
    assert await fill_textbox(page, "//field", "value") is True
    locator.value = "value"
    assert await fill_textbox(page, "//field", "value") is False
    assert [call[0] for call in locator.calls] == ["fill", "type"]

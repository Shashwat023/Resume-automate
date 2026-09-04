from app.services.engine.tier0_harvest import FormField, fill_deterministic


class FakeLocator:
    def __init__(self, calls, xpath, boom=False):
        self._calls = calls
        self._xpath = xpath
        self._boom = boom
        self._suggestion_visible = False

    async def fill(self, value):
        if self._boom:
            raise RuntimeError("stale xpath")
        self._calls.append(("fill", self._xpath, value))

    async def type(self, value, delay=None):
        # field_fill.fill_textbox's retype step (see that module's
        # docstring for why plain fill() alone isn't enough for
        # autocomplete-backed fields like Greenhouse's "Location (City)").
        if self._boom:
            raise RuntimeError("stale xpath")
        self._calls.append(("type", self._xpath, value))

    async def set_input_files(self, path):
        if self._boom:
            raise RuntimeError("element not attached to DOM")
        self._calls.append(("set_input_files", self._xpath, path))

    def first(self):
        return self

    async def is_visible(self):
        return self._suggestion_visible

    async def click(self):
        self._calls.append(("click", self._xpath))


class FakePage:
    def __init__(self, boom_xpaths: set[str] | None = None, suggestion_visible: bool = False):
        self.calls: list[tuple] = []
        self._boom_xpaths = boom_xpaths or set()
        # Whether field_fill.fill_textbox's suggestion-selector locator
        # (see that module's _SUGGESTION_SELECTOR) reports a visible
        # autocomplete option — False by default, same as a plain textbox
        # with no such widget.
        self._suggestion_visible = suggestion_visible

    def locator(self, xpath):
        locator = FakeLocator(self.calls, xpath, boom=xpath in self._boom_xpaths)
        locator._suggestion_visible = self._suggestion_visible
        return locator

    async def wait_for_timeout(self, ms):
        pass


async def test_file_field_attaches_stored_resume_path():
    field = FormField(
        node_id="1", role="file", label="Resume/CV", xpath="//input[@type='file']"
    )
    page = FakePage()

    result = await fill_deterministic(
        page, [field], {}, resume_file_path="/storage/resumes/1/resume.pdf"
    )

    assert result.filled == [("Resume/CV", "/storage/resumes/1/resume.pdf")]
    assert page.calls == [
        ("set_input_files", "//input[@type='file']", "/storage/resumes/1/resume.pdf")
    ]


async def test_file_field_with_no_resume_on_file_is_unmatched():
    field = FormField(
        node_id="1", role="file", label="Resume/CV", xpath="//input[@type='file']"
    )
    page = FakePage()

    result = await fill_deterministic(page, [field], {}, resume_file_path=None)

    assert result.unmatched == ["Resume/CV"]
    assert result.filled == []
    assert page.calls == []


async def test_file_field_with_no_xpath_is_unmatched():
    field = FormField(node_id="1", role="file", label="Resume/CV", xpath=None)
    page = FakePage()

    result = await fill_deterministic(
        page, [field], {}, resume_file_path="/storage/resumes/1/resume.pdf"
    )

    assert result.unmatched == ["Resume/CV"]


async def test_file_field_set_input_files_failure_is_isolated_not_fatal():
    field1 = FormField(
        node_id="1", role="file", label="Resume/CV", xpath="//input[@id='resume']"
    )
    field2 = FormField(
        node_id="2",
        role="textbox",
        label="First Name",
        xpath="//input[@id='first_name']",
    )
    page = FakePage(boom_xpaths={"//input[@id='resume']"})

    result = await fill_deterministic(
        page,
        [field1, field2],
        {"full_name": "Jane Doe"},
        resume_file_path="/storage/resumes/1/resume.pdf",
    )

    assert result.errored == [("Resume/CV", "element not attached to DOM")]
    # the textbox after it still gets filled — one field's failure doesn't
    # abort the rest, same guarantee Day 3 already relies on for textboxes
    assert any(label == "First Name" for label, _ in result.filled)


async def test_resume_only_attaches_to_the_resume_field_not_cover_letter():
    # Two file inputs on one real form (Resume/CV, Cover Letter, see PLAN.md
    # Day 4 recon notes) — attaching the stored resume to BOTH would
    # misrepresent it as a cover letter too. Only the field whose label
    # actually says resume/CV gets it.
    resume_field = FormField(
        node_id="1", role="file", label="Resume/CV", xpath="//input[@id='resume']"
    )
    cover_letter_field = FormField(
        node_id="2",
        role="file",
        label="Cover Letter",
        xpath="//input[@id='cover-letter']",
    )
    page = FakePage()

    result = await fill_deterministic(
        page,
        [resume_field, cover_letter_field],
        {},
        resume_file_path="/storage/resumes/1/resume.pdf",
    )

    filled_labels = {label for label, _ in result.filled}
    assert filled_labels == {"Resume/CV"}
    assert result.unmatched == ["Cover Letter"]


async def test_phone_country_code_stripped_when_separate_country_field_exists():
    # Real bug found live: the profile stores phone WITH its country code,
    # no separator ("+918303545027"), which is correct for a single
    # combined phone field. But this real form splits it — a Country
    # dropdown (dial code) PLUS a plain Phone textbox — so filling the raw
    # profile value duplicated the code.
    #
    # A SECOND real bug was found fixing the first: a naive regex eating
    # up to 4 digits after "+" doesn't know a calling code's real length
    # (1-3 digits, genuinely ambiguous from the digit string alone) — it
    # ate "+9183" instead of "+91", leaving the mangled "03545027". Fixed
    # with `phonenumbers` (parses against the real ITU calling-code table)
    # — this test uses the exact real stored format, no space, that
    # exposed the regex bug.
    phone_field = FormField(
        node_id="1", role="textbox", label="Phone", xpath="//input[@id='phone']"
    )
    country_field = FormField(
        node_id="2", role="combobox", label="Country", xpath="//div[@id='country']"
    )
    page = FakePage()

    result = await fill_deterministic(
        page,
        [phone_field, country_field],
        {"phone": "+918303545027"},
    )

    assert result.filled == [("Phone", "8303545027")]


async def test_phone_country_code_kept_when_no_separate_country_field():
    # A form with a single combined phone field legitimately needs the
    # full number, country code included — must not strip it there.
    phone_field = FormField(
        node_id="1", role="textbox", label="Phone", xpath="//input[@id='phone']"
    )
    page = FakePage()

    result = await fill_deterministic(
        page,
        [phone_field],
        {"phone": "+918303545027"},
    )

    assert result.filled == [("Phone", "+918303545027")]


async def test_phone_without_country_code_prefix_is_unaffected():
    phone_field = FormField(
        node_id="1", role="textbox", label="Phone", xpath="//input[@id='phone']"
    )
    country_field = FormField(
        node_id="2", role="combobox", label="Country", xpath="//div[@id='country']"
    )
    page = FakePage()

    result = await fill_deterministic(
        page,
        [phone_field, country_field],
        {"phone": "8303545027"},
    )

    assert result.filled == [("Phone", "8303545027")]


async def test_phone_country_code_correct_for_a_1_digit_calling_code():
    # A naive fixed-length assumption would break here too (US/Canada's +1
    # is 1 digit, not the 2 this Indian test number happens to have).
    phone_field = FormField(
        node_id="1", role="textbox", label="Phone", xpath="//input[@id='phone']"
    )
    country_field = FormField(
        node_id="2", role="combobox", label="Country", xpath="//div[@id='country']"
    )
    page = FakePage()

    result = await fill_deterministic(
        page,
        [phone_field, country_field],
        {"phone": "+14155552671"},
    )

    assert result.filled == [("Phone", "4155552671")]


async def test_city_field_selects_autocomplete_suggestion_when_one_appears():
    # Real, live-caught bug: Figma's Greenhouse "Location (City)" field
    # was flagged invalid by the ATS on submit in two consecutive live
    # runs despite looking filled — it's backed by an autocomplete widget
    # that plain fill() doesn't satisfy (see field_fill.py's docstring).
    city_field = FormField(
        node_id="1", role="textbox", label="Location (City)", xpath="//input[@id='city']"
    )
    page = FakePage(suggestion_visible=True)

    result = await fill_deterministic(page, [city_field], {"city": "San Francisco"})

    assert result.filled == [("Location (City)", "San Francisco")]
    # fill("") to clear, type() to trigger the widget, then click the
    # suggestion that appeared — not left as raw typed text.
    assert ("fill", "//input[@id='city']", "") in page.calls
    assert ("type", "//input[@id='city']", "San Francisco") in page.calls
    assert any(call[0] == "click" for call in page.calls)


async def test_plain_textbox_with_no_suggestion_is_unaffected():
    # The blanket retype-then-check is applied to EVERY textbox, not just
    # known-autocomplete ones (no reliable way to tell them apart from the
    # accessibility tree alone) — a plain field must end up with the same
    # value and no click, same as before this fix.
    field = FormField(
        node_id="1", role="textbox", label="First Name", xpath="//input[@id='fn']"
    )
    page = FakePage(suggestion_visible=False)

    result = await fill_deterministic(page, [field], {"full_name": "Jane Doe"})

    assert result.filled == [("First Name", "Jane")]
    assert not any(call[0] == "click" for call in page.calls)


async def test_phone_country_code_correct_for_a_3_digit_calling_code():
    phone_field = FormField(
        node_id="1", role="textbox", label="Phone", xpath="//input[@id='phone']"
    )
    country_field = FormField(
        node_id="2", role="combobox", label="Country", xpath="//div[@id='country']"
    )
    page = FakePage()

    result = await fill_deterministic(
        page,
        [phone_field, country_field],
        {"phone": "+971501234567"},
    )

    assert result.filled == [("Phone", "501234567")]

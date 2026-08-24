from app.services.engine.tier0_harvest import FormField, fill_deterministic


class FakeLocator:
    def __init__(self, calls, xpath, boom=False):
        self._calls = calls
        self._xpath = xpath
        self._boom = boom

    async def fill(self, value):
        if self._boom:
            raise RuntimeError("stale xpath")
        self._calls.append(("fill", self._xpath, value))

    async def set_input_files(self, path):
        if self._boom:
            raise RuntimeError("element not attached to DOM")
        self._calls.append(("set_input_files", self._xpath, path))


class FakePage:
    def __init__(self, boom_xpaths: set[str] | None = None):
        self.calls: list[tuple] = []
        self._boom_xpaths = boom_xpaths or set()

    def locator(self, xpath):
        return FakeLocator(self.calls, xpath, boom=xpath in self._boom_xpaths)


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

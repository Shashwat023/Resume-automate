from types import SimpleNamespace

import pytest

from app.services.engine import runner


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

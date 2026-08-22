"""
The fixture tree below is a real fragment captured from a live Anthropic
Greenhouse application form (see PLAN.md Part A) — indentation is copied
verbatim, including the irregular per-field spacing that's the whole reason
collect_fields() uses raw indent-length comparison instead of a fixed
spaces-per-level assumption.
"""

from app.services.engine.tier0_harvest import collect_fields

REAL_FRAGMENT = (
    "                  [5-36] textbox: First Name\n"
    "                  [5-37] textbox: Last Name\n"
    "                  [5-38] textbox: Email\n"
    "                        [5-39] combobox: Country\n"
    "                    [5-41] textbox: Phone\n"
    "                  [5-43] textbox: Website\n"
    "                        [5-44] combobox: Are you open to working in-person in one of our offices 25% of the time?\n"
    "                        [5-51] combobox: Do you require visa sponsorship?\n"
)

XPATH_MAP = {
    "5-36": "//input[@id='first_name']",
    "5-37": "//input[@id='last_name']",
    "5-38": "//input[@id='email']",
    "5-39": "//select[@id='country']",
    "5-41": "//input[@id='phone']",
    "5-43": "//input[@id='website']",
    "5-44": "//div[@id='in-person-combobox']",
    "5-51": "//div[@id='visa-combobox']",
}


def test_collects_every_target_role():
    fields = collect_fields(REAL_FRAGMENT, XPATH_MAP)
    roles = {f.role for f in fields}
    assert roles == {"textbox", "combobox"}
    assert len(fields) == 8


def test_textbox_fields_have_no_options():
    fields = collect_fields(REAL_FRAGMENT, XPATH_MAP)
    textboxes = [f for f in fields if f.role == "textbox"]
    assert all(f.options == [] for f in textboxes)


def test_custom_comboboxes_with_no_tree_options_are_not_native_select():
    fields = collect_fields(REAL_FRAGMENT, XPATH_MAP)
    comboboxes = [f for f in fields if f.role == "combobox"]
    assert len(comboboxes) == 3  # Country, in-person, visa-sponsorship
    for cb in comboboxes:
        assert cb.options == []
        assert cb.is_native_select is False


def test_native_select_with_option_children_is_flagged_native():
    tree = (
        "            [1-1] combobox: State\n"
        "              [1-2] option: California\n"
        "              [1-3] option: New York\n"
        "            [1-4] textbox: Zip\n"
    )
    xmap = {"1-1": "//select[@id='state']", "1-4": "//input[@id='zip']"}

    fields = collect_fields(tree, xmap)

    combobox = next(f for f in fields if f.role == "combobox")
    assert combobox.options == ["California", "New York"]
    assert combobox.is_native_select is True

    # the option: lines themselves must not be collected as top-level fields
    assert all(f.role != "option" for f in fields)


def test_xpath_resolved_from_map():
    fields = collect_fields(REAL_FRAGMENT, XPATH_MAP)
    first_name = next(f for f in fields if f.label == "First Name")
    assert first_name.xpath == "//input[@id='first_name']"


def test_missing_xpath_is_none_not_a_crash():
    tree = "      [9-1] textbox: Orphan Field\n"
    fields = collect_fields(tree, {})  # no entry for 9-1
    assert fields[0].xpath is None


def test_preserves_document_order():
    fields = collect_fields(REAL_FRAGMENT, XPATH_MAP)
    assert [f.label for f in fields] == [
        "First Name",
        "Last Name",
        "Email",
        "Country",
        "Phone",
        "Website",
        "Are you open to working in-person in one of our offices 25% of the time?",
        "Do you require visa sponsorship?",
    ]


def test_sibling_fields_with_different_indent_widths_are_still_flat():
    # Real forms have fields at genuinely different indent widths for
    # siblings (extra wrapper divs on some fields but not others) — this
    # must not be misread as nesting between unrelated fields.
    tree = (
        "                  [1] textbox: A\n"
        "                    [2] textbox: B\n"  # 2 spaces deeper than A, but NOT a child of A
        "              [3] textbox: C\n"  # shallower again
    )
    fields = collect_fields(tree, {})
    assert [f.label for f in fields] == ["A", "B", "C"]
    assert all(f.options == [] for f in fields)

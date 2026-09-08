from app.services.engine.submit import (
    find_invalid_field_labels,
    find_submit_button,
    read_outcome,
)

# Real, multi-line fragment captured live from an actual Anthropic
# Greenhouse form's submit button (see PLAN.md / FLAGGED.md — this is the
# exact case that caught a real bug: every OTHER test in this file used a
# single-line tree, where `^`/`$` trivially matched string start/end even
# WITHOUT re.MULTILINE, completely masking that the real regex couldn't
# match a button in the middle of a real, multi-line tree. A live
# end-to-end submission failed with "submit button not found" before this
# was caught and fixed (added re.M).
REAL_MULTILINE_TREE = (
    "              [5-107] button: Apply\n"
    "                        [5-412] button: Toggle flyout\n"
    "                      [5-1925] button: Attach\n"
    "                    [5-1936] button: Dropbox\n"
    "                      [5-2351] button: Toggle flyout\n"
    "              [5-2662] button: Submit application\n"
)
REAL_MULTILINE_XPATH_MAP = {
    "5-107": "//button[@id='apply-landing']",
    "5-2662": "//button[@id='submit-real']",
}


def test_finds_submit_button_in_the_middle_of_a_real_multiline_tree():
    assert (
        find_submit_button(REAL_MULTILINE_TREE, REAL_MULTILINE_XPATH_MAP)
        == "//button[@id='submit-real']"
    )


def test_finds_submit_application_button():
    tree = "                [5-1] button: Submit Application\n"
    xmap = {"5-1": "//button[@id='submit']"}
    assert find_submit_button(tree, xmap) == "//button[@id='submit']"


def test_finds_bare_submit_button():
    tree = "[5-1] button: Submit\n"
    xmap = {"5-1": "//button[@id='submit']"}
    assert find_submit_button(tree, xmap) == "//button[@id='submit']"


def test_ignores_apply_button_variant_reused_for_landing_page():
    # "Apply Now" also matches the landing-page Apply button pattern in
    # runner.py, but on the actual form page it's the real submit control —
    # both regexes deliberately overlap on this label.
    tree = "[5-1] button: Apply Now\n"
    xmap = {"5-1": "//button[@id='apply']"}
    assert find_submit_button(tree, xmap) == "//button[@id='apply']"


def test_returns_none_when_no_submit_button_present():
    tree = "[1] textbox: First Name\n[2] button: Cancel\n"
    assert find_submit_button(tree, {}) is None


def test_returns_none_when_xpath_missing_from_map():
    tree = "[5-1] button: Submit\n"
    assert find_submit_button(tree, {}) is None


def test_recognizes_confirmation_page():
    tree = "[1] heading: Thank you for applying!\n[2] StaticText: We'll be in touch.\n"
    result = read_outcome(tree)
    assert result.outcome == "completed"


def test_recognizes_received_application_confirmation():
    tree = (
        "[1] StaticText: We've received your application and will review it shortly.\n"
    )
    assert read_outcome(tree).outcome == "completed"


def test_recognizes_validation_error():
    tree = "[1] StaticText: Email is a required field\n"
    result = read_outcome(tree)
    assert result.outcome == "validation_error"


def test_ordinary_required_field_asterisk_copy_is_not_a_validation_error():
    # "* indicates a required field" is normal form copy, not a submission
    # failure — must not be misread as one.
    tree = "[1] StaticText: * indicates a required field\n[2] textbox: Email\n"
    result = read_outcome(tree)
    assert result.outcome == "unknown"


def test_unrecognized_page_state_is_unknown():
    tree = "[1] textbox: First Name\n[2] textbox: Email\n"
    assert read_outcome(tree).outcome == "unknown"


def test_finds_the_field_whose_error_appears_directly_below_it():
    # Real fix: read_outcome() only knows A validation error exists
    # somewhere — this finds WHICH field, matching the real shape
    # observed live (the error text renders immediately after the
    # invalid field's own group in the tree).
    tree = (
        "[1] group: Why Anthropic?*\n"
        "  [2] textbox: Why Anthropic?\n"
        "  [3] StaticText: This field is required.\n"
        "[4] group: Website\n"
        "  [5] textbox: Website\n"
    )
    assert find_invalid_field_labels(tree) == ["Why Anthropic?"]


def test_multiple_invalid_fields_are_all_found_in_order():
    tree = (
        "[1] group: Agreement to Arbitrate*\n"
        "  [2] combobox: Agreement to Arbitrate\n"
        "  [3] StaticText: This field is required.\n"
        "[4] group: Gender\n"
        "  [5] combobox: Gender\n"
        "[6] group: Country*\n"
        "  [7] combobox: Country\n"
        "  [8] StaticText: is a required field\n"
    )
    assert find_invalid_field_labels(tree) == ["Agreement to Arbitrate", "Country"]


def test_error_text_line_itself_does_not_get_mistaken_for_the_field_label():
    # The error StaticText line ITSELF matches the field-line shape
    # ([id] role: text) — it must not overwrite the real label sitting
    # right above it before being attributed.
    tree = (
        "[1] group: Please read the arbitration agreement below*\n"
        "  [2] combobox: Please read the arbitration agreement below\n"
        "  [3] StaticText: This field is required.\n"
    )
    assert find_invalid_field_labels(tree) == [
        "Please read the arbitration agreement below"
    ]


def test_duplicate_errors_for_the_same_field_are_deduped():
    tree = (
        "[1] group: Email*\n"
        "  [2] textbox: Email\n"
        "  [3] StaticText: This field is required.\n"
        "  [4] StaticText: Please enter a valid email.\n"
    )
    assert find_invalid_field_labels(tree) == ["Email"]


def test_no_validation_errors_returns_empty_list():
    tree = "[1] textbox: First Name\n[2] textbox: Email\n"
    assert find_invalid_field_labels(tree) == []


def test_a_dropdowns_own_toggle_button_is_never_mistaken_for_a_field_label():
    # Real bug found live: "Toggle flyout" (a dropdown's own open/close
    # button, not a real field) sat closer to the error text than the
    # actual field's group label and got wrongly reported as the invalid
    # field. Only TARGET_ROLES / group lines are tracked as labels now.
    tree = (
        "[1] group: Please read the arbitration agreement below*\n"
        "  [2] combobox: Please read the arbitration agreement below\n"
        "    [3] button: Toggle flyout\n"
        "  [4] StaticText: This field is required.\n"
    )
    assert find_invalid_field_labels(tree) == [
        "Please read the arbitration agreement below"
    ]

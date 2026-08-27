from app.services.engine.submit import find_submit_button, read_outcome


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
    tree = "[1] StaticText: We've received your application and will review it shortly.\n"
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

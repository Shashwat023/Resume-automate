"""
Focused regression test for runner.py's _APPLY_BUTTON regex — the same
missing-re.MULTILINE bug found and fixed in submit.py's _SUBMIT_BUTTON
(see FLAGGED.md). This one was silently masked throughout the whole
project because every URL actually tested shows the form directly with no
landing-page Apply click needed, so its always-broken return value never
mattered — but it was just as broken, and would matter the moment a real
ATS gates the form behind a landing-page Apply button.
"""

from app.services.engine.runner import _APPLY_BUTTON


def test_matches_apply_button_in_the_middle_of_a_multiline_tree():
    tree = (
        "[1] heading: Staff Engineer\n"
        "[2] StaticText: San Francisco, CA\n"
        "              [5-107] button: Apply\n"
        "[4] paragraph: About the role\n"
    )
    match = _APPLY_BUTTON.search(tree)
    assert match is not None
    assert match.group(1) == "5-107"


def test_does_not_match_a_single_line_string_falsely_passing_without_multiline():
    # A sanity check that this genuinely exercises re.MULTILINE and isn't
    # accidentally passing for some other reason.
    tree_no_multiline_needed = "[5-107] button: Apply\n"
    assert _APPLY_BUTTON.search(tree_no_multiline_needed) is not None

"""
match_field/resolve_value are what Tier 0 uses to decide which form fields
it can safely fill. The label set here is the exact set observed on a real
Anthropic Greenhouse application form during manual testing (see PLAN.md).
"""

import pytest

from app.domain.semantic_dictionary import match_field, resolve_value

PROFILE = {
    "full_name": "Jordan Smith",
    "email": "jordan@example.com",
    "phone": "+14155551234",
    "linkedin_url": "https://linkedin.com/in/jordansmith",
    "portfolio_url": "https://jordansmith.dev",
    "current_title": "Senior Account Executive",
    "current_company": "Acme Corp",
    "years_of_experience": 8,
}


@pytest.mark.parametrize(
    "label,expected_attr",
    [
        ("First Name", "full_name"),
        ("Last Name", "full_name"),
        ("Email", "email"),
        ("Phone", "phone"),
        ("LinkedIn Profile", "linkedin_url"),
        ("Website", "portfolio_url"),
        ("Current Company", "current_company"),
        ("Years of Experience", "years_of_experience"),
    ],
)
def test_matches_known_field_labels(label, expected_attr):
    match = match_field(label)
    assert match is not None
    assert match.profile_attr == expected_attr


@pytest.mark.parametrize(
    "label",
    [
        "(Optional) Personal Preferences",
        "When is the earliest you would want to start working with us?",
        "Do you have any deadlines or timeline considerations we should be aware of?",
        "Why Anthropic?",
        "Additional Information",
    ],
)
def test_free_text_judgment_questions_are_left_unmatched(label):
    # These are exactly the fields Tier 0 correctly left unmatched during
    # the real Anthropic Greenhouse form test — Tier 1/2/3 territory.
    assert match_field(label) is None


def test_relocation_address_question_matches_address_pattern_but_has_no_value():
    # This label ("What is the address from which you plan on working? ...")
    # DOES match the \baddress\b pattern — it's not a Tier-0/Tier-1 boundary
    # case at the matching level. It was unmatched in the real form test only
    # because that profile had no `address` set, so resolve_value() returned
    # None and the harvester's `if not value` check skipped it. Pre-existing
    # behavior, not something this restructure touched — flagged separately
    # as a minor ambiguity (this is really a "where would you work from"
    # judgment question, not a home-address field) rather than "fixed" here.
    match = match_field(
        "What is the address from which you plan on working? If you would "
        'need to relocate, please type "relocating".'
    )
    assert match is not None
    assert match.profile_attr == "address"
    assert resolve_value({}, match) is None


def test_first_name_transform_takes_first_token():
    match = match_field("First Name")
    assert resolve_value(PROFILE, match) == "Jordan"


def test_last_name_transform_takes_last_token():
    match = match_field("Last Name")
    assert resolve_value(PROFILE, match) == "Smith"


def test_last_name_transform_returns_none_for_single_word_name():
    match = match_field("Last Name")
    assert resolve_value({"full_name": "Cher"}, match) is None


def test_resolve_value_returns_none_for_missing_profile_attr():
    match = match_field("Email")
    assert resolve_value({}, match) is None


def test_first_name_pattern_wins_over_generic_name_pattern():
    # "first name" must not fall through to the generic "name" pattern
    match = match_field("First Name")
    assert match.transform == "first_name"

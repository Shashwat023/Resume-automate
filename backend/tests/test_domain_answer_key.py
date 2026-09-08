from app.domain.answer_key import normalize_question, question_hash


def test_normalize_lowercases():
    assert normalize_question("Why Anthropic?") == "why anthropic"


def test_normalize_collapses_whitespace():
    assert (
        normalize_question("Why   do you   want\tto work here?")
        == "why do you want to work here"
    )


def test_normalize_strips_punctuation():
    assert (
        normalize_question("What's your availability (start date)?")
        == "whats your availability start date"
    )


def test_normalize_strips_leading_trailing_whitespace():
    assert normalize_question("   Why Anthropic?   ") == "why anthropic"


def test_differently_formatted_same_question_hashes_identically():
    a = question_hash("Why Anthropic?")
    b = question_hash("  why anthropic  ")
    c = question_hash("WHY   ANTHROPIC")
    assert a == b == c


def test_different_questions_hash_differently():
    assert question_hash("Why Anthropic?") != question_hash(
        "Why do you want to relocate?"
    )


def test_hash_is_deterministic_and_sha256_length():
    h = question_hash("Why Anthropic?")
    assert h == question_hash("Why Anthropic?")
    assert len(h) == 64  # sha256 hex digest

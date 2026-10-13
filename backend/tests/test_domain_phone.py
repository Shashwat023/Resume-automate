import pytest

from app.domain.phone import parse_phone


@pytest.mark.parametrize(
    ("raw", "dial", "national"),
    [
        ("+918303545027", "+91", "8303545027"),
        ("+14155552671", "+1", "4155552671"),
        ("+442071838750", "+44", "2071838750"),
    ],
)
def test_parse_phone_splits_dial_code_and_national_number(raw, dial, national):
    parsed = parse_phone(raw)

    assert parsed is not None
    assert (parsed.dial_code, parsed.national_number) == (dial, national)


def test_parse_phone_keeps_significant_leading_zero():
    parsed = parse_phone("+390212345678")

    assert parsed is not None
    assert parsed.national_number == "0212345678"


def test_parse_phone_without_plus_uses_default_country_name():
    parsed = parse_phone("8303545027", "India")

    assert parsed is not None
    assert parsed.dial_code == "+91"
    assert parsed.e164 == "+918303545027"


def test_parse_phone_unparseable_returns_none():
    assert parse_phone("not a number", "India") is None

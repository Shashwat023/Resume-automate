"""Pure phone-number parsing used by the deterministic form tiers."""

from dataclasses import dataclass

import phonenumbers


# Profile country values have historically been a mixture of ISO codes and
# display names.  Keep this deliberately local and deterministic rather than
# asking an LLM to infer a dialing code.
_COUNTRY_REGIONS = {
    "australia": "AU",
    "austria": "AT",
    "bangladesh": "BD",
    "belgium": "BE",
    "brazil": "BR",
    "canada": "CA",
    "china": "CN",
    "denmark": "DK",
    "egypt": "EG",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "greece": "GR",
    "hong kong": "HK",
    "india": "IN",
    "indonesia": "ID",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "kenya": "KE",
    "malaysia": "MY",
    "mexico": "MX",
    "netherlands": "NL",
    "new zealand": "NZ",
    "nigeria": "NG",
    "norway": "NO",
    "pakistan": "PK",
    "philippines": "PH",
    "poland": "PL",
    "portugal": "PT",
    "singapore": "SG",
    "south africa": "ZA",
    "south korea": "KR",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "thailand": "TH",
    "turkey": "TR",
    "uae": "AE",
    "united arab emirates": "AE",
    "united kingdom": "GB",
    "united states": "US",
    "usa": "US",
    "uk": "GB",
    "vietnam": "VN",
}

# Display candidates deliberately preserve the ambiguity of +1.  They are
# used for matching a select's human-readable option, never as a country
# inference mechanism.
COUNTRY_NAMES_BY_DIAL: dict[str, tuple[str, ...]] = {
    "+1": ("United States", "Canada"),
    "+44": ("United Kingdom",),
    "+39": ("Italy",),
    "+91": ("India",),
    "+971": ("United Arab Emirates",),
}


@dataclass(frozen=True)
class ParsedPhone:
    dial_code: str
    national_number: str
    region: str | None
    e164: str


def _region(default_country: str | None) -> str | None:
    if not default_country:
        return None
    normalized = " ".join(default_country.strip().casefold().split())
    if len(normalized) == 2 and normalized.isalpha():
        return normalized.upper()
    return _COUNTRY_REGIONS.get(normalized)


def parse_phone(
    raw: str | None, default_country: str | None = None
) -> ParsedPhone | None:
    """Return a structured, valid phone number or ``None`` without guessing."""
    if not raw or not str(raw).strip():
        return None
    number = str(raw).strip()
    try:
        parsed = phonenumbers.parse(
            number, None if number.startswith("+") else _region(default_country)
        )
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(parsed):
        return None
    dial_code = f"+{parsed.country_code}"
    return ParsedPhone(
        dial_code=dial_code,
        national_number=phonenumbers.national_significant_number(parsed),
        region=phonenumbers.region_code_for_number(parsed) or _region(default_country),
        e164=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
    )


def _region_display_name(region: str) -> str:
    candidates = [name for name, code in _COUNTRY_REGIONS.items() if code == region]
    if not candidates:
        return region
    return max(candidates, key=len).title()


def country_names_for_dial(
    dial_code: str, region: str | None = None
) -> tuple[str, ...]:
    """Likely option names for a dial code, most specific first.

    The parsed number's own region wins (a +1 number from Canada must not be
    labelled "United States"); the static table and libphonenumber's region
    list supply the rest.
    """
    names: list[str] = []
    if region:
        names.append(_region_display_name(region))
    names.extend(COUNTRY_NAMES_BY_DIAL.get(dial_code, ()))
    try:
        for code in phonenumbers.region_codes_for_country_code(int(dial_code[1:])):
            if code != "001":
                names.append(_region_display_name(code))
    except ValueError:
        pass
    return tuple(dict.fromkeys(names))

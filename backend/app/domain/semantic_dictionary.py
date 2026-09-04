"""
Tier 0's semantic dictionary: normalized field-label pattern -> profile
attribute. Patterns are checked longest-first so "first name" wins over
the more generic "name" for a field labeled "First Name".

Only unambiguous, single-value identity/contact fields belong here. Free-text
judgment questions ("Why do you want to work here?") and fields needing a
value transform beyond straight copy (radio/select semantics) are Tier 1/2/3
territory — see PLAN.md's tier boundaries.

Moved here (from services/engine/semantic_dictionary.py) as part of the
clean-architecture restructure: pure functions, zero I/O, zero framework
imports — the textbook domain-layer fit.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldMatch:
    profile_attr: str
    transform: str | None = None  # None | "first_name" | "last_name"


# Ordered longest/most-specific pattern first within each tier of specificity.
_PATTERNS: list[tuple[re.Pattern, FieldMatch]] = [
    (re.compile(r"\bfirst\s*name\b"), FieldMatch("full_name", "first_name")),
    (
        re.compile(r"\blast\s*name\b|\bsurname\b|\bfamily\s*name\b"),
        FieldMatch("full_name", "last_name"),
    ),
    (re.compile(r"\bfull\s*name\b|^name$|\byour\s*name\b"), FieldMatch("full_name")),
    (re.compile(r"\be[\-\s]?mail\b"), FieldMatch("email")),
    (re.compile(r"\bphone\b|\bmobile\b|\bcell\b|\btelephone\b"), FieldMatch("phone")),
    (re.compile(r"\blinkedin\b"), FieldMatch("linkedin_url")),
    (re.compile(r"\bgithub\b"), FieldMatch("github_url")),
    (re.compile(r"\btwitter\b|\bx\.com\b"), FieldMatch("twitter_url")),
    (
        re.compile(r"\bportfolio\b|\bwebsite\b|\bpersonal\s*site\b"),
        FieldMatch("portfolio_url"),
    ),
    (
        re.compile(r"\bcurrent\s*(job\s*)?title\b|\bcurrent\s*role\b"),
        FieldMatch("current_title"),
    ),
    (re.compile(r"\bcurrent\s*(company|employer)\b"), FieldMatch("current_company")),
    (re.compile(r"\byears?\s*of\s*experience\b"), FieldMatch("years_of_experience")),
    (re.compile(r"\bnotice\s*period\b"), FieldMatch("notice_period")),
    (
        re.compile(
            r"\bexpected\s*salary\b|\bdesired\s*salary\b|\bsalary\s*expectation"
        ),
        FieldMatch("expected_salary"),
    ),
    (re.compile(r"\bcurrent\s*salary\b"), FieldMatch("current_salary")),
    (
        re.compile(r"\bpostal\s*code\b|\bzip\s*code\b|\bzip\b"),
        FieldMatch("postal_code"),
    ),
    # A bare `\baddress\b` over-matched a relocation JUDGMENT question on a
    # real form — "What is the address from which you plan on working? ...
    # type 'relocating'" — filling the candidate's literal home address into
    # a field that is really asking a yes/no relocation question (FLAGGED.md
    # #5). Narrowed to the shapes where "address" is genuinely the noun
    # naming the field: a qualifier immediately before it, an "address line
    # N", or the label starting with it. A question phrased ABOUT an address
    # ("What is the address from which...") no longer matches, and correctly
    # falls through to Tier 1, which can actually reason about it.
    (
        re.compile(
            r"\b(?:street|home|mailing|postal|permanent|current|residential"
            r"|present)\s*address\b"
            r"|\baddress\s*(?:line)?\s*\d*\s*$"
            r"|^address\b"
        ),
        FieldMatch("address"),
    ),
    (re.compile(r"\bcity\b"), FieldMatch("city")),
    (re.compile(r"\bstate\b|\bprovince\b"), FieldMatch("state")),
    (re.compile(r"\bcountry\b"), FieldMatch("country")),
    (
        re.compile(r"\buniversity\b|\bcollege\b|\balma\s*mater\b"),
        FieldMatch("university"),
    ),
    (re.compile(r"\bdegree\b"), FieldMatch("highest_degree")),
    (re.compile(r"\bgraduation\s*year\b"), FieldMatch("graduation_year")),
]


def match_field(label: str) -> FieldMatch | None:
    normalized = label.strip().lower()
    for pattern, match in _PATTERNS:
        if pattern.search(normalized):
            return match
    return None


def resolve_value(profile: dict, match: FieldMatch) -> str | None:
    raw = profile.get(match.profile_attr)
    if raw is None:
        return None
    if match.transform == "first_name":
        parts = str(raw).split()
        return parts[0] if parts else None
    if match.transform == "last_name":
        parts = str(raw).split()
        return parts[-1] if len(parts) > 1 else None
    return str(raw)

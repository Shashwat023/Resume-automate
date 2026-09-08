"""
Normalizes a free-text form question into a stable cache key for the
answers library. Pure functions, zero I/O — two differently-worded but
semantically identical questions across different ATS platforms should
still land on different keys (we don't attempt semantic dedup here, only
whitespace/punctuation/casing noise), but the SAME question re-rendered
with different surrounding whitespace or punctuation must hash identically,
or the cache never pays off.
"""

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s]")


def normalize_question(text: str) -> str:
    normalized = text.strip().lower()
    normalized = _PUNCTUATION.sub("", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    return normalized


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_question(text).encode("utf-8")).hexdigest()

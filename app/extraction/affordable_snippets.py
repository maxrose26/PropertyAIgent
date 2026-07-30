"""Keyword snippet extraction for affordable-housing evidence.

Ported from build_affordable_evidence_snippets.py - finds every mention of
an affordable-housing related term in the document text and returns a window
of surrounding text, deduped so nearby matches don't produce near-duplicate
snippets. These snippets are what the affordable evidence classifier prompt
gets shown.
"""
from __future__ import annotations

import re

SNIPPET_CHARS_BEFORE = 900
SNIPPET_CHARS_AFTER = 1600
MAX_SNIPPETS_PER_DOC = 8

SEARCH_TERMS = [
    "affordable housing", "affordable rent", "social rent", "shared ownership",
    "first homes", "intermediate housing", "discount market", "section 106", "s106",
    "planning obligation", "commuted sum", "off-site contribution", "off site contribution",
    "financial contribution", "viability", "viability assessment", "viability appraisal",
    "financial viability", "affordable contribution", "affordable homes", "affordable units",
    "100% affordable", "all affordable", "affordable-led", "registered provider",
    "housing association", "extra care", "supported living", "older persons",
    "specialist affordable", "no affordable housing", "vacant building credit",
    "policy h", "policy h4", "policy h2", "housing policy", "retirement apartments",
    "offered as affordable housing", "affordable housing requirement", "exceeds the council",
    "special circumstances", "council's requirement",
]


def build_snippets(text: str) -> list[tuple[str, str]]:
    """Returns list of (matched_term, snippet)."""
    if len(text) < 200:
        return []

    lower_text = text.lower()
    matches: list[tuple[int, str]] = []
    for term in SEARCH_TERMS:
        for match in re.finditer(re.escape(term.lower()), lower_text):
            matches.append((match.start(), term))
    matches.sort(key=lambda m: m[0])

    kept_positions: list[int] = []
    results: list[tuple[str, str]] = []

    for pos, term in matches:
        if len(kept_positions) >= MAX_SNIPPETS_PER_DOC:
            break
        if any(abs(pos - existing) < 1000 for existing in kept_positions):
            continue

        start = max(0, pos - SNIPPET_CHARS_BEFORE)
        end = min(len(text), pos + SNIPPET_CHARS_AFTER)
        snippet = text[start:end].replace("\n", " ")
        snippet = re.sub(r"\s+", " ", snippet).strip()

        results.append((term, snippet))
        kept_positions.append(pos)

    return results

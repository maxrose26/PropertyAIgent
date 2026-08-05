"""Deterministic allocation-identifier extraction (Sprint 3F, "Allocation
Policy Page Extraction", Parts 1-2).

A Local Plan allocation policy page (e.g. Places for Everyone's "Policy JP
Allocation 7 Elton Reservoir") carries its own identifier and title printed
directly on the page, in a small, closed set of real-world formats this
platform has already seen: "Policy JP Allocation 7", "JP Allocation 16",
"JPA 7" / "JPA7" / "JPA1.1", "HOM 2.30", "HS1". This module finds and
normalises those identifiers/titles from plain extracted page text - no AI,
no inference, no invented codes (matching app.extraction.local_plan's own
"never invent a policy reference" discipline, just applied deterministically
instead of via an LLM schema).

Pure functions, no I/O - app.visuals.page_detection uses these for Stage 1
candidacy signals, app.visuals.matching uses them for the Part 5 matching
priority chain, and app.visuals.pipeline persists their raw output as
VisualEvidence provenance (Part 7) regardless of whether a confident match
was ultimately made.
"""
from __future__ import annotations

import re

# "Policy JP Allocation 7" / "JP Allocation 16" are the SAME real-world
# allocation as "JPA 7" / "JPA16" - Places for Everyone's own convention
# ("JPA" = Joint Plan Allocation, confirmed against the plan's own Table
# 11.1 and individual policy pages, Sprint 3E/3F live research). These
# patterns capture the allocation NUMBER and construct the canonical
# "JPA<n>" comparison form directly, rather than normalising the whole
# printed phrase (which would never match a stored policy_reference like
# "JPA 7") - raw keeps the text exactly as printed, for provenance/display.
_JP_ALLOCATION_PATTERNS = [
    re.compile(r"\bpolicy\s+jp\s+allocation\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\bjp\s+allocation\s+(\d+)\b", re.IGNORECASE),
]

# Generic "Policy <code> Allocation <number>" (e.g. a hypothetical future
# Local Plan's "Policy HOM Allocation 12") - Part 1's own example. No
# platform-wide numbering convention can be assumed for an arbitrary code,
# so the full printed phrase is kept as both raw and (whitespace/case-
# normalised) comparison form - a weaker signal than the JPA-specific
# patterns above, but still a genuine, deterministic identifier. The
# negative lookahead excludes "jp" specifically - "Policy JP Allocation 7"
# is already captured precisely (and normalised to the canonical "JPA7"
# form) by _JP_ALLOCATION_PATTERNS above; without this exclusion this
# generic pattern ALSO matches the same text and normalises it differently
# ("POLICYJPALLOCATION7"), spuriously creating a second, conflicting
# "identifier" out of the exact same printed words (confirmed against real
# Places for Everyone data, Sprint 3F live validation).
_GENERIC_POLICY_ALLOCATION_PATTERNS = [
    re.compile(r"\bpolicy\s+(?!jp\b)[a-z]{2,6}\s+allocation\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bpolicy\s+allocation\s+\d+\b", re.IGNORECASE),
]

# Bare reference-code formats this platform's real Local Plans already use
# (Sprint 2/3E: JPA7/JPA 7/JPA1.1 for Places for Everyone and Bury; HOM 2.30
# for Stockport; HS1-style single-digit schemes seen elsewhere in the UK).
_CODE_PATTERNS = [
    re.compile(r"\bJPA\s?\d+(?:\.\d+)?\b", re.IGNORECASE),
    re.compile(r"\bHOM\s?\d+\.\d+\b", re.IGNORECASE),
    re.compile(r"\bHS\s?\d+\b", re.IGNORECASE),
]


def normalise_policy_reference(reference: str) -> str:
    """Strips whitespace and case so "JPA 7", "JPA7", and "jpa 7" all
    compare equal, without changing what's actually STORED as
    LocalPlanSite.policy_reference anywhere - normalisation is only ever
    used for comparison, never persisted as a replacement value (Part 2:
    "Normalise these identifiers", not "rewrite the source data")."""
    return re.sub(r"\s+", "", (reference or "")).upper()


def extract_allocation_identifiers(page_text: str) -> list[dict]:
    """Returns every distinct allocation reference identifier found in
    page_text, as [{"raw": <exact printed text>, "normalised": <comparison
    form>}, ...], deduplicated by normalised form (first raw spelling
    wins). Never invents an identifier - only what's genuinely printed on
    the page is ever returned."""
    text = page_text or ""
    found: dict[str, str] = {}  # normalised -> first raw spelling seen

    # Bare codes checked FIRST: a real Local Plan (Places for Everyone
    # included) typically prints the bare code ("JPA 7") ALONGSIDE the
    # fuller "Policy JP Allocation 7" phrasing on the same page, and the
    # bare code is also the form LocalPlanSite.policy_reference is
    # actually stored in (Sprint 2/3E live data) - preferring it as the
    # representative "raw" spelling is what lets Tier 1 (exact match) in
    # app.visuals.matching.match_allocation_reference succeed against real
    # data, rather than always falling through to Tier 2 (normalised).
    for pattern in _CODE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            normalised = normalise_policy_reference(raw)
            found.setdefault(normalised, raw)

    for pattern in _JP_ALLOCATION_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            normalised = f"JPA{match.group(1)}"
            found.setdefault(normalised, raw)

    for pattern in _GENERIC_POLICY_ALLOCATION_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            normalised = normalise_policy_reference(raw)
            found.setdefault(normalised, raw)

    return [{"raw": raw, "normalised": normalised} for normalised, raw in found.items()]


# A title, once an identifier is found, is expected to appear on the SAME
# line, immediately after it (Places for Everyone's real layout: "Policy JP
# Allocation 7 Elton Reservoir", "Picture 11.16 JPA 7 Elton Reservoir") -
# never pulled from anywhere else on the page, so a coincidental later
# mention of an unrelated place name can't be mistaken for the title.
_TITLE_AFTER_STRUCTURAL_PATTERNS = [
    re.compile(r"\bpolicy\s+jp\s+allocation\s+\d+[:\-]?\s+([A-Z][^\n\r.]{2,80})", re.IGNORECASE),
    re.compile(r"\bjp\s+allocation\s+\d+[:\-]?\s+([A-Z][^\n\r.]{2,80})", re.IGNORECASE),
    re.compile(r"\bpolicy\s+allocation\s+\d+[:\-]?\s+([A-Z][^\n\r.]{2,80})", re.IGNORECASE),
]
_TITLE_AFTER_CODE_PATTERN = re.compile(
    r"\b(?:JPA|HOM|HS)\s?\d+(?:\.\d+)?[:\-]?\s+([A-Z][^\n\r.]{2,80})", re.IGNORECASE,
)


def extract_allocation_title(page_text: str) -> str | None:
    """Best-effort deterministic title extraction - the short run of text
    immediately following a recognised identifier on the same line, e.g.
    "Elton Reservoir" out of "Policy JP Allocation 7 Elton Reservoir".
    Returns None (never a guess) when no identifier-adjacent title text is
    found - a page can still be a genuine candidate/match via its
    identifier alone with no title extracted (Part 7's "allocation title"
    provenance field is simply left null in that case, same as every other
    genuinely-absent evidence field elsewhere in this codebase)."""
    text = page_text or ""
    for pattern in _TITLE_AFTER_STRUCTURAL_PATTERNS:
        match = pattern.search(text)
        if match:
            return _clean_title(match.group(1))
    match = _TITLE_AFTER_CODE_PATTERN.search(text)
    if match:
        return _clean_title(match.group(1))
    return None


def _clean_title(raw: str) -> str | None:
    # Stop at the first line break already excluded by the regex's [^\n\r.]
    # class; this just trims trailing whitespace/punctuation noise (e.g. a
    # stray digit/caption fragment picked up past a comma).
    cleaned = re.sub(r"\s+", " ", raw).strip(" \t-:")
    return cleaned or None

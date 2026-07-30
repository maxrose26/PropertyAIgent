"""Regex-based housing-mix pass.

This is the cheap fallback signal that runs before the LLM affordable
classifier - it gives the reconciliation step (reconcile.py) something to
fall back on when the classifier can't find explicit evidence, and gives
a second opinion to sanity-check the classifier's numbers against.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.scrapers.unit_filter import extract_structured_total, extract_unit_counts

AFFORDABLE_UNIT_PATTERNS = [
    r"(\d+)\s*(?:no\.?\s*)?affordable\s*(?:units|homes|dwellings|apartments|houses)",
    r"affordable\s*(?:housing|units|homes)[^.]{0,60}?(\d+)\s*(?:units|homes|dwellings)",
]

PRIVATE_UNIT_PATTERNS = [
    r"(\d+)\s*(?:no\.?\s*)?(?:private|open market|market)\s*(?:units|homes|dwellings|apartments|houses)",
]

AFFORDABLE_PCT_PATTERNS = [
    r"(\d+(?:\.\d+)?)\s*%\s*affordable",
    r"affordable[^.%]{0,30}?(\d+(?:\.\d+)?)\s*%",
]

TENURE_KEYWORDS = [
    "affordable rent", "social rent", "shared ownership", "shared equity",
    "discount market rent", "discount market sale", "first homes", "rent to buy",
]


def _first_match(patterns: list[str], text: str, cast=float) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            try:
                return cast(match.group(1))
            except ValueError:
                continue
    return None


def _tenure_split(text: str) -> str | None:
    lowered = text.lower()
    found = [kw for kw in TENURE_KEYWORDS if kw in lowered]
    return ", ".join(found) if found else None


@dataclass
class HousingMixResult:
    total_units: int | None
    affordable_units: int | None
    private_units: int | None
    affordable_percentage: float | None
    affordable_tenure_split: str | None
    confidence: str


def extract_housing_mix(text: str, portal_estimated_units: int | None = None) -> HousingMixResult:
    candidates = extract_unit_counts(text)
    structured_total = extract_structured_total(text)
    if structured_total is not None:
        # A labeled "Total proposed units" field on the Application Form
        # itself outranks every other source here, including the portal
        # listing's own one-line estimate - it's the applicant's own
        # explicit declared total, not a number that merely sits near a
        # dwelling-word somewhere in free-text prose (see
        # STRUCTURED_TOTAL_RE's docstring for the real case this fixes).
        total_units = structured_total
    elif candidates and portal_estimated_units:
        total_units = min(candidates, key=lambda c: abs(c - portal_estimated_units))
    elif candidates:
        total_units = max(candidates)
    else:
        total_units = portal_estimated_units
    affordable_units = _first_match(AFFORDABLE_UNIT_PATTERNS, text, cast=int)
    private_units = _first_match(PRIVATE_UNIT_PATTERNS, text, cast=int)
    affordable_pct = _first_match(AFFORDABLE_PCT_PATTERNS, text, cast=float)
    tenure_split = _tenure_split(text)

    if affordable_units is not None and private_units is None and total_units is not None:
        private_units = max(total_units - affordable_units, 0)

    if total_units and affordable_units is not None and private_units is not None:
        confidence = "high"
    elif total_units and (affordable_units is not None or affordable_pct is not None):
        confidence = "medium"
    else:
        confidence = "low"

    return HousingMixResult(
        total_units=total_units,
        affordable_units=affordable_units,
        private_units=private_units,
        affordable_percentage=affordable_pct,
        affordable_tenure_split=tenure_split,
        confidence=confidence,
    )

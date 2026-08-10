"""Houses vs Apartments vs Mixed classification, for the map/table view.

Two source fields, checked in priority order: SchemeIntelligence's own
housing_typology (free text - the AI's specific read of the actual unit
mix, e.g. "20 houses and 40 apartments") when it says something concrete,
falling back to development_type (a much coarser controlled-vocabulary
field, e.g. "mixed_apartments_and_houses") when housing_typology is null or
uninformative - which is most records, since documents don't always state
an explicit house/flat breakdown even when total units are known.
"""
from __future__ import annotations

import re

HOUSE_WORDS_RE = re.compile(r"\bhouses?\b|\bdwellinghouses?\b|\bbungalows?\b|\btownhouses?\b|\bvillas?\b", re.I)
APARTMENT_WORDS_RE = re.compile(r"\bflats?\b|\bapartments?\b|\bmaisonettes?\b", re.I)

# A scheme mentioning both house and apartment words isn't necessarily an
# even mix - "2 houses and 48 apartments" is overwhelmingly an apartment
# scheme with a token number of houses. When housing_typology states an
# explicit count against each (only a minority of records do - most just
# name the types with no numbers, e.g. "houses and flats"), a lopsided split
# is reclassified as its dominant type rather than left as "Mixed", with the
# real split kept as a note (see housing_type_note) rather than discarded.
HOUSE_COUNT_RE = re.compile(r"(\d+)\s*(?:no\.?\s*)?(?:houses?|dwellinghouses?|bungalows?|townhouses?|villas?)\b", re.I)
APARTMENT_COUNT_RE = re.compile(r"(\d+)\s*(?:no\.?\s*)?(?:flats?|apartments?|maisonettes?)\b", re.I)
MIXED_DOMINANCE_THRESHOLD = 0.8


def _extract_type_counts(text: str) -> tuple[int, int] | None:
    """(house_count, apartment_count) if housing_typology states an explicit
    number against each type, else None - most records only name the types
    with no numbers at all, which this deliberately doesn't guess at."""
    house_match = HOUSE_COUNT_RE.search(text)
    apartment_match = APARTMENT_COUNT_RE.search(text)
    if not house_match or not apartment_match:
        return None
    return int(house_match.group(1)), int(apartment_match.group(1))

# development_type is a controlled vocabulary (see app/extraction/prompts.py's
# development_type enum) - bucketed by what it actually implies about the
# house/apartment split, not by tenure/affordability, which several of these
# values describe instead.
_DEV_TYPE_HOUSES = {"houses"}
_DEV_TYPE_APARTMENTS = {"apartments"}
_DEV_TYPE_MIXED = {
    "mixed_apartments_and_houses", "mixed_use_residential", "mixed_affordable_and_market_housing",
    "mixed_specialist_and_market_housing", "mixed_retirement_and_market_housing",
}
_DEV_TYPE_OTHER = {
    "supported_living", "care_home", "student_accommodation", "retirement_living", "build_to_rent",
    "conversion", "affordable_housing",
}

HOUSING_TYPE_LABELS = {
    "houses": "Houses",
    "apartments": "Apartments",
    "mixed": "Mixed (houses & apartments)",
    "other": "Other/specialist",
    "unknown": "Unknown",
}

# Sprint 4.5b Product Owner amendment (Part 21) - "Development Type" badge
# kind per bucket, for app.ui.shell's status_badge (_BADGE_KIND_STYLE holds
# the actual colour/icon). Kept alongside HOUSING_TYPE_LABELS rather than
# in shell.py (CLAUDE.md: "keep business logic out of the UI" - this
# mapping is part of the same classification vocabulary this module
# already owns, not a UI concern) - shell.py only ever receives the
# already-resolved kind string, never re-derives it from a raw bucket key.
HOUSING_TYPE_BADGE_KIND = {
    "houses": "dev_type_houses",
    "apartments": "dev_type_apartments",
    "mixed": "dev_type_mixed",
    "other": "dev_type_other",
    "unknown": "dev_type_unknown",
}


def format_affordable_display(units: int | None, percentage: float | None) -> str:
    """Sprint 4.5b Product Owner amendment (Part 18) - merges the
    Affordable Units count and Affordable % into one compact commercial-
    discovery-table string (e.g. "45 (30%)") rather than two separate
    columns. Used only for the Explore results table/card presentation -
    the underlying "Affordable Units"/"Affordable %" figures stay two
    separate columns in `filtered` and in the CSV export
    (app.ui.pages.0_Explore.build_report_rows), unaffected by this.

    Always returns a plain string, never None - a freshly-built pandas
    column mixing Python str and None (rather than a column that was
    int/float-typed with NaN from the start) hits the same Arrow-
    serialization instability tests/test_arrow_safety.py's
    arrow_safe_count hotfix already exists to avoid elsewhere in this
    codebase: confirmed in the browser, a None here rendered as the
    literal text "None" instead of a blank cell. units/percentage are
    cast with int()/round() rather than shown with a stray ".0" - both
    are always whole numbers in practice (a unit count, a percentage),
    even though the source columns are stored as float64 (pandas' own
    NaN-safe representation for a column with some missing values)."""
    if units is None and percentage is None:
        return "Not stated"
    if units is None:
        return f"{round(percentage):,}%"
    if percentage is None:
        return f"{round(units):,}"
    return f"{round(units):,} ({round(percentage):,}%)"

# RGBA outline colours for the map - a distinct hue per bucket, chosen to
# stay legible against every fill colour PLANNING_STATUS_COLORS uses (fill
# is the dominant filled circle, this is a 3px ring around it).
HOUSING_TYPE_COLORS: dict[str, list[int]] = {
    "houses": [139, 69, 19, 255],      # sienna
    "apartments": [0, 150, 150, 255],  # teal
    "mixed": [218, 165, 32, 255],      # goldenrod
    "other": [90, 90, 90, 255],        # dark grey
    "unknown": [255, 255, 255, 255],   # white (neutral - no signal)
}


def classify_housing_type(development_type: str | None, housing_typology: str | None) -> str:
    text = housing_typology or ""
    has_houses = bool(HOUSE_WORDS_RE.search(text))
    has_apartments = bool(APARTMENT_WORDS_RE.search(text))
    if has_houses and has_apartments:
        counts = _extract_type_counts(text)
        if counts:
            house_count, apartment_count = counts
            total = house_count + apartment_count
            if total > 0:
                house_share = house_count / total
                if house_share >= MIXED_DOMINANCE_THRESHOLD:
                    return "houses"
                if house_share <= 1 - MIXED_DOMINANCE_THRESHOLD:
                    return "apartments"
        return "mixed"
    if has_houses:
        return "houses"
    if has_apartments:
        return "apartments"

    dt = (development_type or "").strip().lower()
    if dt in _DEV_TYPE_HOUSES:
        return "houses"
    if dt in _DEV_TYPE_APARTMENTS:
        return "apartments"
    if dt in _DEV_TYPE_MIXED:
        return "mixed"
    if dt in _DEV_TYPE_OTHER:
        return "other"
    return "unknown"


def housing_type_note(development_type: str | None, housing_typology: str | None) -> str | None:
    """Non-None only when classify_housing_type reclassified a lopsided mix
    (>=80% one type) away from "Mixed" - surfaces the real split it's
    hiding, so "Houses" doesn't silently mean "100% houses" when a scheme
    actually has a handful of apartments too."""
    text = housing_typology or ""
    if not (HOUSE_WORDS_RE.search(text) and APARTMENT_WORDS_RE.search(text)):
        return None
    counts = _extract_type_counts(text)
    if not counts:
        return None
    house_count, apartment_count = counts
    total = house_count + apartment_count
    if total == 0:
        return None
    house_share = house_count / total
    if house_share >= MIXED_DOMINANCE_THRESHOLD:
        return f"Technically mixed: {house_count} houses, {apartment_count} apartments ({house_share:.0%} houses)"
    if house_share <= 1 - MIXED_DOMINANCE_THRESHOLD:
        return f"Technically mixed: {house_count} houses, {apartment_count} apartments ({1 - house_share:.0%} apartments)"
    return None

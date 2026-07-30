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

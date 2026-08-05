"""Stage-1 deterministic candidate PAGE detection (Sprint 3C, "Allocation
and Site-Plan Image Extraction", Part 5; extended Sprint 3F, "Allocation
Policy Page Extraction", Part 1) - runs on a candidate document's own
pages (already narrowed down by app.visuals.document_selection) to find
which SPECIFIC pages are worth rendering and sending to the vision model
at all. Never sends every page of every PDF - only pages with a real
textual/structural signal, or a low-text/high-graphics footprint typical
of a drawing sheet, become candidates. Stage 2 (AI visual classification,
app.visuals.classification) only ever runs on what this stage selects.

Sprint 3F added a dedicated signal for ALLOCATION POLICY PAGES - a distinct
document layout (identifier, title, boundary map, then substantial policy
wording underneath - e.g. Places for Everyone's "Policy JP Allocation 7
Elton Reservoir") that the original low-text-density/drawing-sheet
heuristics alone would systematically miss, since these pages are often
text-HEAVY, not sparse. find_allocation_policy_signals is deliberately its
own independent check, added to `reasons` unconditionally alongside (never
instead of, and never gated behind) the existing checks - a page with a
real allocation identifier is a candidate regardless of how much policy
text sits below the map.
"""
from __future__ import annotations

import re

from app.visuals.allocation_identifiers import extract_allocation_identifiers

TEXT_SIGNAL_PHRASES = [
    "site boundary", "red line", "application site", "allocation boundary",
    "masterplan", "proposed layout", "site location plan",
    "blue line", "phasing plan", "parameter plan", "development framework",
]

# Part 1's own example indicators, beyond the identifier codes themselves
# (which are found via app.visuals.allocation_identifiers.
# extract_allocation_identifiers below, not duplicated here as text).
_PICTURE_CAPTION_PATTERN = re.compile(r"\bpicture\s+\d", re.IGNORECASE)
_POLICY_NUMBER_PATTERN = re.compile(r"\bpolicy\s+number\b", re.IGNORECASE)

DRAWING_METADATA_PATTERNS = [
    r"\bdrawing\s*(no|number)\b", r"\bdwg\s*no\b", r"\bscale\s*[:\-]?\s*1\s*:\s*\d+",
    r"\bnorth\b.{0,10}\barrow\b", r"\brev(?:ision)?\s*[:\-]?\s*[a-z0-9]\b",
]

# Below this many characters on a page, plain text extraction is
# essentially "empty" - the hallmark of a drawing sheet, which carries its
# labelling as small annotations rather than body text. Combined with
# _page_has_vector_or_image_content below (never on text density alone -
# a genuinely blank/administrative page would look the same otherwise).
LOW_TEXT_DENSITY_THRESHOLD = 200


def find_text_signals(page_text: str) -> list[str]:
    """Every TEXT_SIGNAL_PHRASES entry found in this page's text
    (case-insensitive), or [] if none."""
    lowered = (page_text or "").lower()
    return [phrase for phrase in TEXT_SIGNAL_PHRASES if phrase in lowered]


def find_drawing_metadata_signals(page_text: str) -> list[str]:
    lowered = (page_text or "").lower()
    return [pattern for pattern in DRAWING_METADATA_PATTERNS if re.search(pattern, lowered)]


def has_low_text_density(page_text: str, threshold: int = LOW_TEXT_DENSITY_THRESHOLD) -> bool:
    return len((page_text or "").strip()) < threshold


def find_allocation_policy_signals(page_text: str) -> list[str]:
    """Sprint 3F Part 1 - deterministic signals that a page is an
    ALLOCATION POLICY PAGE (identifier + title + boundary map + policy
    wording), independent of text density. A page with a genuine
    identifier (app.visuals.allocation_identifiers.
    extract_allocation_identifiers - "JPA 7", "Policy JP Allocation 16",
    "HOM 2.30", "HS1"...) is always flagged, however much text
    surrounds it - text volume plays no part in this check at all."""
    text = page_text or ""
    reasons: list[str] = []

    identifiers = extract_allocation_identifiers(text)
    if identifiers:
        refs = ", ".join(i["raw"] for i in identifiers)
        reasons.append(f"allocation reference identifier(s) found: {refs}")

    lowered = text.lower()
    if _PICTURE_CAPTION_PATTERN.search(lowered) and "allocation" in lowered:
        reasons.append("picture caption alongside 'allocation' text (typical of an allocation policy page)")
    if _POLICY_NUMBER_PATTERN.search(lowered):
        reasons.append("text mentions: policy number")

    return reasons


def _page_has_vector_or_image_content(page) -> bool:
    """page: a pdfplumber Page. A drawing sheet is characterised by real
    vector line-work (walls, boundaries, hatching) or an embedded raster
    image (a scanned plan) - a genuinely blank/administrative low-text
    page has neither."""
    try:
        return bool(page.lines) or bool(page.rects) or bool(page.curves) or bool(page.images)
    except Exception:
        return False


def detect_candidate_pages_in_pdf(
    pdf_path: str, first_page: int = 1, last_page: int | None = None, max_pages: int | None = None,
) -> list[dict]:
    """Opens pdf_path once and evaluates every page in [first_page,
    last_page] (default: whole document, or capped at max_pages - Part 16's
    "maximum pages per document" limit) against every Stage 1 signal.
    Returns [{"page_number", "reasons": [...]}, ...] for every page with
    at least one signal - Part 5: "store why each candidate page was
    selected", which is exactly what "reasons" is for."""
    import pdfplumber

    candidates: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        end = min(last_page or total_pages, total_pages)
        pages_to_check = pdf.pages[first_page - 1:end]
        if max_pages:
            pages_to_check = pages_to_check[:max_pages]

        for i, page in enumerate(pages_to_check):
            page_number = first_page + i
            text = page.extract_text() or ""
            reasons: list[str] = []

            text_signals = find_text_signals(text)
            if text_signals:
                reasons.append(f"text mentions: {', '.join(text_signals)}")

            if find_drawing_metadata_signals(text):
                reasons.append("drawing metadata detected (scale/drawing number/north arrow/revision)")

            if has_low_text_density(text) and _page_has_vector_or_image_content(page):
                reasons.append("low text density with vector/image content (typical of a drawing sheet)")

            # Sprint 3F Part 1 - independent of every check above, and
            # never gated by has_low_text_density: an allocation policy
            # page is frequently TEXT-HEAVY (substantial policy wording
            # under the map), which must not disqualify it.
            reasons.extend(find_allocation_policy_signals(text))

            if reasons:
                candidates.append({"page_number": page_number, "reasons": reasons})

    return candidates

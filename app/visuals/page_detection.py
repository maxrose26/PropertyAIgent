"""Stage-1 deterministic candidate PAGE detection (Sprint 3C, "Allocation
and Site-Plan Image Extraction", Part 5) - runs on a candidate document's
own pages (already narrowed down by app.visuals.document_selection) to
find which SPECIFIC pages are worth rendering and sending to the vision
model at all. Never sends every page of every PDF - only pages with a
real textual/structural signal, or a low-text/high-graphics footprint
typical of a drawing sheet, become candidates. Stage 2 (AI visual
classification, app.visuals.classification) only ever runs on what this
stage selects.
"""
from __future__ import annotations

import re

TEXT_SIGNAL_PHRASES = [
    "site boundary", "red line", "application site", "allocation boundary",
    "masterplan", "proposed layout", "site location plan",
    "blue line", "phasing plan", "parameter plan", "development framework",
]

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

            if reasons:
                candidates.append({"page_number": page_number, "reasons": reasons})

    return candidates

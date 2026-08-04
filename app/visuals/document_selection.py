"""Deterministic candidate DOCUMENT selection (Sprint 3C, "Allocation and
Site-Plan Image Extraction", Part 4). Before any rendering or AI
classification happens, decide which documents are even worth looking at
for visual evidence, using title/filename/document-type keyword rules
alone - never AI, matching the same "deterministic before fuzzy" and
"don't process indiscriminately" discipline already established by
app.policy.report_discovery's classifier.

Works against both a planning application's own Document row
(app.db.models.Document) and a Local Plan source's MonitoredReport row -
both ultimately just need a title string and a type label to classify.
"""
from __future__ import annotations

# Ordered so the FIRST match found is returned - order doesn't change the
# outcome here (any single match is enough), but is kept stable/readable
# rather than relying on dict/set iteration order.
HIGH_PRIORITY_TERMS = [
    "site location plan", "location plan", "red line plan", "red edge plan",
    "site plan", "proposed site plan", "proposed layout", "illustrative masterplan",
    "masterplan", "phasing plan", "parameter plan", "allocation map",
    "policies map", "development framework", "access plan",
]

# Title/filename terms that mark a document as definitely NOT visual
# evidence regardless of anything else - checked before the high-priority
# list, so a coincidentally-named "site plan cover letter" (unlikely, but
# not impossible) is still excluded.
EXCLUDED_TERMS = [
    "application form", "fee calculation", "validation checklist",
    "covering letter", "cover letter", "correspondence",
]

# Document/report types already known (via app.extraction.pdf_text's own
# classifier, or app.policy.report_discovery's) to be purely textual -
# excluded outright even if a title term coincidentally matched, since
# these categories structurally never contain a site-plan-style drawing
# (Part 4: "purely textual reports with no relevant figures").
_EXCLUDED_TYPES = {"application_form", "decision_notice", "officer_report", "s106"}

# Local Plan source types where the allocation map / policies map is
# typically a PAGE inside the plan document itself, not a separately
# titled file - these are always worth a look regardless of the document's
# own title, unlike a narrowly-classified statistics document (an AMR or
# housing land supply statement, which is never a map).
_ALWAYS_CANDIDATE_REPORT_TYPES = {"adopted_plan", "emerging_plan", "local_plan"}


def classify_document_candidacy(title: str | None, doc_type: str | None = None) -> tuple[bool, str | None]:
    """Returns (is_candidate, matched_term). title is a document's own
    name/filename or report title; doc_type is Document.doc_type or
    MonitoredReport.source_type where available."""
    haystack = f" {(title or '').lower()} {(doc_type or '').lower()} ".replace("_", " ")

    for term in EXCLUDED_TERMS:
        if term in haystack:
            return False, None
    if doc_type in _EXCLUDED_TYPES:
        return False, None

    for term in HIGH_PRIORITY_TERMS:
        if term in haystack:
            return True, term

    if doc_type in _ALWAYS_CANDIDATE_REPORT_TYPES:
        return True, None  # candidate by document type, not a specific title term

    return False, None


def select_candidate_documents(documents: list) -> list[dict]:
    """documents: list[app.db.models.Document]. Returns
    [{"document": doc, "matched_term": str | None}, ...] for every
    document that passes classify_document_candidacy."""
    candidates = []
    for doc in documents:
        is_candidate, term = classify_document_candidacy(doc.document_name, doc.doc_type)
        if is_candidate:
            candidates.append({"document": doc, "matched_term": term})
    return candidates


def select_candidate_reports(reports: list) -> list[dict]:
    """reports: list[app.db.models.MonitoredReport]. Same shape, for Local
    Plan sources."""
    candidates = []
    for report in reports:
        is_candidate, term = classify_document_candidacy(report.title, report.source_type)
        if is_candidate:
            candidates.append({"report": report, "matched_term": term})
    return candidates

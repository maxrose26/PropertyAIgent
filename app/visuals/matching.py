"""Deterministic (and, where genuinely necessary, confidence-scored but
never auto-applied-when-ambiguous) matching of a rendered visual to the
domain objects it's evidence for (Sprint 3C, "Allocation and Site-Plan
Image Extraction", Part 8).

Two lineages need two different strategies:

  - A visual from a planning APPLICATION's own Document: Application
    linkage is INHERITED from the Document (Document.application_id is
    never ambiguous - a Document belongs to exactly one Application), and
    Site linkage is INHERITED from that Application's own site_id, where
    the Application has already been confirmed/linked to a Site. Nothing
    here has to guess; if the Application isn't linked to a Site yet, the
    visual's site_id is correctly left null too, not guessed at.

  - A visual from a Local Plan's own MonitoredReport: local_plan_id is
    inherited the same deterministic way when the report is already
    linked to one. WHICH allocation within that plan the image shows is
    not deterministic in the same sense - it has to be inferred from
    whether the page's own text mentions a specific allocation's policy
    reference or name. An exact, UNAMBIGUOUS policy-reference match is
    trusted; anything weaker (a name-only match, or more than one
    candidate matching) is surfaced as an ambiguous match rather than
    guessed - Part 8: "never silently attach to wrong Allocation".

Pure functions throughout, matching every other app.visuals module - this
file never queries the database itself; callers load the relevant rows
and pass them in.
"""
from __future__ import annotations

import re

from app.visuals.allocation_identifiers import (
    extract_allocation_identifiers,
    extract_allocation_title,
    normalise_policy_reference,
)


def match_document_visual(document) -> dict:
    """document: app.db.models.Document (with .application already
    loaded/loadable). Fully deterministic - a Document always belongs to
    exactly one Application, and, if that Application has already been
    confirmed/linked to a Site, that Site."""
    application = document.application
    site_id = getattr(application, "site_id", None) if application else None
    return {
        "application_id": document.application_id,
        "site_id": site_id,
        "local_plan_id": None,
        "allocation_id": None,
        "match_method": "document_application_inheritance",
        "match_confidence": 1.0,
        "ambiguous": False,
        "detected_allocation_reference": None,
        "detected_allocation_title": None,
    }


def _normalise_for_search(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).lower()


def find_allocation_mentions(page_text: str, allocations: list) -> list[dict]:
    """allocations: list[app.db.models.LocalPlanSite], all belonging to
    the SAME local_plan already (callers must pre-filter - matching
    across plans is meaningless). Returns every allocation whose
    policy_reference or site_name is genuinely found in page_text, each
    tagged with how strong that signal is - an exact reference-code match
    is trusted far more than a name substring, since allocation names are
    often generic ("Land off Station Road") and can coincidentally
    recur."""
    haystack = _normalise_for_search(page_text)
    hits = []
    for allocation in allocations:
        reference = getattr(allocation, "policy_reference", None)
        if reference and _normalise_for_search(reference) in haystack:
            hits.append({"allocation": allocation, "method": "policy_reference", "confidence": 0.95})
            continue
        site_name = getattr(allocation, "site_name", None)
        if site_name and _normalise_for_search(site_name) in haystack:
            hits.append({"allocation": allocation, "method": "site_name", "confidence": 0.6})
    return hits


_JPA_BASE_GROUP_PATTERN = re.compile(r"^JPA(\d+)")


def _allocation_group(normalised: str) -> str:
    """Groups "JPA1.1"/"JPA1.2"/"JPA1" together as the same real-world
    allocation's own base number ("JPA1") for AMBIGUITY counting only -
    never for the actual match comparison itself, which stays exact/
    normalised as printed. Confirmed necessary against real Places for
    Everyone data (Sprint 3F live validation): "Policy JP Allocation 1"
    (no decimal - this module's own JP-Allocation pattern only captures
    the whole number) and "JPA1.1" (the bare code, WITH its decimal
    sub-part) are the SAME allocation printed two different ways on its
    own single-allocation page, and must not be counted as "two different
    allocations referenced here" just because they normalise differently."""
    match = _JPA_BASE_GROUP_PATTERN.match(normalised)
    return f"JPA{match.group(1)}" if match else normalised


def match_allocation_reference(page_text: str, allocations: list) -> dict:
    """Sprint 3F ("Allocation Policy Page Extraction", Part 5) - the full
    deterministic matching priority chain for a page carrying a printed
    allocation identifier/title:

        1. Exact policy reference (raw printed text == LocalPlanSite.
           policy_reference, verbatim)
        2. Normalised policy reference (whitespace/case-insensitive
           equality - "JPA7" on the page matches "JPA 7" in the database)
        3. Exact allocation title (the deterministically-extracted title
           text == LocalPlanSite.site_name, case/whitespace-insensitive)
        4. High-confidence review suggestion (app.visuals.matching.
           find_allocation_mentions's existing substring-based signal,
           reused rather than reimplemented - Part 2: "reuse existing
           policy reference matching wherever possible")
        5. Needs review (no signal at all)

    Only tier 1-3 ever return a non-null allocation_id, and only when
    UNAMBIGUOUS (exactly one candidate at that tier) - two allocations
    both matching the same tier is surfaced as ambiguous, never guessed
    (Part 5: "Never guess"). Confirmed necessary against real data (Sprint
    3F live validation): Places for Everyone's own Table 11.1 lists ~34
    different allocations' codes together on one overview page - a page
    printing MORE THAN ONE DISTINCT allocation code is never confidently
    "about" just one of them, even when only one of those codes happens to
    already have a LocalPlanSite row in THIS database (an overview page
    doesn't know or care which allocations happen to be onboarded yet) -
    such a page still surfaces as a review suggestion (tier "4"), never an
    auto-link. Returns the same dict shape as match_report_visual, plus
    detected_allocation_reference/detected_allocation_title for provenance
    (Part 7) regardless of whether a match was made."""
    identifiers = extract_allocation_identifiers(page_text)
    detected_title = extract_allocation_title(page_text)
    detected_reference = identifiers[0]["raw"] if identifiers else None

    def _result(allocation_id, method, confidence, ambiguous) -> dict:
        return {
            "application_id": None,
            "site_id": None,
            "local_plan_id": None,  # filled in by the caller, which knows the plan
            "allocation_id": allocation_id,
            "match_method": method,
            "match_confidence": confidence,
            "ambiguous": ambiguous,
            "detected_allocation_reference": detected_reference,
            "detected_allocation_title": detected_title,
        }

    if identifiers:
        page_is_about_one_allocation = len({_allocation_group(i["normalised"]) for i in identifiers}) == 1

        raw_set = {i["raw"].strip().lower() for i in identifiers}
        exact_hits = [a for a in allocations if a.policy_reference and a.policy_reference.strip().lower() in raw_set]
        norm_set = {i["normalised"] for i in identifiers}
        norm_hits = [
            a for a in allocations
            if a.policy_reference and normalise_policy_reference(a.policy_reference) in norm_set
        ]

        if page_is_about_one_allocation:
            if len(exact_hits) == 1:
                return _result(exact_hits[0].id, "exact_policy_reference", 1.0, False)
            if len(exact_hits) > 1:
                return _result(None, "exact_policy_reference", 1.0, True)
            if len(norm_hits) == 1:
                return _result(norm_hits[0].id, "normalised_policy_reference", 0.9, False)
            if len(norm_hits) > 1:
                return _result(None, "normalised_policy_reference", 0.9, True)
        elif exact_hits or norm_hits:
            # A multi-allocation overview/schedule page where exactly one
            # printed code happens to also be onboarded - a genuine,
            # worth-surfacing suggestion, but never auto-linked.
            method = "exact_policy_reference" if exact_hits else "normalised_policy_reference"
            confidence = 1.0 if exact_hits else 0.9
            return _result(None, method, confidence, True)

    if detected_title:
        title_hits = [
            a for a in allocations
            if a.site_name and a.site_name.strip().lower() == detected_title.strip().lower()
        ]
        if len(title_hits) == 1:
            return _result(title_hits[0].id, "exact_allocation_title", 0.8, False)
        if len(title_hits) > 1:
            return _result(None, "exact_allocation_title", 0.8, True)

    # Tier 4/5 - reuse the existing weaker substring-matching signal
    # verbatim (never reimplemented) as the "high-confidence review
    # suggestion" / "needs review" fallback.
    hits = find_allocation_mentions(page_text, allocations)
    if hits:
        best = max(hits, key=lambda h: h["confidence"])
        return _result(None, best["method"], best["confidence"], True)

    return _result(None, None, None, False)


def match_report_visual(report, page_text: str, allocations: list) -> dict:
    """report: app.db.models.MonitoredReport (or anything duck-typing
    .local_plan_id). allocations: every LocalPlanSite belonging to
    report.local_plan_id (caller loads these - this module never queries
    the DB itself). Delegates the actual allocation-matching decision to
    match_allocation_reference's Part 5 priority chain."""
    local_plan_id = report.local_plan_id
    if not local_plan_id:
        return {
            "application_id": None, "site_id": None, "local_plan_id": None, "allocation_id": None,
            "match_method": None, "match_confidence": None, "ambiguous": False,
            "detected_allocation_reference": None, "detected_allocation_title": None,
        }
    result = match_allocation_reference(page_text, allocations)
    result["local_plan_id"] = local_plan_id
    return result

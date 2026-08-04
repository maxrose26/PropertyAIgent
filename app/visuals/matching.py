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


def match_report_visual(report, page_text: str, allocations: list) -> dict:
    """report: app.db.models.MonitoredReport. allocations: every
    LocalPlanSite belonging to report.local_plan_id (caller loads these -
    this module never queries the DB itself)."""
    local_plan_id = report.local_plan_id
    hits = find_allocation_mentions(page_text, allocations) if local_plan_id else []

    # An exact policy-reference hit is only trustworthy when it's the ONLY
    # one found - two different reference codes both appearing on the same
    # page (a schedule page listing several allocations, say) is exactly
    # the ambiguous case that must go to review rather than being guessed.
    reference_hits = [h for h in hits if h["method"] == "policy_reference"]
    if len(reference_hits) == 1:
        hit = reference_hits[0]
        return {
            "application_id": None,
            "site_id": None,
            "local_plan_id": local_plan_id,
            "allocation_id": hit["allocation"].id,
            "match_method": "policy_reference",
            "match_confidence": hit["confidence"],
            "ambiguous": False,
        }

    if hits:
        # Either multiple candidates, or only a weaker name-only match -
        # both are surfaced for human review rather than auto-linked.
        best = max(hits, key=lambda h: h["confidence"])
        return {
            "application_id": None,
            "site_id": None,
            "local_plan_id": local_plan_id,
            "allocation_id": None,
            "match_method": best["method"],
            "match_confidence": best["confidence"],
            "ambiguous": True,
        }

    return {
        "application_id": None,
        "site_id": None,
        "local_plan_id": local_plan_id,
        "allocation_id": None,
        "match_method": None,
        "match_confidence": None,
        "ambiguous": False,
    }

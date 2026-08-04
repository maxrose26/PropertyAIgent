"""Deterministic document routing and conflict precedence for plan-level
evidence extraction (Sprint 3B, "AI Local Plan Evidence Extraction",
Parts 4 & 8).

Part 4: not every document should be sent to every extraction prompt - an
Annual Monitoring Report has no business being asked for plan_identity
fields it was never written to state, and sending it anyway just adds cost
and hallucination risk for no benefit. DOCUMENT_TYPE_TO_CATEGORIES is the
single source of truth for which of app.extraction.plan_evidence's four
categories a given MonitoredSource.source_type is even eligible for.

Part 8: the same LocalPlan can have several sources with genuinely
different figures for the same field (an older and a newer Annual
Monitoring Report, say). resolve_fact_conflict decides which one wins
using a deterministic precedence rule, or - if precedence can't safely
decide - reports a conflict so the caller queues it for review instead of
silently picking one.
"""
from __future__ import annotations

import re

# Which extraction categories (see app.extraction.plan_evidence.CATEGORIES)
# a given MonitoredSource/MonitoredReport source_type is eligible for. A
# source type not listed here (or mapped to an empty set) is never auto-
# selected for any category - "pdf"/"other"/"landing_page" etc. are
# generic/unclassified and need an explicit category passed in to be
# processed at all (see app.policy.extract_plan_evidence's --category
# override).
DOCUMENT_TYPE_TO_CATEGORIES: dict[str, frozenset[str]] = {
    "adopted_plan": frozenset({"plan_identity", "housing_requirement"}),
    "emerging_plan": frozenset({"plan_identity", "housing_requirement"}),
    # A generically-classified plan document (app.policy.report_discovery
    # couldn't tell adopted from emerging just from title/URL keywords) -
    # treated the same as either, since both categories are still safe to
    # attempt; plan_identity's own extraction will surface the real status.
    "local_plan": frozenset({"plan_identity", "housing_requirement"}),
    "local_development_scheme": frozenset({"plan_identity"}),
    "timetable": frozenset({"plan_identity"}),
    # Housing-supply monitoring amendment ("Add monitored housing supply
    # and delivery reports", Part 4's explicit routing table) - an AMR
    # covers annual delivery and, where a council bundles it in, the
    # five-year supply position too; sending both categories at an AMR is
    # deliberate, not accidental over-reach, since real AMRs commonly do
    # both. "annual_monitoring_report" is the new canonical spelling;
    # Sprint 3B's original "annual_monitoring_report" mapping is extended
    # in place rather than duplicated under a second key.
    "annual_monitoring_report": frozenset({"housing_delivery", "five_year_supply"}),
    "authority_monitoring_report": frozenset({"housing_delivery", "five_year_supply"}),
    "housing_delivery_statement": frozenset({"housing_delivery"}),
    "housing_delivery_report": frozenset({"housing_delivery"}),
    "housing_trajectory": frozenset({"housing_delivery"}),
    # "housing_delivery context only" (Part 4) - still routed to the
    # housing_delivery category (there is no separate category for HDT-
    # specific fields), but see DOCUMENT_TYPE_PRECEDENCE below: ranked
    # BELOW a genuine AMR/housing delivery report, since an HDT action
    # plan is remedial context rather than a fresh authoritative figure.
    "housing_delivery_test_action_plan": frozenset({"housing_delivery"}),
    "five_year_supply_statement": frozenset({"five_year_supply"}),  # legacy synonym
    "housing_land_supply_statement": frozenset({"five_year_supply"}),  # new canonical spelling
    "housing_need_assessment": frozenset({"housing_requirement"}),
    "inspectors_report": frozenset({"plan_identity"}),  # legacy synonym
    "inspector_report": frozenset({"plan_identity"}),  # new canonical spelling
    "main_modifications": frozenset({"plan_identity", "housing_requirement"}),
    "adoption_statement": frozenset({"plan_identity"}),
    "examination_library": frozenset({"plan_identity"}),
    # A generic evidence-base document could plausibly support any of the
    # three non-identity categories - lower precedence than a document
    # explicitly of that type (see DOCUMENT_TYPE_PRECEDENCE), so a real
    # five_year_supply_statement always outranks it when both exist.
    "evidence_library": frozenset({"housing_requirement", "housing_delivery", "five_year_supply"}),
    "pdf": frozenset(),
    "webpage": frozenset(),
    "landing_page": frozenset(),
    "consultation_portal": frozenset(),
    "policies_map": frozenset(),
    "other": frozenset(),
    # Index/discovery pages (housing-supply monitoring amendment, Part 2) -
    # these are pages that LIST reports, never documents in their own
    # right, so they're never eligible for any extraction category
    # themselves; app.policy.report_discovery is what turns their linked
    # documents into individually-classified MonitoredReport rows.
    "monitoring_page": frozenset(),
    "housing_land_supply_page": frozenset(),
    "amr_page": frozenset(),
    "policy_document_library": frozenset(),
}


def select_sources_for_category(sources: list, category: str) -> list:
    """sources: list[MonitoredSource]. Returns only the ones eligible for
    this extraction category, per DOCUMENT_TYPE_TO_CATEGORIES."""
    return [s for s in sources if category in DOCUMENT_TYPE_TO_CATEGORIES.get(s.source_type, frozenset())]


# Higher = more authoritative for the CURRENT position on a fact. Ordered
# roughly by how directly each document type speaks to the plan's actual
# current status/figures, not by general importance - e.g. an inspector's
# report is highly authoritative for examination facts but should not
# casually outrank an adoption statement for adopted status (Part 8's own
# example), which is why conflict resolution below also requires an
# UNAMBIGUOUS winner, not just "whichever ranks higher on this table".
DOCUMENT_TYPE_PRECEDENCE: dict[str, int] = {
    "adoption_statement": 100,
    "five_year_supply_statement": 90,
    "housing_land_supply_statement": 90,  # new canonical spelling, same rank
    "inspectors_report": 85,
    "inspector_report": 85,  # new canonical spelling, same rank
    "main_modifications": 80,
    "annual_monitoring_report": 75,
    "authority_monitoring_report": 75,  # new canonical spelling, same rank
    "housing_delivery_statement": 75,
    "housing_delivery_report": 75,
    "housing_delivery_test_action_plan": 70,  # context/remedial, not a fresh authoritative figure
    "housing_trajectory": 65,
    "housing_need_assessment": 60,
    "adopted_plan": 55,
    "local_development_scheme": 50,
    "timetable": 50,
    "local_plan": 45,  # generic/unclassified - genuinely unsure if adopted or emerging
    "emerging_plan": 40,
    "examination_library": 30,
    "evidence_library": 20,
    "pdf": 10,
    "webpage": 5,
    "landing_page": 5,
    "consultation_portal": 5,
    "policies_map": 5,
    "other": 5,
    "monitoring_page": 5,
    "housing_land_supply_page": 5,
    "amr_page": 5,
    "policy_document_library": 5,
}


def _precedence_key(source) -> tuple[int, str]:
    doc_precedence = DOCUMENT_TYPE_PRECEDENCE.get(source.source_type, 0)
    # String comparison is a reasonable, deterministic tiebreaker for
    # ISO-ish dates but not a guaranteed correct one across every format a
    # scraped published_date might arrive in - a known limitation, not
    # silently pretended away (see the module docstring's own framing:
    # this is a DETERMINISTIC rule, not a claim of perfect date parsing).
    published = source.published_date or ""
    return (doc_precedence, published)


def resolve_fact_conflict(candidates: list[dict]) -> tuple[dict | None, bool]:
    """candidates: [{"source": MonitoredSource, "fact": {field, value, ...}}, ...],
    all proposing a value for the SAME field. Returns (chosen, is_conflict):

    - No candidate has a non-null value -> (None, False) - nothing to propose.
    - Exactly one non-null value (whether from one source or several
      sources that all agree) -> that candidate, False.
    - Multiple DIFFERENT non-null values with an unambiguous highest-
      precedence source -> that candidate, False.
    - Multiple different values with tied precedence -> (None, True) - the
      caller must queue this for review rather than guess (Part 8: "If
      sources conflict and no safe precedence rule exists, queue for
      review")."""
    with_values = [c for c in candidates if c["fact"].get("value") is not None]
    if not with_values:
        return None, False

    distinct_values = {c["fact"]["value"] for c in with_values}
    if len(distinct_values) == 1:
        best = max(with_values, key=lambda c: _precedence_key(c["source"]))
        return best, False

    ranked = sorted(with_values, key=lambda c: _precedence_key(c["source"]), reverse=True)
    top, runner_up = ranked[0], ranked[1]
    if _precedence_key(top["source"]) > _precedence_key(runner_up["source"]):
        return top, False
    return None, True


def _extract_leading_year(text: str | None) -> str:
    """A bare 4-digit year pulled out of a reporting_period/base_date
    string ("2023/24" -> "2023", "1 April 2024" -> "2024") for use as a
    sortable string - good enough to order two MonitoredReports by which
    one's OWN figures are more recent, without needing full date parsing
    of every format a council might use."""
    if not text:
        return ""
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else ""


def _report_precedence_key(report) -> tuple[int, str, str]:
    doc_precedence = DOCUMENT_TYPE_PRECEDENCE.get(report.source_type, 0)
    # Part 5: "reporting period and base date matter more than file
    # download date" - the year embedded in base_date/reporting_period is
    # compared BEFORE publication_date, which only breaks a further tie
    # (e.g. two reports covering the same period, one a corrected reissue).
    period_year = _extract_leading_year(report.base_date) or _extract_leading_year(report.reporting_period)
    return (doc_precedence, period_year, report.publication_date or "")


def resolve_report_conflict(candidates: list[dict]) -> tuple[dict | None, bool]:
    """The MonitoredReport-level equivalent of resolve_fact_conflict:
    candidates: [{"report": MonitoredReport, "fact": {field, value, ...}}, ...],
    all proposing a value for the SAME field from separately-discovered
    reports. Same (chosen, is_conflict) contract, but ranked by
    _report_precedence_key (document type, then reporting/base-date year,
    then publication date) rather than a MonitoredSource's own
    published_date alone - Part 5's explicit precedence rules for the
    housing-supply monitoring amendment.

    Superseded reports are excluded before ranking even begins - a
    superseded report is never itself a live candidate for "current"
    evidence; app.policy.report_discovery is what keeps supersession
    itself queued for review when it's ambiguous, not this function."""
    current_only = [c for c in candidates if getattr(c["report"], "status", "current") == "current"]
    with_values = [c for c in current_only if c["fact"].get("value") is not None]
    if not with_values:
        return None, False

    distinct_values = {c["fact"]["value"] for c in with_values}
    if len(distinct_values) == 1:
        best = max(with_values, key=lambda c: _report_precedence_key(c["report"]))
        return best, False

    ranked = sorted(with_values, key=lambda c: _report_precedence_key(c["report"]), reverse=True)
    top, runner_up = ranked[0], ranked[1]
    if _report_precedence_key(top["report"]) > _report_precedence_key(runner_up["report"]):
        return top, False
    return None, True

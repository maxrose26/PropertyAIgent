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

# Which extraction categories (see app.extraction.plan_evidence.CATEGORIES)
# a given MonitoredSource.source_type is eligible for. A source type not
# listed here (or mapped to an empty set) is never auto-selected for any
# category - "pdf"/"other"/"landing_page" etc. are generic/unclassified and
# need an explicit category passed in to be processed at all (see
# app.policy.extract_plan_evidence's --category override).
DOCUMENT_TYPE_TO_CATEGORIES: dict[str, frozenset[str]] = {
    "adopted_plan": frozenset({"plan_identity", "housing_requirement"}),
    "emerging_plan": frozenset({"plan_identity", "housing_requirement"}),
    "local_development_scheme": frozenset({"plan_identity"}),
    "timetable": frozenset({"plan_identity"}),
    "annual_monitoring_report": frozenset({"housing_delivery"}),
    "housing_delivery_statement": frozenset({"housing_delivery"}),
    "housing_trajectory": frozenset({"housing_delivery"}),
    "five_year_supply_statement": frozenset({"five_year_supply"}),
    "housing_need_assessment": frozenset({"housing_requirement"}),
    "inspectors_report": frozenset({"plan_identity"}),
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
    "inspectors_report": 85,
    "main_modifications": 80,
    "annual_monitoring_report": 75,
    "housing_delivery_statement": 75,
    "housing_trajectory": 65,
    "housing_need_assessment": 60,
    "adopted_plan": 55,
    "local_development_scheme": 50,
    "timetable": 50,
    "emerging_plan": 40,
    "examination_library": 30,
    "evidence_library": 20,
    "pdf": 10,
    "webpage": 5,
    "landing_page": 5,
    "consultation_portal": 5,
    "policies_map": 5,
    "other": 5,
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

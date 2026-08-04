"""PolicyDocumentType classification (Sprint 3D, "Policy Document
Coverage & Discovery", Part 2) - a deterministic, keyword-based taxonomy
covering ANY planning-policy document a council publishes, broader than
app.policy.report_discovery.classify_report_type's existing routing-
focused vocabulary. That classifier exists to decide extraction
ELIGIBILITY (app.policy.document_selection) and has no rule at all for a
Policies Map, an interactive GIS viewer, an SPD, or a masterplan, because
none of those were ever routed to AI text extraction - this module exists
specifically to describe those document kinds too, for the coverage
engine (app.policy.coverage) to reason about what exists versus what's
still missing.

Same "deterministic before AI" discipline as every classifier already in
this codebase (app.policy.report_discovery, app.visuals.document_selection):
title/URL keyword matching only, never AI. An ambiguous document is
classified "other_policy_document" or "unknown" rather than guessed -
Part 2 never invents a more specific type than the evidence supports.
"""
from __future__ import annotations

# Part 2's vocabulary, verbatim. "unknown" and "other_policy_document" are
# both real, storable outcomes - never a null placeholder - matching
# app.visuals.IMAGE_TYPES' own "unknown" convention.
POLICY_DOCUMENT_TYPES = (
    "local_plan",
    "policies_map",
    "interactive_map",
    "allocation_map",
    "development_plan_map",
    "inset_map",
    "authority_monitoring_report",
    "housing_land_supply",
    "housing_trajectory",
    "housing_delivery_test",
    "local_development_scheme",
    "supplementary_planning_document",
    "masterplan",
    "evidence_base",
    "other_policy_document",
    "unknown",
)

# Human-readable labels for the coverage dashboard (Part 7).
POLICY_DOCUMENT_TYPE_LABELS = {
    "local_plan": "Local Plan",
    "policies_map": "Policies Map",
    "interactive_map": "Interactive Policies Map",
    "allocation_map": "Site Allocation Map",
    "development_plan_map": "Development Plan Map",
    "inset_map": "Inset Map",
    "authority_monitoring_report": "Authority Monitoring Report",
    "housing_land_supply": "Five Year Housing Land Supply Statement",
    "housing_trajectory": "Housing Trajectory",
    "housing_delivery_test": "Housing Delivery Test Action Plan",
    "local_development_scheme": "Local Development Scheme",
    "supplementary_planning_document": "Supplementary Planning Document",
    "masterplan": "Masterplan / Strategic Allocation Framework",
    "evidence_base": "Evidence Base",
    "other_policy_document": "Other Policy Document",
    "unknown": "Unclassified",
}

# Ordered most-specific-first: a document is classified by the FIRST rule
# that matches, since several patterns overlap (a generic "map" mention
# inside an otherwise-clearly-AMR title, say) - same AND-of-OR-groups
# shape as app.policy.report_discovery._CLASSIFICATION_RULES, where the
# combined title+URL text must contain at least one keyword from EVERY
# group for that rule to match.
_CLASSIFICATION_RULES: list[tuple[str, list[list[str]]]] = [
    # Interactive/GIS mapping services checked before the generic
    # "policies map" rule - "Interactive Policies Map" would otherwise
    # match the plain policies_map rule first and lose the more specific
    # "this is a live map viewer, not a static PDF" signal Part 5 needs.
    ("interactive_map", [["interactive"], ["map", "mapping"]]),
    ("interactive_map", [["arcgis", "mapserver", "feature server", "featureserver", "geoportal", "gis viewer", "map viewer"]]),
    ("inset_map", [["inset map", "inset maps"]]),
    ("allocation_map", [["allocation map", "allocations map", "site allocation map", "site allocations map"]]),
    ("development_plan_map", [["development plan map", "proposals map"]]),
    ("policies_map", [["policies map"]]),
    ("masterplan", [["masterplan", "strategic allocation framework", "development framework"]]),
    ("supplementary_planning_document", [["supplementary planning document", " spd ", "spd.pdf", "-spd", "spd-"]]),
    ("housing_delivery_test", [["housing delivery test", "hdt"], ["action plan"]]),
    ("housing_trajectory", [["trajectory"]]),
    ("housing_land_supply", [["housing land supply", "5yhls", "five year", "five-year", "5-year", "5 year"]]),
    ("authority_monitoring_report", [["authority monitoring report", "authoritys monitoring report", "annual monitoring report", " amr ", "amr.pdf", "amr-", "-amr"]]),
    ("local_development_scheme", [["local development scheme", " lds "]]),
    ("evidence_base", [["evidence base", "shlaa", "shma", "strategic housing land availability", "strategic housing market assessment"]]),
    ("local_plan", [["local plan"]]),
]


def classify_policy_document_type(title: str | None, url: str) -> tuple[str, str | None]:
    """Returns (policy_document_type, matched_rule). policy_document_type
    is never None - an unmatched document classifies as "unknown", a
    real, storable outcome rather than a null placeholder. matched_rule
    is None only for that unknown case, for the same "every automatic
    decision must be explainable" reason app.policy.document_selection
    keeps precedence explainable."""
    # Apostrophes stripped like app.policy.report_discovery.
    # classify_report_type does, for the same reason: a real council title
    # ("Authority's Monitoring Report") uses the possessive form as often
    # as the bare one.
    raw_text = f" {(title or '').lower()} {url.lower()} "
    haystack = raw_text.replace("'", "").replace("’", "")
    for doc_type, keyword_groups in _CLASSIFICATION_RULES:
        if all(any(kw in haystack for kw in group) for group in keyword_groups):
            return doc_type, f"{doc_type}_keywords"
    return "unknown", None

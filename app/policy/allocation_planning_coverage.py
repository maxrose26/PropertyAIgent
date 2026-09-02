"""Gate 4B ("Allocation <-> Site/Application Planning Activity Coverage") /
Gate 4C ("Strategic Opportunity Identification") -
maps the existing, mature app.reporting.allocation_development_coverage
engine's own 6-value classification onto the narrower product-facing
4-value vocabulary this gate's own task requires (FULL/PARTIAL/NONE_FOUND/
UNCERTAIN), and adds exactly one new, narrow, deterministic safety check
this gate's own real Trafford investigation proved necessary: a site-name
fuzzy match corroboration step, used only to decide whether a candidate
match found by app.extraction.local_plan.match_to_existing_site is safe
enough to treat as CONFIDENT for coverage purposes.

Deliberately NOT a new matching engine, NOT a new coverage-computation
engine - both already exist and are reused here verbatim
(app.extraction.local_plan.match_to_existing_site,
app.reporting.allocation_development_coverage.compute_development_coverage/
summarise_site_activity/build_allocation_development_coverage). This
module's own real reason to exist: Gate 4B's own real-Trafford
investigation found match_to_existing_site's 80.0 fuzzy threshold, alone,
produces confident-looking matches that are actually wrong when two
allocations share only a GENERIC word (e.g. "Trafford Waters" vs
"Manchester Waters Pomona Strand" - both contain "Waters", genuinely
different physical sites in different parts of the borough - Urmston vs
Pomona/Old Trafford), and separately when two unrelated sites share only
a generic BOROUGH/AREA name (e.g. "Land west of Skerton Road, Old
Trafford" vs "Harry Lord House, 120 Humphrey Road, Old Trafford" - sharing
only "Old Trafford", the wider area name, not a specific street/site
identifier). Never lowers match_to_existing_site's own threshold or
touches its own logic - adds one further, independent corroboration
check on top, used only to decide CONFIDENCE, never to reject or override
match_to_existing_site's own result."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.db.models import Site
from app.reporting.allocation_development_coverage import (
    CAPACITY_UNKNOWN,
    FULLY_ACCOUNTED_FOR,
    NO_IDENTIFIED_ACTIVITY,
    PARTIAL_COVERAGE,
    REVIEW_REQUIRED,
    SUBSTANTIALLY_COVERED,
    DevelopmentCoverageResult,
)

# --- Gate 4B product vocabulary (reused, not duplicated, wherever the
# existing engine already has an equivalent concept - see the mapping in
# classify_planning_activity_coverage below) ---------------------------------

FULL = "FULL"
PARTIAL = "PARTIAL"
NONE_FOUND = "NONE_FOUND"
UNCERTAIN = "UNCERTAIN"

# --- Site-match confidence corroboration (Gate 4B's own narrow addition) ----

# Generic words that appear across many genuinely different Trafford sites
# and therefore carry no real corroborating identity value on their own -
# real evidence: "Waters" (Trafford Waters vs Manchester Waters - different
# sites), "Trafford"/"Old Trafford"/"Sale"/"Altrincham"/"Stretford" (area
# names shared by dozens of unrelated sites), plus ordinary address nouns.
# A shared token OUTSIDE this set (e.g. "Pomona", "Stretford Mall",
# "Skerton") is real corroborating evidence; a shared token only INSIDE it
# is not - deliberately the smallest possible list, built from this gate's
# own real false-positive findings, not a generic stop-word dictionary.
_GENERIC_LOCALITY_TOKENS = frozenset({
    "land", "site", "road", "street", "lane", "drive", "avenue", "close", "way",
    "old", "new", "at", "of", "the", "and", "former", "house", "building",
    "waters", "trafford", "manchester", "sale", "altrincham", "stretford",
    "urmston", "partington", "carrington", "davenport", "green",
})
_TOKEN_RE = re.compile(r"[a-z]+")


def _significant_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _GENERIC_LOCALITY_TOKENS and len(t) >= 4}


@dataclass(frozen=True)
class SiteMatchAssessment:
    # "HIGH" (the allocation's own name and the matched Site's address
    # share at least one SPECIFIC, non-generic identifying token - real
    # corroborating evidence beyond the bare fuzzy score) or "LOW" (the
    # fuzzy score alone cleared match_to_existing_site's own threshold,
    # but nothing beyond generic/area-level wording ties the two together
    # - not safe to treat as a confident match for coverage purposes).
    confidence: str
    shared_tokens: frozenset[str]
    reason: str


def classify_site_match_confidence(allocation_site_name: str, matched_site: Site, fuzzy_score: float) -> SiteMatchAssessment:
    """Never touches match_to_existing_site's own threshold/logic - this
    runs strictly AFTER it, only on a candidate it already accepted, to
    decide whether that candidate is corroborated enough to feed
    confidently into coverage classification. See this module's own
    docstring for the two real Trafford false-positive cases this is
    built from."""
    allocation_tokens = _significant_tokens(allocation_site_name)
    site_tokens = _significant_tokens(matched_site.canonical_address or matched_site.display_address or "")
    shared = frozenset(allocation_tokens & site_tokens)

    if shared:
        return SiteMatchAssessment(
            "HIGH", shared,
            f"fuzzy score {fuzzy_score:.0f} corroborated by shared specific identifier(s): {sorted(shared)}",
        )
    return SiteMatchAssessment(
        "LOW", shared,
        f"fuzzy score {fuzzy_score:.0f} alone - no specific identifying wording shared beyond generic/area terms, "
        f"not safe to treat as a confident match",
    )


# --- Planning activity coverage (maps the EXISTING engine's own 6-value
# classification onto this gate's 4-value product vocabulary) ---------------

_COVERAGE_TO_GATE_4B = {
    FULLY_ACCOUNTED_FOR: FULL,
    SUBSTANTIALLY_COVERED: PARTIAL,
    PARTIAL_COVERAGE: PARTIAL,
    NO_IDENTIFIED_ACTIVITY: NONE_FOUND,
    CAPACITY_UNKNOWN: UNCERTAIN,
    REVIEW_REQUIRED: UNCERTAIN,
}


# Website V2 (Website V2 / Product Review + Deployment Preparation, Step
# 14) - this module's own classification/reason text already existed and
# was already safe, but was never wired into the product UI
# (app/ui/pages/3_Local_Plan_Sites.py used the underlying engine's own raw
# 6-value DEVELOPMENT_COVERAGE_LABELS instead - see that task's final
# report). These are the short, product-facing labels a land professional
# reads, one definition reused everywhere this classification is shown -
# never a second, slightly-different wording invented at the UI layer.
PLANNING_ACTIVITY_COVERAGE_LABELS = {
    FULL: "Fully represented by known activity",
    PARTIAL: "Partial activity identified",
    NONE_FOUND: "No identified activity",
    UNCERTAIN: "Activity uncertain — requires review",
}


@dataclass(frozen=True)
class PlanningActivityCoverage:
    classification: str  # FULL | PARTIAL | NONE_FOUND | UNCERTAIN
    reason: str
    underlying_classification: str  # the existing engine's own 6-value label, preserved for audit/explainability


def classify_planning_activity_coverage(coverage: DevelopmentCoverageResult) -> PlanningActivityCoverage:
    """Pure re-labelling of an ALREADY-COMPUTED DevelopmentCoverageResult
    (see app.reporting.allocation_development_coverage.
    compute_development_coverage / build_allocation_development_coverage,
    both reused verbatim, never reimplemented here) onto Gate 4B's own
    product vocabulary - no new capacity arithmetic, no new Site/
    Application logic, no LLM. NONE_FOUND is worded so it can never be
    read as a claim that no planning application exists (Gate 4B's own
    explicit product distinction) - it states only what the CURRENT
    Property AIgent evidence shows."""
    classification = _COVERAGE_TO_GATE_4B[coverage.development_coverage_classification]

    if classification == FULL:
        reason = (
            f"Known planning activity ({coverage.number_of_linked_applications} application(s) across "
            f"{coverage.number_of_sites_with_planning_activity} matched site(s)) accounts for approximately "
            f"{coverage.development_coverage_percentage:.0%} of the allocation's trusted capacity "
            f"({coverage.allocation_capacity:,} homes)."
        )
    elif classification == PARTIAL:
        reason = (
            f"Known planning activity accounts for approximately {coverage.development_coverage_percentage:.0%} "
            f"of the allocation's trusted capacity ({coverage.allocation_capacity:,} homes); approximately "
            f"{coverage.indicative_residual_capacity:,} homes of capacity are not currently accounted for by "
            f"identified planning activity in Property AIgent's current evidence."
        )
    elif classification == NONE_FOUND:
        reason = (
            "No sufficiently confident Site/Application match was found in Property AIgent's current evidence for "
            "this allocation. This describes the current state of Property AIgent's own planning data - it is not "
            "a statement that no planning application exists for this site."
        )
    else:  # UNCERTAIN
        reason = coverage.note or (
            "A candidate Site match and/or its associated planning activity exists, but capacity accounting could "
            "not be safely established (missing unit counts, a disputed relationship pending review, or unknown "
            "allocation capacity) - this requires human review before a confident coverage position can be stated."
        )

    return PlanningActivityCoverage(classification, reason, coverage.development_coverage_classification)


# --- Gate 4C ("Strategic Opportunity Identification") -----------------------
#
# Duplication finding (Gate 4C's own Step 3): the opportunity engine itself
# ALREADY EXISTS - app.reporting.allocation_development_coverage.
# build_opportunity_signal, already wired into production reporting
# (app.reporting.allocation_discovery's own card builder), already
# producing INVESTIGATE/MONITOR/LOWER_PRIORITY/INSUFFICIENT_EVIDENCE with
# an explicit ownership caveat, already never using an LLM. This gate does
# NOT reimplement it. The one real, evidenced gap this gate's own
# investigation found: build_opportunity_signal's own NO_IDENTIFIED_
# ACTIVITY reason ("No planning activity has been identified within this
# allocation.") is IDENTICAL whether literally nothing was ever found
# (e.g. AN9) or whether a real candidate Site was found but not safely
# corroborated (AN3 "Trafford Waters" - a genuine false match) or was
# corroborated but never recorded as a relationship (AN4 "Pomona" - a
# real, evidenced candidate). Step 18's own instruction is to prefer a
# REASON-level distinction over a new top-level coverage state - exactly
# what enrich_none_found_reason below does, appending one extra sentence
# to the EXISTING reasons list, never replacing build_opportunity_signal's
# own signal or its own primary reasons.
from app.extraction.local_plan import match_to_existing_site  # noqa: E402


def enrich_none_found_reason(
    allocation_site_name: str, candidate_sites: list[Site], opportunity: dict,
) -> dict:
    """Only ever appends one extra sentence to opportunity["reasons"] - never
    changes opportunity["signal"], never overrides build_opportunity_signal's
    own decision. Re-runs match_to_existing_site (already used elsewhere in
    the same request, cheap, deterministic, no LLM) purely to distinguish,
    for a NONE_FOUND-based INVESTIGATE, which of three real evidence shapes
    applies - "nothing found", "a candidate exists but isn't corroborated"
    (the Trafford Waters case), or "a corroborated candidate exists but has
    not yet been recorded as a relationship" (the Pomona case). No write to
    AllocationSiteRelationship happens here or anywhere in Gate 4C - this
    is evidence-pack enrichment only."""
    if not opportunity or "No planning activity has been identified" not in " ".join(opportunity.get("reasons", [])):
        return opportunity

    site, score = match_to_existing_site(allocation_site_name, candidate_sites)
    if site is None:
        note = "No candidate Site was identified by Property AIgent's own name/address matching either."
    else:
        assessment = classify_site_match_confidence(allocation_site_name, site, score)
        if assessment.confidence == "HIGH":
            note = (
                f"Property AIgent's own matching identified a plausible candidate Site ({site.display_address}) "
                f"corroborated by shared specific identifying wording, but this has not yet been recorded as a "
                f"confirmed Site relationship - this candidate should be reviewed before being relied upon."
            )
        else:
            note = (
                f"Property AIgent's own matching found a text-similar candidate Site ({site.display_address}), but "
                f"it shares no specific identifying wording with this allocation beyond generic terms - not treated "
                f"as a credible candidate."
            )

    enriched = dict(opportunity)
    enriched["reasons"] = [*opportunity["reasons"][:-1], note, opportunity["reasons"][-1]]
    return enriched

"""Allocation Development Coverage + Opportunity Intelligence (Stage 3A).

Turns the Stage 2D AllocationSiteRelationship many-to-many set into
deterministic development-coverage, phasing, and opportunity intelligence
for a Local Plan allocation. This is an EVIDENCE layer only - it never
equates "not currently accounted for by identified planning activity"
with "available land"/"available units"/"undeveloped land"/"uncontrolled
land"/"land for sale". Those are ownership/control conclusions, out of
scope here entirely (Stage 3A Section 1).

AUTHORITATIVE RELATIONSHIP SOURCE (Section 3): every function in this
module reasons over AllocationSiteRelationship, never LocalPlanSite.
matched_site_id - a large allocation may relate to several Sites, and
this module preserves that structure throughout rather than collapsing
it to one arbitrary "the" Site the way the pre-Stage-2D card logic in
app.reporting.allocation_discovery (assess_delivery_scope, still used for
its own OWN, untouched legacy card fields) necessarily did.

STAGE 3B FINAL PRE-MERGE AMENDMENT ("Disputed-Relationship Coverage
Safety", Sections 5/6): AllocationSiteRelationship.review_status now
directly affects coverage arithmetic, not just display. A "rejected"
relationship is excluded from coverage entirely (not a related Site, not
counted anywhere - see build_allocation_development_coverage's own
filter). A "needs_confirmation" relationship that genuinely contributes a
real capacity number forces development_coverage_classification to
REVIEW_REQUIRED (DISPUTED_RELATIONSHIP_NOTE) rather than silently folding
disputed evidence into a confident percentage/residual - the relationship
row itself is still retained and still counted as related, only the
DERIVED commercial conclusion is withheld pending human review. See
compute_development_coverage's own disputed_sites check and
SiteActivitySummary.relationship_review_status. Deliberately never reads
LocalPlanSite.review_status for this - that field carries unrelated Local
Plan content-review meaning (Section 6's own "do not conflate" rule).

SAFE AGGREGATION (Section 4): the platform holds no dedicated "this
application supersedes that one" relationship - only status/decision
text and a review-status/extraction-completeness state. Rather than
invent a duplicate-detection heuristic, this module reuses the ONE
mechanism this codebase already established for exactly this class of
problem: app.ui.common.pick_representative_application, the same
"one current scheme per Site" selector every other Application-facing
view in this codebase already trusts (see app.reporting.residential_mix's
own module docstring for the identical reasoning). Applying it PER SITE
means outline/reserved-matters pairs, amendments, and superseded
applications on the SAME site are never double-counted - only one
representative application's unit count is ever counted per Site.
Summing across DISTINCT Sites is then safe, since each Site is
genuinely separate land. If a Site has planning activity but its
representative application's unit count cannot be determined, the whole
allocation's capacity accounting falls back to REVIEW_REQUIRED rather
than silently treating that Site as zero (Section 4's explicit
"manufacturing a number" prohibition).

HOUSING MIX (Section 8): reuses app.reporting.residential_mix.
build_residential_mix wholesale for per-Site residential-mix intelligence
- no duplicate housing-mix storage or computation is introduced here.
Per-bedroom-size counts and storeys/height are NOT extracted anywhere on
this platform today (confirmed by architecture audit against
app.extraction.housing_mix, app.extraction.prompts and the
SchemeIntelligence model - a genuine "never asked the question" schema
gap, not a bug); residential_mix.py already reports this honestly rather
than inventing zeros, and this module does not attempt to work around
that gap.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import AllocationSiteRelationship, Application, Document, LocalPlanSite, Site
from app.policy.allocation_document_evidence import SNIPPET_RADIUS_CHARS
from app.ui.common import pick_representative_application


def _load_all_applications_for_sites(session, site_ids: list[int]) -> dict[int, list[Application]]:
    """Deliberately NOT app.ui.common.load_applications_for_sites - that
    helper applies _filter_visible_applications, a CUSTOMER-VISIBILITY
    filter (hide small/unqualified schemes from the public map/table) that
    silently drops any Application with no scheme_intelligence AND no
    qualifying proposal-text keyword - exactly the applications this
    module most needs to see, since "an application exists but its
    capacity cannot be determined" is precisely the REVIEW_REQUIRED signal
    Section 4 requires, not a case to hide. Development-coverage
    accounting needs EVERY linked Application, not just the ones the
    public UI considers worth showing. Same batching/eager-load shape as
    load_applications_for_sites (2 queries total, scheme_intelligence
    eager-loaded), just without that filter."""
    if not site_ids:
        return {}
    apps = session.execute(
        select(Application).where(Application.site_id.in_(site_ids)).options(selectinload(Application.scheme_intelligence))
    ).scalars().all()
    result: dict[int, list[Application]] = {site_id: [] for site_id in site_ids}
    for a in apps:
        result.setdefault(a.site_id, []).append(a)
    return result

# --- Development coverage classification (Stage 3A Section 5) ---------------

NO_IDENTIFIED_ACTIVITY = "NO_IDENTIFIED_ACTIVITY"
PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
SUBSTANTIALLY_COVERED = "SUBSTANTIALLY_COVERED"
FULLY_ACCOUNTED_FOR = "FULLY_ACCOUNTED_FOR"
CAPACITY_UNKNOWN = "CAPACITY_UNKNOWN"
REVIEW_REQUIRED = "REVIEW_REQUIRED"

# Reuses the EXACT ratio boundaries app.extraction.local_plan.
# assess_delivery_scope already established as this platform's one
# documented rule for "does an application cover the whole allocation,
# roughly match it, or only partially cover it" - not invented fresh
# here. >=0.9 is treated as full coverage there ("full_site"); <=0.7 is
# "partial"; between the two is "roughly_matches". This module's 3-tier
# split keeps the same two boundary values, just renamed to Section 5's
# own requested vocabulary (FULLY_ACCOUNTED_FOR / SUBSTANTIALLY_COVERED /
# PARTIAL_COVERAGE).
FULLY_ACCOUNTED_THRESHOLD = 0.9
SUBSTANTIALLY_COVERED_THRESHOLD = 0.7

# --- Phasing classification (Stage 3A Section 7) -----------------------------

CONFIRMED_PHASED = "CONFIRMED_PHASED"
POTENTIAL_PHASED = "POTENTIAL_PHASED"
NO_PHASING_EVIDENCE = "NO_PHASING_EVIDENCE"
PHASING_REVIEW_REQUIRED = "PHASING_REVIEW_REQUIRED"

# Explicit documentary phrases required for CONFIRMED_PHASED (Section 7's
# own list, verbatim) - matched against normalised (lowercased) text with
# simple substring search, the same technique app.policy.
# allocation_document_evidence uses for its own relationship-phrase
# vocabulary. Materially-partial coverage ALONE never produces
# CONFIRMED_PHASED - only text evidence does.
CONFIRMED_PHASING_PHRASES = [
    "phase 1", "phase one", "first phase", "future phase", "future phases",
    "subsequent phase", "phasing plan", "remainder of the allocation",
    "part of a wider phased development",
]

# Real production false-positive class found during Stage 3A live
# verification (North Leigh Park/East of Atherton, Wigan): "phase 1"/
# "phase 1 and 2" is standard UK planning terminology for a TECHNICAL
# SURVEY'S own stage ("Phase 1 Habitat Survey", "Phase 1 and 2 Ground
# Investigation Report", "Phase 1 Desk Study") - universal report-naming
# convention, unrelated to whether the DEVELOPMENT itself is phased. A
# hit is discarded (never counted as phasing evidence) when one of these
# survey/report nouns appears within a short window immediately after
# the matched phrase - conservative exclusion only, never widens what
# counts as CONFIRMED_PHASED, only narrows a genuine false-positive.
_PHASING_FALSE_POSITIVE_SUFFIXES = [
    "habitat survey", "ground investigation", "site investigation", "desk study",
    "ecological survey", "contamination", "geotechnical", "noise assessment",
]
_PHASING_FALSE_POSITIVE_WINDOW_CHARS = 40

# --- Opportunity signal (Stage 3A Section 10) --------------------------------

INVESTIGATE = "INVESTIGATE"
MONITOR = "MONITOR"
LOWER_PRIORITY = "LOWER_PRIORITY"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

OWNERSHIP_CAVEAT = (
    "Ownership/control position not yet assessed - this is not a conclusion about land availability."
)

MULTI_SITE_REVIEW_NOTE = "Multiple development parcels identified — capacity accounting requires review."
SINGLE_SITE_REVIEW_NOTE = "Capacity accounting requires review — see linked applications."
# Stage 3B amendment (Section 5) - exact wording as specified.
DISPUTED_RELATIONSHIP_NOTE = "One or more Allocation↔Site relationships require evidence review."


def _normalise(text: str) -> str:
    """Mirrors app.policy.allocation_document_evidence._normalise_search_text
    exactly (collapse whitespace, lowercase) - a tiny standalone copy
    rather than an import, since that function is a private module-level
    helper and this is the only place in this module that needs it."""
    import re
    return re.sub(r"\s+", " ", text.lower())


def _allocation_capacity_value(allocation: LocalPlanSite) -> int | None:
    """The same single-best-guess capacity number app.reporting.
    allocation_discovery.format_capacity already selects for display
    (max of a genuine range, else minimum, else maximum, else
    indicative) - reimplemented as a standalone function rather than
    imported, since allocation_discovery imports FROM this module (an
    import the other way would be circular), not the reverse. Kept
    byte-for-byte the same selection rule so the two never disagree."""
    minimum = allocation.minimum_dwellings
    indicative = allocation.indicative_capacity
    maximum = allocation.maximum_capacity
    if minimum is not None and maximum is not None and minimum != maximum:
        return maximum
    if minimum is not None:
        return minimum
    if maximum is not None:
        return maximum
    return indicative


# --- Safe per-Site capacity contribution (Section 4) -------------------------


@dataclass
class SiteActivitySummary:
    site_id: int
    site: Site
    applications: list[Application]
    representative_application: Application | None
    capacity_known: bool
    capacity: int | None
    # Stage 3B amendment (Section 5/6) - the AllocationSiteRelationship
    # row's OWN review_status that produced this Site as "related" at
    # all. Deliberately NOT LocalPlanSite.review_status (Section 6:
    # "do not conflate" - that field carries unrelated Local Plan
    # content-review meaning, the exact conflation bug Stage 2B's own
    # amendment already ruled out elsewhere in this codebase). Default
    # matches AllocationSiteRelationship.review_status's own default, for
    # any caller not yet passing a real relationship (e.g. existing
    # tests/callers built before this amendment).
    relationship_review_status: str = "auto_applied"


def summarise_site_activity(
    site: Site, applications: list[Application], *, relationship_review_status: str = "auto_applied",
) -> SiteActivitySummary:
    """One Site's SAFE capacity contribution - never a sum across every
    application on the Site (outline+reserved matters, amendments,
    duplicates, replacement schemes would all double-count), only the
    ONE representative application's figure. Prefers the reconciled
    SchemeIntelligence.total_units_final (the same trusted figure every
    other Application-facing view in this codebase reads - see
    app.reporting.allocation_discovery.build_linked_application_summaries'
    own docstring), falling back to the portal-derived
    estimated_unit_count only when no reconciled figure exists yet."""
    rep = pick_representative_application(applications) if applications else None
    capacity: int | None = None
    capacity_known = False
    if rep is not None:
        si = getattr(rep, "scheme_intelligence", None)
        if si is not None and si.total_units_final is not None:
            capacity = si.total_units_final
            capacity_known = True
        elif rep.estimated_unit_count is not None:
            capacity = rep.estimated_unit_count
            capacity_known = True
    return SiteActivitySummary(
        site_id=site.id, site=site, applications=applications,
        representative_application=rep, capacity_known=capacity_known, capacity=capacity,
        relationship_review_status=relationship_review_status,
    )


# --- Development coverage (Sections 4/5/6) -----------------------------------


@dataclass
class DevelopmentCoverageResult:
    allocation_capacity: int | None
    identified_application_capacity: int | None
    indicative_residual_capacity: int | None
    development_coverage_percentage: float | None
    number_of_related_sites: int
    number_of_linked_applications: int
    number_of_sites_with_planning_activity: int
    number_of_sites_without_identified_planning_activity: int
    capacity_accounting_status: str  # ok | no_activity | capacity_unknown | review_required
    development_coverage_classification: str
    note: str | None
    site_summaries: list[SiteActivitySummary] = field(default_factory=list)


def compute_development_coverage(
    allocation: LocalPlanSite, site_summaries: list[SiteActivitySummary],
) -> DevelopmentCoverageResult:
    """Deterministic, evidence-only. Never sums every application's
    dwelling count (Section 4's core warning) - sums exactly one safe
    per-Site figure (see summarise_site_activity) across Sites. Falls
    back to capacity_accounting_status="review_required" - never a
    manufactured number - whenever aggregation cannot safely proceed:
    a Site has planning activity but no determinable unit count, or the
    identified total would exceed the allocation's own stated capacity
    (a negative residual, Section 6's explicit "clamp to review_required,
    never silently zero" instruction)."""
    number_of_related_sites = len(site_summaries)
    sites_with_activity = [s for s in site_summaries if s.applications]
    sites_without_activity = [s for s in site_summaries if not s.applications]
    number_of_linked_applications = sum(len(s.applications) for s in site_summaries)
    allocation_capacity = _allocation_capacity_value(allocation)

    base_kwargs = dict(
        allocation_capacity=allocation_capacity,
        number_of_related_sites=number_of_related_sites,
        number_of_linked_applications=number_of_linked_applications,
        number_of_sites_with_planning_activity=len(sites_with_activity),
        number_of_sites_without_identified_planning_activity=len(sites_without_activity),
        site_summaries=site_summaries,
    )

    if not sites_with_activity:
        return DevelopmentCoverageResult(
            identified_application_capacity=0,
            indicative_residual_capacity=allocation_capacity,
            development_coverage_percentage=0.0 if allocation_capacity else None,
            capacity_accounting_status="no_activity",
            development_coverage_classification=NO_IDENTIFIED_ACTIVITY,
            note=None,
            **base_kwargs,
        )

    unsafe_sites = [s for s in sites_with_activity if not s.capacity_known]
    if unsafe_sites:
        note = MULTI_SITE_REVIEW_NOTE if number_of_related_sites > 1 else SINGLE_SITE_REVIEW_NOTE
        return DevelopmentCoverageResult(
            identified_application_capacity=None, indicative_residual_capacity=None,
            development_coverage_percentage=None, capacity_accounting_status="review_required",
            development_coverage_classification=REVIEW_REQUIRED, note=note, **base_kwargs,
        )

    # Stage 3B amendment (Section 5) - a Site that genuinely contributes a
    # real capacity number (capacity_known) but whose underlying
    # AllocationSiteRelationship has since been flagged needs_confirmation
    # by contradicting evidence (app.policy.allocation_evidence_scan) must
    # never silently feed a confident coverage percentage/residual - the
    # accounting relationship itself is disputed. Never auto-deletes or
    # ignores the relationship (it is still counted in number_of_related_
    # sites/site_summaries above); only the DERIVED commercial conclusion
    # is withheld until a human resolves the dispute. A relationship still
    # "auto_applied" or "confirmed" is unaffected - only "needs_
    # confirmation" triggers this (Section 6's review-status semantics).
    disputed_sites = [
        s for s in sites_with_activity
        if s.capacity_known and s.relationship_review_status == "needs_confirmation"
    ]
    if disputed_sites:
        return DevelopmentCoverageResult(
            identified_application_capacity=None, indicative_residual_capacity=None,
            development_coverage_percentage=None, capacity_accounting_status="review_required",
            development_coverage_classification=REVIEW_REQUIRED, note=DISPUTED_RELATIONSHIP_NOTE, **base_kwargs,
        )

    identified_application_capacity = sum(s.capacity for s in sites_with_activity if s.capacity is not None)

    if allocation_capacity is None:
        return DevelopmentCoverageResult(
            identified_application_capacity=identified_application_capacity,
            indicative_residual_capacity=None, development_coverage_percentage=None,
            capacity_accounting_status="capacity_unknown",
            development_coverage_classification=CAPACITY_UNKNOWN, note=None, **base_kwargs,
        )

    residual = allocation_capacity - identified_application_capacity
    if residual < 0:
        note = MULTI_SITE_REVIEW_NOTE if number_of_related_sites > 1 else SINGLE_SITE_REVIEW_NOTE
        return DevelopmentCoverageResult(
            identified_application_capacity=identified_application_capacity,
            indicative_residual_capacity=None, development_coverage_percentage=None,
            capacity_accounting_status="review_required",
            development_coverage_classification=REVIEW_REQUIRED, note=note, **base_kwargs,
        )

    coverage_pct = (identified_application_capacity / allocation_capacity) if allocation_capacity else None
    if coverage_pct is not None and coverage_pct >= FULLY_ACCOUNTED_THRESHOLD:
        classification = FULLY_ACCOUNTED_FOR
    elif coverage_pct is not None and coverage_pct >= SUBSTANTIALLY_COVERED_THRESHOLD:
        classification = SUBSTANTIALLY_COVERED
    else:
        classification = PARTIAL_COVERAGE

    return DevelopmentCoverageResult(
        identified_application_capacity=identified_application_capacity,
        indicative_residual_capacity=residual, development_coverage_percentage=coverage_pct,
        capacity_accounting_status="ok", development_coverage_classification=classification,
        note=None, **base_kwargs,
    )


# --- Phasing evidence (Section 7) --------------------------------------------


@dataclass
class PhasingEvidenceHit:
    document_id: int
    document_type: str
    application_id: int
    application_reference: str
    phrase: str
    snippet: str


def search_phasing_evidence(document_application_pairs: list[tuple[Document, Application]]) -> list[PhasingEvidenceHit]:
    """Searches ONLY the documents belonging to applications already
    linked to this allocation via AllocationSiteRelationship - never a
    fresh council-wide scan, since the candidate document set is already
    known and small. READ ONLY, pure function - no DB access itself."""
    hits: list[PhasingEvidenceHit] = []
    for document, application in document_application_pairs:
        if not document.extracted_text:
            continue
        text = _normalise(document.extracted_text)
        for phrase in CONFIRMED_PHASING_PHRASES:
            idx = text.find(phrase)
            if idx == -1:
                continue
            suffix_window = text[idx + len(phrase):idx + len(phrase) + _PHASING_FALSE_POSITIVE_WINDOW_CHARS]
            if any(noun in suffix_window for noun in _PHASING_FALSE_POSITIVE_SUFFIXES):
                continue
            start = max(0, idx - SNIPPET_RADIUS_CHARS)
            end = min(len(text), idx + len(phrase) + SNIPPET_RADIUS_CHARS)
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(text) else ""
            hits.append(PhasingEvidenceHit(
                document_id=document.id, document_type=document.doc_type,
                application_id=application.id, application_reference=application.reference,
                phrase=phrase, snippet=f"{prefix}{text[start:end].strip()}{suffix}",
            ))
    return hits


def classify_phasing(coverage: DevelopmentCoverageResult, phasing_hits: list[PhasingEvidenceHit]) -> dict:
    """CONFIRMED_PHASED requires explicit documentary evidence ONLY -
    never inferred merely because application capacity < allocation
    capacity (Section 7's explicit prohibition, also a Section 16 test
    requirement). POTENTIAL_PHASED is the honest middle ground: coverage
    is materially partial and more than one Site/application is involved,
    but no explicit phasing phrase was found."""
    if phasing_hits:
        return {"classification": CONFIRMED_PHASED, "evidence": phasing_hits}
    if coverage.capacity_accounting_status == "review_required":
        return {"classification": PHASING_REVIEW_REQUIRED, "evidence": []}
    if (
        coverage.development_coverage_classification == PARTIAL_COVERAGE
        and (coverage.number_of_related_sites > 1 or coverage.number_of_linked_applications > 1)
    ):
        return {"classification": POTENTIAL_PHASED, "evidence": []}
    return {"classification": NO_PHASING_EVIDENCE, "evidence": []}


# --- Opportunity signal (Section 10) -----------------------------------------


def build_opportunity_signal(
    *, plan_status_bucket: str | None, coverage: DevelopmentCoverageResult, phasing: dict,
) -> dict:
    """Explicit, explainable reasons only - never a black-box score
    (Section 10's explicit prohibition). Always ends with the ownership/
    control caveat, so a reader can never mistake this for a land-
    availability conclusion."""
    if plan_status_bucket not in ("adopted", "emerging"):
        return {
            "signal": INSUFFICIENT_EVIDENCE,
            "reasons": ["This allocation's plan status is not adopted or emerging, so an investigation signal cannot be established."],
        }
    if coverage.allocation_capacity is None:
        return {
            "signal": INSUFFICIENT_EVIDENCE,
            "reasons": ["Allocation capacity has not been identified, so an investigation signal cannot be established."],
        }
    if coverage.development_coverage_classification == REVIEW_REQUIRED:
        return {
            "signal": INSUFFICIENT_EVIDENCE,
            "reasons": [coverage.note or "Capacity accounting for this allocation requires review before an investigation signal can be set."],
        }

    reasons: list[str] = [
        f"{'Adopted' if plan_status_bucket == 'adopted' else 'Emerging'} residential allocation with capacity of "
        f"approximately {coverage.allocation_capacity:,} homes."
    ]

    classification = coverage.development_coverage_classification
    if classification == NO_IDENTIFIED_ACTIVITY:
        reasons.append("No planning activity has been identified within this allocation.")
        signal = INVESTIGATE
    elif classification == PARTIAL_COVERAGE:
        pct = coverage.development_coverage_percentage or 0.0
        reasons.append(f"Approximately {pct:.0%} of capacity is represented by identified planning activity.")
        if coverage.indicative_residual_capacity:
            reasons.append(
                f"Approximately {coverage.indicative_residual_capacity:,} homes of allocation capacity are not "
                "currently accounted for by identified planning activity."
            )
        signal = INVESTIGATE
    elif classification == SUBSTANTIALLY_COVERED:
        pct = coverage.development_coverage_percentage or 0.0
        reasons.append(f"Approximately {pct:.0%} of capacity is represented by identified planning activity.")
        signal = MONITOR
    elif classification == FULLY_ACCOUNTED_FOR:
        reasons.append("Capacity appears fully accounted for by identified planning activity.")
        signal = LOWER_PRIORITY
    else:  # CAPACITY_UNKNOWN - identified activity exists but no allocation capacity to compare against
        reasons.append("Allocation capacity is not known, so coverage cannot be calculated.")
        signal = MONITOR

    if phasing["classification"] == CONFIRMED_PHASED:
        reasons.append("Confirmed phased development - a further phase may still represent an opportunity.")
        if signal == LOWER_PRIORITY:
            signal = MONITOR
    elif phasing["classification"] == POTENTIAL_PHASED:
        reasons.append("Potential phased development - investigate.")
        if signal == LOWER_PRIORITY:
            signal = MONITOR

    reasons.append(OWNERSHIP_CAVEAT)
    return {"signal": signal, "reasons": reasons}


# --- Batched, bounded top-level builder (Sections 3/12) ----------------------


def build_allocation_development_coverage(session, allocations: list[LocalPlanSite]) -> dict[int, dict]:
    """The one DB-touching entrypoint. Fixed, bounded query budget
    regardless of allocation count:
      1. AllocationSiteRelationship rows for these allocations, with
         selectinload(.site) - the AUTHORITATIVE relationship set
         (Section 3) - never LocalPlanSite.matched_site_id.
      2. Applications for every related site_id, batched via this
         module's own _load_all_applications_for_sites (2 queries,
         scheme_intelligence eager-loaded - never one query per Site;
         deliberately NOT app.ui.common.load_applications_for_sites, see
         that function's own docstring for why).
      3. Documents (text_extracted only) for every linked application,
         batched, for phasing-evidence search.

    Returns {allocation_id: {"coverage": DevelopmentCoverageResult,
    "phasing": dict, "site_summaries": [...]}}, one entry for EVERY
    allocation passed in - even one with zero related Sites is present,
    classified NO_IDENTIFIED_ACTIVITY, never silently absent."""
    allocation_ids = [a.id for a in allocations]
    if not allocation_ids:
        return {}

    relationships = list(session.execute(
        select(AllocationSiteRelationship)
        .where(AllocationSiteRelationship.allocation_id.in_(allocation_ids))
        .options(selectinload(AllocationSiteRelationship.site))
    ).scalars())

    rels_by_allocation: dict[int, list[AllocationSiteRelationship]] = {aid: [] for aid in allocation_ids}
    for rel in relationships:
        rels_by_allocation.setdefault(rel.allocation_id, []).append(rel)

    all_site_ids = sorted({rel.site_id for rel in relationships})
    apps_by_site = _load_all_applications_for_sites(session, all_site_ids)

    applications_by_id: dict[int, Application] = {
        app.id: app for apps in apps_by_site.values() for app in apps
    }
    all_application_ids = list(applications_by_id.keys())

    documents_by_application: dict[int, list[Document]] = {aid: [] for aid in all_application_ids}
    if all_application_ids:
        docs = list(session.execute(
            select(Document).where(
                Document.application_id.in_(all_application_ids), Document.text_extracted.is_(True),
            )
        ).scalars())
        for doc in docs:
            documents_by_application.setdefault(doc.application_id, []).append(doc)

    result: dict[int, dict] = {}
    for allocation in allocations:
        # Stage 3B amendment (Section 6) - a "rejected" relationship must
        # never contribute to accepted development-coverage accounting at
        # all: not counted as a related Site, not counted in linked-
        # application totals, nothing. It is explicitly not a genuine
        # relationship any more, unlike "needs_confirmation" (still
        # counted, see compute_development_coverage's own disputed-Site
        # check above) or "auto_applied"/"confirmed" (both fully usable).
        rels = [rel for rel in rels_by_allocation.get(allocation.id, []) if rel.review_status != "rejected"]
        site_summaries = [
            summarise_site_activity(rel.site, apps_by_site.get(rel.site_id, []), relationship_review_status=rel.review_status)
            for rel in rels
        ]

        coverage = compute_development_coverage(allocation, site_summaries)

        linked_application_ids = [app.id for s in site_summaries for app in s.applications]
        pairs = [
            (doc, applications_by_id[aid])
            for aid in linked_application_ids
            for doc in documents_by_application.get(aid, [])
            if aid in applications_by_id
        ]
        phasing_hits = search_phasing_evidence(pairs)
        phasing = classify_phasing(coverage, phasing_hits)

        result[allocation.id] = {
            "coverage": coverage,
            "phasing": phasing,
            "site_summaries": site_summaries,
        }
    return result

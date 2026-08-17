"""GM Allocation <-> Planning Activity document-evidence matching (Stage 2C).

READ ONLY / DRY-RUN ONLY. This module never writes anything - no
session.add/flush/commit anywhere in it, and it never assigns to
matched_site_id or any other LocalPlanSite/Site/Application attribute. It
exists to build a SECOND, independent evidence layer over Stage 2A's
fuzzy name/address matching (app.policy.allocation_site_dry_run_matching),
using planning-document text PropertyAIgent already holds - never OpenAI,
never external web research, never new document downloads or geocoding.

WHY A SECOND LAYER: the Stage 2A production dry-run surfaced plausible
false positives even among its own HIGH_CONFIDENCE_CANDIDATE tier (e.g.
"John Street, Hazel Grove" scoring 87.8 against "Old Grove House, Vine
Street" - a real but different building on a nearby street). Fuzzy
address/site-name similarity alone is not strong enough evidence to
persist as an accepted relationship. This module asks a different,
stronger question: does the TEXT of a planning document already say, in
words, that an Application/Site relates to this specific Local Plan
allocation?

REUSE, NOT A NEW ARCHITECTURE: this module builds no new document storage,
no new search index, and no new text-extraction pipeline. It queries the
existing app.db.models.Document.extracted_text (already populated by
app.extraction.pdf_text) via a plain SQL ILIKE prefilter (the same
technique already used elsewhere in this project's own read-only
reporting scripts), scoped by Application.council_code (mirroring every
other council-scoped query in this codebase, e.g. app.extraction.
local_plan.match_to_existing_site's own candidate selection), and reuses
app.pipeline.site_linking.normalise_address to strip the exact same noise
prefixes ("land at", "land off", "former", ...) this codebase already
treats as non-identifying when comparing a Local Plan site name against
real-world text.

EVIDENCE CATEGORIES (Stage 2C Section 6), from strongest to weakest -
assigned per (document, occurrence) hit, never for a whole document at
once, since one document can contain both a positive and a contradicting
mention of different allocations:

  EXPLICIT_REFERENCE          - the allocation's own policy_reference (or,
                                 for a short/generic reference, its
                                 contextualised form "policy X"/
                                 "allocation X") is found in the text, AND
                                 an explicit positive relationship phrase
                                 (POSITIVE_RELATIONSHIP_PHRASES) appears
                                 within the same proximity window.
  STRONG_CONTEXTUAL_REFERENCE - the reference is found (same council,
                                 same contextual-safety rule for short
                                 references) but no relationship phrase is
                                 close enough to call it explicit.
  NAME_AND_POLICY_CONTEXT     - no policy_reference hit, but the
                                 allocation's own distinctive site_name is
                                 found together with general Local-Plan/
                                 allocation-context wording nearby.
  WEAK_REFERENCE              - a candidate hit exists (passed the SQL
                                 prefilter) but none of the above stronger
                                 conditions are met - e.g. a bare
                                 distinctive-name mention with no
                                 surrounding policy context at all.
  CONTRADICTORY_REFERENCE     - a NEGATIVE/adjacency phrase
                                 (NEGATIVE_RELATIONSHIP_PHRASES - "adjacent
                                 to allocation", "outside allocation", "not
                                 within", ...) is found within the same
                                 proximity window as the reference/name hit.
                                 Negative language always overrides a
                                 positive phrase found in the SAME window,
                                 per Stage 2C Section 14's explicit
                                 instruction never to read adjacency
                                 language as membership.

SHORT/GENERIC REFERENCE SAFEGUARD (Stage 2C Section 12): a policy
reference of 4 alphanumeric characters or fewer (e.g. "H3", "AN1", "AN6")
is never matched as a bare substring - the SQL prefilter itself only
searches for "policy <ref>" / "allocation <ref>" (Section 4/12: "an
isolated short token is insufficient by itself... context must matter"),
and the same contextual pattern is re-validated in Python with word
boundaries before any hit is recorded.

DOCUMENT-TYPE WEIGHTING (Stage 2C Section 13) - deterministic, never an
LLM-style judgement:
  HIGH   : officer_report, decision_notice, planning_statement, s106
           (authoritative/explanatory - an officer report or decision
           notice is written specifically to describe how a scheme
           relates to policy; a planning statement is the applicant's own
           policy case; an S106's recitals routinely restate the site's
           planning status).
  MEDIUM : design_access, application_form, viability_affordable_housing
           (descriptive of the scheme, but rarely the place explicit
           allocation-relationship language is drafted).
  LOW    : everything else classified as "other" by the existing pdf_text
           taxonomy.
Weighting is informational (surfaced per hit and used only to break ties
when choosing which hit to report as an allocation's "best" evidence) -
it never changes the evidence CATEGORY a hit receives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Application, Document, LocalPlanSite
from app.pipeline.site_linking import normalise_address
from app.policy.allocation_site_dry_run_matching import (
    AMBIGUOUS,
    HIGH_CONFIDENCE_CANDIDATE,
    NO_CANDIDATE,
    REVIEW_CANDIDATE,
    AllocationMatchResult,
)

# --- Evidence categories (Stage 2C Section 6) -------------------------------

EXPLICIT_REFERENCE = "EXPLICIT_REFERENCE"
STRONG_CONTEXTUAL_REFERENCE = "STRONG_CONTEXTUAL_REFERENCE"
NAME_AND_POLICY_CONTEXT = "NAME_AND_POLICY_CONTEXT"
WEAK_REFERENCE = "WEAK_REFERENCE"
CONTRADICTORY_REFERENCE = "CONTRADICTORY_REFERENCE"

# Ordering for "best hit wins" - index = strength, higher is stronger.
# CONTRADICTORY is deliberately not in this list; it is tracked separately
# (a contradiction is never "beaten" by a weaker positive hit elsewhere).
_POSITIVE_CATEGORY_STRENGTH = [WEAK_REFERENCE, NAME_AND_POLICY_CONTEXT, STRONG_CONTEXTUAL_REFERENCE, EXPLICIT_REFERENCE]

# --- Reporting-only recommendation outcomes (Stage 2C Section 8) -----------

DOCUMENT_CONFIRMED_SITE = "DOCUMENT_CONFIRMED_SITE"
DOCUMENT_CONFIRMED_APPLICATION_ONLY = "DOCUMENT_CONFIRMED_APPLICATION_ONLY"
FUZZY_SUPPORTED_BY_DOCUMENT = "FUZZY_SUPPORTED_BY_DOCUMENT"
DOCUMENT_CONTRADICTS_FUZZY = "DOCUMENT_CONTRADICTS_FUZZY"
MULTIPLE_DOCUMENT_SUPPORTED_SITES = "MULTIPLE_DOCUMENT_SUPPORTED_SITES"
DOCUMENT_REVIEW_REQUIRED = "DOCUMENT_REVIEW_REQUIRED"
NO_DOCUMENT_EVIDENCE = "NO_DOCUMENT_EVIDENCE"

# --- Document-type weighting (Stage 2C Section 13) --------------------------

HIGH_WEIGHT_DOC_TYPES = {"officer_report", "decision_notice", "planning_statement", "s106"}
MEDIUM_WEIGHT_DOC_TYPES = {"design_access", "application_form", "viability_affordable_housing"}
DOC_TYPE_WEIGHT = {**{t: 3 for t in HIGH_WEIGHT_DOC_TYPES}, **{t: 2 for t in MEDIUM_WEIGHT_DOC_TYPES}}


def _doc_weight(doc_type: str) -> int:
    return DOC_TYPE_WEIGHT.get(doc_type, 1)  # LOW / unrecognised = 1


# --- Relationship language (Stage 2C Sections 5/14) -------------------------
# Matched against normalised (lowercased) text - simple substring search
# is sufficient since these are already lowercase multi-word phrases.

POSITIVE_RELATIONSHIP_PHRASES = [
    "forms part of allocation", "forms part of the allocation",
    "within allocation", "within the allocated site", "within the allocation",
    "allocated under", "allocated for", "site allocation", "housing allocation",
    "local plan allocation", "local plan site", "places for everyone allocation",
    "identified as allocation", "identified as an allocation", "allocated site",
    "part of policy", "within policy",
]

NEGATIVE_RELATIONSHIP_PHRASES = [
    "adjacent to allocation", "adjacent to the allocation", "adjoining the allocated site",
    "adjoining the allocation", "outside allocation", "outside the allocation",
    "outside the allocated site", "not within allocation", "not within the allocation",
    "not within the allocated site", "near allocation", "near the allocation",
    "opposite allocation", "opposite the allocation",
]

GENERAL_ALLOCATION_CONTEXT_WORDS = ["local plan", "allocation", "allocated", "policy"]

# A reference with this many alphanumeric characters or fewer is treated as
# "generic/short" (Stage 2C Section 12) - "H3", "AN1", "AN6" all fall
# under this; "HOM 2.27", "JPA 30", "HLA0029" do not.
GENERIC_REFERENCE_MAX_LENGTH = 4

PROXIMITY_WINDOW_CHARS = 180
SNIPPET_RADIUS_CHARS = 120


def _normalise_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _alnum_length(reference: str) -> int:
    return len(re.sub(r"[^a-z0-9]", "", reference.lower()))


def is_generic_reference(reference: str) -> bool:
    return _alnum_length(reference) <= GENERIC_REFERENCE_MAX_LENGTH


def _reference_pattern(reference: str) -> re.Pattern:
    """Word-boundary-safe regex for a policy_reference. A generic/short
    reference (Stage 2C Section 12) REQUIRES an immediately preceding
    "policy"/"allocation" word - a bare "H3" is never itself a match,
    only "policy H3" or "allocation H3" is."""
    escaped = re.escape(reference.lower().strip())
    if is_generic_reference(reference):
        return re.compile(rf"\b(?:policy|allocation)\s+{escaped}\b")
    return re.compile(rf"\b{escaped}\b")


def distinctive_name_terms(site_name: str) -> str | None:
    """The allocation's own site_name, normalised the same way
    app.extraction.local_plan already normalises a Local Plan site name
    before comparing it to real-world text (reused, not reimplemented) -
    returns None if what's left is too generic/short to search for on its
    own (Stage 2C Section 4: "an isolated short token is insufficient")."""
    normalised = normalise_address(site_name)
    # Drop the same handful of pure-noise tokens normalise_address doesn't
    # already strip as a prefix but that still carry ~zero identifying
    # value on their own within a much longer document.
    meaningful = [t for t in normalised.split() if t not in {"land", "site", "the", "of", "at", "off"}]
    if len(" ".join(meaningful)) < 8:
        return None
    return normalised


def _name_pattern(distinctive_name: str) -> re.Pattern:
    return re.compile(re.escape(distinctive_name))


@dataclass
class DocumentEvidenceHit:
    document_id: int
    document_type: str
    application_id: int
    application_reference: str
    site_id: int | None
    matched_reference: str
    snippet: str
    category: str
    weight: int


@dataclass
class AllocationEvidenceResult:
    allocation_id: int
    council: str
    policy_reference: str | None
    allocation_name: str
    stage2a_classification: str
    stage2a_candidate_site_ids: list[int]
    positive_hits: list[DocumentEvidenceHit] = field(default_factory=list)
    contradictory_hits: list[DocumentEvidenceHit] = field(default_factory=list)
    recommended_outcome: str = NO_DOCUMENT_EVIDENCE

    @property
    def contradiction_flag(self) -> bool:
        return bool(self.contradictory_hits)

    @property
    def evidenced_site_ids(self) -> set[int]:
        return {h.site_id for h in self.positive_hits if h.site_id is not None}

    @property
    def multi_site_flag(self) -> bool:
        return len(self.evidenced_site_ids) > 1

    @property
    def best_category(self) -> str | None:
        if not self.positive_hits:
            return None
        return max(
            (h.category for h in self.positive_hits),
            key=lambda c: _POSITIVE_CATEGORY_STRENGTH.index(c),
        )


def _search_terms(allocation: LocalPlanSite) -> list[str]:
    """SQL-level ILIKE prefilter terms - deliberately narrow for a generic
    reference (only its contextualised forms), broad for a distinctive
    one. This is a candidate filter only; every candidate is re-validated
    with the strict regex patterns in Python before being recorded as a
    hit, so a noisy prefilter cannot itself produce a false positive."""
    terms: list[str] = []
    ref = allocation.policy_reference
    if ref:
        if is_generic_reference(ref):
            terms.append(f"policy {ref.lower().strip()}")
            terms.append(f"allocation {ref.lower().strip()}")
        else:
            terms.append(ref.lower().strip())
    name = distinctive_name_terms(allocation.site_name)
    if name:
        terms.append(name)
    return terms


def _candidate_documents(session: Session, council_code: str, terms: list[str]) -> list[tuple[Document, Application]]:
    if not terms:
        return []
    conditions = [Document.extracted_text.ilike(f"%{term}%") for term in terms]
    query = (
        select(Document, Application)
        .join(Application, Document.application_id == Application.id)
        .where(
            Application.council_code == council_code,
            Document.text_extracted.is_(True),
            or_(*conditions),
        )
    )
    return list(session.execute(query).all())


def _classify_occurrence(text: str, match_start: int, match_end: int) -> tuple[str | None, bool]:
    """Looks at the proximity window around ONE reference/name occurrence
    and returns (category_if_reference_alone, has_relationship_phrase) -
    the caller combines this with whether the match was a policy_reference
    or a site_name to pick the final category. Returns has_contradiction
    as the second element's sibling via the caller checking NEGATIVE
    phrases separately (see find_document_evidence)."""
    window_start = max(0, match_start - PROXIMITY_WINDOW_CHARS)
    window_end = min(len(text), match_end + PROXIMITY_WINDOW_CHARS)
    window = text[window_start:window_end]
    has_positive = any(phrase in window for phrase in POSITIVE_RELATIONSHIP_PHRASES)
    return window, has_positive


def _has_negative_phrase(text: str, match_start: int, match_end: int) -> bool:
    window_start = max(0, match_start - PROXIMITY_WINDOW_CHARS)
    window_end = min(len(text), match_end + PROXIMITY_WINDOW_CHARS)
    window = text[window_start:window_end]
    return any(phrase in window for phrase in NEGATIVE_RELATIONSHIP_PHRASES)


def _snippet(text: str, match_start: int, match_end: int) -> str:
    start = max(0, match_start - SNIPPET_RADIUS_CHARS)
    end = min(len(text), match_end + SNIPPET_RADIUS_CHARS)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def find_document_evidence_for_allocation(
    session: Session, allocation: LocalPlanSite,
) -> tuple[list[DocumentEvidenceHit], list[DocumentEvidenceHit]]:
    """Returns (positive_hits, contradictory_hits) for one allocation.
    READ ONLY - issues only SELECT statements."""
    terms = _search_terms(allocation)
    if not terms:
        return [], []

    ref_pattern = _reference_pattern(allocation.policy_reference) if allocation.policy_reference else None
    distinctive_name = distinctive_name_terms(allocation.site_name)
    name_pattern = _name_pattern(distinctive_name) if distinctive_name else None

    positive_hits: list[DocumentEvidenceHit] = []
    contradictory_hits: list[DocumentEvidenceHit] = []

    for document, application in _candidate_documents(session, allocation.council_code, terms):
        text = _normalise_search_text(document.extracted_text or "")
        weight = _doc_weight(document.doc_type)

        # Reference occurrences take priority - they carry a real allocation
        # code, not just a place name.
        ref_matches = list(ref_pattern.finditer(text)) if ref_pattern else []
        name_matches = list(name_pattern.finditer(text)) if name_pattern else []

        seen_any = False
        for m in ref_matches:
            seen_any = True
            if _has_negative_phrase(text, m.start(), m.end()):
                contradictory_hits.append(DocumentEvidenceHit(
                    document_id=document.id, document_type=document.doc_type,
                    application_id=application.id, application_reference=application.reference,
                    site_id=application.site_id, matched_reference=allocation.policy_reference,
                    snippet=_snippet(text, m.start(), m.end()), category=CONTRADICTORY_REFERENCE, weight=weight,
                ))
                continue
            _, has_positive = _classify_occurrence(text, m.start(), m.end())
            category = EXPLICIT_REFERENCE if has_positive else STRONG_CONTEXTUAL_REFERENCE
            positive_hits.append(DocumentEvidenceHit(
                document_id=document.id, document_type=document.doc_type,
                application_id=application.id, application_reference=application.reference,
                site_id=application.site_id, matched_reference=allocation.policy_reference,
                snippet=_snippet(text, m.start(), m.end()), category=category, weight=weight,
            ))

        for m in name_matches:
            seen_any = True
            if _has_negative_phrase(text, m.start(), m.end()):
                contradictory_hits.append(DocumentEvidenceHit(
                    document_id=document.id, document_type=document.doc_type,
                    application_id=application.id, application_reference=application.reference,
                    site_id=application.site_id, matched_reference=distinctive_name,
                    snippet=_snippet(text, m.start(), m.end()), category=CONTRADICTORY_REFERENCE, weight=weight,
                ))
                continue
            window, has_positive = _classify_occurrence(text, m.start(), m.end())
            has_context = has_positive or any(w in window for w in GENERAL_ALLOCATION_CONTEXT_WORDS)
            category = NAME_AND_POLICY_CONTEXT if has_context else WEAK_REFERENCE
            positive_hits.append(DocumentEvidenceHit(
                document_id=document.id, document_type=document.doc_type,
                application_id=application.id, application_reference=application.reference,
                site_id=application.site_id, matched_reference=distinctive_name,
                snippet=_snippet(text, m.start(), m.end()), category=category, weight=weight,
            ))

        # Matched the SQL prefilter but neither strict Python regex found
        # anything (e.g. a generic reference's prefilter term appeared,
        # but not immediately adjacent to "policy"/"allocation" the way
        # the regex requires) - explicitly NOT recorded as any evidence.
        del seen_any

    return positive_hits, contradictory_hits


def _stage2a_candidate_site_ids(stage2a: AllocationMatchResult | None) -> set[int]:
    """Union of Stage 2A's decided winners (.candidates - populated for
    HIGH_CONFIDENCE_CANDIDATE and AMBIGUOUS) and its REVIEW_CANDIDATE near
    misses (.near_miss_candidates, but ONLY when classification is
    actually REVIEW_CANDIDATE) - document evidence needs to be able to
    support/contradict a REVIEW_CANDIDATE's proposed Site too (Stage 2C
    Section 21: "Review/ambiguous cases strengthened or contradicted"),
    not just an already-decided HIGH_CONFIDENCE_CANDIDATE.

    Deliberately EXCLUDES near_miss_candidates when classification is
    NO_CANDIDATE: app.policy.allocation_site_dry_run_matching.
    evaluate_allocation() still populates near_miss_candidates for
    NO_CANDIDATE results purely for score-distribution reporting (a
    below-FUZZY_SCORE_THRESHOLD near miss Stage 2A itself judged too weak
    to surface as a review candidate at all) - treating that as "the
    fuzzy layer's proposal" would mislabel a NO_CANDIDATE allocation with
    genuinely new document evidence as DOCUMENT_CONTRADICTS_FUZZY, when
    there was never a real fuzzy candidate to contradict in the first
    place (confirmed a real case during Stage 2C's own production dry
    run - fixed here before that bug reached the report)."""
    if stage2a is None or stage2a.classification == NO_CANDIDATE:
        return set()
    return {c.site_id for c in stage2a.candidates} | {c.site_id for c in stage2a.near_miss_candidates}


def derive_recommended_outcome(
    stage2a: AllocationMatchResult | None, positive_hits: list[DocumentEvidenceHit], contradictory_hits: list[DocumentEvidenceHit],
) -> str:
    """Reporting-only combination of Stage 2A's fuzzy result with Stage 2C's
    document evidence (Stage 2C Section 8). Never persisted. Priority
    order, most specific/actionable first:

    1. Multiple distinct Sites each carry strong (EXPLICIT/STRONG_CONTEXTUAL)
       evidence -> MULTIPLE_DOCUMENT_SUPPORTED_SITES (never forced to one).
    2. A contradictory hit names Stage 2A's own candidate Site, OR a
       strong positive hit names a DIFFERENT Site than Stage 2A's
       candidate(s) -> DOCUMENT_CONTRADICTS_FUZZY.
    3. A strong hit names the SAME Site as a Stage 2A candidate ->
       FUZZY_SUPPORTED_BY_DOCUMENT.
    4. A strong hit names a Site directly (no Stage 2A candidate to
       compare against) -> DOCUMENT_CONFIRMED_SITE.
    5. A strong hit exists but its Application has no linked Site at all
       -> DOCUMENT_CONFIRMED_APPLICATION_ONLY.
    6. Only weak/contextual positive hits, or an unrelated contradiction
       -> DOCUMENT_REVIEW_REQUIRED.
    7. Nothing found at all -> NO_DOCUMENT_EVIDENCE.
    """
    stage2a_site_ids = _stage2a_candidate_site_ids(stage2a)
    strong_hits = [h for h in positive_hits if h.category in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)]
    strong_site_ids = {h.site_id for h in strong_hits if h.site_id is not None}
    contradicted_site_ids = {h.site_id for h in contradictory_hits if h.site_id is not None}

    if len(strong_site_ids) > 1:
        return MULTIPLE_DOCUMENT_SUPPORTED_SITES

    if stage2a_site_ids and (
        (contradicted_site_ids & stage2a_site_ids)
        or (strong_site_ids and not (strong_site_ids & stage2a_site_ids))
    ):
        return DOCUMENT_CONTRADICTS_FUZZY

    if strong_site_ids and stage2a_site_ids and strong_site_ids & stage2a_site_ids:
        return FUZZY_SUPPORTED_BY_DOCUMENT

    strong_linked = [h for h in strong_hits if h.site_id is not None]
    strong_unlinked = [h for h in strong_hits if h.site_id is None]
    if strong_linked:
        return DOCUMENT_CONFIRMED_SITE
    if strong_unlinked:
        return DOCUMENT_CONFIRMED_APPLICATION_ONLY

    if positive_hits or contradictory_hits:
        return DOCUMENT_REVIEW_REQUIRED

    return NO_DOCUMENT_EVIDENCE


def evaluate_allocation_document_evidence(
    session: Session, allocation: LocalPlanSite, stage2a: AllocationMatchResult | None,
) -> AllocationEvidenceResult:
    positive_hits, contradictory_hits = find_document_evidence_for_allocation(session, allocation)
    result = AllocationEvidenceResult(
        allocation_id=allocation.id, council=allocation.council_code,
        policy_reference=allocation.policy_reference, allocation_name=allocation.site_name,
        stage2a_classification=stage2a.classification if stage2a else NO_CANDIDATE,
        stage2a_candidate_site_ids=[c.site_id for c in (stage2a.candidates if stage2a else [])],
        positive_hits=positive_hits, contradictory_hits=contradictory_hits,
    )
    result.recommended_outcome = derive_recommended_outcome(stage2a, positive_hits, contradictory_hits)
    return result


def run_document_evidence_dry_run(
    session: Session, stage2a_results: dict[int, AllocationMatchResult], all_allocations: list[LocalPlanSite],
) -> list[AllocationEvidenceResult]:
    """Orchestrates Stage 2C over every allocation passed in - READ ONLY,
    zero mutations. stage2a_results maps allocation_id -> its Stage 2A
    AllocationMatchResult (from a fresh app.policy.allocation_site_dry_run_matching.
    run_dry_run_matching() call); an allocation with no entry (already
    matched, outside Stage 2A's unmatched scope) is still evaluated for
    document evidence with stage2a=None."""
    return [
        evaluate_allocation_document_evidence(session, allocation, stage2a_results.get(allocation.id))
        for allocation in all_allocations
    ]

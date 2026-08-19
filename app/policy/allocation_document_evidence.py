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

GENERIC-REFERENCE NAME CORROBORATION (Stage 2E.1, "Allocation<->Site
Relationship Matcher Integrity Fix"): the "policy <ref>"/"allocation <ref>"
phrasing test above is NECESSARY but was found NOT SUFFICIENT - a live
production false-positive cluster (Wigan's H3/H4/H5/H6) proved that a
short/generic reference can be reused by the SAME council's own plan for
BOTH a numbered site allocation AND an unrelated, generically-worded
Development Management policy (e.g. "Policy H3: accessibility to
sustainable transport", a borough-wide DM policy, entirely distinct from
"Allocation H3: North Leigh Park"). A document's own boilerplate "relevant
policies: H1, H2, H3, H4..." list, or a sentence like "policy H3 confirms
that development across the plan area should...", satisfies the old
"policy <ref>" phrasing test while saying NOTHING about this specific
Site/Application's relationship to the allocation.

The fix: for a GENERIC reference only (is_generic_reference), a hit is
NEVER promoted past WEAK_REFERENCE unless the allocation's own distinctive
site_name (the exact same distinctive_name_terms() value already used for
this module's separate name-matching pass) is ALSO found within the same
PROXIMITY_WINDOW_CHARS window as the reference occurrence - see
_generic_reference_has_name_corroboration. This applies to BOTH
EXPLICIT_REFERENCE and STRONG_CONTEXTUAL_REFERENCE for a generic
reference (Stage 2E.1 Section 6's own instruction to also confirm
EXPLICIT_REFERENCE is interpreting the phrase as an allocation reference,
not merely finding the code near generic text) - every real production
EXPLICIT_REFERENCE example already carries the allocation's own name
alongside the code ("North Leigh Park allocation (H3)", "forms part of
the allocation for housing need... (draft policy H3: North Leigh Park)"),
so this never weakens a genuine case.

A NON-generic reference (more than 4 alphanumeric characters, e.g. "HOM
2.27", "JPA 30", "HLA2094") is UNCHANGED by this amendment - such
references are already distinctive enough on their own not to need name
corroboration (Stage 2E.1 Section 5: "do not over-correct unique
references"). GENERIC_REFERENCE_MAX_LENGTH/is_generic_reference remain the
one, general (non-council-specific) definition of "short/generic" used
throughout this module - nothing here is Wigan-specific; the same rule
applies identically to any council whose plan reuses a short code.

MULTI-REFERENCE PHRASE ATTRIBUTION (Stage 2E.2 Final Matcher Amendment,
"Multi-Reference Sentence Attribution Fix"): the proximity-window check
above (PROXIMITY_WINDOW_CHARS either side of a reference/name occurrence)
was found NOT SUFFICIENT either, for a different reason than the generic-
reference gap Stage 2E.1 fixed - a live production case proved a positive
phrase anchored to ONE allocation reference can "bleed" onto a SECOND,
DIFFERENT allocation reference mentioned nearby in the same sentence,
purely because the whole undifferentiated window was treated as
semantically uniform. Confirmed real example (application FUL/355603/26,
Site "Land South Of Bullcote Lane"): "...the site forms part of Places
for Everyone allocation policy JPA 12 Broadbent Moss and adjoins
allocation Policy JPA 10 Beal Valley..." - the ONLY phrase match in this
whole sentence is "places for everyone allocation" (grammatically
describing JPA 12), which falls within 180 characters of BOTH references,
so JPA 10 incorrectly inherited EXPLICIT_REFERENCE membership evidence
from a phrase that never described it at all - while JPA 10's own
genuinely negative "adjoins" relationship went entirely undetected,
because no NEGATIVE_RELATIONSHIP_PHRASES entry recognised bare "adjoins
allocation"/"adjoins policy" phrasing (only the gerund "adjoining the
allocation" form existed).

The fix, in two parts:
1. _nearest_relationship_phrase replaces "does ANY phrase (positive or
   negative) appear anywhere in the ±PROXIMITY_WINDOW_CHARS window" with
   "what is the SINGLE CLOSEST phrase occurrence (by character distance,
   not by which polarity list it happens to be in) to THIS SPECIFIC
   reference/name occurrence". A phrase anchored to a different, more
   distant reference is never credited to this one just because both
   happen to fall inside the same window - only genuine proximity wins.
   This deliberately needs no knowledge of OTHER allocations' reference
   positions in the text (which the backward, per-allocation direction of
   this module does not have available) - it only compares candidate
   phrase distances against the ONE occurrence being classified, which is
   sufficient to solve the bleed problem in general, not just for JPA10/
   JPA12: "X and Y" (a single phrase governing a compound object, e.g.
   "forms part of allocations X and Y") still correctly credits both X
   and Y, since neither has a CLOSER competing phrase to displace it;
   "forms part of X and adjoins Y" correctly separates the two, since
   "adjoins" is closer to Y than "forms part of" now is.
2. NEGATIVE_RELATIONSHIP_PHRASES gained bare-verb ("adjoins allocation"/
   "adjoins the allocation"/"adjoins policy"/"adjoins the policy",
   "adjoining allocation"/"adjoining policy") and "beyond" forms
   alongside the pre-existing gerund/preposition forms - general phrasing
   additions, not specific to JPA10/JPA12/Beal Valley/Broadbent Moss, so
   the SAME widened vocabulary protects every other council's documents
   too. POSITIVE_RELATIONSHIP_PHRASES gained "straddles" (bare, no
   "allocation"/"policy" suffix required) - the one deliberately explicit
   phrase this amendment adds capable of establishing GENUINE membership
   for two DIFFERENT allocation references at once ("the development
   straddles JPA10 and JPA12"), since nearest-phrase attribution alone
   would otherwise have no way to let one phrase legitimately cover two
   separate, unrelated-by-conjunction reference occurrences.

Neither change touches the generic-reference name-corroboration logic
above (_generic_reference_has_name_corroboration) - a short/generic
reference still requires the allocation's own distinctive name to appear
somewhere in the document before EXPLICIT_REFERENCE/STRONG_CONTEXTUAL_
REFERENCE is possible at all, entirely independently of which phrase (if
any) attribution picks for a given occurrence.

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
    # Stage 2E.2 Final Matcher Amendment - the one deliberately explicit
    # phrase capable of establishing GENUINE membership for two DIFFERENT
    # allocation references at once ("the development straddles JPA10 and
    # JPA12") - bare (no "allocation"/"policy" suffix required), general,
    # not tied to any specific reference/council.
    "straddles",
]

NEGATIVE_RELATIONSHIP_PHRASES = [
    "adjacent to allocation", "adjacent to the allocation", "adjoining the allocated site",
    "adjoining the allocation", "outside allocation", "outside the allocation",
    "outside the allocated site", "not within allocation", "not within the allocation",
    "not within the allocated site", "near allocation", "near the allocation",
    "opposite allocation", "opposite the allocation",
    # Stage 2E.2 Final Matcher Amendment - bare present-tense verb forms
    # ("adjoins", not just the gerund "adjoining") and "beyond", none of
    # which any prior entry recognised (see module docstring's "MULTI-
    # REFERENCE PHRASE ATTRIBUTION" for the real production sentence that
    # slipped through: "...adjoins allocation Policy JPA 10 Beal Valley").
    "adjoins allocation", "adjoins the allocation", "adjoins policy", "adjoins the policy",
    "adjoining allocation", "adjoining policy",
    "beyond allocation", "beyond the allocation", "beyond policy", "beyond the policy",
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


def _window(text: str, match_start: int, match_end: int) -> str:
    window_start = max(0, match_start - PROXIMITY_WINDOW_CHARS)
    window_end = min(len(text), match_end + PROXIMITY_WINDOW_CHARS)
    return text[window_start:window_end]


def _all_substring_positions(haystack: str, needle: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            return positions
        positions.append(idx)
        start = idx + 1


def _gap_distance(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    """Character gap between two spans - 0 if they overlap, otherwise the
    number of characters strictly between them. Symmetric in the two
    spans' order."""
    if a_end <= b_start:
        return b_start - a_end
    if b_end <= a_start:
        return a_start - b_end
    return 0


# Stage 2E.2 Final Matcher Amendment - clause segmentation (Section 4's
# "clause segmentation around conjunctions/punctuation" option, layered on
# top of nearest-phrase-distance). Nearest-distance alone correctly
# separates two REFERENCE occurrences ("...JPA 12... and adjoins... JPA
# 10..." - each code sits right next to its own governing phrase), but a
# NAME occurrence sitting immediately AT a clause boundary ("...Broadbent
# Moss and adjoins allocation JPA 10...") can end up textually closer to
# the WRONG clause's phrase by raw distance alone, since "Broadbent Moss"
# is the tail of clause 1 but only a few characters from clause 2's own
# governing verb. Clause bounds fix this: a reference/name occurrence may
# only be attributed a phrase from its OWN clause, never one on the other
# side of a genuine clause break.
_HARD_CLAUSE_BOUNDARY_CHARS = ".;:\n"
_CLAUSE_BREAK_LOOKAHEAD_CHARS = 30


def _and_positions(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\band\b", text)]


def _introduces_new_relationship_clause(text: str, and_end: int) -> bool:
    """True when a "and" conjunction is immediately followed by the START
    of another relationship phrase (positive or negative) - a genuine new
    clause describing a DIFFERENT relationship ("...and adjoins..."), as
    opposed to a bare compound object with no new relationship verb at all
    ("...forms part of allocations X and Y...", where nothing but another
    reference follows "and"). Leading whitespace after "and" is stripped
    before checking, so the phrase's own length is never shortchanged by
    the separating space eating into the lookahead budget."""
    lookahead = text[and_end:and_end + _CLAUSE_BREAK_LOOKAHEAD_CHARS].lstrip()
    return any(lookahead.startswith(phrase) for phrase in POSITIVE_RELATIONSHIP_PHRASES + NEGATIVE_RELATIONSHIP_PHRASES)


def _clause_bounds(text: str, position: int) -> tuple[int, int]:
    """The widest span around `position` not crossing a hard sentence
    boundary (.;: or newline) or a genuine "and"-introduced new-relationship
    clause break (see _introduces_new_relationship_clause)."""
    left_hard = 0
    for i in range(position - 1, -1, -1):
        if text[i] in _HARD_CLAUSE_BOUNDARY_CHARS:
            left_hard = i + 1
            break
    right_hard = len(text)
    for i in range(position, len(text)):
        if text[i] in _HARD_CLAUSE_BOUNDARY_CHARS:
            right_hard = i
            break

    clause_start, clause_end = left_hard, right_hard
    for and_start, and_end in _and_positions(text[left_hard:right_hard]):
        abs_and_start, abs_and_end = left_hard + and_start, left_hard + and_end
        if not _introduces_new_relationship_clause(text, abs_and_end):
            continue
        if abs_and_start < position:
            clause_start = max(clause_start, abs_and_end)
        else:
            clause_end = min(clause_end, abs_and_start)
    return clause_start, clause_end


def _nearest_relationship_phrase(text: str, match_start: int, match_end: int) -> tuple[str | None, bool]:
    """Stage 2E.2 Final Matcher Amendment - the core attribution fix (see
    module docstring's "MULTI-REFERENCE PHRASE ATTRIBUTION"). Finds every
    POSITIVE_RELATIONSHIP_PHRASES/NEGATIVE_RELATIONSHIP_PHRASES occurrence
    within BOTH the ±PROXIMITY_WINDOW_CHARS window AND this occurrence's
    own clause (see _clause_bounds) around this ONE reference/name
    occurrence, and returns the (phrase, is_negative) of whichever
    occurrence is CLOSEST by character distance - never "does any phrase
    exist anywhere in the window" (the old, unsafe rule that let a phrase
    anchored to a different allocation reference bleed onto this one), and
    never a phrase from a DIFFERENT clause even if it happens to be
    textually closer (the refinement clause-bounding adds over distance
    alone - see _clause_bounds' own docstring for the NAME-occurrence
    case this specifically corrects). Returns (None, False) if no phrase
    occurs in the window/clause at all - deliberately never falls back to
    searching outside this occurrence's own clause.

    Ties (equal distance) are broken by whichever phrase occurrence starts
    earlier in the text - deterministic, and irrelevant in practice since
    two phrases at the exact same distance from one occurrence essentially
    never occurs in real planning-document prose."""
    window_start = max(0, match_start - PROXIMITY_WINDOW_CHARS)
    window_end = min(len(text), match_end + PROXIMITY_WINDOW_CHARS)
    clause_start, clause_end = _clause_bounds(text, match_start)
    search_start = max(window_start, clause_start)
    search_end = min(window_end, clause_end)
    search_span = text[search_start:search_end]

    best_phrase: str | None = None
    best_is_negative = False
    best_distance: int | None = None
    best_start = None

    for phrase, is_negative in (
        [(p, False) for p in POSITIVE_RELATIONSHIP_PHRASES] + [(p, True) for p in NEGATIVE_RELATIONSHIP_PHRASES]
    ):
        for occurrence_start in _all_substring_positions(search_span, phrase):
            abs_start = search_start + occurrence_start
            abs_end = abs_start + len(phrase)
            distance = _gap_distance(abs_start, abs_end, match_start, match_end)
            if best_distance is None or distance < best_distance or (distance == best_distance and abs_start < best_start):
                best_distance, best_phrase, best_is_negative, best_start = distance, phrase, is_negative, abs_start

    return best_phrase, best_is_negative


def _classify_occurrence(text: str, match_start: int, match_end: int) -> tuple[str, bool]:
    """Looks at the proximity window around ONE reference/name occurrence
    and returns (window, has_relationship_phrase) - the caller combines
    this with whether the match was a policy_reference or a site_name to
    pick the final category. has_relationship_phrase now means "the
    NEAREST relationship phrase to this occurrence is positive" (see
    _nearest_relationship_phrase), not "any positive phrase anywhere in
    the window"."""
    window = _window(text, match_start, match_end)
    phrase, is_negative = _nearest_relationship_phrase(text, match_start, match_end)
    has_positive = phrase is not None and not is_negative
    return window, has_positive


def _has_negative_phrase(text: str, match_start: int, match_end: int) -> bool:
    phrase, is_negative = _nearest_relationship_phrase(text, match_start, match_end)
    return phrase is not None and is_negative


def _generic_reference_has_name_corroboration(document_text: str, distinctive_name: str | None) -> bool:
    """Stage 2E.1 - the corroboration test a GENERIC reference hit must
    pass before it may be classified as EXPLICIT_REFERENCE or
    STRONG_CONTEXTUAL_REFERENCE (see module docstring's "GENERIC-REFERENCE
    NAME CORROBORATION"). Deliberately searches the WHOLE document text,
    not just the local PROXIMITY_WINDOW_CHARS window around the reference
    occurrence - a real production regression check (Stage 2E.1 Section 9's
    own re-run) found a genuine officer report ("East of Atherton", H6)
    that names its allocation eight times throughout the document but only
    once uses the bare "policy H6" phrasing, over 1,000 characters from the
    nearest name mention; a same-document check correctly keeps this
    genuine case while a narrower proximity-window check would have
    wrongly excluded it. The SAME document-wide check still correctly
    excludes every confirmed Stage 2E false positive (verified: none of
    "north leigh park"/"south hindley"/"east of atherton"/"remaining land
    south of atherton" appears ANYWHERE in the King Street or Rectory Lane
    documents, not merely far from the reference) - the distinguishing
    fact is genuinely whether the SAME document ever names the allocation
    at all, not how close together the two mentions happen to fall.
    `distinctive_name` is the allocation's own distinctive_name_terms()
    value (None when the allocation's site_name has no distinctive/
    searchable form at all, in which case a generic reference can never be
    corroborated)."""
    if not distinctive_name:
        return False
    return distinctive_name in document_text


def _snippet(text: str, match_start: int, match_end: int) -> str:
    start = max(0, match_start - SNIPPET_RADIUS_CHARS)
    end = min(len(text), match_end + SNIPPET_RADIUS_CHARS)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def _build_reference_hits(
    text: str, ref_pattern: "re.Pattern | None", *, is_generic: bool, distinctive_name: str | None,
    document: Document, application: Application, allocation: LocalPlanSite, weight: int,
) -> tuple[list[DocumentEvidenceHit], list[DocumentEvidenceHit]]:
    """Classifies every policy_reference occurrence for ONE allocation
    within ONE document's text - the ONE shared implementation used by
    both find_document_evidence_for_allocation (Stage 2C backward
    direction) and find_allocation_evidence_for_document (Stage 3B forward
    direction), so the Stage 2E.1 generic-reference name-corroboration fix
    (see module docstring) applies identically to both paths rather than
    risking the two independently-duplicated loops drifting apart."""
    positive_hits: list[DocumentEvidenceHit] = []
    contradictory_hits: list[DocumentEvidenceHit] = []
    for m in (list(ref_pattern.finditer(text)) if ref_pattern else []):
        if _has_negative_phrase(text, m.start(), m.end()):
            contradictory_hits.append(DocumentEvidenceHit(
                document_id=document.id, document_type=document.doc_type,
                application_id=application.id, application_reference=application.reference,
                site_id=application.site_id, matched_reference=allocation.policy_reference,
                snippet=_snippet(text, m.start(), m.end()), category=CONTRADICTORY_REFERENCE, weight=weight,
            ))
            continue
        _, has_positive = _classify_occurrence(text, m.start(), m.end())
        if is_generic and not _generic_reference_has_name_corroboration(text, distinctive_name):
            # Stage 2E.1: a generic/short reference alone (or even paired
            # with a positive relationship phrase) never establishes
            # membership without the allocation's own name corroborating
            # it - downgraded to WEAK_REFERENCE, which is never eligible
            # for auto-creation anywhere in this codebase, but is still
            # recorded (never silently dropped) for human review.
            category = WEAK_REFERENCE
        else:
            category = EXPLICIT_REFERENCE if has_positive else STRONG_CONTEXTUAL_REFERENCE
        positive_hits.append(DocumentEvidenceHit(
            document_id=document.id, document_type=document.doc_type,
            application_id=application.id, application_reference=application.reference,
            site_id=application.site_id, matched_reference=allocation.policy_reference,
            snippet=_snippet(text, m.start(), m.end()), category=category, weight=weight,
        ))
    return positive_hits, contradictory_hits


def find_document_evidence_for_allocation(
    session: Session, allocation: LocalPlanSite,
) -> tuple[list[DocumentEvidenceHit], list[DocumentEvidenceHit]]:
    """Returns (positive_hits, contradictory_hits) for one allocation.
    READ ONLY - issues only SELECT statements."""
    terms = _search_terms(allocation)
    if not terms:
        return [], []

    ref_pattern = _reference_pattern(allocation.policy_reference) if allocation.policy_reference else None
    is_generic = bool(allocation.policy_reference) and is_generic_reference(allocation.policy_reference)
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

        seen_any = bool(ref_matches)
        ref_positive, ref_contradictory = _build_reference_hits(
            text, ref_pattern, is_generic=is_generic, distinctive_name=distinctive_name,
            document=document, application=application, allocation=allocation, weight=weight,
        )
        positive_hits.extend(ref_positive)
        contradictory_hits.extend(ref_contradictory)

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


def find_allocation_evidence_for_document(
    document: Document, application: Application, allocations: list[LocalPlanSite],
) -> dict[int, tuple[list[DocumentEvidenceHit], list[DocumentEvidenceHit]]]:
    """FORWARD direction (Stage 3A Section 9): given ONE already-extracted
    Document (with its owning Application) already in hand, check it
    against a council's LocalPlanSite allocations - the mirror image of
    find_document_evidence_for_allocation's "one allocation, search many
    documents" direction above. Returns {allocation_id: (positive_hits,
    contradictory_hits)}, one entry per allocation in `allocations` that
    found at least one hit (an allocation with no hits is simply absent
    from the dict, never present with empty lists).

    REUSES every regex/proximity/classification primitive this module
    already has (_reference_pattern, distinctive_name_terms, _name_pattern,
    _classify_occurrence, _has_negative_phrase, _snippet, _doc_weight,
    _normalise_search_text) - no second matcher, no new evidence
    vocabulary. Deliberately skips _candidate_documents' SQL ILIKE
    prefilter entirely: that prefilter exists to avoid scanning every
    document in a council for one allocation's terms, but here the ONE
    document's text is already loaded in memory, so prefiltering it
    against itself would be pure overhead, not a safety mechanism.

    Callers must pre-scope `allocations` to the document's own
    application.council_code (this function does not query the database
    itself and takes no Session, mirroring find_document_evidence_for_
    allocation's own "READ ONLY" discipline by simply doing no I/O at
    all). READ ONLY - issues no queries, makes no writes.

    Recommended integration point (Stage 3A Section 9 audit finding): a
    NEW, separate pipeline stage run once per council after stage_documents
    (mirroring stage_evidence_refresh's own established shape in
    app.pipeline.run_weekly) - never invoked inline inside
    discover_and_store_documents_for_application's existing hot loop,
    which this codebase has already hardened carefully against exactly
    this kind of added risk (circuit-breaker interaction, OOM-diagnostic
    checkpoints, acquisition_complete bookkeeping). Any resulting
    DOCUMENT_CONFIRMED_SITE-eligible evidence should feed the SAME
    existing human-confirm-phrase-gated app.policy.allocation_site_
    relationships.run_controlled_relationship_write path - never a new,
    silent, per-document auto-write, which no other part of this codebase
    does even for its strongest evidence category."""
    if not document.extracted_text:
        return {}
    text = _normalise_search_text(document.extracted_text)
    weight = _doc_weight(document.doc_type)

    results: dict[int, tuple[list[DocumentEvidenceHit], list[DocumentEvidenceHit]]] = {}

    for allocation in allocations:
        if allocation.council_code != application.council_code:
            continue
        terms = _search_terms(allocation)
        if not terms:
            continue

        ref_pattern = _reference_pattern(allocation.policy_reference) if allocation.policy_reference else None
        is_generic = bool(allocation.policy_reference) and is_generic_reference(allocation.policy_reference)
        distinctive_name = distinctive_name_terms(allocation.site_name)
        name_pattern = _name_pattern(distinctive_name) if distinctive_name else None

        positive_hits, contradictory_hits = _build_reference_hits(
            text, ref_pattern, is_generic=is_generic, distinctive_name=distinctive_name,
            document=document, application=application, allocation=allocation, weight=weight,
        )

        for m in (list(name_pattern.finditer(text)) if name_pattern else []):
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

        if positive_hits or contradictory_hits:
            results[allocation.id] = (positive_hits, contradictory_hits)

    return results


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
    2. A contradictory hit NAMES Stage 2A's own candidate Site
       -> DOCUMENT_CONTRADICTS_FUZZY.
    3. A strong hit names the SAME Site as a Stage 2A candidate ->
       FUZZY_SUPPORTED_BY_DOCUMENT.
    4. A strong hit names a Site directly (no Stage 2A candidate to
       compare against, OR a DIFFERENT Site than Stage 2A's candidate(s)
       with no negative evidence about the fuzzy candidate itself) ->
       DOCUMENT_CONFIRMED_SITE.
    5. A strong hit exists but its Application has no linked Site at all
       -> DOCUMENT_CONFIRMED_APPLICATION_ONLY.
    6. Only weak/contextual positive hits, or an unrelated contradiction
       -> DOCUMENT_REVIEW_REQUIRED.
    7. Nothing found at all -> NO_DOCUMENT_EVIDENCE.

    STAGE 2D EVIDENCE-SEMANTICS AMENDMENT: a contradiction requires genuine
    NEGATIVE evidence about the fuzzy candidate itself (a
    CONTRADICTORY_REFERENCE hit - "outside allocation", "adjacent to
    allocation", etc, see NEGATIVE_RELATIONSHIP_PHRASES - naming that same
    Site). Strong POSITIVE evidence for a DIFFERENT Site than Stage 2A's
    candidate is never, by itself, a contradiction - in a many-to-many
    world (Stage 2D) one allocation can genuinely relate to more than one
    Site, so "documents confirm Site B" says nothing about whether Site A
    (the fuzzy candidate) is also related or unrelated. A live production
    audit of all 4 real DOCUMENT_CONTRADICTS_FUZZY cases under the
    now-corrected logic (JPA 32, JPA 1.1, JPA 29, JPA 30) found EVERY one
    had zero contradictory_hits - all four were this exact
    different-Site-with-no-negation pattern being misclassified as a
    contradiction. All four now fall through to DOCUMENT_CONFIRMED_SITE
    below: the document-supported Site is still persisted; the fuzzy
    candidate is simply left unconfirmed (no relationship created for it
    from this evidence alone) rather than falsely excluded as
    "contradicted". Genuine contradictions (an explicit negative phrase
    naming the fuzzy candidate's own Site) are unaffected and still take
    priority over everything below.
    """
    stage2a_site_ids = _stage2a_candidate_site_ids(stage2a)
    strong_hits = [h for h in positive_hits if h.category in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)]
    strong_site_ids = {h.site_id for h in strong_hits if h.site_id is not None}
    contradicted_site_ids = {h.site_id for h in contradictory_hits if h.site_id is not None}

    if len(strong_site_ids) > 1:
        return MULTIPLE_DOCUMENT_SUPPORTED_SITES

    if stage2a_site_ids and (contradicted_site_ids & stage2a_site_ids):
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

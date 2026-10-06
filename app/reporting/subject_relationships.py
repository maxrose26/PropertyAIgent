"""Stage 2.5B G2 - evidence-qualified subject relationships (specifications/025, "G2").

PURE: no database, session, network or Streamlit. Derives ONLY one relationship, ``CONTAINED_IN``, and only when the
evidence is complete; it prefers NO RELATIONSHIP over a plausible but unproven one. It never persists anything, creates no
id and carries no confidence score (only qualified relationships are emitted).

``CONTAINED_IN`` means: the available evidence establishes that the child planning scope is pursued PURSUANT TO the
identified parent permission/count scope. It does NOT establish ownership, availability, transaction structure, non-overlap
with sibling subjects, completeness of child phases, residual capacity or parcel geometry. Non-overlap is never inferred here
(siblings remain potentially overlapping; ``evidenced_pairs`` stays an explicit evidence input with no producer).

Qualified direct-parent rule - ALL must hold:
  1. the child is a ``phase`` CountAssessment scope (total_residential metric);
  2. a supporting source application of the child is RESERVED MATTERS (``resolve_planning_role``);
  3. its proposal contains EXACTLY ONE DISTINCT qualifying parent citation (ALL citations are scanned; never the first match);
  4. the citation is a full formatted reference that EXACTLY equals the reference of an existing application on the same
     council and site (no fuzzy matching, no inferred prefixes or year components);
  5. that cited application is a supporting source of the selected parent CountAssessment;
  6. the parent CountAssessment is EXACT, operative/consented, WHOLE_SITE, total_residential, on the same site;
  7. exactly ONE parent CountAssessment qualifies (several -> no relationship).
No multi-hop chain is ever traversed: the child must directly cite the parent (a variation can only be that direct parent if
it independently satisfies rule 6). Bare digits, "relating to", "in association with", smaller counts, later dates,
reserved-matters status alone, similar addresses, the same site, phase wording and counts that add up are NOT evidence.

Reference normalisation is deliberately minimal: whitespace and trailing punctuation are trimmed, nothing else; the
comparison with an existing reference is exact and CASE-SENSITIVE.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

CONTAINED_IN = "CONTAINED_IN"
RELATIONSHIPS = frozenset({CONTAINED_IN})          # no other relationship (in particular no non-overlap) is ever emitted
BASIS_RM_DIRECT_PARENT_CITATION = "RM_DIRECT_PARENT_CITATION"

# Same literal as app.reporting.scheme_reconciliation.ROLE_RESERVED_MATTERS (asserted equal by a test); kept literal so the
# module stays import-light and pure.
ROLE_RESERVED_MATTERS = "reserved_matters"
SCOPE_PHASE = "phase"
SCOPE_WHOLE_SITE = "whole_site"
METRIC_TOTAL_RESIDENTIAL = "total_residential"
PRECISION_EXACT = "EXACT"
BASIS_CONSENTED = "consented"

REASON_QUALIFIED = "QUALIFIED"
REASON_NO_CITATION = "NO_CITATION"
REASON_BARE_DIGIT_CITATION = "BARE_DIGIT_CITATION"
REASON_UNSPECIFIED_RELATION = "UNSPECIFIED_RELATION"
REASON_NOT_RESERVED_MATTERS = "NOT_RESERVED_MATTERS"
REASON_AMBIGUOUS_CITATIONS = "AMBIGUOUS_CITATIONS"
REASON_CITED_APPLICATION_NOT_FOUND = "CITED_APPLICATION_NOT_FOUND"
REASON_CITED_NOT_PARENT_COUNT_SOURCE = "CITED_NOT_PARENT_COUNT_SOURCE"
REASON_PARENT_SCOPE_NOT_WHOLE_SITE = "PARENT_SCOPE_NOT_WHOLE_SITE"
REASON_PARENT_NOT_EXACT_OPERATIVE = "PARENT_NOT_EXACT_OPERATIVE"
REASON_MULTIPLE_PARENT_ASSESSMENTS = "MULTIPLE_PARENT_ASSESSMENTS"
REASON_CHILD_NOT_PHASE_SCOPE = "CHILD_NOT_PHASE_SCOPE"
REASON_NO_CHILD_SOURCE = "NO_CHILD_SOURCE"
REASON_METRIC_NOT_COMPATIBLE = "METRIC_NOT_COMPATIBLE"
REASON_PARENT_SITE_MISMATCH = "PARENT_SITE_MISMATCH"
REASON_SUBJECT_IDENTITY_UNAVAILABLE = "SUBJECT_IDENTITY_UNAVAILABLE"
REASONS = frozenset({
    REASON_QUALIFIED, REASON_NO_CITATION, REASON_BARE_DIGIT_CITATION, REASON_UNSPECIFIED_RELATION, REASON_NOT_RESERVED_MATTERS,
    REASON_AMBIGUOUS_CITATIONS, REASON_CITED_APPLICATION_NOT_FOUND, REASON_CITED_NOT_PARENT_COUNT_SOURCE,
    REASON_PARENT_SCOPE_NOT_WHOLE_SITE, REASON_PARENT_NOT_EXACT_OPERATIVE, REASON_MULTIPLE_PARENT_ASSESSMENTS,
    REASON_CHILD_NOT_PHASE_SCOPE, REASON_NO_CHILD_SOURCE, REASON_METRIC_NOT_COMPATIBLE, REASON_PARENT_SITE_MISMATCH,
    REASON_SUBJECT_IDENTITY_UNAVAILABLE,
})


# --- phrase scanner (dedicated; scans ALL matches) -------------------------------------------------------------------------------------

# A formatted reference (letters/digits joined by '/' or '-', 2-5 parts). The trailing lookahead makes an OVER-LONG candidate (a 6th
# component, or any backtracked shorter fragment) fail to match at all: it is REJECTED, never truncated into a shorter reference. It can capture hyphenated words, so the exact-equality
# gate against an existing application reference is MANDATORY. (Same shape as app.pipeline.site_linking's formatted pattern,
# duplicated here so G2 neither imports nor changes site_linking.)
_REF = r"([A-Za-z0-9]+(?:[/-][A-Za-z0-9]+){1,4})(?![A-Za-z0-9]|[/-][A-Za-z0-9])"
_NO = r"\s*(?:ref\.?|reference|no\.?)?\s*:?\s*\(?"

_QUALIFYING_PATTERNS = (
    # "pursuant to [the] [outline|hybrid|full|detailed] [planning] permission|approval <ref>"
    re.compile(rf"pursuant\s+to\s+(?:the\s+)?(?:(?:outline|hybrid|full|detailed)\s+)?(?:planning\s+)?(?:permission|approval){_NO}{_REF}", re.I),
    # "pursuant to [the] outline|hybrid [planning] application <ref>"  (explicitly authorised wording)
    re.compile(rf"pursuant\s+to\s+(?:the\s+)?(?:outline|hybrid)\s+(?:planning\s+)?application{_NO}{_REF}", re.I),
    # "following [outline|hybrid|full|reserved matters] [planning] approval <ref>"
    re.compile(rf"following\s+(?:(?:outline|hybrid|full|reserved\s+matters)\s+)?(?:planning\s+)?approval{_NO}{_REF}", re.I),
)
# Diagnostic only - NEVER qualifying.
_BARE_DIGIT_PATTERNS = (
    re.compile(r"(?:pursuant\s+to|following)\s+(?:the\s+)?(?:(?:outline|hybrid|full|detailed|reserved\s+matters|planning)\s+)*"
               r"(?:permission|approval|application)\s*(?:ref\.?|reference|no\.?)?\s*:?\s*\(?(\d{4,6})\b", re.I),
    re.compile(r"reserved\s+matters.{0,60}?\((\d{4,6})\)", re.I),
)
_UNSPECIFIED_PATTERNS = (
    re.compile(rf"relating\s+to\s+(?:approved\s+)?app(?:lication)?\s*(?:no\.?)?\s*\(?{_REF}", re.I),
    re.compile(rf"in\s+association\s+with\s+(?:application\s*)?\(?{_REF}", re.I),
)
_TRAILING = " \t\r\n.,;:)'\"]"


def normalise_reference(raw: str) -> str:
    """The ONLY normalisation: trim surrounding whitespace and trailing punctuation. No case change, no inference."""
    return raw.strip().rstrip(_TRAILING).lstrip("(").strip()


@dataclass(frozen=True)
class Citation:
    reference: str   # normalised formatted reference
    phrase: str      # the matched text (provenance)


@dataclass(frozen=True)
class CitationScan:
    qualifying: tuple[Citation, ...]  # DISTINCT references, ordered by reference (never by textual/regex position)
    bare_digit: bool                  # a bare numeric citation was seen (never qualifying)
    unspecified_relation: bool        # "relating to" / "in association with" was seen (never qualifying)


def scan_parent_citations(text: str | None) -> CitationScan:
    """Scan ALL qualifying citations in ``text``. Order-independent: distinct references are returned sorted, so no
    'first match' ever decides anything."""
    text = text or ""
    spans = []
    found: dict[str, Citation] = {}
    for pattern in _QUALIFYING_PATTERNS:
        for match in pattern.finditer(text):
            reference = normalise_reference(match.group(1))
            spans.append(match.span())
            if reference and reference not in found:
                found[reference] = Citation(reference=reference, phrase=normalise_phrase(match.group(0)))
    qualifying = tuple(found[ref] for ref in sorted(found))

    def _overlaps(span):
        return any(span[0] < other[1] and other[0] < span[1] for other in spans)

    bare = any(not _overlaps(m.span()) for p in _BARE_DIGIT_PATTERNS for m in p.finditer(text))
    unspecified = any(True for p in _UNSPECIFIED_PATTERNS for _ in p.finditer(text))
    return CitationScan(qualifying=qualifying, bare_digit=bare, unspecified_relation=unspecified)


def normalise_phrase(phrase: str) -> str:
    return " ".join(phrase.split())


# --- relationship model -----------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SubjectRelationshipEvidence:
    """A qualified relationship. Derived each build; not persisted; no id; no confidence (only qualified ones exist)."""
    relationship: str                    # CONTAINED_IN
    child_subject_id: str                # the child CountAssessment.subject_id
    parent_subject_id: str               # the specific parent CountAssessment.subject_id (not merely a site id)
    child_application_reference: str     # the reserved-matters application whose proposal carries the citation
    parent_application_reference: str    # the cited application (a supporting source of the parent count)
    basis: str                           # RM_DIRECT_PARENT_CITATION
    provenance: str                      # the matched phrase, e.g. "pursuant to outline application OUT/1"


@dataclass(frozen=True)
class ContainmentResult:
    relationship: SubjectRelationshipEvidence | None
    reason: str                          # REASON_QUALIFIED iff a relationship is present, otherwise a diagnostic code


def _no(reason: str) -> ContainmentResult:
    return ContainmentResult(relationship=None, reason=reason)


_SITE_ID_RE = re.compile(r"^site:([1-9][0-9]*):")


def _site_of(subject_id) -> int | None:
    match = _SITE_ID_RE.match(subject_id) if isinstance(subject_id, str) else None
    return int(match.group(1)) if match else None


def _field(application, name):
    value = getattr(application, name, None)
    if value is None and hasattr(application, "application"):
        value = getattr(application.application, name, None)
    return value


def derive_containment(child_count, parent_counts: Iterable, applications: Iterable) -> ContainmentResult:
    """Derive ``CONTAINED_IN`` for ONE child phase scope, or return NO relationship with a reason.

    ``child_count`` / ``parent_counts``: CountAssessment-like (``scope_type``, ``subject_id``, ``metric``, ``precision``,
    ``basis``, ``sources`` with ``application_reference``). ``applications``: objects exposing ``reference``, ``role`` (the
    resolved planning role), ``proposal``, ``council_code`` and ``site_id`` (a ResolvedApplication also works). The caller may
    pass applications for many sites; only same-council/same-site ones are used."""
    applications = list(applications)
    parent_counts = list(parent_counts)

    if getattr(child_count, "scope_type", None) != SCOPE_PHASE:
        return _no(REASON_CHILD_NOT_PHASE_SCOPE)
    child_site = _site_of(getattr(child_count, "subject_id", None))
    if child_site is None:
        return _no(REASON_SUBJECT_IDENTITY_UNAVAILABLE)
    if getattr(child_count, "metric", None) != METRIC_TOTAL_RESIDENTIAL:
        return _no(REASON_METRIC_NOT_COMPATIBLE)

    # 1. the child's supporting source applications that are reserved matters (and on the child's site)
    source_refs = {getattr(s, "application_reference", None) for s in getattr(child_count, "sources", ())}
    source_refs.discard(None)
    sources = [a for a in applications if _field(a, "reference") in source_refs and _field(a, "site_id") == child_site]
    if not sources:
        return _no(REASON_NO_CHILD_SOURCE)
    reserved_matters = sorted((a for a in sources if _field(a, "role") == ROLE_RESERVED_MATTERS), key=lambda a: _field(a, "reference"))
    if not reserved_matters:
        return _no(REASON_NOT_RESERVED_MATTERS)

    # 2. scan ALL qualifying citations of every reserved-matters source; distinct references only
    citing: dict[str, tuple] = {}       # reference -> (citing application, Citation) - the first citing app by reference order
    bare = unspecified = False
    for application in reserved_matters:
        scan = scan_parent_citations(_field(application, "proposal"))
        bare = bare or scan.bare_digit
        unspecified = unspecified or scan.unspecified_relation
        for citation in scan.qualifying:
            citing.setdefault(citation.reference, (application, citation))
    if not citing:
        if bare:
            return _no(REASON_BARE_DIGIT_CITATION)
        if unspecified:
            return _no(REASON_UNSPECIFIED_RELATION)
        return _no(REASON_NO_CITATION)
    if len(citing) > 1:
        return _no(REASON_AMBIGUOUS_CITATIONS)      # never choose among distinct qualifying parents

    # 3. the single citation must EXACTLY equal an existing application on the same council and site
    (cited_reference, (citing_application, citation)), = citing.items()
    council = _field(citing_application, "council_code")
    cited = [a for a in applications if _field(a, "reference") == cited_reference
             and _field(a, "council_code") == council and _field(a, "site_id") == child_site]
    if not cited:
        return _no(REASON_CITED_APPLICATION_NOT_FOUND)

    # 4. parent CountAssessment: the cited application must be one of its supporting sources, then the parent gates
    containing = [pc for pc in parent_counts
                  if cited_reference in {getattr(s, "application_reference", None) for s in getattr(pc, "sources", ())}]
    if not containing:
        return _no(REASON_CITED_NOT_PARENT_COUNT_SOURCE)     # includes a citation of a variation that is not itself a parent source
    containing = [pc for pc in containing if _site_of(getattr(pc, "subject_id", None)) == child_site]
    if not containing:
        return _no(REASON_PARENT_SITE_MISMATCH)
    containing = [pc for pc in containing if getattr(pc, "scope_type", None) == SCOPE_WHOLE_SITE]
    if not containing:
        return _no(REASON_PARENT_SCOPE_NOT_WHOLE_SITE)
    containing = [pc for pc in containing if getattr(pc, "metric", None) == METRIC_TOTAL_RESIDENTIAL]
    if not containing:
        return _no(REASON_METRIC_NOT_COMPATIBLE)
    containing = [pc for pc in containing if getattr(pc, "precision", None) == PRECISION_EXACT
                  and getattr(pc, "basis", None) == BASIS_CONSENTED]
    if not containing:
        return _no(REASON_PARENT_NOT_EXACT_OPERATIVE)
    parent_ids = sorted({pc.subject_id for pc in containing})
    if len(parent_ids) > 1:
        return _no(REASON_MULTIPLE_PARENT_ASSESSMENTS)       # never silently choose one

    relationship = SubjectRelationshipEvidence(
        relationship=CONTAINED_IN, child_subject_id=child_count.subject_id, parent_subject_id=parent_ids[0],
        child_application_reference=_field(citing_application, "reference"), parent_application_reference=cited_reference,
        basis=BASIS_RM_DIRECT_PARENT_CITATION, provenance=citation.phrase)
    return ContainmentResult(relationship=relationship, reason=REASON_QUALIFIED)

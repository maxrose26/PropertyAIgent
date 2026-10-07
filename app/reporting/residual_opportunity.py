"""Stage 2.5B V8-B (specifications/025): residual-opportunity qualification - the R1 / R2 / R3 ladder.

PURE and deterministic: no database, network, model, schema or persistence. It qualifies ONE planning family's parent/child counts using the existing
safety primitive (``app.reporting.residual_capacity.assess_residual_planning_capacity``) and explicit, provenance-bearing evidence. It never invents evidence.

  R1 QUALIFIED RESIDUAL   every predicate TRUE. The only level that yields a derived FamilySubject (RESIDUAL_OPPORTUNITY), a derived residual count, a
                          deterministic non-persisted identity and an evidence fingerprint. Buyer fit is capped at POSSIBLE_FIT (app.policy.residual_fit).
  R2 POTENTIAL RESIDUAL   a wider permission and contained subordinate activity are evidenced but safe arithmetic is not (completeness / non-overlap
                          unknown, approximate counts). INVESTIGATION CONTEXT ONLY: no subject, no subject id, no fingerprint, no trusted count, no fit.
  R3 NO CONCLUSION        no residual proposition (missing evidence is never zero; a zero, negative or conflicting result creates nothing).

R1 is DORMANT in production BY EVIDENCE, not by a switch: the production evidence producer (``production_residual_evidence``) supplies containment
only (the existing G2 ``derive_containment``). Child-set completeness and sibling non-overlap have NO production producer, so they are UNKNOWN and
no production input can satisfy them: not database completeness, same-site membership, matching arithmetic, phase labels or "all children we know".
A later (Stage 2.6) qualified producer activates R1 by supplying ``ResidualEvidence`` through this same interface - no residual logic changes.

Predicate vocabulary (each TRUE / FALSE / UNKNOWN, with a provenance basis; UNKNOWN never becomes TRUE):
  PARENT_SCOPE_QUALIFIED, CHILD_RELATIONSHIP_QUALIFIED, COUNT_METRICS_COMPATIBLE, COUNT_PRECISION_COMPATIBLE, NO_SUPERSESSION_CONFLICT,
  SIBLING_NON_OVERLAP_ESTABLISHED, CHILD_SET_COMPLETE.
CHILD_SET_COMPLETE means sourced planning evidence names the complete relevant child set for the parent - never "all children in our database".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.reporting.acquisition_subjects import PLANNING_DELIVERY, build_new_kind_opportunity_id
from app.reporting.residential_count import CountAssessment, evidenced_pairs, is_meaningful_provenance
from app.reporting import residual_capacity as rc

RESIDUAL_EVIDENCE_VERSION = 1
KIND_RESIDUAL = "residual"

LEVEL_R1 = "R1_QUALIFIED_RESIDUAL"
LEVEL_R2 = "R2_POTENTIAL_RESIDUAL"
LEVEL_R3 = "R3_NO_RESIDUAL_CONCLUSION"

TRUE, FALSE, UNKNOWN = "TRUE", "FALSE", "UNKNOWN"
PARENT_SCOPE_QUALIFIED = "PARENT_SCOPE_QUALIFIED"
CHILD_RELATIONSHIP_QUALIFIED = "CHILD_RELATIONSHIP_QUALIFIED"
COUNT_METRICS_COMPATIBLE = "COUNT_METRICS_COMPATIBLE"
COUNT_PRECISION_COMPATIBLE = "COUNT_PRECISION_COMPATIBLE"
NO_SUPERSESSION_CONFLICT = "NO_SUPERSESSION_CONFLICT"
SIBLING_NON_OVERLAP_ESTABLISHED = "SIBLING_NON_OVERLAP_ESTABLISHED"
CHILD_SET_COMPLETE = "CHILD_SET_COMPLETE"
PREDICATES = (PARENT_SCOPE_QUALIFIED, CHILD_RELATIONSHIP_QUALIFIED, COUNT_METRICS_COMPATIBLE, COUNT_PRECISION_COMPATIBLE, NO_SUPERSESSION_CONFLICT,
              SIBLING_NON_OVERLAP_ESTABLISHED, CHILD_SET_COMPLETE)

R1_CAVEAT = ("Derived (apparent) residual planning capacity: the parent permission count less the contained subordinate count. Availability, ownership, parcel geometry "
             "and independent deliverability are unverified.")
PLANNING_R2_TEXT = ("Potential residual scope — investigate. A wider permission and subordinate planning activity are identified, but a distinct residual "
                    "acquisition scope and its capacity are not yet established.")
ALLOCATION_R2_TEXT = ("Potential residual scope — investigate. Planning evidence indicates partial development coverage, but a distinct residual acquisition "
                      "scope and its capacity are not yet established.")

# gate reasons (from the safety primitive) at which a residual PROPOSITION still exists but safe arithmetic does not -> R2 (containment already holds there)
_R2_REASONS = frozenset({rc.REASON_CHILD_OVERLAP_NOT_EXCLUDED, rc.REASON_CHILD_SET_NOT_ESTABLISHED, rc.REASON_CHILD_SET_MISMATCH, rc.REASON_CHILD_SET_CONFLICT})


@dataclass(frozen=True)
class ResidualEvidence:
    """Explicit, provenance-bearing evidence a qualified producer supplies. Every tuple element carries a non-empty provenance string.
    containment:  (child_subject_id, parent_subject_id, provenance)
    non_overlap:  (subject_id, subject_id, provenance)
    child_set:    (parent_subject_id, child_subject_ids, provenance) - the COMPLETE relevant child set, sourced
    Supersession / conflict is carried by the counts themselves (basis, resolution) and by excluded children; no separate input exists."""
    containment: tuple = ()
    non_overlap: tuple = ()
    child_set: tuple = ()


NO_EVIDENCE = ResidualEvidence()


def production_residual_evidence(containment_pairs) -> ResidualEvidence:
    """The ONLY production evidence producer: G2 containment (``derive_containment``) pairs ``(child_id, parent_id, provenance)``.
    Completeness and non-overlap have no producer here and are deliberately always empty: R1 is dormant in production by evidence."""
    return ResidualEvidence(containment=tuple(containment_pairs))


@dataclass(frozen=True)
class PredicateResult:
    name: str
    state: str
    basis: str


@dataclass(frozen=True)
class ResidualQualification:
    level: str
    reason: str
    site_id: int | None
    parent_subject_id: str | None
    child_subject_ids: tuple
    predicates: tuple
    explanation: str
    residual_value: int | None = None              # R1 ONLY
    residual_assessment: CountAssessment | None = None   # R1 ONLY
    subject_id: str | None = None                  # R1 ONLY (derived, non-persisted)
    evidence_fingerprint: str | None = None        # R1 ONLY

    def predicate(self, name: str) -> PredicateResult:
        return next(p for p in self.predicates if p.name == name)

    @property
    def is_subject(self) -> bool:
        return self.level == LEVEL_R1

    @property
    def context_text(self) -> str | None:
        """The only user-facing residual text a non-R1 level may carry: R2 investigation context (never a number)."""
        return PLANNING_R2_TEXT if self.level == LEVEL_R2 else None


def _site_of(subject_id: str | None) -> int | None:
    parsed = rc._parse_subject(subject_id) if subject_id else None
    return int(parsed[0]) if parsed else None


def _prov(items) -> str:
    return "; ".join(sorted(str(i) for i in items)) or "none supplied"


def _canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def residual_subject_identity(site_id: int, parent_subject_id: str, child_subject_ids) -> str:
    """Deterministic, non-persisted identity from the parent scope and the QUALIFIED child-set identity (+ the evidence version) - not from the residual number.
    sha256, never Python's runtime hash; independent of child order and duplicates."""
    digest = hashlib.sha256(_canonical({"v": RESIDUAL_EVIDENCE_VERSION, "parent": parent_subject_id, "children": sorted(set(child_subject_ids))}).encode("utf-8")).hexdigest()[:20]
    return build_new_kind_opportunity_id(KIND_RESIDUAL, site_id, digest)


def _source_refs(count: CountAssessment) -> list:
    return sorted({str(getattr(s, "application_reference", None)) for s in count.sources if getattr(s, "application_reference", None)})


def residual_evidence_fingerprint(parent: CountAssessment, subtracted, evidence: ResidualEvidence, residual_value: int) -> str:
    """sha256 over ONLY the evidence that establishes the proposition: parent and child counts (+ source references), the containment / non-overlap / child-set
    evidence actually used (with provenance), the level and the derived residual. EXCLUDES buyer, fit, wording, rank and timestamps."""
    child_ids = {c.subject_id for c in subtracted}
    payload = {
        "v": RESIDUAL_EVIDENCE_VERSION, "level": LEVEL_R1,
        "parent": {"id": parent.subject_id, "metric": parent.metric, "value": parent.exact_value, "refs": _source_refs(parent)},
        "children": sorted(({"id": c.subject_id, "value": c.exact_value, "refs": _source_refs(c)} for c in subtracted), key=lambda d: d["id"]),
        "containment": sorted([c, p, s.strip()] for c, p, s in evidence.containment if p == parent.subject_id and c in child_ids and is_meaningful_provenance(s)),
        "non_overlap": sorted(sorted([a, b]) + [s.strip()] for a, b, s in evidence.non_overlap if a in child_ids and b in child_ids and is_meaningful_provenance(s)),
        "child_set": sorted([p, sorted(ids), s.strip()] for p, ids, s in evidence.child_set if p == parent.subject_id and is_meaningful_provenance(s)),
        "residual": residual_value,
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _predicates(parent, children, evidence, result) -> tuple:
    reason = result.reason
    eligible = [c for c in children if c.basis == rc.OPERATIVE_APPROVED_BASIS and c.subject_id and c.subject_id != parent.subject_id]
    ids = sorted({c.subject_id for c in eligible})
    contained = {(c, p) for c, p, s in evidence.containment if is_meaningful_provenance(s)}
    contained_all = bool(ids) and all((i, parent.subject_id) in contained for i in ids)
    out = []

    parent_ok = (bool(parent.subject_id) and parent.basis == rc.OPERATIVE_APPROVED_BASIS and _site_of(parent.subject_id) is not None
                 and reason not in (rc.REASON_PARENT_IDENTITY_MISSING, rc.REASON_PARENT_NOT_OPERATIVE, rc.REASON_SCOPE_INCOMPATIBLE))
    out.append(PredicateResult(PARENT_SCOPE_QUALIFIED, TRUE if parent_ok else FALSE,
                               f"operative approved whole-site/phase parent {parent.subject_id or '(no identity)'}" if parent_ok else f"parent not qualified ({reason})"))
    out.append(PredicateResult(CHILD_RELATIONSHIP_QUALIFIED, TRUE if contained_all else UNKNOWN,
                               _prov(f"{c}->{p}: {s}" for c, p, s in evidence.containment if (c, p) in {(i, parent.subject_id) for i in ids})
                               if contained_all else "explicit containment evidence is not supplied for every contributing child"))
    metrics = {parent.metric} | {c.metric for c in eligible}
    out.append(PredicateResult(COUNT_METRICS_COMPATIBLE, TRUE if len(metrics) == 1 else FALSE, "metric " + _prov(metrics)))
    counted = [parent, *eligible]
    if any(c.precision == "UNKNOWN" for c in counted):
        precision = (UNKNOWN, "a count is unknown")
    elif all(c.precision == "EXACT" and c.exact_value is not None for c in counted):
        precision = (TRUE, "parent and every contributing child count is exact")
    else:
        precision = (FALSE, "a count is approximate or a range; an exact residual is never invented")
    out.append(PredicateResult(COUNT_PRECISION_COMPATIBLE, *precision))
    conflict = reason in (rc.REASON_COUNT_MATERIAL_CONFLICT, rc.REASON_CONFLICTING_DUPLICATE_CHILD, rc.REASON_CHILDREN_EXCEED_PARENT)
    unresolved = reason == rc.REASON_UNRESOLVED_CHILD
    out.append(PredicateResult(NO_SUPERSESSION_CONFLICT, FALSE if conflict else UNKNOWN if unresolved else TRUE,
                               f"conflict ({reason})" if conflict else "a child's eligibility is unresolved" if unresolved else "no unresolved conflict or supersession among the supplied counts"))
    pairs = evidenced_pairs(evidence.non_overlap)
    unproven = [(a, b) for k, a in enumerate(ids) for b in ids[k + 1:] if frozenset((a, b)) not in pairs]
    if len(ids) <= 1:
        out.append(PredicateResult(SIBLING_NON_OVERLAP_ESTABLISHED, TRUE if ids else UNKNOWN, "a single contributing child has no sibling" if ids else "no contributing child"))
    elif not unproven:
        out.append(PredicateResult(SIBLING_NON_OVERLAP_ESTABLISHED, TRUE, "explicit non-overlap evidence for every child pair"))
    else:
        out.append(PredicateResult(SIBLING_NON_OVERLAP_ESTABLISHED, UNKNOWN, "explicit non-overlap evidence is missing for: " + ", ".join(f"{a}/{b}" for a, b in unproven)))
    if result.child_set_completeness == rc.COMPLETENESS_ESTABLISHED:
        out.append(PredicateResult(CHILD_SET_COMPLETE, TRUE, f"sourced child-set evidence: {result.child_set_provenance}"))
    elif reason in (rc.REASON_CHILD_SET_MISMATCH, rc.REASON_CHILD_SET_CONFLICT):
        out.append(PredicateResult(CHILD_SET_COMPLETE, FALSE, f"child-set evidence disagrees with the supplied children ({reason})"))
    else:
        out.append(PredicateResult(CHILD_SET_COMPLETE, UNKNOWN, "no sourced evidence names the complete relevant child set"))
    return tuple(out)


def qualify_residual(parent: CountAssessment, children, evidence: ResidualEvidence = NO_EVIDENCE) -> ResidualQualification:
    """Qualify one parent's residual: R1 / R2 / R3. Pure; ``evidence`` defaults to none (nothing is ever inferred)."""
    children = tuple(children)
    result = rc.assess_residual_planning_capacity(parent, children, containment_evidence=evidence.containment, non_overlap_evidence=evidence.non_overlap,
                                                  child_set_evidence=evidence.child_set)
    predicates = _predicates(parent, children, evidence, result)
    site_id = _site_of(parent.subject_id)
    child_ids = tuple(sorted({c.subject_id for c in children if c.basis == rc.OPERATIVE_APPROVED_BASIS and c.subject_id}))

    def outcome(level, explanation, **fields):
        return ResidualQualification(level=level, reason=result.reason, site_id=site_id, parent_subject_id=parent.subject_id or None, child_subject_ids=child_ids,
                                     predicates=predicates, explanation=explanation, **fields)

    if result.resolved:
        value = result.residual_planning_capacity
        if value is None or value <= 0:
            return outcome(LEVEL_R3, "The qualified parent is fully accounted for by the qualified child set; no residual subject exists.")
        subtracted = result.subtracted_children
        subject_id = residual_subject_identity(site_id, parent.subject_id, [c.subject_id for c in subtracted])
        assessment = CountAssessment(scope_type="residual", scope_label=subject_id.rsplit(":", 1)[1], subject_id=subject_id, metric=result.metric, precision="EXACT",
                                     value=value, resolution="derived_residual", confidence="derived", sources=(), basis="derived_residual")
        return outcome(LEVEL_R1, result.explanation, residual_value=value, residual_assessment=assessment, subject_id=subject_id,
                       evidence_fingerprint=residual_evidence_fingerprint(parent, subtracted, evidence, value))
    contained = {p for p in predicates if p.name == CHILD_RELATIONSHIP_QUALIFIED}.pop().state == TRUE
    if result.reason in _R2_REASONS or (result.reason == rc.REASON_COUNT_NOT_EXACT and contained):
        return outcome(LEVEL_R2, "A wider permission and contained subordinate planning activity are evidenced, but the remaining scope cannot be quantified safely.")
    return outcome(LEVEL_R3, f"No residual proposition is established ({result.reason}).")


# --- allocation trigger (R2 only; the subtraction is never exposed as a scale) -------------------------------------------------------------

@dataclass(frozen=True)
class AllocationResidualContext:
    """R2 investigation context for a strategic allocation. Carries NO number: the Stage 3A coverage arithmetic is only the trigger."""
    level: str
    text: str


POTENTIAL_RESIDUAL_SHORT = "Potential residual scope — investigate"
NO_POTENTIAL_RESIDUAL_SHORT = "Not indicated"


def is_potential_residual_scope(classification, status, residual, activity_count) -> bool:
    """The ONE R2 trigger for a strategic allocation, from the internal Stage 3A coverage fields: planning activity accounts for only PART of the allocation (PARTIAL_COVERAGE),
    accounting is sound (``ok``) and the internal subtraction is positive. The figure is read ONLY as a trigger; it is never returned."""
    from app.reporting.allocation_development_coverage import PARTIAL_COVERAGE
    return bool(status == "ok" and classification == PARTIAL_COVERAGE and isinstance(residual, int) and not isinstance(residual, bool) and residual > 0
                and isinstance(activity_count, int) and activity_count > 0)


def allocation_residual_context(coverage) -> AllocationResidualContext | None:
    """R2 context for a strategic allocation from a DevelopmentCoverageResult-like object (see ``is_potential_residual_scope``); otherwise nothing (R3)."""
    if coverage is None:
        return None
    if is_potential_residual_scope(getattr(coverage, "development_coverage_classification", None), getattr(coverage, "capacity_accounting_status", None),
                                   getattr(coverage, "indicative_residual_capacity", None), getattr(coverage, "number_of_sites_with_planning_activity", 0) or 0):
        return AllocationResidualContext(LEVEL_R2, ALLOCATION_R2_TEXT)
    return None


def potential_residual_label(classification, status, residual, activity_count) -> str:
    """Short, number-free label for tables / CSV: R2 context text or 'Not indicated'."""
    return POTENTIAL_RESIDUAL_SHORT if is_potential_residual_scope(classification, status, residual, activity_count) else NO_POTENTIAL_RESIDUAL_SHORT


def r1_prompt_fact(qualification: ResidualQualification) -> str:
    """The ONLY sanctioned way to put a qualified residual in front of a model: labelled DERIVED / APPARENT with the approved caveat, and never for R2/R3 (which have no quantity).
    No prompt in the platform uses R1 today (R1 is dormant in production); this is the interface a future grounding step must use."""
    if qualification.level != LEVEL_R1 or qualification.residual_value is None:
        raise ValueError("only an R1 qualification has a residual quantity that may be supplied to a model")
    return (f"Derived (apparent) residual planning capacity: {qualification.residual_value:,} homes, computed deterministically as the qualified parent permission count less the qualified "
            f"contained subordinate count. {R1_CAVEAT} Do not recompute it and do not treat it as available land.")

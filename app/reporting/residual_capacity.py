"""Residual planning-capacity safety contract (Stage 2.5 preflight gates 2 and 2H).

Answers one narrow question: can these trusted planning subjects safely take
part in residual-capacity arithmetic (a parent count minus contained child
counts)? It does NOT create opportunities, rank, persist, render or decide who
could buy anything, and nothing in production calls it yet.

A numeric residual must never look more complete or certain than the evidence
used to derive it. RESOLVED therefore means: given a trusted parent count, an
EVIDENCED-COMPLETE set of relevant child scopes, compatible metrics, same-site
compatible scopes, explicit containment and (for several children) explicit
non-overlap, this arithmetic residual is supported as PLANNING CAPACITY. It
never establishes land availability, ownership, control, willingness to sell,
deliverability, one coherent parcel or an acquisition package. There is
deliberately no "available units" field.

Child-set completeness is never inferred from "one child was supplied", "all
supplied children have counts", "all are contained" or "all are non-overlapping".
It requires explicit sourced child-set evidence naming every relevant child
subject for the parent; without it the result is UNVERIFIED and no integer is
returned. Production currently has no source for that evidence, so in production
this primitive fails safe to UNVERIFIED until Stage 2.5/2.6 supplies it.

`basis == "consented"` means only that a count belongs to the accepted approved
planning position used for this arithmetic. It does not establish that the
permission is unexpired, that development has not commenced or is incomplete,
that land is available or that development is deliverable; lapse and build
status are deliberately outside this primitive.

Known limitation: the primitive cannot prove that two differently identified
subjects are not the same real-world development scope. Explicit containment
and non-overlap evidence remains required, and entity resolution is not solved
here.

Pure and deterministic: inputs are existing Stage 2 CountAssessment values plus
explicit, sourced evidence tuples. Nothing is inferred from shared sites or
addresses, newer or smaller applications, "phase" wording, Reserved Matters
status or related references. Unknown or unsafe stays explicit: when the
arithmetic is not safe no residual is calculated.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.material_change import (
    DECIDED_RECOMMENDATION_ONLY, DECIDED_REFUSED, DECIDED_UNDETERMINED, DECIDED_WITHDRAWN,
)
from app.reporting.residential_count import CountAssessment, evidenced_pairs, is_meaningful_provenance

RESOLVED = "RESOLVED"
UNVERIFIED = "UNVERIFIED"
MATERIAL_CONFLICT = "MATERIAL_CONFLICT"

# Operative-position basis values CountAssessment already carries: "consented"
# (accepted approved position) and "active" (undecided/pending).
OPERATIVE_APPROVED_BASIS = "consented"
PENDING_BASIS = "active"
SUPERSEDED_BASIS = "superseded"
# A child with one of these is KNOWN not to consume approved parent capacity.
# Any other basis (None, "", unrecognised) leaves eligibility UNRESOLVED, which
# blocks a numeric residual because that child may consume parent capacity.
KNOWN_INELIGIBLE_BASES = frozenset({
    PENDING_BASIS, SUPERSEDED_BASIS, DECIDED_REFUSED, DECIDED_WITHDRAWN,
    DECIDED_UNDETERMINED, DECIDED_RECOMMENDATION_ONLY,
})

# Scope vocabulary and subject identity follow scheme_reconciliation
# (SCOPE_*, subject_id "site:{site_id}:{scope_type}:{scope_label}"); a test
# asserts these literals stay equal to the originals.
SCOPE_WHOLE_SITE = "whole_site"
SCOPE_PHASE = "phase"
SCOPE_PLOT = "plot"
_CONTAINING_SCOPES = frozenset({SCOPE_WHOLE_SITE, SCOPE_PHASE})
_CONTAINABLE_SCOPES = frozenset({SCOPE_PHASE, SCOPE_PLOT})

# Reasons (why arithmetic was allowed or withheld).
REASON_RESOLVED = "resolved"
REASON_PARENT_IDENTITY_MISSING = "parent_identity_missing"
REASON_PARENT_NOT_OPERATIVE = "parent_not_operative_approved"
REASON_CHILD_IDENTITY_MISSING = "child_identity_missing"
REASON_CHILD_IS_PARENT = "child_is_parent"
REASON_UNRESOLVED_CHILD = "unresolved_child_eligibility"
REASON_NO_OPERATIVE_CHILD = "no_operative_child"
REASON_COUNT_MATERIAL_CONFLICT = "count_material_conflict"
REASON_SCOPE_INCOMPATIBLE = "site_or_scope_incompatible"
REASON_METRIC_MISMATCH = "metric_mismatch"
REASON_UNKNOWN_COUNT = "unknown_count"
REASON_COUNT_NOT_EXACT = "count_not_exact"
REASON_CONFLICTING_DUPLICATE_CHILD = "conflicting_duplicate_child"
REASON_CONTAINMENT_NOT_ESTABLISHED = "containment_not_established"
REASON_CHILD_OVERLAP_NOT_EXCLUDED = "child_overlap_not_excluded"
REASON_CHILDREN_EXCEED_PARENT = "children_exceed_parent"
REASON_CHILD_SET_NOT_ESTABLISHED = "child_set_completeness_not_established"
REASON_CHILD_SET_MISMATCH = "child_set_mismatch"
REASON_CHILD_SET_CONFLICT = "child_set_evidence_conflict"

# Why a supplied child did not consume capacity (known ineligible only).
EXCLUDED_NOT_OPERATIVE_APPROVED = "not_operative_approved"

COMPLETENESS_ESTABLISHED = "established"
COMPLETENESS_NOT_ESTABLISHED = "not_established"

CLAIM = ("Residual planning capacity supported by current evidence over an evidenced-complete set of child "
         "subjects. It is not land availability, ownership, control, willingness to sell, deliverability, one "
         "coherent parcel or an acquisition package. 'Consented' denotes the accepted approved planning position "
         "only; it says nothing about lapse or expiry, commencement, completion, availability or deliverability.")


@dataclass(frozen=True)
class ExcludedChild:
    child: CountAssessment
    reason: str


@dataclass(frozen=True)
class ResidualCapacityAssessment:
    status: str
    reason: str
    explanation: str
    parent: CountAssessment
    metric: str | None = None
    subtracted_children: tuple = ()
    excluded_children: tuple = ()
    unresolved_children: tuple = ()
    residual_planning_capacity: int | None = None
    containment_provenance: tuple = ()
    non_overlap_provenance: tuple = ()
    child_set_completeness: str = COMPLETENESS_NOT_ESTABLISHED
    child_set_provenance: str | None = None
    claim: str = CLAIM

    @property
    def resolved(self) -> bool:
        return (self.status == RESOLVED and self.residual_planning_capacity is not None
                and self.child_set_completeness == COMPLETENESS_ESTABLISHED)

    def label(self) -> str:
        if not self.resolved:
            return "Residual planning capacity not established"
        noun = "homes" if self.metric == "total_residential" else (self.metric or "units").replace("_", " ")
        return f"{self.residual_planning_capacity:,} {noun} of residual planning capacity (planning capacity only)"


def _result(status, reason, explanation, parent, **fields) -> ResidualCapacityAssessment:
    return ResidualCapacityAssessment(status=status, reason=reason, explanation=explanation, parent=parent, **fields)


def _parse_subject(subject_id: str):
    """(site_id, scope_type, scope_label) for 'site:{site_id}:{scope_type}:{scope_label}', else None."""
    parts = subject_id.split(":", 3)
    if len(parts) != 4 or parts[0] != "site" or not (parts[1].isascii() and parts[1].isdigit()):
        return None
    if not parts[2] or not parts[3]:
        return None
    return parts[1], parts[2], parts[3]


def _scope_incompatibility(parent: CountAssessment, child: CountAssessment) -> str | None:
    """Why this child cannot sit under this parent, or None. No fuzzy matching, no naming inference."""
    p, c = _parse_subject(parent.subject_id), _parse_subject(child.subject_id)
    if p is None or c is None:
        return f"{child.subject_id}: subject identity is not a parseable site/scope identity"
    if p[0] != c[0]:
        return f"{child.subject_id}: belongs to site {c[0]}, not the parent's site {p[0]}"
    if p[1] != parent.scope_type or c[1] != child.scope_type:
        return f"{child.subject_id}: subject identity and scope type disagree"
    if p[1] not in _CONTAINING_SCOPES:
        return f"{child.subject_id}: a {p[1]} scope cannot contain other scopes"
    if c[1] not in _CONTAINABLE_SCOPES:
        return f"{child.subject_id}: a {c[1]} scope cannot be contained in the parent"
    return None


def _child_set_state(parent: CountAssessment, supplied_ids: frozenset, evidence):
    """('established', provenance) / ('not_established', None) / ('mismatch', detail) / ('conflict', None)."""
    matching = []
    for parent_id, child_ids, provenance in evidence:
        if (parent_id == parent.subject_id and is_meaningful_provenance(provenance)
                and isinstance(child_ids, (tuple, list, set, frozenset))):
            matching.append((frozenset(child_ids), provenance.strip()))
    if not matching:
        return "not_established", None
    if len({ids for ids, _ in matching}) > 1:
        return "conflict", None
    ids, provenance = matching[0]
    if ids != supplied_ids:
        missing, extra = sorted(ids - supplied_ids), sorted(supplied_ids - ids)
        detail = []
        if missing:
            detail.append("named by the child-set evidence but not supplied: " + ", ".join(missing))
        if extra:
            detail.append("supplied but not in the child-set evidence: " + ", ".join(extra))
        return "mismatch", "; ".join(detail)
    return "established", provenance


def assess_residual_planning_capacity(parent: CountAssessment, children, *, containment_evidence=(),
                                      non_overlap_evidence=(), child_set_evidence=()) -> ResidualCapacityAssessment:
    """Parent count minus contained child counts, only when every safety gate holds.

    containment_evidence: iterable of (child_subject_id, parent_subject_id, provenance).
    non_overlap_evidence: iterable of (subject_id, subject_id, provenance) - the same
    pair contract and rule as phase aggregation (evidenced_pairs).
    child_set_evidence: iterable of (parent_subject_id, child_subject_ids, provenance)
    stating that child_subject_ids is the COMPLETE set of relevant child subjects of that
    parent (operative, known-ineligible or otherwise); every one must be supplied and
    nothing else may be.
    Provenance must be a non-empty string. All evidence is explicit caller input; this
    function never invents any of it.
    """
    children = tuple(children)
    containment_evidence = tuple(containment_evidence)
    non_overlap_evidence = tuple(non_overlap_evidence)
    child_set_evidence = tuple(child_set_evidence)

    if not parent.subject_id:
        return _result(UNVERIFIED, REASON_PARENT_IDENTITY_MISSING,
                       "The parent has no subject identity, so containment cannot be established.", parent)
    if parent.basis != OPERATIVE_APPROVED_BASIS:
        return _result(UNVERIFIED, REASON_PARENT_NOT_OPERATIVE,
                       "The parent count is not an operative approved position, so it cannot supply capacity.", parent)

    # Operative approved children may consume capacity; refused, withdrawn, superseded and pending
    # children are KNOWN not to; any child whose eligibility cannot be established is UNRESOLVED.
    eligible: list[CountAssessment] = []
    excluded: list[ExcludedChild] = []
    unresolved: list[CountAssessment] = []
    for child in children:
        if child.basis == OPERATIVE_APPROVED_BASIS:
            if not child.subject_id:
                return _result(UNVERIFIED, REASON_CHILD_IDENTITY_MISSING,
                               "An operative child has no subject identity, so containment cannot be established.",
                               parent, excluded_children=tuple(excluded))
            if child.subject_id == parent.subject_id:
                return _result(UNVERIFIED, REASON_CHILD_IS_PARENT,
                               "A subject cannot be its own child.", parent, excluded_children=tuple(excluded))
            eligible.append(child)
        elif child.basis in KNOWN_INELIGIBLE_BASES:
            excluded.append(ExcludedChild(child, EXCLUDED_NOT_OPERATIVE_APPROVED))
        else:
            unresolved.append(child)

    def withheld(status, reason, explanation, **fields):
        return _result(status, reason, explanation, parent, excluded_children=tuple(excluded),
                       unresolved_children=tuple(unresolved), **fields)

    # Material conflicts are preserved, never averaged or resolved by arithmetic.
    if parent.resolution == "material_conflict" or any(c.resolution == "material_conflict" for c in eligible):
        return withheld(MATERIAL_CONFLICT, REASON_COUNT_MATERIAL_CONFLICT,
                        "A parent or child count is an unresolved material conflict; no residual is calculated.")
    if unresolved:
        return withheld(UNVERIFIED, REASON_UNRESOLVED_CHILD,
                        "A supplied child's planning eligibility cannot be established, so it may consume parent "
                        "capacity; no residual is calculated for: "
                        + ", ".join(sorted(c.subject_id or "(no identity)" for c in unresolved)) + ".")
    if not eligible:
        return withheld(UNVERIFIED, REASON_NO_OPERATIVE_CHILD,
                        "No operative approved child subject was supplied, so no residual is derived.")

    incompatible = [reason for reason in (_scope_incompatibility(parent, c) for c in eligible) if reason]
    if incompatible:
        return withheld(UNVERIFIED, REASON_SCOPE_INCOMPATIBLE,
                        "Site or scope compatibility with the parent is not established: " + "; ".join(sorted(incompatible)) + ".")

    metrics = {parent.metric} | {c.metric for c in eligible}
    if len(metrics) > 1:
        return withheld(UNVERIFIED, REASON_METRIC_MISMATCH,
                        "Parent and child counts use different metrics and are never converted: "
                        + ", ".join(sorted(str(m) for m in metrics)) + ".")
    metric = parent.metric

    counted = [parent, *eligible]
    if any(c.precision == "UNKNOWN" or (c.precision == "EXACT" and c.exact_value is None) for c in counted):
        return withheld(UNVERIFIED, REASON_UNKNOWN_COUNT,
                        "A parent or child count is unknown; unknown is never treated as zero.", metric=metric)
    if any(c.precision != "EXACT" or c.exact_value is None for c in counted):
        return withheld(UNVERIFIED, REASON_COUNT_NOT_EXACT,
                        "A parent or child count is approximate or a range; no exact residual is invented.",
                        metric=metric)

    # The same child subject supplied twice is one subject; differing values are a conflict.
    distinct: dict[str, CountAssessment] = {}
    for child in eligible:
        seen = distinct.get(child.subject_id)
        if seen is None:
            distinct[child.subject_id] = child
        elif seen.exact_value != child.exact_value:
            return withheld(MATERIAL_CONFLICT, REASON_CONFLICTING_DUPLICATE_CHILD,
                            "The same child subject was supplied with different counts.", metric=metric)
    subtracted = tuple(distinct[key] for key in sorted(distinct))

    contained = {(child_id, parent_id) for child_id, parent_id, source in containment_evidence
                 if is_meaningful_provenance(source)}
    uncontained = [c.subject_id for c in subtracted if (c.subject_id, parent.subject_id) not in contained]
    if uncontained:
        return withheld(UNVERIFIED, REASON_CONTAINMENT_NOT_ESTABLISHED,
                        "Containment within the parent is not established by explicit evidence for: "
                        + ", ".join(uncontained) + ".", metric=metric)
    containment_used = tuple(sorted((c.subject_id, parent.subject_id) for c in subtracted))

    pairs = evidenced_pairs(non_overlap_evidence)
    ids = [c.subject_id for c in subtracted]
    overlapping = [(a, b) for index, a in enumerate(ids) for b in ids[index + 1:] if frozenset((a, b)) not in pairs]
    if overlapping:
        return withheld(UNVERIFIED, REASON_CHILD_OVERLAP_NOT_EXCLUDED,
                        "Explicit non-overlap evidence is missing for child pair(s): "
                        + ", ".join(f"{a} / {b}" for a, b in overlapping) + ".", metric=metric)
    non_overlap_used = tuple(sorted((a, b) for index, a in enumerate(ids) for b in ids[index + 1:]))

    consumed = sum(c.exact_value for c in subtracted)
    if consumed > parent.exact_value:
        return withheld(MATERIAL_CONFLICT, REASON_CHILDREN_EXCEED_PARENT,
                        f"The contained child counts ({consumed:,}) exceed the parent ({parent.exact_value:,}); "
                        "no negative residual is produced.", metric=metric)

    # A numeric residual may only stand for the parent's whole relevant child set.
    supplied_ids = frozenset(c.subject_id for c in (*eligible, *(e.child for e in excluded)) if c.subject_id)
    state, detail = _child_set_state(parent, supplied_ids, child_set_evidence)
    if state == "not_established":
        return withheld(UNVERIFIED, REASON_CHILD_SET_NOT_ESTABLISHED,
                        "Completeness of the relevant child set is not established by explicit sourced evidence, "
                        "so no complete residual is stated.", metric=metric, subtracted_children=subtracted)
    if state == "conflict":
        return withheld(UNVERIFIED, REASON_CHILD_SET_CONFLICT,
                        "Child-set evidence for this parent names different sets of child subjects.",
                        metric=metric, subtracted_children=subtracted)
    if state == "mismatch":
        return withheld(UNVERIFIED, REASON_CHILD_SET_MISMATCH,
                        "The supplied children do not match the evidenced child set: " + detail + ".",
                        metric=metric, subtracted_children=subtracted)

    return _result(RESOLVED, REASON_RESOLVED,
                   f"{parent.exact_value:,} minus {consumed:,} contained, non-overlapping operative child subject(s) "
                   "from an evidenced-complete child set.",
                   parent, metric=metric, subtracted_children=subtracted, excluded_children=tuple(excluded),
                   residual_planning_capacity=parent.exact_value - consumed,
                   containment_provenance=containment_used, non_overlap_provenance=non_overlap_used,
                   child_set_completeness=COMPLETENESS_ESTABLISHED, child_set_provenance=detail)

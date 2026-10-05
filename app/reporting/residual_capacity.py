"""Residual planning-capacity safety contract (Stage 2.5 preflight gate 2).

Answers one narrow question: can these trusted planning subjects safely take
part in residual-capacity arithmetic (a parent count minus contained child
counts)? It does NOT create opportunities, rank, persist, render or decide who
could buy anything.

A RESOLVED result means only: residual PLANNING capacity supported by the
current evidence, over the child subjects supplied. It never establishes land
availability, ownership, control, willingness to sell, deliverability, one
coherent parcel or an acquisition package, and it does not establish that the
supplied children are the complete set of subjects consuming the parent
(`child_set_completeness` says so explicitly). There is deliberately no
"available units" field.

Pure and deterministic: inputs are existing Stage 2 CountAssessment values plus
explicit, sourced evidence tuples. Nothing is inferred from shared sites or
addresses, newer or smaller applications, "phase" wording, Reserved Matters
status or related references. Unknown or unsafe stays explicit: when the
arithmetic is not safe no residual is calculated.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.reporting.residential_count import CountAssessment, evidenced_pairs

RESOLVED = "RESOLVED"
UNVERIFIED = "UNVERIFIED"
MATERIAL_CONFLICT = "MATERIAL_CONFLICT"

# Operative-position basis values CountAssessment already carries.
OPERATIVE_APPROVED_BASIS = "consented"

# Reasons (why arithmetic was allowed or withheld).
REASON_RESOLVED = "resolved"
REASON_PARENT_IDENTITY_MISSING = "parent_identity_missing"
REASON_PARENT_NOT_OPERATIVE = "parent_not_operative_approved"
REASON_CHILD_IDENTITY_MISSING = "child_identity_missing"
REASON_CHILD_IS_PARENT = "child_is_parent"
REASON_NO_OPERATIVE_CHILD = "no_operative_child"
REASON_COUNT_MATERIAL_CONFLICT = "count_material_conflict"
REASON_METRIC_MISMATCH = "metric_mismatch"
REASON_UNKNOWN_COUNT = "unknown_count"
REASON_COUNT_NOT_EXACT = "count_not_exact"
REASON_CONFLICTING_DUPLICATE_CHILD = "conflicting_duplicate_child"
REASON_CONTAINMENT_NOT_ESTABLISHED = "containment_not_established"
REASON_CHILD_OVERLAP_NOT_EXCLUDED = "child_overlap_not_excluded"
REASON_CHILDREN_EXCEED_PARENT = "children_exceed_parent"

# Why a supplied child did not consume capacity.
EXCLUDED_NOT_OPERATIVE_APPROVED = "not_operative_approved"

COMPLETENESS_NOT_ESTABLISHED = "not_established"

CLAIM = ("Residual planning capacity supported by current evidence over the supplied child subjects only. "
         "It is not land availability, ownership, control, willingness to sell, deliverability, one coherent "
         "parcel or an acquisition package.")


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
    residual_planning_capacity: int | None = None
    containment_provenance: tuple = ()
    non_overlap_provenance: tuple = ()
    child_set_completeness: str = COMPLETENESS_NOT_ESTABLISHED
    claim: str = CLAIM

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED and self.residual_planning_capacity is not None

    def label(self) -> str:
        if not self.resolved:
            return "Residual planning capacity not established"
        noun = "homes" if self.metric == "total_residential" else (self.metric or "units").replace("_", " ")
        return f"{self.residual_planning_capacity:,} {noun} of residual planning capacity (planning capacity only)"


def _result(status, reason, explanation, parent, **fields) -> ResidualCapacityAssessment:
    return ResidualCapacityAssessment(status=status, reason=reason, explanation=explanation, parent=parent, **fields)


def assess_residual_planning_capacity(parent: CountAssessment, children, *, containment_evidence=(),
                                      non_overlap_evidence=()) -> ResidualCapacityAssessment:
    """Parent count minus contained child counts, only when every safety gate holds.

    containment_evidence: iterable of (child_subject_id, parent_subject_id, provenance).
    non_overlap_evidence: iterable of (subject_id, subject_id, provenance) - the same
    pair contract and rule as phase aggregation (evidenced_pairs): no provenance, no evidence.
    Both are explicit evidence supplied by the caller; this function never invents either.
    """
    children = tuple(children)
    containment_evidence = tuple(containment_evidence)
    non_overlap_evidence = tuple(non_overlap_evidence)

    if not parent.subject_id:
        return _result(UNVERIFIED, REASON_PARENT_IDENTITY_MISSING,
                       "The parent has no subject identity, so containment cannot be established.", parent)
    if parent.basis != OPERATIVE_APPROVED_BASIS:
        return _result(UNVERIFIED, REASON_PARENT_NOT_OPERATIVE,
                       "The parent count is not an operative approved position, so it cannot supply capacity.", parent)

    # Only operative approved children can consume approved capacity. Refused,
    # withdrawn, pending and pending-variation values never do.
    eligible: list[CountAssessment] = []
    excluded: list[ExcludedChild] = []
    for child in children:
        if child.basis != OPERATIVE_APPROVED_BASIS:
            excluded.append(ExcludedChild(child, EXCLUDED_NOT_OPERATIVE_APPROVED))
            continue
        if not child.subject_id:
            return _result(UNVERIFIED, REASON_CHILD_IDENTITY_MISSING,
                           "An operative child has no subject identity, so containment cannot be established.",
                           parent, excluded_children=tuple(excluded))
        if child.subject_id == parent.subject_id:
            return _result(UNVERIFIED, REASON_CHILD_IS_PARENT,
                           "A subject cannot be its own child.", parent, excluded_children=tuple(excluded))
        eligible.append(child)

    def withheld(status, reason, explanation, **fields):
        return _result(status, reason, explanation, parent, excluded_children=tuple(excluded), **fields)

    # Material conflicts are preserved, never averaged or resolved by arithmetic.
    if parent.resolution == "material_conflict" or any(c.resolution == "material_conflict" for c in eligible):
        return withheld(MATERIAL_CONFLICT, REASON_COUNT_MATERIAL_CONFLICT,
                        "A parent or child count is an unresolved material conflict; no residual is calculated.")
    if not eligible:
        return withheld(UNVERIFIED, REASON_NO_OPERATIVE_CHILD,
                        "No operative approved child subject was supplied, so no residual is derived.")

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

    contained = {(child_id, parent_id) for child_id, parent_id, source in containment_evidence if source}
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

    return _result(RESOLVED, REASON_RESOLVED,
                   f"{parent.exact_value:,} minus {consumed:,} contained, non-overlapping operative child subject(s).",
                   parent, metric=metric, subtracted_children=subtracted, excluded_children=tuple(excluded),
                   residual_planning_capacity=parent.exact_value - consumed,
                   containment_provenance=containment_used, non_overlap_provenance=non_overlap_used)

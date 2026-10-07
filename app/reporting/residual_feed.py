"""Stage 2.5B V8-B: wiring of the pure residual ladder (app.reporting.residual_opportunity) to the buyer-family feed. No database access of its own, no schema, no model.

Inputs are the per-site ``OperativePlanningFacts`` the feed already computed (one batched read; nothing is re-read here). For each site with an operative
approved WHOLE-SITE parent count and operative approved PHASE child counts it qualifies the residual with the PRODUCTION evidence only: G2 containment
(``derive_containment``). Completeness and non-overlap have no production producer, so production yields R2 or R3 and never R1 (dormant by evidence).
``evidence_provider`` is the single injection point a qualified (Stage 2.6) producer - or a test - uses to supply further provenance-bearing evidence.
"""
from __future__ import annotations

from app.reporting.residual_opportunity import (
    LEVEL_R1, LEVEL_R2, NO_EVIDENCE, ResidualEvidence, qualify_residual,
)
from app.reporting.scheme_reconciliation import SCOPE_PHASE, scoped_count_assessment
from app.reporting.subject_relationships import derive_containment


def _children_for(operative):
    """Operative approved PHASE child counts of one site (one per distinct phase scope), with their applications."""
    scopes = {}
    for resolved in operative.resolved_applications:
        if resolved.scope_type == SCOPE_PHASE:
            scopes.setdefault(resolved.scope_label, []).append(resolved.application)
    children = []
    for label in sorted(scopes):
        assessment = scoped_count_assessment(scopes[label], SCOPE_PHASE, label)
        if assessment is not None and assessment.basis == "consented":
            children.append(assessment)
    return children


def build_site_residuals(operative_by_site: dict, evidence_provider=None) -> dict:
    """``{site_id: ResidualQualification}`` for sites that have a parent and at least one operative phase child. ``evidence_provider(site_id, parent, children)`` may
    return additional ``ResidualEvidence`` (default: none). Production passes none."""
    out = {}
    for site_id, operative in operative_by_site.items():
        position = operative.consented_position
        parent = position.approved_units.count_assessment if position.exists else None
        if parent is None or not parent.subject_id:
            continue
        children = _children_for(operative)
        if not children:
            continue
        pairs = []
        for child in children:
            result = derive_containment(child, [parent], operative.resolved_applications)
            if result.relationship is not None:
                pairs.append((result.relationship.child_subject_id, result.relationship.parent_subject_id,
                              f"{result.relationship.basis}: {result.relationship.provenance}"))
        evidence = ResidualEvidence(containment=tuple(pairs))
        if evidence_provider is not None:
            extra = evidence_provider(site_id, parent, children) or NO_EVIDENCE
            evidence = ResidualEvidence(containment=evidence.containment + tuple(extra.containment), non_overlap=tuple(extra.non_overlap),
                                        child_set=tuple(extra.child_set))
        out[int(site_id)] = qualify_residual(parent, children, evidence)
    return out


def residual_levels(residuals: dict) -> dict:
    counts = {LEVEL_R1: 0, LEVEL_R2: 0}
    for q in residuals.values():
        if q.level in counts:
            counts[q.level] += 1
    return counts

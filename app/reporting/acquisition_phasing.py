"""Stage 2.5B V7A: the ONE pure derivation of planning-delivery ACQUISITION phasing evidence (spec 025, "V7A").

Operates only on already-loaded site applications and the Site row - no database call, no model call, no persistence. It is the single source of truth consumed by the
context builders (-> B2MatchingContext.acquisition_phasing -> assess_buyer_fit reasons, the agent-evaluation fingerprint) and by the Slice 2 presentation label; the rule is
deliberately NOT duplicated anywhere else.

A named phase (established from the application PROPOSAL scope - an address-only label never qualifies) counts as CURRENT evidence only if ALL hold: it is a genuine named phase scope (kind "phase", never the unphased bucket); it has a SUBSTANTIVE GRANTED anchor
(refused / withdrawn / undecided / recommendation-only / non-substantive-only - conditions or non-material amendments - groups never qualify); and the existing accepted lapse
model does not classify it as `lapsed` (an ASSUMED three-year date with implementation unverified - this is not legal certainty). A granted phase that is assumed-lapsed is
HISTORICAL evidence only; one whose operative decision date is missing or unparseable is PHASE_EVIDENCE_CURRENTNESS_UNKNOWN (neither current nor historical). A phase is evidence that phased delivery exists - never availability, disposal intent, ownership, residual capacity, non-overlap or another phase.

Known limits of today's evidence (documented, not hidden): replacement/abandonment of a phase consent by a differently-scoped later application and true lapse cannot be detected;
phase labels come from proposal/address text (extract_phase_labels). DOCUMENTED_PHASING is reserved for Stage 2.6 qualified evidence and is never produced here.
"""
from __future__ import annotations

from app.pipeline.lapse_tracking import compute_lapse_status
from app.pipeline.phase_tracking import UNPHASED_LABEL, compute_phase_progress, extract_phase_labels
from app.policy.buyer_matching import (
    PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, AcquisitionPhasingEvidence,
)

LAPSED = "lapsed"
CURRENTNESS_UNKNOWN_STATUS = "unknown"   # compute_lapse_status: the operative decision date is missing / unparseable


def phasing_state_of(evidence):
    """The state string of a derived fact, or None when the fact was not supplied."""
    return None if evidence is None else evidence.state


def is_current_evidenced_phase(evidence) -> bool:
    """True only for CURRENT_EVIDENCED_PHASE - the one predicate the presentation label uses (never re-derived there)."""
    return evidence is not None and evidence.state == PHASING_CURRENT_EVIDENCED_PHASE


def _proposal_phase_groups(applications) -> dict:
    """Named phase scopes established from the application PROPOSAL scope only. Address text alone never establishes a phase for acquisition-phasing evidence (it may remain
    supporting/display context elsewhere); an application naming several phases attaches to each, as in the detectors' own grouping."""
    groups: dict[tuple[str, str], list] = {}
    for application in applications:
        for code, kind in extract_phase_labels(application.proposal):
            groups.setdefault((code, kind), []).append(application)
    return groups


def derive_acquisition_phasing_evidence(applications, site) -> AcquisitionPhasingEvidence:
    """CURRENT_EVIDENCED_PHASE > PHASE_EVIDENCE_CURRENTNESS_UNKNOWN > HISTORICAL_PHASE_ONLY > NONE_IDENTIFIED for one site's applications (exact predicate: module docstring).

    Per qualifying phase (named in a proposal, substantive granted anchor): `lapsed` -> historical; an undated / unparseable operative decision date (lapse status `unknown`)
    -> currentness UNKNOWN (never current, and never historical merely because the date is missing); everything else -> current. The site-level precedence is deterministic and
    safe: an unknown-currentness phase can never be downgraded to history by a sibling, nor upgraded to current."""
    if site is None:                                     # currency cannot be verified without the Site row: nothing is claimed
        return AcquisitionPhasingEvidence(PHASING_NONE_IDENTIFIED)
    current = unknown = historical = False
    for (code, kind), phase_applications in _proposal_phase_groups(list(applications)).items():
        if kind != "phase" or code == UNPHASED_LABEL:
            continue
        if compute_phase_progress(phase_applications)["latest_grant"] is None:      # no substantive GRANTED anchor in this scope
            continue
        status = compute_lapse_status(phase_applications, site).get("status")
        if status == LAPSED:
            historical = True
        elif status == CURRENTNESS_UNKNOWN_STATUS:
            unknown = True
        else:
            current = True
    if current:
        return AcquisitionPhasingEvidence(PHASING_CURRENT_EVIDENCED_PHASE)
    if unknown:
        return AcquisitionPhasingEvidence(PHASING_CURRENTNESS_UNKNOWN)
    return AcquisitionPhasingEvidence(PHASING_HISTORICAL_ONLY if historical else PHASING_NONE_IDENTIFIED)


def subject_scope_for_feed_card(card) -> tuple[str | None, bool]:
    """(subject_phase_scope_key, subject_application_anchored) for a feed card - the explicit self-scope guard inputs. A named phase card is its own phase scope; the unphased bucket is
    the wider scope (no key); recent-permission / long-pending subjects are application-anchored; everything else is a wider whole-site subject."""
    card_id = str(card.get("id") or "")
    if card_id.startswith("opp-phase-"):
        code = card.get("phase_code")
        return (None if code in (None, UNPHASED_LABEL) else str(code)), False
    return None, card_id.startswith(("opp-recent-permission-", "opp-long-pending-"))


def subject_scope_for_opportunity_id(opportunity_id: str) -> tuple[str | None, bool]:
    """The same guard inputs from an opportunity-universe id (planning_delivery:{kind}:{site}[:{phase_code}])."""
    parts = opportunity_id.split(":", 3)
    kind = parts[1] if len(parts) > 1 else ""
    if kind == "phase":
        code = parts[3] if len(parts) > 3 else None
        return (None if code in (None, UNPHASED_LABEL) else code), False
    return None, kind in ("recent_permission", "long_pending_application")

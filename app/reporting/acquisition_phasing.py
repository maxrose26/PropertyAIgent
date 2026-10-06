"""Stage 2.5B V7A: the ONE pure derivation of planning-delivery ACQUISITION phasing evidence (spec 025, "V7A").

Operates only on already-loaded site applications and the Site row - no database call, no model call, no persistence. It is the single source of truth consumed by the
context builders (-> B2MatchingContext.acquisition_phasing -> assess_buyer_fit reasons, the agent-evaluation fingerprint) and by the Slice 2 presentation label; the rule is
deliberately NOT duplicated anywhere else.

A named phase counts as CURRENT evidence only if ALL hold: it is a genuine named phase scope (kind "phase", never the unphased bucket); it has a SUBSTANTIVE GRANTED anchor
(refused / withdrawn / undecided / recommendation-only / non-substantive-only - conditions or non-material amendments - groups never qualify); and the existing accepted lapse
model does not classify it as `lapsed` (an ASSUMED three-year date with implementation unverified - this is not legal certainty). A granted phase that is assumed-lapsed is
HISTORICAL evidence only. A phase is evidence that phased delivery exists - never availability, disposal intent, ownership, residual capacity, non-overlap or another phase.

Known limits of today's evidence (documented, not hidden): replacement/abandonment of a phase consent by a differently-scoped later application and true lapse cannot be detected;
phase labels come from proposal/address text (extract_phase_labels). DOCUMENTED_PHASING is reserved for Stage 2.6 qualified evidence and is never produced here.
"""
from __future__ import annotations

from app.pipeline.lapse_tracking import compute_lapse_status
from app.pipeline.phase_tracking import UNPHASED_LABEL, compute_phase_progress, group_applications_by_phase
from app.policy.buyer_matching import (
    PHASING_CURRENT_EVIDENCED_PHASE, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, AcquisitionPhasingEvidence,
)

LAPSED = "lapsed"


def is_current_evidenced_phase(evidence) -> bool:
    """True only for CURRENT_EVIDENCED_PHASE - the one predicate the presentation label uses (never re-derived there)."""
    return evidence is not None and evidence.state == PHASING_CURRENT_EVIDENCED_PHASE


def derive_acquisition_phasing_evidence(applications, site) -> AcquisitionPhasingEvidence:
    """CURRENT_EVIDENCED_PHASE > HISTORICAL_PHASE_ONLY > NONE_IDENTIFIED for one site's applications (see the module docstring for the exact predicate)."""
    if site is None:                                     # currency cannot be verified without the Site row: nothing is claimed
        return AcquisitionPhasingEvidence(PHASING_NONE_IDENTIFIED)
    current = historical = False
    for (code, kind), phase_applications in group_applications_by_phase(list(applications)).items():
        if kind != "phase" or code == UNPHASED_LABEL:
            continue
        if compute_phase_progress(phase_applications)["latest_grant"] is None:      # no substantive GRANTED anchor in this scope
            continue
        if compute_lapse_status(phase_applications, site).get("status") == LAPSED:
            historical = True
        else:
            current = True
    if current:
        return AcquisitionPhasingEvidence(PHASING_CURRENT_EVIDENCED_PHASE)
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

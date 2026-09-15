"""Agent Evaluation Policy V1 - tests for app.policy.agent_evaluation_
prompt.compute_ownership_control_posture() and the governing-policy text
introduced by the Final Pre-Release Ownership & Stability Patch.

Pure, DB-free - compute_ownership_control_posture is a pure function over
already-computed packet fields; the GOVERNING_POLICY checks are plain
string-membership assertions (this module never re-implements an LLM to
test prompt wording)."""
from __future__ import annotations

from dataclasses import dataclass

from app.policy.agent_evaluation_prompt import (
    GOVERNING_POLICY,
    OWNERSHIP_CONTROL_ESTABLISHED_SAME_SUBJECT_CONTROL,
    OWNERSHIP_CONTROL_EVIDENCED_CONFLICT_POTENTIALLY_BLOCKING,
    OWNERSHIP_CONTROL_INCOMPLETE_NON_BLOCKING,
    compute_ownership_control_posture,
)


@dataclass
class _FakeActorsControl:
    developer_indications: tuple = ()
    ownership_coverage: str | None = None
    conflicts: tuple = ()
    has_ownership_evidence: bool = False


@dataclass
class _FakePacket:
    actors_control: _FakeActorsControl
    development_state_scope_verified: bool = False


def test_no_evidence_no_conflict_is_incomplete_non_blocking():
    packet = _FakePacket(actors_control=_FakeActorsControl(has_ownership_evidence=False, conflicts=()))
    assert compute_ownership_control_posture(packet) == OWNERSHIP_CONTROL_INCOMPLETE_NON_BLOCKING


def test_conflict_present_is_evidenced_conflict_regardless_of_scope():
    packet = _FakePacket(
        actors_control=_FakeActorsControl(has_ownership_evidence=True, conflicts=("Conflicting developer evidence.",)),
        development_state_scope_verified=True,
    )
    assert compute_ownership_control_posture(packet) == OWNERSHIP_CONTROL_EVIDENCED_CONFLICT_POTENTIALLY_BLOCKING


def test_ownership_evidence_with_verified_scope_is_established_same_subject():
    packet = _FakePacket(
        actors_control=_FakeActorsControl(has_ownership_evidence=True, conflicts=()),
        development_state_scope_verified=True,
    )
    assert compute_ownership_control_posture(packet) == OWNERSHIP_CONTROL_ESTABLISHED_SAME_SUBJECT_CONTROL


def test_ownership_evidence_with_unverified_scope_stays_incomplete():
    """The core scope-preservation guarantee: evidence exists, but is not
    confirmed to apply to THIS opportunity's own scope (e.g. a named phase
    where site-wide developer evidence may belong to a different phase) -
    must never be promoted to ESTABLISHED_SAME_SUBJECT_CONTROL."""
    packet = _FakePacket(
        actors_control=_FakeActorsControl(has_ownership_evidence=True, conflicts=()),
        development_state_scope_verified=False,
    )
    assert compute_ownership_control_posture(packet) == OWNERSHIP_CONTROL_INCOMPLETE_NON_BLOCKING


def test_no_evidence_with_verified_scope_stays_incomplete():
    packet = _FakePacket(
        actors_control=_FakeActorsControl(has_ownership_evidence=False, conflicts=()),
        development_state_scope_verified=True,
    )
    assert compute_ownership_control_posture(packet) == OWNERSHIP_CONTROL_INCOMPLETE_NON_BLOCKING


# --- Governing policy text: role separation, posture, NOT_RELEVANT --------

def test_governing_policy_states_role_separation():
    text = GOVERNING_POLICY
    assert "LANDOWNER" in text and "PROMOTER" in text and "APPLICANT" in text
    assert "DEVELOPER" in text and "CONTROLLER" in text
    assert "never assumed to control Phase 2" in text or "never control Phase 2" in text.replace(
        "never assumed to control Phase 2 or the wider allocation", "never control Phase 2"
    )


def test_governing_policy_defines_ownership_control_posture_values():
    for value in (
        OWNERSHIP_CONTROL_INCOMPLETE_NON_BLOCKING,
        OWNERSHIP_CONTROL_EVIDENCED_CONFLICT_POTENTIALLY_BLOCKING,
        OWNERSHIP_CONTROL_ESTABLISHED_SAME_SUBJECT_CONTROL,
    ):
        assert value in GOVERNING_POLICY


def test_governing_policy_forbids_developer_identity_alone_for_not_relevant():
    lowered = GOVERNING_POLICY.lower()
    assert "known developer" in lowered
    assert "national housebuilder" in lowered
    assert "never sufficient alone for not_relevant" in lowered or "alone is never sufficient" in lowered or "never, individually or combined" in lowered


def test_governing_policy_forbids_unsupported_availability_claims_about_developer():
    normalized = " ".join(GOVERNING_POLICY.split())
    for phrase in ("will develop the site", "is unavailable", "will not sell", "unwilling to sell", "transaction is impossible"):
        assert phrase in normalized


def test_governing_policy_addresses_phase_scope_for_developer_evidence():
    text = GOVERNING_POLICY
    assert "Phase 1" in text and "Phase 2" in text
    assert "WHOLE_ALLOCATION" in text


def test_ownership_control_posture_reference_token_key_is_flat_not_dotted():
    """Regression for a real live-calibration finding: a dotted token name
    (the original "posture.ownership_control") was blended by the model
    with the visually-adjacent packet.actors_control.* tokens into a
    hallucinated, non-existent reference ("packet.actors_control.posture.
    ownership_control"), which then survived the bounded repair retry
    unchanged. The token key must stay a flat, dot-free identifier
    matching the prose name (OWNERSHIP_CONTROL_POSTURE) exactly."""
    import inspect

    from app.policy import agent_evaluation_prompt

    source = inspect.getsource(agent_evaluation_prompt.build_prompt_context)
    assert 'reference_tokens["ownership_control_posture"]' in source
    assert 'reference_tokens["posture.ownership_control"]' not in source
    assert 'reference_tokens["packet.actors_control.posture' not in source


# --- Recommendation Taxonomy V2 (Product Owner Implementation Gate) --------

def test_governing_policy_uses_investigate_not_verify_as_a_recommendation():
    """Every bare "VERIFY" occurrence must be immediately followed by "_"
    (part of a VERIFY_* next_action name, e.g. VERIFY_OWNERSHIP) - VERIFY
    must never stand alone as a recommendation-layer word."""
    import re

    for match in re.finditer("VERIFY(.)", GOVERNING_POLICY):
        assert match.group(1) == "_", f"bare VERIFY found, not part of a VERIFY_* name: ...{GOVERNING_POLICY[max(0, match.start()-40):match.start()+40]}..."
    assert "INVESTIGATE" in GOVERNING_POLICY
    assert "PURSUE / INVESTIGATE / MONITOR /" in GOVERNING_POLICY or "PURSUE/INVESTIGATE/MONITOR" in GOVERNING_POLICY.replace(" ", "")


def test_governing_policy_teaches_verify_action_does_not_imply_investigate():
    lowered = GOVERNING_POLICY.lower()
    assert "next_action named verify_*" in lowered or "a verify_* next_action" in lowered
    assert "never by itself impl" in lowered or "never implies" in lowered


def test_governing_policy_teaches_commercial_counterparty_principle():
    assert "COMMERCIAL COUNTERPARTY PRINCIPLE" in GOVERNING_POLICY
    normalized = " ".join(GOVERNING_POLICY.split()).lower()
    assert "commercially actionable counterparty" in normalized or "commercially relevant counterparty" in normalized
    assert "without establishing legal ownership or control" in normalized


def test_governing_policy_teaches_lifecycle_aware_ownership_significance():
    normalized = " ".join(GOVERNING_POLICY.split()).lower()
    assert "early strategic allocation" in normalized
    assert "active planning application" in normalized or "permissioned site" in normalized


def test_governing_policy_teaches_planning_outcome_does_not_establish_control():
    assert "PLANNING OUTCOME DOES NOT ESTABLISH LAND CONTROL" in GOVERNING_POLICY
    normalized = " ".join(GOVERNING_POLICY.split()).lower()
    assert "refused" in normalized
    assert "never tells you whether the applicant" in normalized or "never establish" in normalized


def test_governing_policy_teaches_parcel_tbd_does_not_mean_investigate():
    assert "PARCEL_TBD DOES NOT MEAN INVESTIGATE" in GOVERNING_POLICY


def test_governing_policy_teaches_scope_safe_application_vs_allocation_inference():
    normalized = " ".join(GOVERNING_POLICY.split())
    assert "2,000-home" in normalized
    normalized_lower = normalized.lower()
    assert "application/parcel-level involvement" in normalized_lower
    assert "allocation-level control" in normalized_lower

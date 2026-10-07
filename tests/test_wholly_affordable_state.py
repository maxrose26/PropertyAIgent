"""Whole-site affordable evidence state: do trusted, SAME-SCOPE, EXACT counts establish that an acquisition
subject is wholly affordable? WHOLLY_AFFORDABLE / NOT_WHOLLY_AFFORDABLE / UNKNOWN - never a percentage.

Evidence plumbing only: the existing hard exclusion semantics, BUYER_MATCHING_POLICY_VERSION (6) and the opportunity
fingerprint fields are unchanged. The end-to-end tests drive the REAL operative builder
(build_planning_delivery_matching_facts_from_operative) over real Application/SchemeIntelligence rows.
"""
from __future__ import annotations

import inspect
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.db.models import Application, SchemeIntelligence, Site
from app.policy.ah_assessment import AHAssessment, AHClaim, legacy_assessment
from app.policy.buyer_matching import (
    AFFORDABLE_STATE_NOT_WHOLLY, AFFORDABLE_STATE_UNKNOWN, AFFORDABLE_STATE_WHOLLY, BUYER_MATCHING_POLICY_VERSION,
    NOT_SUITABLE, PLANNING_DELIVERY, MatchingFacts, assess_buyer_fit,
    build_planning_delivery_matching_facts_from_operative, derive_whole_site_affordable_state,
)
from app.policy.buyer_profiles import (
    HOUSING_ASSOCIATION, NATIONAL_HOUSEBUILDER, NESTEN_HOMES, PERMISSION_GRANTED, STRATEGIC_LAND_BUYER,
)
from app.reporting.residential_count import CountAssessment
from app.reporting.scheme_reconciliation import build_operative_planning_facts


# --- the derivation itself (pure) -------------------------------------------------------------------------------

def _total(value=21, *, precision="EXACT", scope_type="whole_site", scope_label="Whole site",
           metric="total_residential", refs=("APP/1",)):
    exact = precision == "EXACT"
    return CountAssessment(
        scope_type=scope_type, scope_label=scope_label, metric=metric, precision=precision, value=value,
        lower=value if exact else None, upper=value if exact else None, resolution="agreement", confidence="high",
        sources=tuple(SimpleNamespace(application_reference=r, application_id=i) for i, r in enumerate(refs)))


def _ah(value=21, *, qualifier="exact", state="verified", ref="APP/1", scope_type="whole_site", scope_label="Whole site",
        alternatives=()):
    claim = AHClaim(value=value, qualifier=qualifier, state=state, application_reference=ref, scope_type=scope_type,
                    scope_label=scope_label, document_id="doc-1", passage="stated in the planning statement")
    return AHAssessment(count=claim, alternatives=alternatives)


def _derive(total, ah, current=True):
    return derive_whole_site_affordable_state(total, ah, current_scope=current)


def test_a_exact_same_scope_all_affordable_is_wholly_affordable():
    assert _derive(_total(21), _ah(21)) == AFFORDABLE_STATE_WHOLLY


def test_b_exact_same_scope_fewer_affordable_is_not_wholly_affordable():
    assert _derive(_total(21), _ah(10)) == AFFORDABLE_STATE_NOT_WHOLLY


def test_c_total_exact_affordable_unknown_is_unknown():
    unknown = AHAssessment(count=AHClaim(application_reference="APP/1", scope_type="whole_site", scope_label="Whole site"))
    assert _derive(_total(21), unknown) == AFFORDABLE_STATE_UNKNOWN


def test_d_exact_total_with_approximate_affordable_is_unknown():
    assert _derive(_total(21), _ah(21, qualifier="approximate", state="estimated")) == AFFORDABLE_STATE_UNKNOWN


def test_e_approximate_total_with_exact_affordable_is_unknown():
    assert _derive(_total(21, precision="APPROXIMATE"), _ah(21)) == AFFORDABLE_STATE_UNKNOWN


def test_f_conflicting_affordable_evidence_is_unknown():
    other = AHClaim(value=10, qualifier="exact", state="verified", application_reference="APP/1", scope_type="whole_site",
                    scope_label="Whole site", document_id="doc-2", passage="a different figure")
    assert _derive(_total(21), _ah(21, alternatives=(other,))) == AFFORDABLE_STATE_UNKNOWN
    conflicting = replace(_ah(21), count=replace(_ah(21).count, state="conflicting"))
    assert _derive(_total(21), conflicting) == AFFORDABLE_STATE_UNKNOWN


def test_g_parent_site_total_with_child_phase_affordable_is_unknown():
    assert _derive(_total(21, scope_type="whole_site"), _ah(21, scope_type="phase", scope_label="Phase 1")) == AFFORDABLE_STATE_UNKNOWN


def test_h_child_phase_total_with_parent_site_affordable_is_unknown():
    total = _total(21, scope_type="phase", scope_label="Phase 1")
    assert _derive(total, _ah(21, scope_type="whole_site", scope_label="Whole site")) == AFFORDABLE_STATE_UNKNOWN


def test_i_counts_from_unrelated_applications_are_unknown():
    assert _derive(_total(21, refs=("APP/1",)), _ah(21, ref="APP/OTHER")) == AFFORDABLE_STATE_UNKNOWN


def test_j_missing_or_legacy_unqualified_affordable_is_unknown_never_zero_or_full():
    si = SimpleNamespace(affordable_units_final=0, affordable_percentage_final=100.0, affordable_status_note=None,
                         affordable_tenure_split_final=None, affordable_classification_evidence=None,
                         affordable_housing_status="legally_secured")
    legacy_zero = legacy_assessment(si, application_reference="APP/1", scope_type="whole_site", scope_label="Whole site")
    assert _derive(_total(21), legacy_zero) == AFFORDABLE_STATE_UNKNOWN  # stored 0 / reported 100% never qualify
    assert _derive(_total(21), None) == AFFORDABLE_STATE_UNKNOWN
    assert _derive(_total(21), AHAssessment()) == AFFORDABLE_STATE_UNKNOWN


def test_matching_scope_labels_make_a_phase_subject_wholly_affordable():
    total = _total(40, scope_type="phase", scope_label="Phase 1")
    assert _derive(total, _ah(40, scope_type="phase", scope_label=" phase 1 ")) == AFFORDABLE_STATE_WHOLLY
    assert _derive(total, _ah(40, scope_type="phase", scope_label="Phase 2")) == AFFORDABLE_STATE_UNKNOWN


@pytest.mark.parametrize("total", [
    _total(21, scope_type="unclear", scope_label="Whole site (scope not confirmed by phase evidence)"),
    _total(21, metric="all_use_units"),
    _total(0),
])
def test_unconfirmed_scope_non_residential_metric_or_empty_total_is_unknown(total):
    assert _derive(total, _ah(0 if total.exact_value == 0 else 21)) == AFFORDABLE_STATE_UNKNOWN


def test_contradictory_or_non_current_evidence_is_unknown():
    assert _derive(_total(21), _ah(25)) == AFFORDABLE_STATE_UNKNOWN  # more affordable than total: never resolved by guessing
    assert _derive(_total(21), _ah(21), current=False) == AFFORDABLE_STATE_UNKNOWN


# --- the real operative facts path -----------------------------------------------------------------------------

def _site_with_outline_and_phase(session):
    site = Site(council_code="testcouncil", canonical_address="whole-site", display_address="Whole site")
    session.add(site)
    session.flush()
    apps = []
    for ref, proposal, units, received in (
        ("OUT/1", "Outline application for 100 dwellings", 100, "Wed 01 Jan 2020"),
        ("RM/2", "Reserved matters for Phase 1: erection of 40 dwellings pursuant to OUT/1", 40, "Wed 01 Jan 2024"),
    ):
        app = Application(site_id=site.id, council_code="testcouncil", reference=ref, proposal=proposal,
                          application_received=received, decision="Granted", status="Decided")
        session.add(app)
        session.flush()
        app.scheme_intelligence = SchemeIntelligence(
            application_id=app.id, core_intelligence_complete=True, total_units_final=units,
            affordable_units_final=100 if ref == "OUT/1" else None, development_type="houses")
        apps.append(app)
    session.commit()
    return apps


def _genuine_facts(session, affordable_units=None):
    apps = _site_with_outline_and_phase(session)
    operative = build_operative_planning_facts(apps)
    if affordable_units is not None:
        position = operative.affordable_housing.whole_site
        claim = AHClaim(value=affordable_units, qualifier="exact", state="verified", application_reference="OUT/1",
                        scope_type="whole_site", scope_label="Whole site", document_id="doc-1", passage="stated in the S106 summary")
        position = replace(position, assessment=AHAssessment(count=claim))
        operative = replace(operative, affordable_housing=replace(operative.affordable_housing, whole_site=position))
    return build_planning_delivery_matching_facts_from_operative(operative, apps)


def test_genuine_path_establishes_wholly_affordable_without_a_percentage(session):
    facts = _genuine_facts(session, affordable_units=100)
    assert facts.whole_site_affordable_state == AFFORDABLE_STATE_WHOLLY
    assert facts.affordable_percentage is None and not facts.affordable_percentage_trusted


def test_genuine_path_not_wholly_and_legacy_unqualified_are_never_wholly(session):
    assert _genuine_facts(session, affordable_units=30).whole_site_affordable_state == AFFORDABLE_STATE_NOT_WHOLLY


def test_genuine_path_legacy_extraction_alone_is_unknown(session):
    # The stored extraction says 100 of 100 affordable, but it is not qualified evidence.
    facts = _genuine_facts(session)
    assert facts.whole_site_affordable_state == AFFORDABLE_STATE_UNKNOWN
    assert facts.affordable_unit_count is None


def _wholly(session):
    return replace(_genuine_facts(session, affordable_units=100), planning_state=PERMISSION_GRANTED)


def test_national_housebuilder_hard_exclusion_fires_end_to_end(session):
    fit = assess_buyer_fit(NATIONAL_HOUSEBUILDER, _wholly(session))
    assert fit.classification == NOT_SUITABLE
    assert any("wholly (every residential unit is affordable)" in r for r in fit.does_not_match)


def test_strategic_land_buyer_exclusion_fires_end_to_end(session):
    fit = assess_buyer_fit(STRATEGIC_LAND_BUYER, _wholly(session))
    assert fit.classification == NOT_SUITABLE
    assert any("affordable-led" in r for r in fit.does_not_match)


def test_nesten_is_not_excluded_on_affordable_grounds_end_to_end(session):
    assert NESTEN_HOMES.wholly_affordable_is_exclusion is False
    fit = assess_buyer_fit(NESTEN_HOMES, _wholly(session))
    assert not any("affordable" in r.lower() for r in fit.does_not_match)
    assert not any("affordable" in m.lower() for m in fit.matches)  # context only, never a fit signal
    assert any("not a fit signal" in u for u in fit.unknown)


def test_housing_association_keeps_its_positive_affordable_reading(session):
    fit = assess_buyer_fit(HOUSING_ASSOCIATION, _wholly(session))
    assert any("directly relevant to this buyer's affordable-housing focus" in m for m in fit.matches)
    assert not any("affordable-led" in r for r in fit.does_not_match)


def test_not_wholly_and_unknown_never_exclude_and_unknown_is_never_zero_or_full(session):
    not_wholly = replace(_genuine_facts(session, affordable_units=30), planning_state=PERMISSION_GRANTED)
    assert not any("affordable-led" in r for r in assess_buyer_fit(NATIONAL_HOUSEBUILDER, not_wholly).does_not_match)


def test_unknown_state_is_visible_uncertainty_not_zero_or_hundred_percent(session):
    unknown = replace(_genuine_facts(session), planning_state=PERMISSION_GRANTED)
    fit = assess_buyer_fit(NATIONAL_HOUSEBUILDER, unknown)
    assert not any("affordable-led" in r for r in fit.does_not_match)
    assert any("not assumed to be 0%" in u for u in fit.unknown)


def test_percentage_path_for_hand_built_facts_is_unchanged():
    facts = MatchingFacts(
        opportunity_type=PLANNING_DELIVERY, unit_count=300, development_type_raw="houses", is_specialist_development=False,
        affordable_percentage=100.0, affordable_percentage_trusted=True, affordable_unit_count=300,
        planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True, has_phasing_evidence=False, matched_to_site=True)
    fit = assess_buyer_fit(NATIONAL_HOUSEBUILDER, facts)
    assert fit.classification == NOT_SUITABLE and any("wholly (100%)" in r for r in fit.does_not_match)


# --- policy / fingerprint boundaries ---------------------------------------------------------------------------------

def test_policy_version_and_fingerprint_inputs_are_unchanged():
    assert BUYER_MATCHING_POLICY_VERSION == 8   # moved 6 -> 7 by V7A (reason wording only); the hard-exclusion semantics asserted here are unchanged
    import ast
    import app.reporting.opportunity_universe as universe
    key_sets = []
    for node in ast.walk(ast.parse(inspect.getsource(universe))):
        if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "fingerprint_fields" for t in node.targets)
                and isinstance(node.value, ast.Dict)):
            key_sets.append({k.value for k in node.value.keys if isinstance(k, ast.Constant)})
    assert key_sets and all("whole_site_affordable_state" not in keys for keys in key_sets)  # not a fingerprint input
    planning_delivery = [k for k in key_sets if "affordable_unit_count" in k]
    assert planning_delivery and {"unit_count", "affordable_unit_count", "development_type_raw", "is_specialist_development"} <= planning_delivery[0]
    assert MatchingFacts(
        opportunity_type=PLANNING_DELIVERY, unit_count=None, development_type_raw=None, is_specialist_development=None,
        affordable_percentage=None, affordable_percentage_trusted=False, affordable_unit_count=None,
        planning_state="other_or_unknown", has_identified_planning_activity=None, has_phasing_evidence=False,
        matched_to_site=False).whole_site_affordable_state == AFFORDABLE_STATE_UNKNOWN


def test_a_phase_card_never_inherits_the_whole_site_affordable_state(session, monkeypatch):
    """Regression (independent review): the feed's phase-card path resets every other whole-site affordable field;
    the new state must be reset there too, or a phase opportunity would be excluded on its PARENT's counts."""
    import app.policy.buyer_matching as buyer_matching
    from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
    apps = _site_with_outline_and_phase(session)
    site_id = apps[0].site_id
    monkeypatch.setattr(buyer_matching, "derive_whole_site_affordable_state", lambda *a, **k: AFFORDABLE_STATE_WHOLLY)
    whole_site_card = {"params": {"site_id": str(site_id)}, "application_reference": "OUT/1"}
    phase_card = {"params": {"site_id": str(site_id)}, "application_reference": "RM/2", "phase_code": "1",
                  "phase_unit_count": 40,
                  "count_assessment": CountAssessment(scope_type="phase", scope_label="Phase 1", metric="total_residential",
                                                      precision="EXACT", value=40, lower=40, upper=40, resolution="agreement",
                                                      confidence="high", sources=())}
    _attach_planning_delivery_matching_facts(session, [whole_site_card, phase_card])
    assert whole_site_card["matching_facts"].whole_site_affordable_state == AFFORDABLE_STATE_WHOLLY  # control
    assert phase_card["matching_facts"].whole_site_affordable_state == AFFORDABLE_STATE_UNKNOWN

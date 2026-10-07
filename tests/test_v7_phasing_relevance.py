"""Stage 2.5B Gate A resolution: the buyer-facing phasing label is shown only where phasing is ACQUISITION-RELEVANT (evidence existence is a separate question).

Relevance (app.policy.buyer_matching.phasing_is_acquisition_relevant): planning-delivery WIDER (non-self-phase) subject, TOTAL-units mandate, scale ABOVE the buyer's discovery maximum.
The shared AcquisitionPhasingEvidence fact, buyer classification, investigative flag, policy version 7 and fingerprints are untouched.
"""
from __future__ import annotations

import inspect
import itertools
import re

import pytest

import app.policy.buyer_matching as bm
import app.reporting.family_presentation as fp
import verification.transition.frozen_v6_matcher as frozen
from app.policy.buyer_matching import (
    PHASING_CURRENT_EVIDENCED_PHASE as CURRENT, PHASING_CURRENTNESS_UNKNOWN as UNKNOWN, PHASING_HISTORICAL_ONLY as HISTORICAL, PHASING_NONE_IDENTIFIED as NONE,
    AcquisitionPhasingEvidence, B2MatchingContext, MatchingFacts, assess_buyer_fit, phasing_is_acquisition_relevant,
)
from app.policy.buyer_profiles import BUYER_PROFILES
from app.reporting.opportunity_families import ID_SYSTEM_OPPORTUNITY, OpportunityFamily, RelatedSubject, subject_from_opportunity_id
from app.reporting.residential_count import CountAssessment
from benchmark.v7.cases import pd


def facts(units, **kw):
    return MatchingFacts(**pd(unit_count=units, **kw))


def context(state=CURRENT, phase_key=None, anchored=False):
    return B2MatchingContext(acquisition_phasing=AcquisitionPhasingEvidence(state) if state else None, subject_phase_scope_key=phase_key, subject_application_anchored=anchored)


def family_label(profile_key, units, state, *, with_phase=False):
    """The real presenter label for a one- or two-subject family, with the relevance computed by the real rule."""
    profile = BUYER_PROFILES[profile_key]
    evidence = AcquisitionPhasingEvidence(state) if state else None
    parent_facts, parent_ctx = facts(units), context(state)
    parent = subject_from_opportunity_id("planning_delivery:site:1", fit="INSUFFICIENT_EVIDENCE", investigative=True,
                                         source={"acquisition_phasing": evidence, "acquisition_phasing_relevant": phasing_is_acquisition_relevant(profile, parent_facts, parent_ctx)})
    members = [parent]
    if with_phase:
        phase_ctx = context(state, phase_key="1")
        members.append(subject_from_opportunity_id("planning_delivery:phase:1:1", fit="STRONG_FIT",
                                                   source={"acquisition_phasing": evidence, "acquisition_phasing_relevant": phasing_is_acquisition_relevant(profile, facts(125), phase_ctx)}))
    ordered = sorted(members, key=lambda m: m.fit != "STRONG_FIT")
    family = OpportunityFamily(("planning_delivery", 1), ordered[0], tuple(RelatedSubject(m, "INSUFFICIENT_INVESTIGATIVE") for m in ordered[1:]))
    return fp.phasing_context(family), family


# --- A-I. the approved scenarios ---------------------------------------------------------------------------------------------------------

def test_a_nesten_oversized_wider_subject_with_current_phase_shows_the_label():
    assert family_label("nesten_homes", 520, CURRENT, with_phase=True)[0] == fp.PHASING_CONTEXT
    assert family_label("nesten_homes", 520, CURRENT)[0] == fp.PHASING_CONTEXT


def test_b_national_housebuilder_oversized_wider_subject_with_current_phase_shows_the_label():
    assert family_label("national_housebuilder", 900, CURRENT, with_phase=True)[0] == fp.PHASING_CONTEXT


def test_c_nesten_below_minimum_subject_with_current_phase_shows_no_label_and_the_fact_remains_current():
    label, family = family_label("nesten_homes", 20, CURRENT)
    assert label is None and fp.phasing_evidenced(family) is True                      # J: the underlying fact is unchanged


def test_d_nesten_in_range_subject_with_current_phase_has_no_redundant_label():
    label, family = family_label("nesten_homes", 120, CURRENT)
    assert label is None and fp.phasing_evidenced(family) is True
    for units in (45, 50, 200, 220):                                                  # every in-discovery boundary: preferred and envelope
        assert family_label("nesten_homes", units, CURRENT)[0] is None, units
    assert family_label("nesten_homes", 221, CURRENT)[0] == fp.PHASING_CONTEXT       # the first value ABOVE the discovery maximum


def test_e_housing_association_total_site_oversize_with_current_phase_shows_no_label():
    for units in (120, 520, 5000):
        label, family = family_label("housing_association", units, CURRENT, with_phase=True)
        assert label is None, units
        assert fp.phasing_evidenced(family) is True                                   # evidence retained; only the buyer-facing acquisition badge is withheld


def test_f_strategic_allocation_never_shows_the_planning_delivery_phasing_label():
    subject = subject_from_opportunity_id("strategic_land:allocation:7", fit="STRONG_FIT", investigative=True,
                                          source={"acquisition_phasing": AcquisitionPhasingEvidence(CURRENT), "acquisition_phasing_relevant": True})
    assert fp.phasing_context(OpportunityFamily(("strategic_land", 7), subject, ())) is None
    strategic_facts = MatchingFacts(**{**pd(unit_count=2000), "opportunity_type": bm.STRATEGIC_LAND})
    assert phasing_is_acquisition_relevant(BUYER_PROFILES["strategic_land_buyer"], strategic_facts, context()) is False


def test_g_currentness_unknown_never_shows_the_current_label():
    label, _ = family_label("nesten_homes", 520, UNKNOWN)
    assert label == fp.PHASING_CONTEXT_CURRENTNESS_UNKNOWN != fp.PHASING_CONTEXT      # the weaker, honest label (relevant: oversized wider subject)
    assert family_label("nesten_homes", 20, UNKNOWN)[0] is None and family_label("nesten_homes", 120, UNKNOWN)[0] is None


def test_h_historical_shows_no_current_label():
    for units in (20, 120, 520):
        assert family_label("nesten_homes", units, HISTORICAL)[0] is None


def test_i_none_shows_no_label():
    for units in (20, 120, 520):
        assert family_label("nesten_homes", units, NONE)[0] is None
        assert family_label("nesten_homes", units, None)[0] is None


def test_self_phase_and_application_anchored_subjects_are_not_wider_subjects():
    profile = BUYER_PROFILES["nesten_homes"]
    assert phasing_is_acquisition_relevant(profile, facts(520), context(phase_key="2")) is False                    # a named phase scope restating itself
    assert phasing_is_acquisition_relevant(profile, facts(520), context(anchored=True)) is False                    # application-anchored under a CURRENT phase
    assert phasing_is_acquisition_relevant(profile, facts(520), context()) is True
    lone_phase, family = family_label("nesten_homes", 520, CURRENT, with_phase=False)
    phase_only = OpportunityFamily(("planning_delivery", 1), family.representative, ())
    assert fp.phasing_context(phase_only) == fp.PHASING_CONTEXT                       # sanity: a relevant wider subject shows it
    only_phase = subject_from_opportunity_id("planning_delivery:phase:1:1", fit="STRONG_FIT", source={"acquisition_phasing": AcquisitionPhasingEvidence(CURRENT),
                                                                                                    "acquisition_phasing_relevant": False})
    assert fp.phasing_context(OpportunityFamily(("planning_delivery", 1), only_phase, ())) is None


def test_uncertain_counts_follow_the_matchers_scale_semantics():
    profile = BUYER_PROFILES["nesten_homes"]

    def relevant(assessment):
        return phasing_is_acquisition_relevant(profile, MatchingFacts(**pd(unit_count=assessment.value or 0, count_assessment=assessment)), context())
    rng = lambda lo, hi, p="RANGE": CountAssessment(scope_type="whole_site", scope_label="x", precision=p, lower=lo, upper=hi, resolution="material_conflict", confidence="low")
    assert relevant(rng(300, 400)) is True and relevant(rng(10, 30)) is False and relevant(rng(100, 400)) is False and relevant(rng(100, 150)) is False
    assert relevant(CountAssessment(scope_type="whole_site", scope_label="x", precision="UNKNOWN")) is False
    assert relevant(CountAssessment(scope_type="whole_site", scope_label="x", precision="APPROXIMATE", value=500, resolution="portal_estimate", confidence="low")) is False   # no supported bounds
    assert relevant(CountAssessment(scope_type="whole_site", scope_label="x", precision="EXACT", value=500, lower=500, upper=500, resolution="agreement", confidence="high")) is True


# --- the rule is pinned to the matcher's own above-maximum semantics ---------------------------------------------------------------------------

@pytest.mark.parametrize("buyer", ("nesten_homes", "national_housebuilder", "strategic_land_buyer", "housing_association"))
def test_relevance_equals_the_matchers_above_discovery_maximum_wording(buyer):
    profile = BUYER_PROFILES[buyer]
    exact = lambda n: CountAssessment(scope_type="whole_site", scope_label="x", precision="EXACT", value=n, lower=n, upper=n, resolution="agreement", confidence="high")
    rng = lambda lo, hi: CountAssessment(scope_type="whole_site", scope_label="x", precision="RANGE", lower=lo, upper=hi, resolution="material_conflict", confidence="low")
    scalars = (1, 20, 44, 45, 50, 100, 200, 220, 221, 300, 500, 550, 551, 900, 5000)
    cases = [exact(n) for n in scalars] + [rng(1, 10), rng(10, 40), rng(100, 150), rng(100, 600), rng(300, 400), rng(560, 900), rng(900, 1500)]
    for assessment, state in itertools.product(cases, (CURRENT, UNKNOWN, HISTORICAL, NONE)):
        f = MatchingFacts(**pd(unit_count=assessment.value or assessment.lower, count_assessment=assessment, affordable_unit_count=assessment.value or assessment.lower))
        ctx = context(state)
        a = assess_buyer_fit(profile, f, context=ctx)
        text = " ".join([*a.matches, *a.unknown, *a.investigate, *a.does_not_match])
        matcher_says_above = ("outside this buyer's discovery range" in text) and profile.scale_metric != "affordable_units"
        assert phasing_is_acquisition_relevant(profile, f, ctx) == matcher_says_above, (buyer, assessment, state)


# --- nothing else moved ---------------------------------------------------------------------------------------------------------------

def test_classification_and_investigative_flag_are_unchanged_from_v6_for_every_relevance_scenario():
    for buyer, units, state, phase_key in itertools.product(BUYER_PROFILES, (1, 20, 120, 520, 900, 5000), (CURRENT, UNKNOWN, HISTORICAL, NONE, None), (None, "1")):
        profile, f, ctx = BUYER_PROFILES[buyer], facts(units, affordable_unit_count=max(1, units // 3)), context(state, phase_key=phase_key)
        v6, v7 = frozen.assess_buyer_fit(profile, f, context=ctx), assess_buyer_fit(profile, f, context=ctx)
        assert (v6.classification, bool(v6.is_investigative_exception)) == (v7.classification, bool(v7.is_investigative_exception))
        before = (v7.classification, v7.is_investigative_exception, tuple(v7.matches), tuple(v7.unknown), tuple(v7.investigate), tuple(v7.does_not_match))
        phasing_is_acquisition_relevant(profile, f, ctx)                                 # pure: calling the rule changes nothing
        assert before == (v7.classification, v7.is_investigative_exception, tuple(v7.matches), tuple(v7.unknown), tuple(v7.investigate), tuple(v7.does_not_match))
    assert bm.BUYER_MATCHING_POLICY_VERSION == 8


def test_the_phasing_evidence_states_and_derivation_are_unchanged():
    assert (bm.PHASING_STATES, CURRENT, UNKNOWN, HISTORICAL, NONE, bm.PHASING_DOCUMENTED) == (
        bm.PHASING_STATES, "CURRENT_EVIDENCED_PHASE", "PHASE_EVIDENCE_CURRENTNESS_UNKNOWN", "HISTORICAL_PHASE_ONLY", "NONE_IDENTIFIED", "DOCUMENTED_PHASING")
    import app.reporting.acquisition_phasing as ap
    source = inspect.getsource(ap)
    assert "phasing_is_acquisition_relevant" not in source and "scale_metric" not in source        # the derivation knows nothing about buyers or scale


def test_no_buyer_name_hardcoding_in_the_relevance_rule_or_the_presenter():
    for source in (inspect.getsource(phasing_is_acquisition_relevant), inspect.getsource(fp.phasing_context)):
        code = re.sub(r'""".*?"""', "", source, flags=re.S)                               # code and comments only; docstrings may explain which buyers exist
        for forbidden in ("nesten", "national_housebuilder", "housing_association", "strategic_land_buyer", "housebuilder"):
            assert forbidden not in code.lower(), forbidden
    assert "scale_metric" in inspect.getsource(phasing_is_acquisition_relevant)                   # the distinction follows the mandate's scale metric


def test_the_presenter_does_not_detect_phases_itself():
    source = inspect.getsource(fp)
    assert "derive_acquisition_phasing_evidence" not in source and "extract_phase_labels" not in source and "compute_lapse_status" not in source


def test_no_availability_residual_or_aggregation_inference_in_the_label_text():
    for label in (fp.PHASING_CONTEXT, fp.PHASING_CONTEXT_CURRENTNESS_UNKNOWN):
        assert not re.search(r"availab|residual|remaining|aggregat|combin|for sale|owner|willing|subdivi|another phase", label, re.I), label

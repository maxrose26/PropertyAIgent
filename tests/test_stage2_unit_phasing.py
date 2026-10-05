"""Approved A–N amendment cases, synthetic/offline; no production assertions."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.db.models import Application, SchemeIntelligence, Site
from app.reporting.scheme_reconciliation import (
    build_operative_planning_facts, count_assessment_for_facts, resolve_operative_filter_facts,
    scoped_count_assessment,
)
from app.reporting.residential_count import aligned_tenure_counts, supported_range
from app.pipeline.phase_tracking import build_phase_breakdown, summarize_phase_units
from app.reporting.dashboard import _undeveloped_phase_cards
from app.reporting.opportunity_feed import _reshape_signal_card, _attach_planning_delivery_matching_facts
from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative, assess_buyer_fit, NOT_SUITABLE
from app.policy.buyer_profiles import NESTEN_HOMES, HOUSING_ASSOCIATION


def scheme(session):
    site = Site(council_code="testcouncil", canonical_address="synthetic scope", display_address="Synthetic scope")
    session.add(site); session.flush()
    return site


def application(session, site, reference, units, *, phase=None, decision="Granted", date="2026-01-01", variation_of=None):
    proposal = (f"Section 73 variation of {variation_of} to provide {units} dwellings" if variation_of
                else f"Erection of {units or 'residential'} dwellings")
    if phase:
        proposal += f" in Phase {phase}"
    app = Application(site_id=site.id, council_code=site.council_code, reference=reference,
                      proposal=proposal, application_category="variation_or_amendment" if variation_of else "primary_residential",
                      decision=decision, status="Awaiting decision" if decision is None else "Decided",
                      application_received="2025-01-01", decision_issued_date=date if decision else None)
    session.add(app); session.flush()
    app.scheme_intelligence = SchemeIntelligence(application_id=app.id, total_units_final=units,
                                                development_type="houses", core_intelligence_complete=True)
    session.flush()
    return app


def assessment(apps):
    return count_assessment_for_facts(build_operative_planning_facts(apps))


def test_a_same_scope_variance_discovery_retains_bounds_and_provenance(session):
    site = scheme(session)
    apps = [application(session, site, f"FULL/{n}", n) for n in (100, 101, 102)]
    result = assessment(apps)
    assert result.label() == "~100 homes"
    assert result.note() == "Current evidence varies slightly: 100–102."
    assert (result.lower, result.upper, result.exact_value) == (100, 102, None)
    assert {p.application_reference for p in result.sources} == {a.reference for a in apps}
    assert all(p.decision_date for p in result.sources)


@pytest.mark.parametrize("values", [(100, 180), (100, 10), (100, 102), (200, 201, 202)])
def test_b_no_material_midpoint_or_unapproved_general_tolerance(session, values):
    site = scheme(session)
    result = assessment([application(session, site, f"FULL/{n}", n) for n in values])
    assert result.resolution == "material_conflict"
    assert result.precision == "UNKNOWN" and result.value is None


@pytest.mark.parametrize("decision,expected", [("Granted", 120), (None, 100), ("Refused", 100), ("Withdrawn", 100)])
def test_c_d_e_only_approved_linked_variation_supersedes(session, decision, expected):
    site = scheme(session)
    base = application(session, site, "BASE/1", 100)
    variation = application(session, site, "VAR/1", 120, decision=decision, date="2026-02-01", variation_of="BASE/1")
    facts = build_operative_planning_facts([base, variation])
    assert facts.consented_position.approved_units.value == expected
    assert resolve_operative_filter_facts(facts).units == expected
    if decision is None:
        assert facts.active_positions[0].proposed_units.value == 120


@pytest.mark.parametrize("date,link", [("2025-01-01", "BASE/1"), ("2026-02-01", "OTHER/1")])
def test_variation_without_current_supersession_does_not_win(session, date, link):
    site = scheme(session)
    result = assessment([application(session, site, "BASE/1", 100),
                         application(session, site, "VAR/1", 120, date=date, variation_of=link)])
    assert result.resolution == "material_conflict" and result.exact_value is None


def hierarchy(session):
    site = scheme(session)
    apps = [application(session, site, "PARENT/1", 2000),
            application(session, site, "RM/3", 180, phase="3", date="2026-02-01"),
            application(session, site, "RM/3A", 72, phase="3A", date="2026-03-01")]
    return site, apps


def test_f_g_parent_and_children_separate_without_252(session):
    _, apps = hierarchy(session)
    facts = build_operative_planning_facts(apps)
    assert facts.consented_position.approved_units.value == 2000
    assert facts.consented_position.superseded_units == ()
    rows = build_phase_breakdown(apps)
    assert {r["code"]: r.get("unit_count") for r in rows} == {"3": 180, "3A": 72, "Whole site / unphased": None}
    bucket = summarize_phase_units(rows)["approved_commencement_unverified"]
    assert bucket["units"] is None and bucket["phases_with_known_units"] == 2


def test_h_disjointness_requires_explicit_pair_provenance(session):
    _, apps = hierarchy(session)
    rows = build_phase_breakdown(apps)
    assert summarize_phase_units(rows, non_overlap_evidence=(("3", "3A", ""),))["approved_commencement_unverified"]["units"] is None
    assert summarize_phase_units(rows, non_overlap_evidence=(("3", "3A", "Synthetic approved boundary schedule"),))["approved_commencement_unverified"]["units"] == 252


def test_i_j_tenure_metric_scope_and_version_must_align(session):
    site = scheme(session)
    total = assessment([application(session, site, "FULL/1", 100)])
    private = replace(total, metric="private_units", value=70, lower=70, upper=70)
    affordable = replace(total, metric="affordable_units", value=30, lower=30, upper=30)
    assert aligned_tenure_counts(total, private, affordable) is None  # legacy scalars lack document versions
    def qualified(value):
        source = SimpleNamespace(qualified=True, metric=value.metric, subject_id=value.subject_id,
                                 version="approved-plan-v2", source_reference="synthetic-document", evidence_date="2026-01-01")
        return replace(value, sources=(source,))
    total, private, affordable = map(qualified, (total, private, affordable))
    assert aligned_tenure_counts(total, private, affordable) == {"total": 100, "private": 70, "affordable": 30}
    assert aligned_tenure_counts(total, private, replace(affordable, scope_label="Phase 3")) is None
    other = SimpleNamespace(**{**vars(affordable.sources[0]), "version": "other-version"})
    assert aligned_tenure_counts(total, private, replace(affordable, sources=(other,))) is None


def test_k_l_hard_boundary_uses_bounds_soft_discovery_keeps_uncertainty(session):
    site = scheme(session)
    apps = [application(session, site, f"FULL/{n}", n) for n in (100, 101, 102)]
    result = assessment(apps)
    assert result.within_hard_bounds(maximum=100) is None
    assert result.within_hard_bounds(maximum=99) is False
    assert result.within_hard_bounds(minimum=50, maximum=102) is True
    facts = build_planning_delivery_matching_facts_from_operative(build_operative_planning_facts(apps), apps)
    fit = assess_buyer_fit(NESTEN_HOMES, facts)
    assert fit.classification != NOT_SUITABLE and fit.is_investigative_exception
    assert facts.unit_count is None and facts.count_assessment == result
    assert any("uncertain discovery scale" in r for r in fit.unknown)
    # HA metric does not acquire total evidence through the new adapter.
    assert assess_buyer_fit(HOUSING_ASSOCIATION, facts).classification != NOT_SUITABLE
    assert facts.affordable_unit_count is None


def test_m_unknown_never_zero_or_active_fallback(session):
    site = scheme(session)
    approved = [application(session, site, f"FULL/{n}", n) for n in (100, 180)]
    active = application(session, site, "LIVE/1", 50, decision=None)
    result = assessment(approved + [active])
    assert result.precision == "UNKNOWN" and result.value is None
    assert result.within_hard_bounds(maximum=100) is None
    assert resolve_operative_filter_facts(build_operative_planning_facts(approved + [active])).units is None


def test_n_every_eligible_phase_card_has_own_aligned_matching_count(session):
    site, apps = hierarchy(session)
    session.commit()
    raw = [c for c in _undeveloped_phase_cards(session, 100) if c["params"]["site_id"] == str(site.id)]
    phase_cards = {c["phase_code"]: c for c in raw}
    assert {"3", "3A"}.issubset(phase_cards)
    cards = [_reshape_signal_card(c, opportunity_type="planning_delivery", extra_tags=[]) for c in raw]
    _attach_planning_delivery_matching_facts(session, cards)
    for card in cards:
        if card["phase_code"] in ("3", "3A"):
            expected = {"3": 180, "3A": 72}[card["phase_code"]]
            assert card["matching_facts"].unit_count == expected
            assert card["count_assessment"].value == expected
            assert card["matching_facts"].affordable_unit_count is None


def test_supported_range_requires_source_qualified_bounds():
    source = SimpleNamespace(qualified=True, qualifier="range", scope_type="phase", scope_label="Phase 3", lower=100, upper=120,
                             subject_id="site:1:phase:3", metric="total_residential", source_reference="synthetic", version="v1", evidence_date="2026-01-01")
    result = supported_range(lower=100, upper=120, sources=(source,), scope_type="phase", scope_label="Phase 3", subject_id="site:1:phase:3")
    assert result.label() == "100–120 homes" and result.exact_value is None
    assert result.within_hard_bounds(maximum=110) is None
    source.qualified = False
    assert supported_range(lower=100, upper=120, sources=(source,), scope_type="phase", scope_label="Phase 3", subject_id="site:1:phase:3").precision == "UNKNOWN"


def test_phase_approved_supersession_uses_same_contract(session):
    site = scheme(session)
    apps = [application(session, site, "RM/1", 100, phase="3"),
            application(session, site, "VAR/1", 120, phase="3", variation_of="RM/1", date="2026-02-01")]
    assert assessment(apps).exact_value is None  # never a whole-site count
    rows = build_phase_breakdown(apps)
    assert len(rows) == 1 and rows[0]["unit_count"] == 120


def test_different_scope_variation_link_cannot_supersede_parent(session):
    site = scheme(session)
    apps = [application(session, site, "BASE/1", 2000),
            application(session, site, "VAR/1", 120, phase="3", variation_of="BASE/1", date="2026-02-01")]
    assert assessment(apps).value == 2000


def test_multi_phase_application_is_not_whole_site_or_each_phase_count(session):
    site = scheme(session)
    app = application(session, site, "MULTI/1", 200, phase="3 and 4")
    assert assessment([app]).exact_value is None
    assert all(r.get("unit_count") is None for r in build_phase_breakdown([app]))


def test_same_small_variance_across_unresolved_versions_is_not_current_approximation(session):
    site = scheme(session)
    apps = [application(session, site, f"FULL/{n}", n, date=f"{year}-01-01")
            for n, year in ((100, 2010), (101, 2020), (102, 2026))]
    assert assessment(apps).resolution == "material_conflict"


@pytest.mark.parametrize("change", [{"metric": "affordable_units"}, {"subject_id": "another-site"},
                                   {"version": None}, {"source_reference": None}, {"evidence_date": None}])
def test_range_never_borrows_other_metric_subject_or_missing_provenance(change):
    data = dict(qualified=True, qualifier="range", scope_type="phase", scope_label="Phase 3",
                lower=100, upper=120, subject_id="site:1:phase:3", metric="total_residential",
                source_reference="synthetic", version="v1", evidence_date="2026-01-01")
    source = SimpleNamespace(**{**data, **change})
    result = supported_range(lower=100, upper=120, sources=(source,), scope_type="phase",
                             scope_label="Phase 3", subject_id="site:1:phase:3")
    assert result.precision == "UNKNOWN"


def test_all_use_count_is_not_relabelled_residential_homes(session):
    site = scheme(session)
    app = application(session, site, "MIXED/1", 100)
    app.scheme_intelligence.specialist_housing_type = "care home"
    facts = build_operative_planning_facts([app])
    assert assessment([app]).metric == "all_use_units"
    assert resolve_operative_filter_facts(facts).units_kind == "all_use"
    assert assessment([app]).label() == "100 all use units"


def test_profile_filter_and_report_share_approximate_display_without_exact_scalar(session):
    from app.reporting.site_profile import build_site_profile
    from app.reporting.pdf_report import _fmt_scheme
    from app.pipeline.lapse_tracking import compute_lapse_status
    from app.ui.common import aggregate_scheme_fields, _operative_units_display
    site = scheme(session)
    apps = [application(session, site, f"FULL/{n}", n) for n in (100, 101, 102)]
    session.commit()
    facts = build_operative_planning_facts(apps)
    filtered = resolve_operative_filter_facts(facts)
    profile = build_site_profile(session, site, apps, merged=aggregate_scheme_fields(apps), rep_app=apps[0],
                                 lapse=compute_lapse_status(apps, site), phase_breakdown=[], decision_status="granted")
    assert filtered.units is None
    assert profile["count_assessment"] == filtered.count_assessment
    assert profile["headline_metrics"][0]["value"] == "~100 homes"
    assert _operative_units_display(facts) == (True, "~100 homes")
    assert "~100 homes" in _fmt_scheme({"Total Units": None, "Count Display": filtered.count_assessment.label()})


def test_approved_unknown_cannot_borrow_known_active_count(session):
    site = scheme(session)
    apps = [application(session, site, "BASE/1", None), application(session, site, "LIVE/1", 100, decision=None)]
    facts = build_operative_planning_facts(apps)
    assert count_assessment_for_facts(facts).exact_value is None
    assert resolve_operative_filter_facts(facts).units is None


def test_single_phase_feed_uses_own_permission_state_not_absent_parent_state(session):
    site = scheme(session)
    application(session, site, "RM/ONLY", 72, phase="3A")
    session.commit()
    cards = [_reshape_signal_card(c, opportunity_type="planning_delivery", extra_tags=[])
             for c in _undeveloped_phase_cards(session, 100)]
    _attach_planning_delivery_matching_facts(session, cards)
    card = next(c for c in cards if c["phase_code"] == "3A")
    assert card["matching_facts"].planning_state == "permission_granted"
    assert card["matching_facts"].unit_count == 72
    assert assessment(list(site.applications)).exact_value is None


def test_portal_only_phase_scale_is_visible_but_not_exact_qualification(session):
    site = scheme(session)
    app = application(session, site, "RM/ONLY", None, phase="3A")
    app.proposal = "Reserved matters for Phase 3A comprising 72 dwellings"
    app.estimated_unit_count = 72  # explicit portal estimate; text has an ambiguous phase numeral
    result = build_phase_breakdown([app])[0]
    assert result["unit_count"] is None
    assert result["count_display"] == "~72 homes"
    assert result["count_assessment"].within_hard_bounds(maximum=72) is None


def test_linked_allocation_report_capacity_cannot_pick_child_as_site_total(session):
    from app.reporting.allocation_development_coverage import summarise_site_activity
    site, apps = hierarchy(session)
    assert summarise_site_activity(site, apps).capacity == 2000
    apps[0].scheme_intelligence.total_units_final = None
    apps[0].proposal = "Outline application for residential development"
    assert summarise_site_activity(site, apps).capacity is None


def test_duplicate_phase_scope_is_never_aggregated_even_with_pair_token(session):
    _, apps = hierarchy(session)
    row = build_phase_breakdown(apps)[0]
    bucket = summarize_phase_units([row, row], non_overlap_evidence=(("3", "3", "synthetic"),))["approved_commencement_unverified"]
    assert bucket["units"] is None

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
    # Stage 2.5A (v6): the SCALE dimension treats 100-102 as within discovery 45-110
    # but not wholly within preferred 50-100 (a POSSIBLE scale reason, never STRONG
    # from the rounded 100) ...
    assert any(r.startswith("~100 homes - not fully within this buyer's preferred range (50-100 homes)")
               and "wholly within its discovery range (45-110 homes)" in r for r in fit.matches)
    assert not any("does not establish whether scale is within" in r for r in fit.unknown)
    assert not any("outside this buyer's discovery range" in r for r in fit.investigate)
    # ... and, with v6 hardening (N1-B/N2-B), the overall result is POSSIBLE_FIT:
    # the three agreeing supporters corroborate development type ("houses"), and
    # the untrusted affordable percentage stays a visible, non-blocking unknown.
    assert fit.classification == "POSSIBLE_FIT", fit.unknown
    assert facts.development_type_raw == "houses"
    assert "Affordable housing proportion has not been confirmed - not assumed to be 0%." in fit.unknown
    assert ("Development type has not been established with enough confidence to confirm this is "
            "general-needs housing.") not in fit.unknown
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


def test_category_navigation_and_count_text_stay_inside_each_card(monkeypatch):
    from contextlib import contextmanager, nullcontext
    from app.ui import shell
    from app.reporting.residential_count import CountAssessment
    class UI:
        def __init__(self):
            self.stack, self.links, self.captions = [], [], []
        @contextmanager
        def container(self, **kwargs):
            self.stack.append(kwargs["key"])
            try:
                yield
            finally:
                self.stack.pop()
        def columns(self, spec, **kwargs):
            return [nullcontext() for _ in range(spec if isinstance(spec, int) else len(spec))]
        def markdown(self, *args, **kwargs):
            pass
        def badge(self, *args, **kwargs):
            pass
        def caption(self, text):
            self.captions.append((self.stack[-1], text))
        def page_link(self, page, **kwargs):
            self.links.append((self.stack[-1], page, kwargs["query_params"]))
    ui = UI()
    monkeypatch.setattr(shell, "st", ui)
    exact = CountAssessment("whole_site", "Whole site", precision="EXACT", value=102, lower=102, upper=102)
    approximate = replace(exact, precision="APPROXIMATE", value=100, lower=100, upper=102, resolution="immaterial_variance")
    cards = [dict(id=str(i), title="Synthetic", subtitle="Council", reason="Evidence", metric="Permission",
                  count_assessment=count, page="pages/1_Scheme_Detail.py", params={"site_id": str(i)})
             for i, count in enumerate((exact, approximate, None), 1)]
    shell.opportunity_category_section(dict(key="phase", heading="Phases", count=3, explanation="Synthetic",
                                            available=True, cards=cards), key="test")
    assert [(context, params) for context, _, params in ui.links] == [
        (f"opp-cat-card-test-{i}", {"site_id": str(i)}) for i in range(1, 4)]
    assert ("opp-cat-card-test-1", "102 homes") in ui.captions
    assert ("opp-cat-card-test-2", "Current evidence varies slightly: 100–102.") in ui.captions


def test_phase_and_material_plot_same_number_keep_distinct_identity_and_count(session):
    from app.reporting.opportunity_universe import build_current_opportunity_universe
    from app.pipeline.phase_tracking import acquisition_scope_key, build_acquisition_scope_breakdown
    site = scheme(session)
    application(session, site, "PHASE/3", 180, phase="3")
    plot = application(session, site, "PLOT/3", 72)
    plot.proposal = "Full application for Plot 3 comprising 72 dwellings"
    session.commit()
    raw = _undeveloped_phase_cards(session, 100)
    assert {c["phase_code"] for c in raw} == {"3", "plot_3"}
    assert len({c["id"] for c in raw}) == 2
    cards = [_reshape_signal_card(c, opportunity_type="planning_delivery", extra_tags=[]) for c in raw]
    _attach_planning_delivery_matching_facts(session, cards)
    assert {c["params"]["phase_code"]: c["matching_facts"].unit_count for c in cards} == {"3": 180, "plot_3": 72}
    rows = build_acquisition_scope_breakdown(list(site.applications))
    assert {acquisition_scope_key(r): r["label"] for r in rows} == {"3": "Phase 3", "plot_3": "Plot 3"}
    records = build_current_opportunity_universe(session)
    own = [r for r in records if r.opportunity_id.startswith(f"planning_delivery:phase:{site.id}:")]
    assert len({r.opportunity_id for r in own}) == 2
    from app.policy.agent_evaluation_persistence import resolve_acquisition_subject_key
    assert {resolve_acquisition_subject_key(r.opportunity_id, r.opportunity_type)[2] for r in own} == {"3", "plot_3"}


@pytest.mark.parametrize("source_count", [1, 2])
def test_exact_extraction_source_stays_separate_from_newer_portal_and_ah_identity(session, source_count):
    from app.reporting.site_profile import build_site_profile
    from app.pipeline.lapse_tracking import compute_lapse_status
    from app.ui.common import aggregate_scheme_fields
    site = scheme(session)
    old = [application(session, site, f"OLD/{n}", 440, decision=None) for n in range(source_count)]
    for app in old:
        app.scheme_intelligence.affordable_units_final = 0
    newer = application(session, site, "NEW/1", None, decision=None)
    newer.scheme_intelligence = None
    newer.proposal = "Residential development of 82 homes"
    newer.application_received = "2026-02-01"
    session.commit()
    apps = old + [newer]
    profile = build_site_profile(session, site, apps, merged=aggregate_scheme_fields(apps), rep_app=newer,
        lapse=compute_lapse_status(apps, site), phase_breakdown=[], decision_status="pending")
    assert profile["count_assessment"].exact_value == 440
    mix = profile["residential_mix"]
    assert mix["extraction_reference"] in {app.reference for app in old}
    assert mix["scheme"].total_units_final == 440
    assert mix["affordable_assessment"].count.application_reference == "NEW/1"
    assert mix["affordable_assessment"].count.value is None


@pytest.mark.parametrize("precision,lower,upper,expected", [
    # Stage 2.5A (v6): wholly within discovery 45-110 but not preferred -> POSSIBLE.
    ("APPROXIMATE", 100, 102, "POSSIBLE_FIT"),
    ("RANGE", 45, 55, "POSSIBLE_FIT"),
    ("RANGE", 90, 120, "INSUFFICIENT_EVIDENCE"),
    ("RANGE", 110, 120, "INSUFFICIENT_EVIDENCE"),
    ("APPROXIMATE", None, None, "INSUFFICIENT_EVIDENCE"),
    ("UNKNOWN", None, None, "INSUFFICIENT_EVIDENCE"),
    ("RANGE", 70, 80, "STRONG_FIT"),
    ("EXACT", 100, 100, "STRONG_FIT"),
])
def test_uncertain_scale_fit_uses_evidence_bounds_not_rounded_scalar(precision, lower, upper, expected):
    from app.reporting.residential_count import CountAssessment
    from app.policy.buyer_matching import MatchingFacts, PLANNING_DELIVERY
    count = CountAssessment(scope_type="whole_site", scope_label="Whole site", precision=precision,
                            value=100, lower=lower, upper=upper)
    facts = MatchingFacts(opportunity_type=PLANNING_DELIVERY, unit_count=100,
        count_assessment=count, affordable_unit_count=None, development_type_raw="houses", is_specialist_development=False,
        affordable_percentage=30.0, affordable_percentage_trusted=True,
        planning_state="permission_granted", has_identified_planning_activity=True,
        has_phasing_evidence=False, matched_to_site=True)
    fit = assess_buyer_fit(NESTEN_HOMES, facts)
    assert fit.classification == expected
    assert fit.classification != NOT_SUITABLE
    if precision in ("APPROXIMATE", "RANGE"):
        assert fit.is_investigative_exception and fit.investigate
        if expected == "STRONG_FIT":
            assert any("exact mandate compliance unverified" in r for r in fit.unknown)
        assert not any("sits within" in r for r in fit.matches)


def _profile_for_sources(session, site, apps):
    from app.reporting.site_profile import build_site_profile
    from app.pipeline.lapse_tracking import compute_lapse_status
    from app.ui.common import aggregate_scheme_fields
    return build_site_profile(session, site, apps, merged=aggregate_scheme_fields(apps), rep_app=apps[-1],
        lapse=compute_lapse_status(apps, site), phase_breakdown=[], decision_status="granted")


def test_exact_source_prefers_operative_supporter_over_alphabetical_first(session):
    site = scheme(session)
    older = application(session, site, "A/OLD", 100)
    current = application(session, site, "Z/CURRENT", 100, date="2026-02-01")
    session.commit()
    profile = _profile_for_sources(session, site, [older, current])
    assert profile["count_assessment"].exact_value == 100
    assert profile["residential_mix"]["extraction_reference"] == current.reference
    assert len(profile["count_assessment"].sources) == 2


@pytest.mark.parametrize("multiple_active", [False, True])
def test_exact_source_without_operative_identity_has_deterministic_supporting_fallback(session, monkeypatch, multiple_active):
    import app.reporting.site_profile as sp
    site = scheme(session)
    apps = [application(session, site, ref, 100) for ref in ("Z/1", "A/1")]
    session.commit()
    facts = build_operative_planning_facts(apps)
    active = ()
    if multiple_active:
        # Two active positions cannot establish a single operative identity.
        pending = application(session, site, "PENDING", 100, decision=None)
        position = build_operative_planning_facts([pending]).active_positions[0]
        active = tuple(replace(position, reference=replace(position.reference,
                       source=replace(position.reference.source, application_id=a.id), value=a.reference))
                       for a in apps)
    # No established operative reference; count evidence itself remains intact.
    facts = replace(facts, consented_position=replace(facts.consented_position,
                    reference=replace(facts.consented_position.reference, state="not_determined", source=None)),
                    active_positions=active)
    monkeypatch.setattr(sp, "build_operative_planning_facts", lambda _: facts)
    for order in (apps, list(reversed(apps))):
        profile = _profile_for_sources(session, site, order)
        assert profile["residential_mix"]["extraction_reference"] == "A/1"
        assert profile["count_assessment"].exact_value == 100


def test_exact_source_rejects_stale_supporter_without_displayed_count(session, monkeypatch):
    import app.reporting.site_profile as sp
    site = scheme(session)
    good = application(session, site, "A/GOOD", 100)
    current = application(session, site, "Z/CURRENT", 100, date="2026-02-01")
    session.commit()
    facts = build_operative_planning_facts([good, current])
    monkeypatch.setattr(sp, "build_operative_planning_facts", lambda _: facts)
    current.scheme_intelligence.total_units_final = 82
    profile = _profile_for_sources(session, site, [good, current])
    assert profile["count_assessment"].exact_value == 100
    assert profile["residential_mix"]["extraction_reference"] == "A/GOOD"
    assert profile["residential_mix"]["affordable_assessment"].count.application_reference == "Z/CURRENT"
    good.scheme_intelligence.total_units_final = 82
    profile = _profile_for_sources(session, site, [good, current])
    assert profile["residential_mix"]["extraction_reference"] is None
    assert profile["count_assessment"].exact_value == 100


# --- Stage 2.5 preflight gate 1: opportunity-position phase counts are never blindly summed ---


def _phase_row(code, units, status="approved_commencement_unverified", kind="phase"):
    return {"code": code, "kind": kind, "status": status, "unit_count": units, "latest_grant": object(),
            "label": f"Phase {code}"}


def _position_reasons(phase_breakdown, *, merged=None, non_overlap_evidence=()):
    from app.reporting.site_profile import build_opportunity_position
    op = build_opportunity_position(
        merged=merged or {"total_units_final": None},
        lapse={"status": "not_granted", "build_status": "unknown", "deadline": None},
        phase_breakdown=phase_breakdown, policy_rows=[], council_supply=None, has_missing_evidence=False,
        non_overlap_evidence=non_overlap_evidence)
    return " | ".join(op["reasons"])


def test_safe_phase_aggregation_a_evidenced_non_overlap_may_aggregate():
    text = _position_reasons([_phase_row("2", 180), _phase_row("3", 72)],
                             non_overlap_evidence=(("2", "3", "synthetic pairwise non-overlap provenance"),))
    assert "2 phase(s) have permission recorded" in text
    assert "(252 units)" in text


def test_safe_phase_aggregation_b_potential_overlap_never_shows_252():
    breakdown = [_phase_row("2", 180), _phase_row("2A", 72)]
    text = _position_reasons(breakdown)
    assert "252" not in text and "units)" not in text
    # Phase-status information stays available while the aggregate is unverified.
    assert "2 phase(s) have permission recorded; physical commencement and availability remain unverified." in text
    # Evidence about a different pair must not authorise this pair.
    assert "252" not in _position_reasons(breakdown, non_overlap_evidence=(("2", "9", "synthetic provenance"),))
    assert "252" not in _position_reasons(breakdown, non_overlap_evidence=(("3", "2A", "synthetic provenance"),))
    # An evidence pair with no provenance is not evidence.
    assert "252" not in _position_reasons(breakdown, non_overlap_evidence=(("2", "2A", ""),))
    assert "252" not in _position_reasons(breakdown, non_overlap_evidence=(("2", "2A", None),))


def test_safe_phase_aggregation_c_partial_known_counts_are_withheld():
    pairs = (("1", "2", "p"), ("1", "3", "p"), ("2", "3", "p"))
    text = _position_reasons([_phase_row("1", 180), _phase_row("2", 72), _phase_row("3", None)], non_overlap_evidence=pairs)
    assert "3 phase(s) have permission recorded" in text
    assert "252" not in text and "units)" not in text
    # One known and one unknown phase: the known 180 is not a combined total.
    two = _position_reasons([_phase_row("1", 180), _phase_row("2", None)], non_overlap_evidence=(("1", "2", "p"),))
    assert "2 phase(s) have permission recorded" in two
    assert "180" not in two and "units)" not in two


def test_safe_phase_aggregation_d_single_known_phase_keeps_its_scoped_count():
    text = _position_reasons([_phase_row("2", 180)])
    assert "1 phase(s) have permission recorded" in text
    assert "(180 units)" in text


def test_safe_phase_aggregation_e_parent_phase_and_subphase_stay_scope_separated():
    merged = {"total_units_final": 2000}
    breakdown = [_phase_row("2", 180), _phase_row("2A", 72)]
    text = _position_reasons(breakdown, merged=merged)
    assert "Major scheme recorded — 2,000 homes." in text
    assert "252" not in text and "2,252" not in text and "2,180" not in text and "2,072" not in text
    # Even where the two child scopes are evidenced as independent, the parent is never added or replaced.
    evidenced = _position_reasons(breakdown, merged=merged, non_overlap_evidence=(("2", "2A", "synthetic provenance"),))
    assert "Major scheme recorded — 2,000 homes." in evidenced
    assert "(252 units)" in evidenced
    assert "2,252" not in evidenced and "2,000 homes" in evidenced and "2,180" not in evidenced


def test_safe_phase_aggregation_f_plots_and_mixed_status_buckets_stay_unverified():
    # A plot row cannot be counted by the shared rule, so it must not leave a partial sum behind.
    with_plot = [_phase_row("2", 72), _phase_row("5", None, kind="plot")]
    text = _position_reasons(with_plot, non_overlap_evidence=(("2", "5", "p"),))
    assert "2 phase(s) have permission recorded" in text and "units)" not in text
    # An unphased bucket row likewise.
    unphased = [_phase_row("2", 72), _phase_row("Whole site / unphased", 100)]
    unphased_text = _position_reasons(unphased, non_overlap_evidence=(("2", "Whole site / unphased", "p"),))
    assert "units)" not in unphased_text
    # Phases in different status buckets are not aggregated across buckets.
    mixed = [_phase_row("2", 180), _phase_row("3", 72, status="planning_activity")]
    mixed_text = _position_reasons(mixed, non_overlap_evidence=(("2", "3", "p"),))
    assert "252" not in mixed_text and "units)" not in mixed_text


def test_safe_phase_aggregation_g_h_unknown_stays_unknown_and_status_wording_survives():
    text = _position_reasons([_phase_row("2", None)])
    assert "1 phase(s) have permission recorded; physical commencement and availability remain unverified." in text
    assert "0 units" not in text and "units)" not in text
    # A phase with no recorded grant is not counted as permission recorded at all.
    ungranted = _position_reasons([{"code": "2", "kind": "phase", "status": "not_yet_approved", "unit_count": 50}])
    assert "permission recorded" not in ungranted



# --- Stage 2.5 preflight gates 2 and 2H: residual planning-capacity safety contract ---

_RC_PARENT = "site:1:whole_site:Whole site"
_RC_A = "site:1:phase:Phase 2"
_RC_B = "site:1:phase:Phase 3"
_RC_R = "site:1:phase:Phase 9"
_RC_INVENTORY = "synthetic child-set inventory"
_RC_BAD_PROVENANCE = (True, 1, object(), "", "   ", None)


def _rc_count(subject, value, *, metric="total_residential", precision="EXACT", basis="consented",
              resolution=None):
    from app.reporting.residential_count import CountAssessment
    exact = precision == "EXACT"
    parts = subject.split(":", 3)
    return CountAssessment(
        scope_type=parts[2] if len(parts) == 4 else "phase", scope_label=parts[3] if len(parts) == 4 else subject,
        subject_id=subject, metric=metric, precision=precision, value=value,
        lower=value if exact else None, upper=value if exact else None,
        resolution=resolution or ("agreement" if exact else "portal_estimate"),
        confidence="high" if exact else "low", basis=basis)


def _rc_conflict_parent(lower=500, upper=650):
    from app.reporting.residential_count import CountAssessment
    return CountAssessment(scope_type="whole_site", scope_label="Whole site", subject_id=_RC_PARENT,
                           precision="UNKNOWN", lower=lower, upper=upper, resolution="material_conflict",
                           confidence="low", basis="consented")


def _rc_contained(*children, parent=_RC_PARENT):
    return tuple((child, parent, "synthetic containment provenance") for child in children)


def _rc_complete(*children, parent=_RC_PARENT, provenance=_RC_INVENTORY):
    """Explicit sourced evidence that these children are the parent's complete relevant child set."""
    return ((parent, tuple(children), provenance),)


def _rc_assess(parent, children, **evidence):
    from app.reporting.residual_capacity import assess_residual_planning_capacity
    return assess_residual_planning_capacity(parent, children, **evidence)


def test_residual_a_simple_safe_case_resolves_planning_capacity():
    from app.reporting.residual_capacity import RESOLVED
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125)],
                        containment_evidence=_rc_contained(_RC_A), child_set_evidence=_rc_complete(_RC_A))
    assert result.status == RESOLVED and result.resolved
    assert result.residual_planning_capacity == 375 and result.reason == "resolved"
    assert result.metric == "total_residential"
    assert [c.subject_id for c in result.subtracted_children] == [_RC_A]
    assert result.containment_provenance == ((_RC_A, _RC_PARENT),)
    assert result.child_set_completeness == "established" and result.child_set_provenance == _RC_INVENTORY
    assert result.parent.exact_value == 500


@pytest.mark.parametrize("parent_metric,child_metric", [
    ("total_residential", "private_units"), ("private_units", "total_residential"),
    ("total_residential", "affordable_units"), ("total_residential", "all_use_units"),
])
def test_residual_b_metric_mismatch_is_never_converted(parent_metric, child_metric):
    from app.reporting.residual_capacity import UNVERIFIED
    result = _rc_assess(_rc_count(_RC_PARENT, 500, metric=parent_metric),
                        [_rc_count(_RC_A, 125, metric=child_metric)], containment_evidence=_rc_contained(_RC_A),
                        child_set_evidence=_rc_complete(_RC_A))
    assert result.status == UNVERIFIED and result.reason == "metric_mismatch"
    assert result.residual_planning_capacity is None and not result.resolved


def test_residual_c_containment_must_be_explicitly_evidenced():
    from app.reporting.residual_capacity import UNVERIFIED
    parent, child = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125)
    for evidence in ((), ((_RC_A, _RC_PARENT, ""),), ((_RC_A, _RC_PARENT, None),),
                     ((_RC_B, _RC_PARENT, "p"),), ((_RC_A, "site:9:whole_site:Whole site", "p"),),
                     ((_RC_PARENT, _RC_A, "p"),)):
        result = _rc_assess(parent, [child], containment_evidence=evidence, child_set_evidence=_rc_complete(_RC_A))
        assert result.status == UNVERIFIED and result.reason == "containment_not_established", evidence
        assert result.residual_planning_capacity is None


def test_residual_d_children_that_may_overlap_withhold_the_residual():
    from app.reporting.residual_capacity import UNVERIFIED
    parent, children = _rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125), _rc_count(_RC_B, 100)]
    for non_overlap in ((), ((_RC_A, "site:1:phase:Phase 9", "p"),), ((_RC_A, _RC_B, ""),), ((_RC_A, _RC_B, None),)):
        result = _rc_assess(parent, children, containment_evidence=_rc_contained(_RC_A, _RC_B),
                            non_overlap_evidence=non_overlap, child_set_evidence=_rc_complete(_RC_A, _RC_B))
        assert result.status == UNVERIFIED and result.reason == "child_overlap_not_excluded", non_overlap
        assert result.residual_planning_capacity is None


def test_residual_e_explicitly_non_overlapping_children_resolve_and_order_does_not_matter():
    from app.reporting.residual_capacity import RESOLVED
    parent, a, b = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125), _rc_count(_RC_B, 100)
    forward = _rc_assess(parent, [a, b], containment_evidence=_rc_contained(_RC_A, _RC_B),
                         non_overlap_evidence=((_RC_A, _RC_B, "synthetic non-overlap provenance"),),
                         child_set_evidence=_rc_complete(_RC_A, _RC_B))
    backward = _rc_assess(parent, [b, a], containment_evidence=tuple(reversed(_rc_contained(_RC_A, _RC_B))),
                          non_overlap_evidence=((_RC_B, _RC_A, "synthetic non-overlap provenance"),),
                          child_set_evidence=_rc_complete(_RC_B, _RC_A))
    assert forward.status == RESOLVED and forward.residual_planning_capacity == 275
    assert forward == backward


def test_residual_f_known_ineligible_child_never_consumes_capacity():
    from app.reporting.residual_capacity import RESOLVED, UNVERIFIED
    parent = _rc_count(_RC_PARENT, 500)
    for basis in ("refused", "withdrawn", "superseded"):
        refused = _rc_count(_RC_A, 125, basis=basis)
        alone = _rc_assess(parent, [refused], containment_evidence=_rc_contained(_RC_A))
        assert alone.status == UNVERIFIED and alone.reason == "no_operative_child"
        assert alone.residual_planning_capacity is None
        assert [e.child.subject_id for e in alone.excluded_children] == [_RC_A]
        assert alone.excluded_children[0].reason == "not_operative_approved"
        # Beside a genuine operative child, the known-ineligible value is excluded, not subtracted.
        mixed = _rc_assess(parent, [refused, _rc_count(_RC_B, 100)], containment_evidence=_rc_contained(_RC_A, _RC_B),
                           child_set_evidence=_rc_complete(_RC_A, _RC_B))
        assert mixed.status == RESOLVED and mixed.residual_planning_capacity == 400
        assert [c.subject_id for c in mixed.subtracted_children] == [_RC_B]
        assert [e.child.subject_id for e in mixed.excluded_children] == [_RC_A]


def test_residual_g_pending_variation_neither_replaces_nor_consumes_approved_capacity():
    from app.reporting.residual_capacity import UNVERIFIED
    parent = _rc_count(_RC_PARENT, 500)
    pending = _rc_count(_RC_A, 125, basis="active")
    result = _rc_assess(parent, [pending], containment_evidence=_rc_contained(_RC_A))
    assert result.status == UNVERIFIED and result.reason == "no_operative_child"
    assert result.residual_planning_capacity is None and result.parent.exact_value == 500
    # A pending parent (not an operative approved position) cannot supply capacity either.
    pending_parent = _rc_assess(_rc_count(_RC_PARENT, 500, basis="active"), [_rc_count(_RC_A, 125)],
                                containment_evidence=_rc_contained(_RC_A), child_set_evidence=_rc_complete(_RC_A))
    assert pending_parent.status == UNVERIFIED and pending_parent.reason == "parent_not_operative_approved"


def test_residual_h_material_count_conflict_is_preserved_never_averaged():
    from app.reporting.residual_capacity import MATERIAL_CONFLICT
    result = _rc_assess(_rc_conflict_parent(), [_rc_count(_RC_A, 125)], containment_evidence=_rc_contained(_RC_A),
                        child_set_evidence=_rc_complete(_RC_A))
    assert result.status == MATERIAL_CONFLICT and result.reason == "count_material_conflict"
    assert result.residual_planning_capacity is None
    conflicted_child = _rc_assess(_rc_count(_RC_PARENT, 500),
                                  [_rc_count(_RC_A, None, precision="UNKNOWN", resolution="material_conflict")],
                                  containment_evidence=_rc_contained(_RC_A), child_set_evidence=_rc_complete(_RC_A))
    assert conflicted_child.status == MATERIAL_CONFLICT and conflicted_child.residual_planning_capacity is None


def test_residual_i_approximate_or_range_counts_never_become_an_exact_residual():
    from app.reporting.residual_capacity import UNVERIFIED
    exact_child = _rc_count(_RC_A, 125)
    for parent in (_rc_count(_RC_PARENT, 500, precision="APPROXIMATE"), _rc_count(_RC_PARENT, 500, precision="RANGE")):
        result = _rc_assess(parent, [exact_child], containment_evidence=_rc_contained(_RC_A),
                            child_set_evidence=_rc_complete(_RC_A))
        assert result.status == UNVERIFIED and result.reason == "count_not_exact"
        assert result.residual_planning_capacity is None
    approximate_child = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125, precision="APPROXIMATE")],
                                   containment_evidence=_rc_contained(_RC_A), child_set_evidence=_rc_complete(_RC_A))
    assert approximate_child.status == UNVERIFIED and approximate_child.residual_planning_capacity is None


def test_residual_j_unknown_counts_stay_unknown_not_zero():
    from app.reporting.residual_capacity import UNVERIFIED
    unknown_child = _rc_count(_RC_A, None, precision="UNKNOWN", resolution="insufficient_evidence")
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [unknown_child], containment_evidence=_rc_contained(_RC_A),
                        child_set_evidence=_rc_complete(_RC_A))
    assert result.status == UNVERIFIED and result.reason == "unknown_count"
    assert result.residual_planning_capacity is None
    unknown_parent = _rc_assess(_rc_count(_RC_PARENT, None, precision="UNKNOWN"), [_rc_count(_RC_A, 125)],
                                containment_evidence=_rc_contained(_RC_A), child_set_evidence=_rc_complete(_RC_A))
    assert unknown_parent.status == UNVERIFIED and unknown_parent.residual_planning_capacity is None


def test_residual_k_children_greater_than_parent_never_give_a_negative_residual():
    from app.reporting.residual_capacity import MATERIAL_CONFLICT, RESOLVED
    parent = _rc_count(_RC_PARENT, 500)
    single = _rc_assess(parent, [_rc_count(_RC_A, 600)], containment_evidence=_rc_contained(_RC_A),
                        child_set_evidence=_rc_complete(_RC_A))
    assert single.status == MATERIAL_CONFLICT and single.reason == "children_exceed_parent"
    assert single.residual_planning_capacity is None
    two = _rc_assess(parent, [_rc_count(_RC_A, 300), _rc_count(_RC_B, 300)],
                     containment_evidence=_rc_contained(_RC_A, _RC_B), non_overlap_evidence=((_RC_A, _RC_B, "p"),),
                     child_set_evidence=_rc_complete(_RC_A, _RC_B))
    assert two.status == MATERIAL_CONFLICT and two.residual_planning_capacity is None
    # A child that consumes exactly the parent leaves zero, never a negative number.
    full = _rc_assess(parent, [_rc_count(_RC_A, 500)], containment_evidence=_rc_contained(_RC_A),
                      child_set_evidence=_rc_complete(_RC_A))
    assert full.status == RESOLVED and full.residual_planning_capacity == 0


def test_residual_l_duplicate_child_is_subtracted_once_and_conflicting_duplicates_are_a_conflict():
    from app.reporting.residual_capacity import MATERIAL_CONFLICT, RESOLVED
    parent, child = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125)
    twice = _rc_assess(parent, [child, child], containment_evidence=_rc_contained(_RC_A),
                       child_set_evidence=_rc_complete(_RC_A))
    assert twice.status == RESOLVED and twice.residual_planning_capacity == 375
    assert len(twice.subtracted_children) == 1
    differing = _rc_assess(parent, [child, _rc_count(_RC_A, 130)], containment_evidence=_rc_contained(_RC_A),
                           child_set_evidence=_rc_complete(_RC_A))
    assert differing.status == MATERIAL_CONFLICT and differing.reason == "conflicting_duplicate_child"
    assert differing.residual_planning_capacity is None


def test_residual_m_planning_capacity_is_never_availability():
    import dataclasses
    from app.reporting.residual_capacity import ResidualCapacityAssessment
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125)], containment_evidence=_rc_contained(_RC_A),
                        child_set_evidence=_rc_complete(_RC_A))
    assert result.residual_planning_capacity == 375
    assert not any("avail" in field.name.lower() for field in dataclasses.fields(ResidualCapacityAssessment))
    assert result.label() == "375 homes of residual planning capacity (planning capacity only)"
    assert "available" not in result.label().lower()
    assert "not land availability" in result.claim and "ownership" in result.claim and "control" in result.claim
    assert result.child_set_completeness == "established"
    unresolved = _rc_assess(_rc_count(_RC_PARENT, 500), [])
    assert unresolved.child_set_completeness == "not_established"
    assert not any(char.isdigit() for char in unresolved.label())


def test_residual_identity_guards_and_shared_pair_rule():
    from app.pipeline.phase_tracking import summarize_phase_units
    from app.reporting.residential_count import evidenced_pairs
    from app.reporting.residual_capacity import UNVERIFIED
    parent = _rc_count(_RC_PARENT, 500)
    self_child = _rc_assess(parent, [_rc_count(_RC_PARENT, 125)], containment_evidence=_rc_contained(_RC_PARENT))
    assert self_child.status == UNVERIFIED and self_child.reason == "child_is_parent"
    no_identity = _rc_assess(parent, [_rc_count("", 125)])
    assert no_identity.status == UNVERIFIED and no_identity.reason == "child_identity_missing"
    no_parent_identity = _rc_assess(_rc_count("", 500), [_rc_count(_RC_A, 125)])
    assert no_parent_identity.status == UNVERIFIED and no_parent_identity.reason == "parent_identity_missing"
    # One pair-evidence rule for phase aggregation and residual arithmetic: provenance or nothing.
    assert evidenced_pairs((("a", "b", "p"), ("c", "d", ""), ("e", "f", None))) == {frozenset(("a", "b"))}
    rows = [{"code": code, "kind": "phase", "status": "approved_commencement_unverified", "unit_count": units}
            for code, units in (("2", 180), ("3", 72))]
    assert summarize_phase_units(rows, non_overlap_evidence=(("2", "3", ""),))["approved_commencement_unverified"]["units"] is None
    assert summarize_phase_units(rows, non_overlap_evidence=(("2", "3", "p"),))["approved_commencement_unverified"]["units"] == 252


# --- Gate 2H hardening: completeness, site/scope compatibility, provenance, unresolved children ---


def test_residual_2h_a_incomplete_child_set_is_not_a_resolved_residual():
    from app.reporting.residual_capacity import RESOLVED, UNVERIFIED
    parent, child = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125)
    for evidence in ((), ((_RC_PARENT, (_RC_A,), ""),), ((_RC_PARENT, (_RC_A,), None),),
                     (("site:9:whole_site:Whole site", (_RC_A,), _RC_INVENTORY),),
                     ((_RC_PARENT, _RC_A, _RC_INVENTORY),)):   # a bare string is not a set of child ids
        result = _rc_assess(parent, [child], containment_evidence=_rc_contained(_RC_A), child_set_evidence=evidence)
        assert result.status == UNVERIFIED and result.status != RESOLVED, evidence
        assert result.reason == "child_set_completeness_not_established", evidence
        assert result.residual_planning_capacity is None and not result.resolved
        assert result.child_set_completeness == "not_established"
        assert result.label() == "Residual planning capacity not established"
        # The supplied-children arithmetic is not exposed as a residual figure.
        assert [c.subject_id for c in result.subtracted_children] == [_RC_A]


def test_residual_2h_b_complete_child_set_resolves():
    from app.reporting.residual_capacity import RESOLVED
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125)], containment_evidence=_rc_contained(_RC_A),
                        child_set_evidence=_rc_complete(_RC_A, provenance="Approved phasing plan PL/2026/001 table 2"))
    assert result.resolved and result.residual_planning_capacity == 375
    assert result.child_set_provenance == "Approved phasing plan PL/2026/001 table 2"


def test_residual_2h_b2_omitted_extra_or_conflicting_child_set_evidence_withholds_the_residual():
    from app.reporting.residual_capacity import UNVERIFIED
    parent, a, r = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125), _rc_count(_RC_B, 200)
    # The evidence names a second child that was not supplied: it cannot silently inflate the residual.
    omitted = _rc_assess(parent, [a], containment_evidence=_rc_contained(_RC_A),
                         child_set_evidence=_rc_complete(_RC_A, _RC_B))
    assert omitted.status == UNVERIFIED and omitted.reason == "child_set_mismatch"
    assert "not supplied" in omitted.explanation and _RC_B in omitted.explanation
    assert omitted.residual_planning_capacity is None
    # A supplied child the evidence does not name is also a mismatch.
    extra = _rc_assess(parent, [a, r], containment_evidence=_rc_contained(_RC_A, _RC_B),
                       non_overlap_evidence=((_RC_A, _RC_B, "p"),), child_set_evidence=_rc_complete(_RC_A))
    assert extra.status == UNVERIFIED and extra.reason == "child_set_mismatch"
    assert "not in the child-set evidence" in extra.explanation
    # Two evidence statements naming different sets are a conflict.
    conflicting = _rc_assess(parent, [a], containment_evidence=_rc_contained(_RC_A),
                             child_set_evidence=_rc_complete(_RC_A) + _rc_complete(_RC_A, _RC_B))
    assert conflicting.status == UNVERIFIED and conflicting.reason == "child_set_evidence_conflict"
    assert conflicting.residual_planning_capacity is None


def test_residual_2h_c_unresolved_child_eligibility_blocks_a_complete_residual():
    from app.reporting.residual_capacity import UNVERIFIED
    parent, a = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125)
    for basis in (None, "", "granted", "something_else"):
        unresolved = _rc_count(_RC_B, 100, basis=basis)
        result = _rc_assess(parent, [a, unresolved], containment_evidence=_rc_contained(_RC_A),
                            child_set_evidence=_rc_complete(_RC_A, _RC_B))
        assert result.status == UNVERIFIED and result.reason == "unresolved_child_eligibility", basis
        assert result.residual_planning_capacity is None and not result.resolved
        assert [c.subject_id for c in result.unresolved_children] == [_RC_B]
        assert _RC_B in result.explanation


def test_residual_2h_d_known_ineligible_children_do_not_block_when_the_set_is_complete():
    from app.reporting.residual_capacity import RESOLVED
    parent, a = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125)
    for basis in ("refused", "withdrawn", "superseded", "active", "undetermined", "recommendation_only"):
        known = _rc_count(_RC_R, 100, basis=basis)
        result = _rc_assess(parent, [a, known], containment_evidence=_rc_contained(_RC_A),
                            child_set_evidence=_rc_complete(_RC_A, _RC_R))
        assert result.status == RESOLVED and result.residual_planning_capacity == 375, basis
        assert [c.subject_id for c in result.subtracted_children] == [_RC_A]
        assert [e.child.subject_id for e in result.excluded_children] == [_RC_R]


def test_residual_2h_e_cross_site_subtraction_is_blocked():
    from app.reporting.residual_capacity import UNVERIFIED
    parent_id, child_id = "site:123:whole_site:Whole site", "site:999:phase:Phase 2"
    result = _rc_assess(_rc_count(parent_id, 500), [_rc_count(child_id, 125)],
                        containment_evidence=_rc_contained(child_id, parent=parent_id),
                        child_set_evidence=_rc_complete(child_id, parent=parent_id))
    assert result.status == UNVERIFIED and result.reason == "site_or_scope_incompatible"
    assert result.residual_planning_capacity is None and "site 999" in result.explanation


def test_residual_2h_f_invalid_scope_direction_and_unparseable_identity_are_blocked():
    import dataclasses
    from app.reporting.residual_capacity import RESOLVED, UNVERIFIED
    cases = [
        ("site:1:phase:Phase 2", "site:1:whole_site:Whole site"),                  # a whole site is not inside a phase
        ("site:1:plot:Plot 5", "site:1:phase:Phase 2"),                            # a plot cannot contain a phase
        (_RC_PARENT, "site:1:whole_site:Other"),                                   # a second whole-site scope
        (_RC_PARENT, "site:1:unclear:Unclear"),                                    # unclear scope
        (_RC_PARENT, "site:1:multiple_scopes:Multiple named scopes"),              # multi-scope application
        (_RC_PARENT, "not-a-site-identity"),                                       # unparseable child
        ("not-a-site-identity", _RC_A),                                            # unparseable parent
    ]
    for parent_id, child_id in cases:
        result = _rc_assess(_rc_count(parent_id, 500), [_rc_count(child_id, 125)],
                            containment_evidence=_rc_contained(child_id, parent=parent_id),
                            child_set_evidence=_rc_complete(child_id, parent=parent_id))
        assert result.status == UNVERIFIED and result.reason == "site_or_scope_incompatible", (parent_id, child_id)
        assert result.residual_planning_capacity is None
    # The identity and the recorded scope type must agree.
    disagree = dataclasses.replace(_rc_count("site:1:plot:Plot 5", 125), scope_type="phase")
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [disagree], containment_evidence=_rc_contained("site:1:plot:Plot 5"),
                        child_set_evidence=_rc_complete("site:1:plot:Plot 5"))
    assert result.status == UNVERIFIED and result.reason == "site_or_scope_incompatible"
    # A sub-phase inside a phase, and a plot inside a whole site, are valid directions.
    sub_phase = _rc_assess(_rc_count("site:1:phase:Phase 2", 180), [_rc_count("site:1:phase:Phase 2A", 72)],
                           containment_evidence=_rc_contained("site:1:phase:Phase 2A", parent="site:1:phase:Phase 2"),
                           child_set_evidence=_rc_complete("site:1:phase:Phase 2A", parent="site:1:phase:Phase 2"))
    assert sub_phase.status == RESOLVED and sub_phase.residual_planning_capacity == 108


def test_residual_2h_g_h_i_meaningless_provenance_is_rejected_everywhere():
    from app.reporting.residual_capacity import UNVERIFIED
    parent, a, b = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125), _rc_count(_RC_B, 100)
    for bad in _RC_BAD_PROVENANCE:
        containment = _rc_assess(parent, [a], containment_evidence=((_RC_A, _RC_PARENT, bad),),
                                 child_set_evidence=_rc_complete(_RC_A))
        assert containment.status == UNVERIFIED and containment.reason == "containment_not_established", bad
        overlap = _rc_assess(parent, [a, b], containment_evidence=_rc_contained(_RC_A, _RC_B),
                             non_overlap_evidence=((_RC_A, _RC_B, bad),), child_set_evidence=_rc_complete(_RC_A, _RC_B))
        assert overlap.status == UNVERIFIED and overlap.reason == "child_overlap_not_excluded", bad
        completeness = _rc_assess(parent, [a], containment_evidence=_rc_contained(_RC_A),
                                  child_set_evidence=_rc_complete(_RC_A, provenance=bad))
        assert completeness.status == UNVERIFIED and completeness.reason == "child_set_completeness_not_established", bad
        assert completeness.residual_planning_capacity is None


def test_residual_2h_j_meaningful_string_provenance_is_accepted():
    from app.reporting.residential_count import is_meaningful_provenance
    from app.reporting.residual_capacity import RESOLVED
    source = "Decision notice PL/2026/001, condition 4 phasing schedule"
    assert is_meaningful_provenance(source) and is_meaningful_provenance("  x  ")
    assert not any(is_meaningful_provenance(bad) for bad in _RC_BAD_PROVENANCE)
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125), _rc_count(_RC_B, 100)],
                        containment_evidence=tuple((child, _RC_PARENT, source) for child in (_RC_A, _RC_B)),
                        non_overlap_evidence=((_RC_A, _RC_B, source),),
                        child_set_evidence=_rc_complete(_RC_A, _RC_B, provenance=source))
    assert result.status == RESOLVED and result.residual_planning_capacity == 275


def test_residual_2h_k_gate1_phase_aggregation_still_accepts_sourced_and_rejects_malformed_provenance():
    from app.pipeline.phase_tracking import summarize_phase_units
    rows = [{"code": code, "kind": "phase", "status": "approved_commencement_unverified", "unit_count": units}
            for code, units in (("2", 180), ("3", 72))]
    for bad in _RC_BAD_PROVENANCE:
        assert summarize_phase_units(rows, non_overlap_evidence=(("2", "3", bad),))["approved_commencement_unverified"]["units"] is None
        assert "252" not in _position_reasons([_phase_row("2", 180), _phase_row("3", 72)],
                                              non_overlap_evidence=(("2", "3", bad),))
    good = "Approved boundary schedule rev B"
    assert summarize_phase_units(rows, non_overlap_evidence=(("2", "3", good),))["approved_commencement_unverified"]["units"] == 252
    assert "(252 units)" in _position_reasons([_phase_row("2", 180), _phase_row("3", 72)],
                                              non_overlap_evidence=(("2", "3", good),))


def test_residual_2h_l_consented_semantics_make_no_lapse_commencement_or_availability_claim():
    import app.reporting.residual_capacity as module
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125)], containment_evidence=_rc_contained(_RC_A),
                        child_set_evidence=_rc_complete(_RC_A))
    assert result.resolved and module.OPERATIVE_APPROVED_BASIS == "consented"
    claim = result.claim.lower()
    for word in ("lapse", "expiry", "commencement", "completion", "availability", "deliverability", "consented"):
        assert word in claim, word
    doc = module.__doc__.lower()
    for phrase in ("unexpired", "commenced", "deliverable", "same real-world development scope", "not solved"):
        assert phrase in doc, phrase
    assert not any(word in result.label().lower() for word in ("lapse", "commenc", "complet", "avail", "deliver"))


def test_residual_2h_m_vocabulary_matches_the_platform_it_reuses():
    import app.reporting.residual_capacity as module
    from app.pipeline.material_change import DECIDED_RECOMMENDATION_ONLY, DECIDED_REFUSED, DECIDED_UNDETERMINED, DECIDED_WITHDRAWN
    from app.reporting.scheme_reconciliation import SCOPE_PHASE, SCOPE_PLOT, SCOPE_WHOLE_SITE
    assert (module.SCOPE_WHOLE_SITE, module.SCOPE_PHASE, module.SCOPE_PLOT) == (SCOPE_WHOLE_SITE, SCOPE_PHASE, SCOPE_PLOT)
    assert module.KNOWN_INELIGIBLE_BASES == {
        "active", "superseded", DECIDED_REFUSED, DECIDED_WITHDRAWN, DECIDED_UNDETERMINED, DECIDED_RECOMMENDATION_ONLY}
    assert "consented" not in module.KNOWN_INELIGIBLE_BASES
    assert module._parse_subject("site:12:phase:Phase 2A") == ("12", "phase", "Phase 2A")
    assert module._parse_subject("site:x:phase:Phase 2A") is None and module._parse_subject("phase:2") is None



# --- Stage 2.5 preflight gate 3: operative supporting-source preference (support first) ---


def _cs_app(app_id, reference, total, *, scheme=True):
    return SimpleNamespace(id=app_id, reference=reference,
                           scheme_intelligence=SimpleNamespace(total_units_final=total) if scheme else None)


def _cs_count(value, source_ids, *, metric="total_residential", precision="EXACT", source_values=None):
    from app.reporting.residential_count import CountAssessment
    exact = precision == "EXACT"
    sources = tuple(SimpleNamespace(application_id=i, value=(source_values or {}).get(i, value)) for i in source_ids)
    return CountAssessment(scope_type="whole_site", scope_label="Whole site", subject_id="site:1:whole_site:Whole site",
                           metric=metric, precision=precision, value=value, lower=value if exact else None,
                           upper=value if exact else None, resolution="agreement" if exact else "portal_estimate",
                           confidence="high", sources=sources, basis="consented")


def _cs_select(count, applications, operative=None):
    from app.reporting.residential_count import select_count_supporting_source
    chosen = select_count_supporting_source(count, applications, operative_application_id=operative)
    return chosen.id if chosen is not None else None


def test_gate3_a_operative_supporter_is_preferred_over_alphabetical_first():
    apps = [_cs_app(1, "Z/CURRENT", 440), _cs_app(2, "A/OLD", 440)]
    count = _cs_count(440, (1, 2))
    assert _cs_select(count, apps, operative=1) == 1
    # Without an operative supporter the deterministic fallback is reference order, not authority.
    assert _cs_select(count, apps, operative=None) == 2


def test_gate3_b_non_supporting_operative_never_receives_attribution():
    apps = [_cs_app(1, "Z/CURRENT", 82), _cs_app(2, "A/OLD", 440)]
    assert _cs_select(_cs_count(440, (2,)), apps, operative=1) == 2
    # Even if the operative application is listed among the sources, its own different value disqualifies it.
    assert _cs_select(_cs_count(440, (1, 2), source_values={1: 82}), apps, operative=1) == 2
    # An application whose own total matches but which is not one of the count's sources does not support it.
    both_440 = [_cs_app(1, "Z/CURRENT", 440), _cs_app(2, "A/OLD", 440)]
    assert _cs_select(_cs_count(440, (2,)), both_440, operative=1) == 2


def test_gate3_c_multiple_agreeing_without_operative_use_a_deterministic_genuine_supporter():
    apps = [_cs_app(5, "B/2", 440), _cs_app(9, "A/1", 440)]
    count = _cs_count(440, (5, 9))
    assert _cs_select(count, apps) == 9 and _cs_select(count, list(reversed(apps))) == 9
    # An operative id that is not a supporter changes nothing.
    assert _cs_select(count, apps, operative=99) == 9
    # Equal references fall back to identifier order; the result is still the same for any input order.
    twins = [_cs_app(1, "M/1", 440), _cs_app(2, "M/1", 440)]
    twin_count = _cs_count(440, (1, 2))
    assert _cs_select(twin_count, twins) == _cs_select(twin_count, list(reversed(twins))) == 1


def test_gate3_d_single_supporter_is_selected():
    apps = [_cs_app(1, "Z/CURRENT", 82), _cs_app(2, "B/ONLY", 440)]
    assert _cs_select(_cs_count(440, (2,)), apps) == 2
    assert _cs_select(_cs_count(440, (2,)), apps, operative=2) == 2


def test_gate3_e_newer_non_supporter_cannot_steal_attribution():
    apps = [_cs_app(1, "Z/NEW", 82), _cs_app(2, "A/OLD", 440)]
    count = _cs_count(440, (2,))
    assert _cs_select(count, apps, operative=1) == 2 and _cs_select(count, apps) == 2


def test_gate3_f_selection_is_independent_of_input_order():
    import itertools
    apps = [_cs_app(1, "Z/CURRENT", 440), _cs_app(2, "A/OLD", 440), _cs_app(3, "M/MID", 440), _cs_app(4, "B/NO", 82)]
    for operative in (None, 1, 2, 3, 4, 99):
        results = set()
        for ordered_apps in itertools.permutations(apps):
            for source_ids in ((1, 2, 3), (3, 2, 1), (2, 1, 3)):
                results.add(_cs_select(_cs_count(440, source_ids), list(ordered_apps), operative=operative))
        assert len(results) == 1, operative


def test_gate3_g_metric_separation_and_count_support_are_required():
    apps = [_cs_app(1, "Z/CURRENT", 440), _cs_app(2, "A/OLD", 440)]
    # A private or affordable count is never attributed to a source through the total-units field.
    for metric in ("private_units", "affordable_units"):
        assert _cs_select(_cs_count(440, (1, 2), metric=metric), apps, operative=1) is None
    assert _cs_select(_cs_count(440, (1, 2), metric="all_use_units"), apps, operative=1) == 1
    # Only an exact count can be attributed; no count means no source.
    assert _cs_select(_cs_count(440, (1, 2), precision="APPROXIMATE"), apps, operative=1) is None
    assert _cs_select(_cs_count(None, (1, 2), precision="UNKNOWN"), apps, operative=1) is None
    assert _cs_select(None, apps, operative=1) is None
    # An application with no extracted scheme intelligence supports nothing.
    assert _cs_select(_cs_count(440, (1,)), [_cs_app(1, "Z", None, scheme=False)], operative=1) is None


def test_gate3_shared_rule_is_the_single_implementation():
    import app.policy.buyer_matching as buyer_matching
    import app.reporting.residential_count as residential_count
    import app.reporting.site_profile as site_profile
    assert (buyer_matching.select_count_supporting_source is residential_count.select_count_supporting_source
            is site_profile.select_count_supporting_source)


def _gate3_facts(apps, **kwargs):
    return build_planning_delivery_matching_facts_from_operative(build_operative_planning_facts(apps), apps, **kwargs)


def test_gate3_i_buyer_matching_reads_development_type_from_the_operative_supporter(session):
    site = scheme(session)
    old = application(session, site, "A/OLD", 440, date="2026-01-01")
    current = application(session, site, "Z/CURRENT", 440, date="2026-03-01")
    old.scheme_intelligence.development_type = "retirement_living"
    current.scheme_intelligence.development_type = "houses"
    session.flush()
    for ordered in ([old, current], [current, old]):
        facts = _gate3_facts(ordered)
        assert facts.unit_count == 440
        # The alphabetically-first agreeing source (A/OLD, a specialist type) must not win over the operative one.
        assert facts.development_type_raw == "houses" and facts.is_specialist_development is False


def test_gate3_b_buyer_matching_never_borrows_from_a_non_supporting_operative_application(session):
    site = scheme(session)
    supporter = application(session, site, "A/OLD", 440, date="2026-01-01")
    operative = application(session, site, "Z/CURRENT", None, date="2026-03-01")   # latest grant, no extracted count
    supporter.scheme_intelligence.development_type = "houses"
    operative.scheme_intelligence.development_type = "retirement_living"
    session.flush()
    facts = _gate3_facts([supporter, operative])
    assert facts.unit_count == 440
    assert facts.development_type_raw == "houses" and facts.is_specialist_development is False


def test_gate3_e_newer_pending_application_does_not_steal_buyer_matching_attribution(session):
    site = scheme(session)
    old = application(session, site, "A/OLD", 440, date="2026-01-01")
    newer = application(session, site, "Z/NEW", 82, decision=None)
    old.scheme_intelligence.development_type = "houses"
    newer.scheme_intelligence.development_type = "retirement_living"
    session.flush()
    facts = _gate3_facts([old, newer])
    assert facts.unit_count == 440
    assert facts.development_type_raw == "houses" and facts.is_specialist_development is False


def test_gate3_h_ah_identity_is_independent_of_count_source_selection(session):
    site = scheme(session)
    old = application(session, site, "A/OLD", 440, date="2026-01-01")
    current = application(session, site, "Z/CURRENT", 440, date="2026-03-01")
    old.scheme_intelligence.development_type = "retirement_living"
    current.scheme_intelligence.development_type = "houses"
    session.flush()
    default = _gate3_facts([old, current])
    for reference in ("A/OLD", "Z/CURRENT"):
        facts = _gate3_facts([old, current], application_reference=reference)
        # Choosing which application the AH figure belongs to never changes the count source.
        assert facts.development_type_raw == default.development_type_raw == "houses"
        assert facts.unit_count == default.unit_count == 440



# --- Stage 2.5A: buyer discovery envelope & POSSIBLE_FIT (policy v6) ---------
# Preferred 50-100 (Nesten, soft scale) -> discovery 45-110 (10%, rounded outward).

from dataclasses import replace as _replace
from types import SimpleNamespace as _NS

from app.policy import buyer_matching as _bm
from app.policy.buyer_matching import (
    POSSIBLE_FIT, STRONG_FIT, INSUFFICIENT_EVIDENCE, MatchingFacts, PLANNING_DELIVERY,
    B2MatchingContext, discovery_bounds,
)
from app.reporting.residential_count import CountAssessment

_OUTSIDE = "outside this buyer's discovery range"


def _s25_facts(**overrides):
    base = dict(opportunity_type=PLANNING_DELIVERY, unit_count=75, development_type_raw="houses",
                is_specialist_development=False, affordable_percentage=30.0, affordable_percentage_trusted=True,
                affordable_unit_count=None, planning_state="permission_granted", has_identified_planning_activity=True,
                has_phasing_evidence=False, matched_to_site=True)
    base.update(overrides)
    return MatchingFacts(**base)


def _range_facts(lower, upper, precision="RANGE"):
    count = CountAssessment(scope_type="whole_site", scope_label="Whole site", precision=precision,
                            value=lower, lower=lower, upper=upper, resolution="supported_range")
    return _s25_facts(unit_count=lower, count_assessment=count)


@pytest.mark.parametrize("minimum,maximum,expected", [
    (50, 100, (45, 110)),
    (51, 99, (45, 109)),      # 45.9 -> 45 and 108.9 -> 109: rounded outward, never inward
    (100, 300, (90, 330)),
    (200, 500, (180, 550)),
    (None, 100, (None, 110)),  # maximum-only: no invented lower bound
    (50, None, (45, None)),    # minimum-only: no invented upper bound
    (None, None, (None, None)),
])
def test_s25a_discovery_bounds_are_ten_percent_rounded_outward(minimum, maximum, expected):
    assert _bm.DEFAULT_DISCOVERY_TOLERANCE_PERCENT == 10
    assert discovery_bounds(minimum, maximum) == expected


@pytest.mark.parametrize("units,expected", [
    (75, STRONG_FIT), (50, STRONG_FIT), (100, STRONG_FIT),
    (45, POSSIBLE_FIT), (49, POSSIBLE_FIT), (101, POSSIBLE_FIT), (105, POSSIBLE_FIT), (110, POSSIBLE_FIT),
    (44, INSUFFICIENT_EVIDENCE), (111, INSUFFICIENT_EVIDENCE), (300, INSUFFICIENT_EVIDENCE),
])
def test_s25a_exact_counts_against_preferred_and_discovery(units, expected):
    fit = assess_buyer_fit(NESTEN_HOMES, _s25_facts(unit_count=units))
    assert fit.classification == expected
    assert fit.classification != NOT_SUITABLE
    if expected == POSSIBLE_FIT:
        side = "below" if units < 50 else "above"
        assert any(f"{units:,} homes is slightly {side}" in m and "preferred range (50-100 homes)" in m
                   and "discovery range (45-110 homes)" in m for m in fit.matches)
    if expected == INSUFFICIENT_EVIDENCE:
        # A KNOWN count outside discovery: investigate for sub-scope, never "count unknown".
        assert fit.is_investigative_exception
        assert any(_OUTSIDE in i and "sub-scope" in i and f"{units:,} homes" in i for i in fit.investigate)
        assert not any("No trusted unit count" in u or "does not establish" in u for u in fit.unknown)


@pytest.mark.parametrize("lower,upper,expected,kind", [
    (100, 102, POSSIBLE_FIT, "possible"),
    (48, 52, POSSIBLE_FIT, "possible"),
    (105, 110, POSSIBLE_FIT, "possible"),
    (105, 115, INSUFFICIENT_EVIDENCE, "crossing"),
    (40, 60, INSUFFICIENT_EVIDENCE, "crossing"),
    (90, 120, INSUFFICIENT_EVIDENCE, "crossing"),
    (40, 44, INSUFFICIENT_EVIDENCE, "outside"),
    (111, 120, INSUFFICIENT_EVIDENCE, "outside"),
    (60, 80, STRONG_FIT, "preferred"),
])
def test_s25a_range_evidence_uses_supported_bounds(lower, upper, expected, kind):
    fit = assess_buyer_fit(NESTEN_HOMES, _range_facts(lower, upper))
    assert fit.classification == expected
    assert fit.classification != NOT_SUITABLE and fit.is_investigative_exception
    if kind == "possible":
        assert any("not fully within" in m and "discovery range (45-110 homes)" in m for m in fit.matches)
    elif kind == "crossing":
        # Uncertain evidence crossing a discovery boundary - distinct wording.
        assert any("does not establish whether scale is within" in u for u in fit.unknown)
        assert not any(_OUTSIDE in i for i in fit.investigate)
    elif kind == "outside":
        assert any(_OUTSIDE in i for i in fit.investigate)
        assert not any("does not establish" in u for u in fit.unknown)


def test_s25a_rounded_scalar_cannot_override_range_evidence():
    count = CountAssessment(scope_type="whole_site", scope_label="Whole site", precision="APPROXIMATE",
                            value=100, lower=100, upper=102, resolution="immaterial_variance")
    fit = assess_buyer_fit(NESTEN_HOMES, _s25_facts(unit_count=100, count_assessment=count))
    assert fit.classification == POSSIBLE_FIT  # never STRONG from the rounded display value 100


def test_s25a_material_conflict_and_unknown_never_possible():
    conflict = CountAssessment(scope_type="whole_site", scope_label="Whole site", lower=100, upper=180,
                               resolution="material_conflict", confidence="low")
    for facts in (_s25_facts(unit_count=100, count_assessment=conflict), _s25_facts(unit_count=None)):
        fit = assess_buyer_fit(NESTEN_HOMES, facts)
        assert fit.classification == INSUFFICIENT_EVIDENCE
        assert any("No trusted unit count" in u for u in fit.unknown)
        assert not any("discovery range" in m for m in fit.matches)


@pytest.mark.parametrize("units,expected", [(45, POSSIBLE_FIT), (44, INSUFFICIENT_EVIDENCE), (109, POSSIBLE_FIT),
                                            (110, INSUFFICIENT_EVIDENCE), (51, STRONG_FIT), (99, STRONG_FIT)])
def test_s25a_outward_rounded_boundaries_on_an_uneven_preferred_range(units, expected):
    policy = _replace(NESTEN_HOMES, target_unit_min=51, target_unit_max=99)
    assert assess_buyer_fit(policy, _s25_facts(unit_count=units)).classification == expected


@pytest.mark.parametrize("affordable,expected_not_suitable", [(49, True), (47, True), (45, True), (50, False), (120, False)])
def test_s25a_explicit_hard_minimum_is_never_weakened_by_discovery_tolerance(affordable, expected_not_suitable):
    assert HOUSING_ASSOCIATION.below_minimum_scale_is_exclusion and HOUSING_ASSOCIATION.target_unit_min == 50
    fit = assess_buyer_fit(HOUSING_ASSOCIATION, _s25_facts(affordable_unit_count=affordable))
    assert (fit.classification == NOT_SUITABLE) is expected_not_suitable
    if expected_not_suitable:
        assert any("below this buyer's minimum requirement of 50" in r for r in fit.does_not_match)


def test_s25a_hard_minimum_applies_to_range_evidence_at_the_stated_minimum():
    policy = _replace(NESTEN_HOMES, below_minimum_scale_is_exclusion=True)
    assert assess_buyer_fit(policy, _range_facts(40, 49)).classification == NOT_SUITABLE
    assert assess_buyer_fit(policy, _s25_facts(unit_count=47)).classification == NOT_SUITABLE
    assert assess_buyer_fit(policy, _s25_facts(unit_count=105)).classification == POSSIBLE_FIT


def test_s25a_hard_exclusions_outrank_possible_scale():
    from app.policy.buyer_profiles import GEOGRAPHY_COUNCILS
    geo = _replace(NESTEN_HOMES, geography_scope=GEOGRAPHY_COUNCILS, geography_councils=frozenset({"bury"}))
    outside = assess_buyer_fit(geo, _s25_facts(unit_count=105), context=B2MatchingContext(council_code="trafford"))
    assert outside.classification == NOT_SUITABLE
    inside = assess_buyer_fit(geo, _s25_facts(unit_count=105), context=B2MatchingContext(council_code="bury"))
    assert inside.classification != NOT_SUITABLE
    assert any("discovery range (45-110 homes)" in m for m in inside.matches)
    specialist = assess_buyer_fit(NESTEN_HOMES, _s25_facts(unit_count=105, is_specialist_development=True,
                                                          development_type_raw="retirement_living"))
    assert specialist.classification == NOT_SUITABLE
    wholly_affordable = assess_buyer_fit(NESTEN_HOMES, _s25_facts(unit_count=105, affordable_percentage=100.0))
    assert wholly_affordable.classification == NOT_SUITABLE


def test_s25a_overall_precedence_strong_possible_and_unresolved_evidence():
    assert assess_buyer_fit(NESTEN_HOMES, _s25_facts(unit_count=80)).classification == STRONG_FIT
    assert assess_buyer_fit(NESTEN_HOMES, _s25_facts(unit_count=105)).classification == POSSIBLE_FIT
    unresolved = assess_buyer_fit(NESTEN_HOMES, _s25_facts(unit_count=105, is_specialist_development=None,
                                                          development_type_raw=None))
    assert unresolved.classification == INSUFFICIENT_EVIDENCE  # possible scale never hides a blocking gap


def test_s25a_feed_surfaces_possible_between_strong_and_insufficient(monkeypatch):
    from app.reporting import opportunity_feed
    from app.policy import buyer_matching_b2_context, buyer_profile_store
    order = ["insufficient", "not_suitable", "possible_b", "strong", "exception", "possible_a"]
    fits = {"strong": (STRONG_FIT, False), "possible_a": (POSSIBLE_FIT, False), "possible_b": (POSSIBLE_FIT, True),
            "exception": (INSUFFICIENT_EVIDENCE, True), "insufficient": (INSUFFICIENT_EVIDENCE, False),
            "not_suitable": (NOT_SUITABLE, False)}
    cards = [{"title": name, "opportunity_type": PLANNING_DELIVERY, "matching_facts": object(), "params": {"site_id": i}}
             for i, name in enumerate(order)]
    monkeypatch.setattr(buyer_profile_store, "get_buyer_profile_dataclass", lambda session, key: NESTEN_HOMES)
    monkeypatch.setattr(opportunity_feed, "_attach_planning_delivery_matching_facts", lambda session, delivery: None)
    by_site = {i: name for i, name in enumerate(order)}
    monkeypatch.setattr(buyer_matching_b2_context, "evaluate_buyer_fit",
                        lambda session, profile, facts, site_id=None, allocation_id=None:
                        _NS(classification=fits[by_site[site_id]][0], is_investigative_exception=fits[by_site[site_id]][1]))
    ordered, counts = opportunity_feed._buyer_selection(None, [], cards, 10, "nesten_homes")
    assert [c["title"] for c in ordered] == ["strong", "possible_b", "possible_a", "exception", "insufficient"]
    assert counts["excluded_not_suitable"] == 1
    again, _ = opportunity_feed._buyer_selection(None, [], cards, 10, "nesten_homes")
    assert [c["title"] for c in again] == [c["title"] for c in ordered]


def test_s25a_possible_badge_and_label_render():
    # Read the presentation module's literal mappings without importing Streamlit.
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app" / "ui" / "shell.py").read_text(encoding="utf-8"))
    literals = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name) and t.id in ("BUYER_FIT_BADGE_KIND", "_BADGE_KIND_STYLE")}
    kind = literals["BUYER_FIT_BADGE_KIND"][POSSIBLE_FIT]
    assert literals["_BADGE_KIND_STYLE"][kind]["label"] == "Possible fit"
    assert POSSIBLE_FIT.replace("_", " ").title() == "Possible Fit"


def test_s25a_onboarding_counts_possible_separately():
    from app.policy import buyer_profile_store
    from app.policy.buyer_profile_store import OnboardingBaselineResult
    result = OnboardingBaselineResult(opportunities_reviewed=3, strong_fit=1, not_suitable=0, insufficient_evidence=1,
                                      investigative_exceptions=0, summary_line="", possible_fit=1)
    assert result.possible_fit == 1 and result.strong_fit == 1 and result.insufficient_evidence == 1
    source = inspect_source(buyer_profile_store)
    assert "elif assessment.classification == POSSIBLE_FIT:" in source and "possible_fit={possible_fit}" in source


def test_s25a_agent_prompt_carries_deterministic_possible_fit():
    from app.policy.agent_evaluation_prompt import PromptContext, render_prompt
    def ctx(classification):
        return PromptContext(buyer_key="nesten_homes", acquisition_type="LAND_SITE_ACQUISITION", opportunity_id="x",
                             opportunity_type=PLANNING_DELIVERY, mandate_interpretation_lines=(),
                             buyer_fit_classification=classification, buyer_fit_is_investigative_exception=False,
                             buyer_fit_matches=(), buyer_fit_does_not_match=(), buyer_fit_unknown=(),
                             buyer_fit_investigate=(), reference_tokens={})
    possible = render_prompt(ctx(POSSIBLE_FIT))
    assert "- classification: POSSIBLE_FIT" in possible
    assert "NOT verified within its preferred range" in possible and "Do not treat or describe it as a strong" in possible
    # Other classifications render byte-identically to before (no new line).
    assert "POSSIBLE_FIT is deterministic" not in render_prompt(ctx(STRONG_FIT))
    # The model's output schema carries no buyer-fit classification to upgrade.
    from app.policy import agent_evaluation_result
    assert "buyer_fit_classification" not in inspect_source(agent_evaluation_result)


def inspect_source(module):
    import inspect
    return inspect.getsource(module)


def test_s25a_fingerprint_ownership(monkeypatch):
    from app.policy import buyer_profile_store
    from app.reporting.opportunity_universe import compute_opportunity_fingerprint
    assert _bm.BUYER_MATCHING_POLICY_VERSION == 6
    v6 = buyer_profile_store.compute_buyer_mandate_fingerprint(NESTEN_HOMES)
    fields = {"opportunity_type": PLANNING_DELIVERY, "unit_count": 105, "development_type_raw": "houses"}
    opportunity_v6 = compute_opportunity_fingerprint(fields)
    monkeypatch.setattr(buyer_profile_store, "BUYER_MATCHING_POLICY_VERSION", 5)
    assert buyer_profile_store.compute_buyer_mandate_fingerprint(NESTEN_HOMES) != v6
    assert compute_opportunity_fingerprint(fields) == opportunity_v6  # policy version never enters it
    # The agent-evaluation input fingerprint hashes the mandate fingerprint, the
    # buyer-fit classification and the policy version itself.
    from app.policy import agent_evaluation_persistence
    src = inspect_source(agent_evaluation_persistence)
    assert '"buyer_mandate_matching_fingerprint": mandate_fingerprint' in src
    assert '"classification": buyer_fit_assessment.classification' in src
    assert '"buyer_matching_policy_version": BUYER_MATCHING_POLICY_VERSION' in src



# --- Stage 2.5A v6 hardening: N1-B (affordable % non-blocking) + N2-B ----------
# Through the REAL operative matching-facts builder (the live feed path).

from app.policy.buyer_matching import _corroborated_development_type

_AFFORDABLE_UNKNOWN = "Affordable housing proportion has not been confirmed - not assumed to be 0%."
_AFFORDABLE_INVESTIGATE = "Confirm the affordable housing proportion and whether the scheme is affordable-led."
_DEV_TYPE_UNKNOWN = ("Development type has not been established with enough confidence to confirm this is "
                     "general-needs housing.")


def _live_facts(apps):
    return build_planning_delivery_matching_facts_from_operative(build_operative_planning_facts(apps), apps)


def _why(fit):
    return f"{fit.classification}: unknown={fit.unknown} does_not_match={fit.does_not_match}"


@pytest.mark.parametrize("units,expected", [(75, "STRONG_FIT"), (105, "POSSIBLE_FIT")])
def test_n1_untrusted_affordable_percentage_is_visible_but_not_blocking(session, units, expected):
    site = scheme(session)
    apps = [application(session, site, f"FULL/{units}", units)]
    facts = _live_facts(apps)
    assert facts.unit_count == units and facts.development_type_raw == "houses"
    assert facts.affordable_percentage_trusted is False and facts.affordable_percentage is None
    fit = assess_buyer_fit(NESTEN_HOMES, facts)
    assert fit.classification == expected, _why(fit)
    assert _AFFORDABLE_UNKNOWN in fit.unknown           # never silently assumed 0%
    assert _AFFORDABLE_INVESTIGATE in fit.investigate   # gap stays investigable
    assert facts.affordable_percentage is None          # None never becomes 0
    assert not fit.does_not_match                       # missing % is not a mismatch either way
    assert not any("affordable" in m.lower() for m in fit.matches)  # no affordable claim made


def test_n1_positive_wholly_affordable_exclusion_still_hard():
    from app.policy.buyer_matching import MatchingFacts, PLANNING_DELIVERY
    facts = MatchingFacts(opportunity_type=PLANNING_DELIVERY, unit_count=75, development_type_raw="houses",
                          is_specialist_development=False, affordable_percentage=100.0, affordable_percentage_trusted=True,
                          affordable_unit_count=75, planning_state="permission_granted",
                          has_identified_planning_activity=True, has_phasing_evidence=False, matched_to_site=True)
    fit = assess_buyer_fit(NESTEN_HOMES, facts)
    assert fit.classification == NOT_SUITABLE
    assert any("wholly" in d and "100%" in d for d in fit.does_not_match)


@pytest.mark.parametrize("affordable_units,expected", [(None, "INSUFFICIENT_EVIDENCE"), (49, "NOT_SUITABLE")])
def test_n1_rp_affordable_quantum_requirements_unchanged(affordable_units, expected):
    from app.policy.buyer_matching import MatchingFacts, PLANNING_DELIVERY
    facts = MatchingFacts(opportunity_type=PLANNING_DELIVERY, unit_count=150, development_type_raw="houses",
                          is_specialist_development=False, affordable_percentage=None, affordable_percentage_trusted=False,
                          affordable_unit_count=affordable_units, planning_state="permission_granted",
                          has_identified_planning_activity=True, has_phasing_evidence=False, matched_to_site=True)
    fit = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    assert fit.classification == expected, _why(fit)


def test_n1_rp_with_qualified_affordable_count_is_not_blocked_by_percentage_alone():
    from app.policy.buyer_matching import MatchingFacts, PLANNING_DELIVERY
    facts = MatchingFacts(opportunity_type=PLANNING_DELIVERY, unit_count=150, development_type_raw="houses",
                          is_specialist_development=False, affordable_percentage=None, affordable_percentage_trusted=False,
                          affordable_unit_count=60, planning_state="permission_granted",
                          has_identified_planning_activity=True, has_phasing_evidence=False, matched_to_site=True)
    fit = assess_buyer_fit(HOUSING_ASSOCIATION, facts)
    assert fit.classification == "STRONG_FIT", _why(fit)
    assert _AFFORDABLE_UNKNOWN in fit.unknown


@pytest.mark.parametrize("affordable_units,expected", [(None, "INSUFFICIENT_EVIDENCE"), (60, "STRONG_FIT")])
def test_n1_rp_acquisition_type_still_requires_trusted_affordable_quantum(affordable_units, expected):
    from app.policy.buyer_matching import MatchingFacts, PLANNING_DELIVERY, B2MatchingContext
    facts = MatchingFacts(opportunity_type=PLANNING_DELIVERY, unit_count=150, development_type_raw="houses",
                          is_specialist_development=False, affordable_percentage=None, affordable_percentage_trusted=False,
                          affordable_unit_count=affordable_units, planning_state="permission_granted",
                          has_identified_planning_activity=True, has_phasing_evidence=False, matched_to_site=True)
    fit = assess_buyer_fit(HOUSING_ASSOCIATION, facts, context=B2MatchingContext(council_code="bury"))
    package_reasons = [r for r in fit.matches + fit.unknown if "affordable-housing-package" in r]
    assert package_reasons, _why(fit)
    assert fit.classification == expected, _why(fit)
    if affordable_units is None:
        assert any("affordable-housing-package" in u for u in fit.unknown)
    else:
        assert any("affordable-housing-package" in m for m in fit.matches)
        assert _AFFORDABLE_UNKNOWN in fit.unknown  # still visible, no longer a second blocker


def test_n1_strategic_land_affordable_treatment_unchanged():
    from app.policy.buyer_matching import MatchingFacts
    from app.policy.buyer_profiles import STRATEGIC_LAND_BUYER
    facts = MatchingFacts(opportunity_type="strategic_land", unit_count=3500, development_type_raw="residential",
                          is_specialist_development=None, affordable_percentage=None, affordable_percentage_trusted=False,
                          affordable_unit_count=None, planning_state="adopted_allocation",
                          has_identified_planning_activity=False, has_phasing_evidence=False, matched_to_site=False)
    fit = assess_buyer_fit(STRATEGIC_LAND_BUYER, facts)
    assert fit.classification == "STRONG_FIT", _why(fit)
    assert any("strategic land allocation - not assumed to be 0%" in u for u in fit.unknown)
    assert _AFFORDABLE_INVESTIGATE not in fit.investigate


def _approximate_apps(session, types, order=(0, 1, 2), values=(100, 101, 102)):
    site = scheme(session)
    apps = [application(session, site, f"FULL/{n}", n) for n in values]
    for app, dev in zip(apps, types):
        app.scheme_intelligence.development_type = dev
    session.flush()
    return [apps[i] for i in order]


def test_n2_unanimous_supporters_corroborate_development_type(session):
    apps = _approximate_apps(session, ["houses", "houses", "houses"])
    facts = _live_facts(apps)
    assert facts.count_assessment.resolution == "immaterial_variance"
    assert facts.development_type_raw == "houses" and facts.is_specialist_development is False
    fit = assess_buyer_fit(NESTEN_HOMES, facts)
    # Scale is POSSIBLE (100-102 within discovery, not wholly preferred); development
    # type no longer blocks; the affordable gap stays visible and non-blocking.
    assert fit.classification == "POSSIBLE_FIT", _why(fit)
    assert _DEV_TYPE_UNKNOWN not in fit.unknown and _AFFORDABLE_UNKNOWN in fit.unknown


@pytest.mark.parametrize("types", [["houses", "apartments", "houses"], ["houses", None, "houses"],
                                   ["houses", "  ", "houses"]])
def test_n2_disagreement_or_missing_type_fails_closed(session, types):
    facts = _live_facts(_approximate_apps(session, types))
    assert facts.development_type_raw is None and facts.is_specialist_development is None
    fit = assess_buyer_fit(NESTEN_HOMES, facts)
    assert fit.classification == "INSUFFICIENT_EVIDENCE" and _DEV_TYPE_UNKNOWN in fit.unknown


def test_n2_input_order_does_not_change_result(session):
    apps = _approximate_apps(session, ["houses"] * 3)  # one evidence set, two input orders
    forward = _live_facts(apps)
    reverse = _live_facts(list(reversed(apps)))
    assert forward.development_type_raw == reverse.development_type_raw == "houses"


def test_n2_operative_preference_is_provenance_only_and_requires_support(session):
    apps = _approximate_apps(session, ["houses", "houses", "houses"])
    assessment = count_assessment_for_facts(build_operative_planning_facts(apps))
    by_id = {a.id: a for a in apps}
    for app in apps:
        # The value never changes; an operative SUPPORTER is preferred for provenance.
        result = _corroborated_development_type(assessment, by_id, operative_application_id=app.id)
        assert result.value == "houses" and result.provenance_reference == app.reference
    # A non-supporting "operative" application supplies neither value nor provenance.
    outsider = SimpleNamespace(id=-1, reference="ZZZ", scheme_intelligence=SimpleNamespace(development_type="retirement_living"))
    result = _corroborated_development_type(assessment, {**by_id, -1: outsider}, operative_application_id=-1)
    assert result.value == "houses" and result.provenance_reference == min(a.reference for a in apps)
    # A supporter whose application is missing fails closed rather than being skipped.
    assert _corroborated_development_type(assessment, {a.id: a for a in apps[:2]}) is None


def test_n2_values_compared_as_stored_without_collapsing_representations(session):
    # No shared domain normaliser exists for development type; differing stored
    # representations are not treated as agreement (documented limitation).
    facts = _live_facts(_approximate_apps(session, ["houses", "Houses", "houses"]))
    assert facts.development_type_raw is None


@pytest.mark.parametrize("values", [(200, 201, 202), (100, 102)])
def test_n2_no_new_tolerance_beyond_the_accepted_set(session, values):
    facts = _live_facts(_approximate_apps(session, ["houses"] * len(values), order=tuple(range(len(values))), values=values))
    assert facts.count_assessment.resolution == "material_conflict"
    assert facts.development_type_raw is None


def test_n2_value_only_no_cross_field_borrowing(session):
    apps = _approximate_apps(session, ["houses"] * 3)
    for app in apps:
        app.scheme_intelligence.affordable_percentage_final = 35.0
        app.scheme_intelligence.affordable_units_final = 35
    session.flush()
    facts = _live_facts(apps)
    assert facts.development_type_raw == "houses"
    result = _corroborated_development_type(facts.count_assessment, {a.id: a for a in apps})
    assert type(result)._fields == ("value", "provenance_reference")  # value + reference only, never a row
    assert isinstance(result.value, str) and isinstance(result.provenance_reference, str)
    # Corroboration changes development type ONLY: every affordable fact is identical
    # to the same evidence without corroboration (one supporter's type removed).
    apps[1].scheme_intelligence.development_type = None
    session.flush()
    uncorroborated = _live_facts(apps)
    assert uncorroborated.development_type_raw is None
    for field in ("affordable_percentage", "affordable_percentage_trusted", "affordable_unit_count", "unit_count"):
        assert getattr(facts, field) == getattr(uncorroborated, field)
    assert facts.affordable_percentage is None and facts.affordable_percentage_trusted is False


def test_n2_hard_exclusion_outranks_corroborated_scale_and_type(session):
    facts = _live_facts(_approximate_apps(session, ["retirement_living"] * 3))
    assert facts.development_type_raw == "retirement_living" and facts.is_specialist_development is True
    fit = assess_buyer_fit(NESTEN_HOMES, facts)
    assert fit.classification == NOT_SUITABLE, _why(fit)


def test_n2_exact_count_gate3_selection_unchanged(session):
    site = scheme(session)
    a = application(session, site, "A/OLD", 440, date="2026-01-01")
    b = application(session, site, "Z/CURRENT", 440, date="2026-03-01")
    a.scheme_intelligence.development_type = "retirement_living"
    b.scheme_intelligence.development_type = "houses"
    session.flush()
    facts = _live_facts([a, b])
    assert facts.unit_count == 440 and facts.development_type_raw == "houses"
    assert _corroborated_development_type(facts.count_assessment, {a.id: a, b.id: b}) is None  # exact: not this path

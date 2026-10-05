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
    ("APPROXIMATE", 100, 102, "INSUFFICIENT_EVIDENCE"),
    ("RANGE", 45, 55, "INSUFFICIENT_EVIDENCE"),
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


# --- Stage 2.5 preflight gate 2: residual planning-capacity safety contract ---

_RC_PARENT = "site:1:whole_site:Whole site"
_RC_A = "site:1:phase:Phase 2"
_RC_B = "site:1:phase:Phase 3"


def _rc_count(subject, value, *, metric="total_residential", precision="EXACT", basis="consented",
              resolution=None):
    from app.reporting.residential_count import CountAssessment
    exact = precision == "EXACT"
    return CountAssessment(
        scope_type="whole_site" if subject == _RC_PARENT else "phase", scope_label=subject.split(":")[-1],
        subject_id=subject, metric=metric, precision=precision, value=value,
        lower=value if exact else None, upper=value if exact else None,
        resolution=resolution or ("agreement" if exact else "portal_estimate"),
        confidence="high" if exact else "low", basis=basis)


def _rc_conflict_parent(lower=500, upper=650):
    from app.reporting.residential_count import CountAssessment
    return CountAssessment(scope_type="whole_site", scope_label="Whole site", subject_id=_RC_PARENT,
                           precision="UNKNOWN", lower=lower, upper=upper, resolution="material_conflict",
                           confidence="low", basis="consented")


def _rc_contained(*children):
    return tuple((child, _RC_PARENT, "synthetic containment provenance") for child in children)


def _rc_assess(parent, children, **evidence):
    from app.reporting.residual_capacity import assess_residual_planning_capacity
    return assess_residual_planning_capacity(parent, children, **evidence)


def test_residual_a_simple_safe_case_resolves_planning_capacity():
    from app.reporting.residual_capacity import RESOLVED
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125)], containment_evidence=_rc_contained(_RC_A))
    assert result.status == RESOLVED and result.resolved
    assert result.residual_planning_capacity == 375 and result.reason == "resolved"
    assert result.metric == "total_residential"
    assert [c.subject_id for c in result.subtracted_children] == [_RC_A]
    assert result.containment_provenance == ((_RC_A, _RC_PARENT),)
    assert result.parent.exact_value == 500


@pytest.mark.parametrize("parent_metric,child_metric", [
    ("total_residential", "private_units"), ("private_units", "total_residential"),
    ("total_residential", "affordable_units"), ("total_residential", "all_use_units"),
])
def test_residual_b_metric_mismatch_is_never_converted(parent_metric, child_metric):
    from app.reporting.residual_capacity import UNVERIFIED
    result = _rc_assess(_rc_count(_RC_PARENT, 500, metric=parent_metric),
                        [_rc_count(_RC_A, 125, metric=child_metric)], containment_evidence=_rc_contained(_RC_A))
    assert result.status == UNVERIFIED and result.reason == "metric_mismatch"
    assert result.residual_planning_capacity is None and not result.resolved


def test_residual_c_containment_must_be_explicitly_evidenced():
    from app.reporting.residual_capacity import UNVERIFIED
    parent, child = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125)
    for evidence in ((), ((_RC_A, _RC_PARENT, ""),), ((_RC_A, _RC_PARENT, None),),
                     ((_RC_B, _RC_PARENT, "p"),), ((_RC_A, "site:9:whole_site:Whole site", "p"),),
                     ((_RC_PARENT, _RC_A, "p"),)):
        result = _rc_assess(parent, [child], containment_evidence=evidence)
        assert result.status == UNVERIFIED and result.reason == "containment_not_established", evidence
        assert result.residual_planning_capacity is None


def test_residual_d_children_that_may_overlap_withhold_the_residual():
    from app.reporting.residual_capacity import UNVERIFIED
    parent, children = _rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125), _rc_count(_RC_B, 100)]
    for non_overlap in ((), ((_RC_A, "site:1:phase:Phase 9", "p"),), ((_RC_A, _RC_B, ""),), ((_RC_A, _RC_B, None),)):
        result = _rc_assess(parent, children, containment_evidence=_rc_contained(_RC_A, _RC_B),
                            non_overlap_evidence=non_overlap)
        assert result.status == UNVERIFIED and result.reason == "child_overlap_not_excluded", non_overlap
        assert result.residual_planning_capacity is None


def test_residual_e_explicitly_non_overlapping_children_resolve_and_order_does_not_matter():
    from app.reporting.residual_capacity import RESOLVED
    parent, a, b = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125), _rc_count(_RC_B, 100)
    forward = _rc_assess(parent, [a, b], containment_evidence=_rc_contained(_RC_A, _RC_B),
                         non_overlap_evidence=((_RC_A, _RC_B, "synthetic non-overlap provenance"),))
    backward = _rc_assess(parent, [b, a], containment_evidence=tuple(reversed(_rc_contained(_RC_A, _RC_B))),
                          non_overlap_evidence=((_RC_B, _RC_A, "synthetic non-overlap provenance"),))
    assert forward.status == RESOLVED and forward.residual_planning_capacity == 275
    assert forward == backward


def test_residual_f_refused_child_never_consumes_capacity():
    from app.reporting.residual_capacity import RESOLVED, UNVERIFIED
    parent = _rc_count(_RC_PARENT, 500)
    for basis in (None, "refused", "withdrawn"):
        refused = _rc_count(_RC_A, 125, basis=basis)
        alone = _rc_assess(parent, [refused], containment_evidence=_rc_contained(_RC_A))
        assert alone.status == UNVERIFIED and alone.reason == "no_operative_child"
        assert alone.residual_planning_capacity is None
        assert [e.child.subject_id for e in alone.excluded_children] == [_RC_A]
        assert alone.excluded_children[0].reason == "not_operative_approved"
        # Beside a genuine operative child, the refused value is excluded, not subtracted.
        mixed = _rc_assess(parent, [refused, _rc_count(_RC_B, 100)], containment_evidence=_rc_contained(_RC_A, _RC_B))
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
                                containment_evidence=_rc_contained(_RC_A))
    assert pending_parent.status == UNVERIFIED and pending_parent.reason == "parent_not_operative_approved"


def test_residual_h_material_count_conflict_is_preserved_never_averaged():
    from app.reporting.residual_capacity import MATERIAL_CONFLICT
    result = _rc_assess(_rc_conflict_parent(), [_rc_count(_RC_A, 125)], containment_evidence=_rc_contained(_RC_A))
    assert result.status == MATERIAL_CONFLICT and result.reason == "count_material_conflict"
    assert result.residual_planning_capacity is None
    conflicted_child = _rc_assess(_rc_count(_RC_PARENT, 500),
                                  [_rc_count(_RC_A, None, precision="UNKNOWN", resolution="material_conflict")],
                                  containment_evidence=_rc_contained(_RC_A))
    assert conflicted_child.status == MATERIAL_CONFLICT and conflicted_child.residual_planning_capacity is None


def test_residual_i_approximate_or_range_counts_never_become_an_exact_residual():
    from app.reporting.residual_capacity import UNVERIFIED
    exact_child = _rc_count(_RC_A, 125)
    for parent in (_rc_count(_RC_PARENT, 500, precision="APPROXIMATE"), _rc_count(_RC_PARENT, 500, precision="RANGE")):
        result = _rc_assess(parent, [exact_child], containment_evidence=_rc_contained(_RC_A))
        assert result.status == UNVERIFIED and result.reason == "count_not_exact"
        assert result.residual_planning_capacity is None
    approximate_child = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125, precision="APPROXIMATE")],
                                   containment_evidence=_rc_contained(_RC_A))
    assert approximate_child.status == UNVERIFIED and approximate_child.residual_planning_capacity is None


def test_residual_j_unknown_counts_stay_unknown_not_zero():
    from app.reporting.residual_capacity import UNVERIFIED
    unknown_child = _rc_count(_RC_A, None, precision="UNKNOWN", resolution="insufficient_evidence")
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [unknown_child], containment_evidence=_rc_contained(_RC_A))
    assert result.status == UNVERIFIED and result.reason == "unknown_count"
    assert result.residual_planning_capacity is None
    unknown_parent = _rc_assess(_rc_count(_RC_PARENT, None, precision="UNKNOWN"), [_rc_count(_RC_A, 125)],
                                containment_evidence=_rc_contained(_RC_A))
    assert unknown_parent.status == UNVERIFIED and unknown_parent.residual_planning_capacity is None


def test_residual_k_children_greater_than_parent_never_give_a_negative_residual():
    from app.reporting.residual_capacity import MATERIAL_CONFLICT, RESOLVED
    parent = _rc_count(_RC_PARENT, 500)
    single = _rc_assess(parent, [_rc_count(_RC_A, 600)], containment_evidence=_rc_contained(_RC_A))
    assert single.status == MATERIAL_CONFLICT and single.reason == "children_exceed_parent"
    assert single.residual_planning_capacity is None
    two = _rc_assess(parent, [_rc_count(_RC_A, 300), _rc_count(_RC_B, 300)],
                     containment_evidence=_rc_contained(_RC_A, _RC_B), non_overlap_evidence=((_RC_A, _RC_B, "p"),))
    assert two.status == MATERIAL_CONFLICT and two.residual_planning_capacity is None
    # A child that consumes exactly the parent leaves zero, never a negative number.
    full = _rc_assess(parent, [_rc_count(_RC_A, 500)], containment_evidence=_rc_contained(_RC_A))
    assert full.status == RESOLVED and full.residual_planning_capacity == 0


def test_residual_l_duplicate_child_is_subtracted_once_and_conflicting_duplicates_are_a_conflict():
    from app.reporting.residual_capacity import MATERIAL_CONFLICT, RESOLVED
    parent, child = _rc_count(_RC_PARENT, 500), _rc_count(_RC_A, 125)
    twice = _rc_assess(parent, [child, child], containment_evidence=_rc_contained(_RC_A))
    assert twice.status == RESOLVED and twice.residual_planning_capacity == 375
    assert len(twice.subtracted_children) == 1
    differing = _rc_assess(parent, [child, _rc_count(_RC_A, 130)], containment_evidence=_rc_contained(_RC_A))
    assert differing.status == MATERIAL_CONFLICT and differing.reason == "conflicting_duplicate_child"
    assert differing.residual_planning_capacity is None


def test_residual_m_planning_capacity_is_never_availability():
    import dataclasses
    from app.reporting.residual_capacity import ResidualCapacityAssessment
    result = _rc_assess(_rc_count(_RC_PARENT, 500), [_rc_count(_RC_A, 125)], containment_evidence=_rc_contained(_RC_A))
    assert result.residual_planning_capacity == 375
    assert not any("avail" in field.name.lower() for field in dataclasses.fields(ResidualCapacityAssessment))
    assert result.label() == "375 homes of residual planning capacity (planning capacity only)"
    assert "available" not in result.label().lower()
    assert "not land availability" in result.claim and "ownership" in result.claim and "control" in result.claim
    assert result.child_set_completeness == "not_established"
    assert not any(char.isdigit() for char in _rc_assess(_rc_count(_RC_PARENT, 500), []).label())


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

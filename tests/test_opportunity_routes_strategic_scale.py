"""Stage 2.5B final slice: opportunity ROUTE (derived, presentation-only), strategic capacity representation (plan-stated, unverified), residual-inference neutralisation, and the shadow
evidence for a later matching decision. Matching itself is UNCHANGED in this slice (BUYER_MATCHING_POLICY_VERSION stays 7).
"""
from __future__ import annotations

import ast
import inspect
import re
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.reporting.opportunity_route as orr
import app.reporting.strategic_capacity as sc
from app.policy.buyer_matching import BUYER_MATCHING_POLICY_VERSION, build_strategic_land_matching_facts
from app.reporting.residential_count import CountAssessment
from benchmark.v7.runner import FORBIDDEN_INFERENCES
from tests.test_buyer_family_feed import LAPSE_AGE, World

ROOT = Path(__file__).resolve().parents[1]


def alloc(minimum=None, indicative=None, maximum=None):
    return SimpleNamespace(minimum_dwellings=minimum, indicative_capacity=indicative, maximum_capacity=maximum)


# --- strategic capacity semantics (H-L, M) -----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("figures,precision,lower,upper,value,kind", [
    ((150, None, 150), "EXACT", 150, 150, 150, "exact"),                  # same min and max: the plan states one figure as floor and ceiling
    ((80, None, 150), "RANGE", 80, 150, None, "range"),                   # a genuine range is a RANGE, never reduced to its maximum
    ((80, 120, 150), "RANGE", 80, 150, None, "range"),                    # an indicative figure inside the range is recorded, never averaged
    ((100, None, None), "RANGE", 100, None, None, "minimum"),             # a stated minimum is a FLOOR: open-ended, never exact
    ((None, None, 300), "RANGE", None, 300, None, "maximum"),             # a stated maximum is a ceiling only
    ((None, 160, None), "APPROXIMATE", None, None, 160, "indicative"),    # indicative only: an unbounded estimate
    ((None, None, None), "UNKNOWN", None, None, None, "unknown"),
])
def test_strategic_capacity_semantics(figures, precision, lower, upper, value, kind):
    assessment = sc.strategic_capacity_assessment(alloc(*figures))
    assert (assessment.precision, assessment.lower, assessment.upper, assessment.value) == (precision, lower, upper, value)
    assert sc.classify_capacity_kind(*figures) == kind
    assert assessment.basis == sc.BASIS and assessment.confidence == "plan_stated"
    view = sc.strategic_scale_view(alloc(*figures))
    assert view["verified"] is False and view["basis"] == sc.SCALE_BASIS_PLAN_STATED_UNVERIFIED and view["kind"] == kind


@pytest.mark.parametrize("figures", [(300, None, 100), (0, None, 100), (-5, None, None), (None, None, 0), (100, 50, 200), (100, 250, 200), (100, 90, None), (None, 250, 200),
                                     (150, 160, 150), (True, None, None), (1.5, None, None), ("100", None, None)])
def test_malformed_or_conflicting_figures_fail_closed(figures):
    assessment = sc.strategic_capacity_assessment(alloc(*figures))
    assert assessment.precision == "UNKNOWN" and assessment.value is None and assessment.resolution == "conflicting_or_malformed_plan_figures"
    view = sc.strategic_scale_view(alloc(*figures))
    assert view["kind"] == "malformed" and "not used" in view["display"] and view["verified"] is False


def test_wording_always_states_plan_stated_and_unverified_and_never_a_bare_number():
    cases = {(150, None, 150): "Plan-stated capacity: 150 homes — unverified", (60, None, 300): "Plan-stated range: 60–300 homes — unverified",
             (100, None, None): "Plan-stated minimum: 100 homes — unverified", (None, None, 300): "Plan-stated maximum: 300 homes — unverified",
             (None, 160, None): "Plan-stated indicative capacity: approximately 160 homes — unverified", (80, 120, 150): "Plan-stated range: 80–150 homes (plan-indicative ~120) — unverified"}
    for figures, text in cases.items():
        assert sc.strategic_scale_view(alloc(*figures))["display"] == text
    for figures in cases:
        display = sc.strategic_scale_view(alloc(*figures))["display"]
        assert display.startswith("Plan-stated") and display.endswith("unverified")
        for name, pattern in FORBIDDEN_INFERENCES.items():                                        # N, O: no ownership / availability / residual / subdivision / willingness claim
            assert not re.search(pattern, display, re.I), (name, display)
        assert not re.search(r"permission|deliver|promot|owner|commenc|sale", display, re.I)


def test_open_ended_ranges_have_a_safe_label_instead_of_crashing_and_the_pinned_module_is_untouched():
    assert sc.PlanStatedCapacity("allocation", "x", precision="RANGE", lower=100).label() == "at least 100 homes"
    assert sc.PlanStatedCapacity("allocation", "x", precision="RANGE", upper=300).label() == "up to 300 homes"
    assert sc.PlanStatedCapacity("allocation", "x", precision="RANGE", lower=100, upper=300).label() == "100–300 homes"
    assert sc.PlanStatedCapacity("allocation", "x", precision="UNKNOWN").label() == "Unit count unverified"
    assert all(isinstance(sc.strategic_capacity_assessment(alloc(*f)), CountAssessment) for f in ((1, None, 2), (3, None, None), (None, None, 4)))   # still the existing count semantics
    import hashlib, json
    import verification.transition.frozen_v6_matcher as frozen
    for relative in ("app/reporting/residential_count.py", "app/reporting/allocation_development_coverage.py"):                                       # whole-file pinned by the frozen v6 oracle: never edited
        text = (ROOT / relative).read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10))
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == frozen.SUPPORTING_MODULE_SHA256[relative]


def test_the_conversion_is_pure_arithmetic_free_and_never_invents_a_unit():
    tree = ast.parse(inspect.getsource(sc))
    arithmetic = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div))]
    assert all(isinstance(n.left, (ast.Constant, ast.JoinedStr)) or isinstance(n.right, (ast.Constant, ast.JoinedStr)) for n in arithmetic)      # only string joins, no unit arithmetic
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported <= {"__future__", "dataclasses", "app.reporting.residential_count"}                          # no database, model or network module


# --- matching is UNCHANGED (W, X, Y, Z-compatible) ----------------------------------------------------------------------------------------------------

def test_v8_strategic_builder_carries_count_semantics_and_keeps_the_legacy_scalar():
    assert BUYER_MATCHING_POLICY_VERSION == 8
    facts = build_strategic_land_matching_facts(SimpleNamespace(minimum_dwellings=60, indicative_capacity=120, maximum_capacity=300, intended_use="residential",
                                                                 local_plan=SimpleNamespace(status="adopted"), plan_status="adopted", matched_site_id=None), None, None)
    assert facts.unit_count == 300 and facts.count_assessment is not None and facts.count_assessment.precision == "RANGE"   # v8: matching reads the assessment; the legacy scalar is display/fingerprint continuity only
    for module in ("app/reporting/opportunity_universe.py", "app/reporting/opportunity_change.py", "app/policy/agent_evaluation_persistence.py"):
        text = (ROOT / module).read_text(encoding="utf-8").replace("strategic_capacity_fingerprint_fields", "")      # V8: the one sanctioned fingerprint helper (non-exact kinds only)
        assert "opportunity_route" not in text and "strategic_scale" not in text and "strategic_capacity" not in text, module     # routes / presentation are not part of fingerprints or monitoring


def test_shadow_compares_frozen_v7_with_v8_and_every_difference_is_an_expected_strategic_delta():
    from benchmark.v8_strategic_scale_shadow import APPROVED_BY_PRODUCT_OWNER, run_shadow
    result = run_shadow()
    assert APPROVED_BY_PRODUCT_OWNER is True and result["unexpected_regressions"] == []
    v7 = {r["case_id"]: r["frozen_v7_result"] for r in result["rows"]}
    v8 = {r["case_id"]: r["v8_result"] for r in result["rows"]}
    assert v7["S6_minimum_only"] == v7["S7_maximum_only"] == v7["S8_malformed_conflicting"] == "STRONG_FIT"          # the v7 reduction to a scalar
    assert all(v8[c].startswith("INSUFFICIENT") for c in ("S6_minimum_only", "S7_maximum_only", "S8_malformed_conflicting"))
    for c in ("S9a_self_qualifying_exact", "S9b_self_qualifying_range", "S9c_self_qualifying_minimum_only"):
        assert v7[c] == v8[c] == "STRONG_FIT+investigative"                                                          # preserved large-allocation route
    assert v8["S1_exact_inside_preferred"] == "STRONG_FIT" and v8["S10_nesten_very_large_allocation"] == "INSUFFICIENT_EVIDENCE+investigative"
    # S3/S4 differ only by the investigative flag (existing uncertain-scale semantics now apply to a range); recorded for REVIEW as a v8 finding, classification unchanged.
    assert set(result["differences"]) == {"S2_indicative_only_inside_preferred", "S3_range_inside_preferred", "S4_range_crossing_preferred_discovery", "S6_minimum_only", "S7_maximum_only", "S8_malformed_conflicting"}
    assert v7["S3_range_inside_preferred"] == "STRONG_FIT" and v8["S3_range_inside_preferred"] == "STRONG_FIT+investigative"
    assert len(result["rows"]) == 12 and all(r["proposed_intended_outcome_for_review"] for r in result["rows"])


def test_nothing_in_the_new_modules_can_reach_a_model_or_the_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    from benchmark.v8_strategic_scale_shadow import run_shadow
    assert run_shadow()["rows"] and sc.strategic_scale_view(alloc(1, None, 2))
    for module in (sc, orr):
        text = inspect.getsource(module)
        assert not re.search(r"openai|anthropic|requests|httpx|urlopen|sqlalchemy|session", text, re.I), module.__name__


# --- opportunity route (A, C-G) -----------------------------------------------------------------------------------------------------------------------

def card(**kw):
    return {"opportunity_type": "planning_delivery", **kw}


def test_route_is_deterministic_pure_and_separate_from_fit():
    inputs = [card(consent_role="outline"), card(consent_role="full"), card(phase_code="2"), card(phase_code="plot_A6"), {"opportunity_type": "strategic_land"}, card()]
    first = [orr.derive_opportunity_route(c) for c in inputs]
    again = [orr.derive_opportunity_route(dict(c)) for c in inputs]
    assert first == again
    assert [r.route for r in first] == [orr.OUTLINE_CONSENTED_SITE, orr.CONSENTED_SITE, orr.PHASE_OR_PLOT, orr.PHASE_OR_PLOT, orr.STRATEGIC_ALLOCATION, orr.UNCLASSIFIED_PLANNING_ROUTE]
    snapshot = card(consent_role="outline", buyer_fit="x")
    before = dict(snapshot)
    orr.derive_opportunity_route(snapshot)
    assert snapshot == before                                                                   # never mutates, never reads buyer fit
    assert "buyer_fit" not in inspect.getsource(orr).replace('"""', "").split("def derive_opportunity_route")[1].split("def _make")[0]
    for text in (orr.__doc__,):
        assert "ROUTE IS NOT A RANK" in text and "never affects buyer fit" in text.lower().replace("\n", " ") or "never affects buyer fit" in text.replace("\n", " ")


def test_consented_and_outline_are_distinguished_by_the_existing_planning_role_and_pending_fails_closed():
    assert orr.derive_opportunity_route(card(consent_role="outline")).route == orr.OUTLINE_CONSENTED_SITE
    for role in ("full", "hybrid", "reserved_matters", "other_substantive"):
        assert orr.derive_opportunity_route(card(consent_role=role)).route == orr.CONSENTED_SITE
    for role in (None, "", "unknown", "s73_variation", "condition_discharge", "eia_screening"):
        assert orr.derive_opportunity_route(card(consent_role=role)).route == orr.UNCLASSIFIED_PLANNING_ROUTE          # never guessed
    assert orr.derive_opportunity_route(card(phase_code="Whole site / unphased", consent_role="outline")).route == orr.OUTLINE_CONSENTED_SITE   # the unphased bucket is the WIDER subject


def test_phase_and_plot_stay_distinct_subtypes_and_a_plot_is_not_phasing_evidence():
    phase, plot = orr.derive_opportunity_route(card(phase_code="2")), orr.derive_opportunity_route(card(phase_code="plot_A6"))
    assert (phase.route, phase.subtype, plot.route, plot.subtype) == (orr.PHASE_OR_PLOT, orr.SUBTYPE_PHASE, orr.PHASE_OR_PLOT, orr.SUBTYPE_PLOT)
    assert "plot alone does not establish formal phasing" in plot.caveat
    from app.policy.buyer_matching import PHASING_NONE_IDENTIFIED
    from tests.test_acquisition_phasing import app as make_application, state
    plot_application = make_application(1, "Reserved matters for Plot A6 for the erection of 79 dwellings")
    assert state([plot_application]) == PHASING_NONE_IDENTIFIED                                  # the route label does not change the phasing derivation (unchanged module)


def test_strategic_allocation_route_and_caveats_make_no_unsupported_claim():
    strategic = orr.derive_opportunity_route({"opportunity_type": "strategic_land"})
    assert strategic.route == orr.STRATEGIC_ALLOCATION and "unverified" in strategic.caveat
    for route in orr.ALL_ROUTE_KEYS:
        text = f"{orr.ROUTE_LABELS[route]} {orr.ROUTE_CAVEATS[route]}"
        forbidden = r"\bavailable\b|willing|for sale\b|remaining|will sell|owns\b" + ("" if route == orr.RESIDUAL_OPPORTUNITY else "|residual")   # only R1 may say residual
        assert not re.search(forbidden, text, re.I), (route, text)
    assert "unverified" in orr.ROUTE_CAVEATS[orr.RESIDUAL_OPPORTUNITY] and "derived" in orr.ROUTE_LABELS[orr.RESIDUAL_OPPORTUNITY].lower()
    assert "has not started" not in " ".join(orr.ROUTE_CAVEATS.values()).lower() or "not verified" in orr.ROUTE_CAVEATS[orr.CONSENTED_SITE]    # never claims "development not started"
    counts = orr.route_counts([orr.CONSENTED_SITE, orr.CONSENTED_SITE, orr.STRATEGIC_ALLOCATION])
    assert counts == {orr.CONSENTED_SITE: 2, orr.OUTLINE_CONSENTED_SITE: 0, orr.PHASE_OR_PLOT: 0, orr.RESIDUAL_OPPORTUNITY: 0, orr.STRATEGIC_ALLOCATION: 1, orr.UNCLASSIFIED_PLANNING_ROUTE: 0}


# --- the feed, family presentation and the unchanged family architecture ----------------------------------------------------------------------------

@pytest.fixture
def world(session, monkeypatch):
    from tests.test_family_dashboard import treat_portal_estimates_as_exact
    treat_portal_estimates_as_exact(monkeypatch)
    return World(session, monkeypatch)


def test_planning_cards_carry_the_consent_role_and_strategic_cards_the_scale_view_and_families_stay_separate(world):
    import app.reporting.buyer_family_feed as bff
    outline_site = world.site(outline_age=LAPSE_AGE, units_out=60)
    from app.db.models import Application
    world.session.query(Application).filter(Application.site_id == outline_site.id).update({"application_type": "Outline Planning Permission"})   # the portal's own Application Type is the most authoritative role input
    world.session.commit()
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, units_out=60, units_rm=40)
    allocation = world.allocation(capacity=150, minimum_dwellings=80)
    inputs = bff.load_buyer_family_inputs(world.session)
    roles = {c["id"]: c.get("consent_role") for c in inputs.delivery}
    assert roles[f"opp-lapse-{outline_site.id}"] == "outline"
    assert any(role in ("full", "hybrid", "reserved_matters", "other_substantive", "outline") for role in roles.values())
    strategic = next(c for c in inputs.strategic if c["id"] == f"opp-feed-alloc-{allocation.id}")
    assert strategic["strategic_scale"]["display"] == "Plan-stated range: 80–150 homes — unverified" and ("Plan-stated capacity (unverified)", "80–150 homes") in strategic["metrics"]
    result = bff.build_buyer_opportunity_families(world.session, "housing_association", 20)
    assert all(len({m.domain for m in (f.representative, *[r.subject for r in f.related])}) == 1 for f in result["families"])      # strategic and planning never share a family
    assert set(result["route_counts"]) == set(orr.ALL_ROUTE_KEYS) and sum(result["route_counts"].values()) == len(result["families"])
    assert result["route_counts"][orr.STRATEGIC_ALLOCATION] >= 1


def test_presenter_exposes_route_scale_basis_and_route_counts_without_changing_fit_or_order(world):
    import app.reporting.family_presentation as fp
    world.site(outline_age=LAPSE_AGE, units_out=60)
    world.allocation(capacity=150, minimum_dwellings=150)
    view = fp.build_buyer_family_dashboard_view(world.session, "nesten_homes", 20)
    strategic = next(f for f in view.families if f.is_strategic)
    assert strategic.best.route == orr.STRATEGIC_ALLOCATION and strategic.best.scale_basis == "Plan-stated capacity: 150 homes — unverified"
    assert strategic.best.route_caveat and "unverified" in strategic.best.route_caveat
    planning = next(f for f in view.families if not f.is_strategic)
    assert planning.best.scale_basis is None and planning.best.route in (orr.OUTLINE_CONSENTED_SITE, orr.CONSENTED_SITE, orr.UNCLASSIFIED_PLANNING_ROUTE)
    counts = dict(view.route_counts)
    assert counts[orr.STRATEGIC_ALLOCATION] == 1 and "strategic allocation(s)" in view.route_caption and view.route_caption.startswith("Opportunity routes among the families shown:")
    assert [f.best.fit_key for f in view.families] == sorted((f.best.fit_key for f in view.families), key=lambda k: ["STRONG_FIT", "POSSIBLE_FIT", "INSUFFICIENT_EVIDENCE", "NOT_SUITABLE"].index(k))


def test_family_and_subject_identity_do_not_depend_on_the_new_card_keys(world):
    from app.reporting.opportunity_families import subject_from_feed_card
    import app.reporting.buyer_family_feed as bff
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)
    world.allocation(capacity=150)
    inputs = bff.load_buyer_family_inputs(world.session)
    for source in (*inputs.strategic, *inputs.delivery):
        source = {**source, "buyer_fit": SimpleNamespace(classification="STRONG_FIT", is_investigative_exception=False)}
        stripped = {k: v for k, v in source.items() if k not in ("strategic_scale", "consent_role")}
        before, after = subject_from_feed_card(dict(source)), subject_from_feed_card(stripped)
        assert (before.domain, before.anchor_id, before.subject_key, before.slot) == (after.domain, after.anchor_id, after.subject_key, after.slot)


# --- residual inference (P, Q) ---------------------------------------------------------------------------------------------------------------------------

def test_user_facing_signal_wording_no_longer_presents_residual_or_coverage_arithmetic_but_the_internal_diagnostic_remains():
    from app.reporting.allocation_development_coverage import (
        PARTIAL_COVERAGE, SUBSTANTIALLY_COVERED, FULLY_ACCOUNTED_FOR, DevelopmentCoverageResult, build_opportunity_signal,
    )
    from app.reporting.opportunity_signal import PLANNING_ACTIVITY_IDENTIFIED_REASON, build_neutral_opportunity_signal
    import dataclasses
    fields = {f.name for f in dataclasses.fields(DevelopmentCoverageResult)}
    assert {"indicative_residual_capacity", "development_coverage_percentage", "identified_application_capacity"} <= fields           # internal diagnostic preserved
    phasing = {"classification": "NONE", "evidence": []}
    for classification, pct, residual in ((PARTIAL_COVERAGE, 0.22, 856), (SUBSTANTIALLY_COVERED, 0.8, 220), (FULLY_ACCOUNTED_FOR, 0.95, 55)):
        kwargs = {f.name: None for f in dataclasses.fields(DevelopmentCoverageResult)}
        kwargs.update(allocation_capacity=1100, development_coverage_classification=classification, development_coverage_percentage=pct, indicative_residual_capacity=residual,
                      capacity_accounting_status="ok", note=None, site_summaries=[])
        for name in ("number_of_related_sites", "number_of_linked_applications", "number_of_sites_with_planning_activity"):
            kwargs[name] = 1
        coverage = DevelopmentCoverageResult(**kwargs)
        raw = build_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing=phasing)                      # the unchanged internal producer still computes residual wording
        assert re.search(r"not (currently )?accounted for|represented by identified|fully accounted", " ".join(raw["reasons"]))
        neutral = build_neutral_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing=phasing)
        assert neutral["signal"] == raw["signal"]                                                                              # the signal selection is untouched
        reasons = " ".join(neutral["reasons"])
        assert neutral["reasons"].count(PLANNING_ACTIVITY_IDENTIFIED_REASON) == 1
        assert PLANNING_ACTIVITY_IDENTIFIED_REASON in reasons
        from app.reporting.residual_opportunity import ALLOCATION_R2_TEXT
        if classification != PARTIAL_COVERAGE:
            assert ALLOCATION_R2_TEXT not in reasons                                                              # nothing is left unaccounted: no R2 context
        else:
            assert neutral["reasons"].count(ALLOCATION_R2_TEXT) == 1                                              # V8-B: partial coverage -> R2 investigation context (no number)
        bare = reasons.replace(ALLOCATION_R2_TEXT, "")
        assert str(residual) not in reasons and f"{round(pct * 100)}%" not in reasons and not re.search(r"not (currently )?accounted for|residual|remaining|available", bare, re.I)
        assert not re.search(r"[0-9,]+ homes (available|remaining|residual)|available|remaining parcel", ALLOCATION_R2_TEXT, re.I)
        assert "plan-stated capacity" in reasons and "unverified" in reasons


# --- Part 14: the four routes presented for Nesten (the data/presenter contract; fit values are the deterministic test double used throughout the family tests) ------------

def test_the_four_opportunity_routes_present_type_fit_scale_basis_planning_state_and_a_key_caveat_for_nesten(world, capsys):
    import app.reporting.family_presentation as fp
    from app.db.models import Application
    consented = world.site(outline_age=LAPSE_AGE, units_out=120, parent="S")
    outlined = world.site(outline_age=LAPSE_AGE, units_out=120, parent="S")
    phased = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, units_out=500, units_rm=140, parent="I", phase="S")
    world.session.query(Application).filter(Application.site_id == consented.id).update({"application_type": "Full Planning Permission", "proposal": "Full application for 120 dwellings"})
    world.session.query(Application).filter(Application.site_id == outlined.id).update({"application_type": "Outline Planning Permission"})
    world.session.query(Application).filter(Application.site_id == phased.id, Application.reference.like("OUT/%")).update({"application_type": "Outline Planning Permission"})
    world.session.commit()
    world.allocation(capacity=160, minimum_dwellings=160, fit="S")
    view = fp.build_buyer_family_dashboard_view(world.session, "nesten_homes", 20)
    rows = {}
    for family in view.families:
        best = family.best
        rows[best.route] = {"OPPORTUNITY TYPE": best.route_label, "BUYER FIT": best.fit_label, "SCALE / SCALE BASIS": best.scale_basis or best.scale or "Unit count unverified",
                            "PLANNING/EVIDENCE STATE": best.route_caveat.split(";")[0], "KEY CAVEAT": best.route_caveat}
    assert set(rows) >= {orr.CONSENTED_SITE, orr.OUTLINE_CONSENTED_SITE, orr.PHASE_OR_PLOT, orr.STRATEGIC_ALLOCATION}
    for route in (orr.CONSENTED_SITE, orr.OUTLINE_CONSENTED_SITE, orr.PHASE_OR_PLOT, orr.STRATEGIC_ALLOCATION):
        assert all(rows[route].values()), (route, rows[route])
        for name, pattern in FORBIDDEN_INFERENCES.items():
            assert not re.search(pattern, " ".join(rows[route].values()), re.I), (route, name)
    assert rows[orr.STRATEGIC_ALLOCATION]["SCALE / SCALE BASIS"] == "Plan-stated capacity: 160 homes — unverified"
    assert "not verified" in rows[orr.CONSENTED_SITE]["KEY CAVEAT"] and "further approvals are required" in rows[orr.OUTLINE_CONSENTED_SITE]["KEY CAVEAT"]
    assert "plot alone does not establish formal phasing" in rows[orr.PHASE_OR_PLOT]["KEY CAVEAT"]
    print("\nNESTEN ROUTE PRESENTATION CONTRACT")
    for route, row in rows.items():
        print(route, row)

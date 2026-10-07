"""Stage 2.5B V8-B: the residual ladder (R1 dormant / R2 context-only / R3 nothing), identity, fingerprint, the POSSIBLE_FIT ceiling and family behaviour.

Offline and deterministic: no database, network or model. 'Qualified' evidence is SYNTHETIC; production supplies none (R1 is dormant by evidence)."""
from __future__ import annotations

import dataclasses
import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.reporting.residual_opportunity as ro
from app.policy import buyer_matching as bm
from app.policy.buyer_profiles import BUYER_PROFILES, PERMISSION_GRANTED
from app.policy.residual_fit import CAP_NOTE, NotAResidualSubject, assess_residual_fit
from app.reporting.opportunity_families import (
    INSUFFICIENT_EVIDENCE, POSSIBLE_FIT, SLOT_PHASE, SLOT_RESIDUAL, STRONG_FIT, FamilySubject, UnsupportedSubject, group_into_families, subject_from_feed_card,
)
from benchmark.v8_residual_cases import (
    CHILD_SET, CONTAINMENT, NON_OVERLAP, PARENT_ID, SITE, allocation_case, child, containment_for, pairs_for, parent, qualified_evidence, run_residual_benchmark,
)

ROOT = Path(__file__).resolve().parents[1]


def q500_300(evidence=None, **parent_kw):
    p, c = parent(500, **parent_kw), child("1", 300)
    return p, c, ro.qualify_residual(p, [c], qualified_evidence(p, [c]) if evidence is None else evidence)


# --- 1/2 production cannot make R1; synthetic qualified evidence can --------------------------------------------------------------------------------------------

def test_production_default_evidence_cannot_produce_r1_today():
    p, c = parent(500), child("1", 300)
    production = ro.production_residual_evidence(containment_for(p, [c]))
    assert production.non_overlap == () and production.child_set == ()                       # no production producer for completeness / non-overlap
    q = ro.qualify_residual(p, [c], production)
    assert q.level == ro.LEVEL_R2 and not q.is_subject and q.predicate(ro.CHILD_SET_COMPLETE).state == ro.UNKNOWN
    assert ro.qualify_residual(p, [c]).level != ro.LEVEL_R1                                  # no evidence at all
    sig = inspect.signature(ro.production_residual_evidence)
    assert list(sig.parameters) == ["containment_pairs"]                                     # the production producer cannot even accept completeness / non-overlap


def test_explicit_synthetic_qualified_evidence_produces_r1_with_the_canonical_200():
    _, _, q = q500_300()
    assert q.level == ro.LEVEL_R1 and q.residual_value == 200 and q.is_subject and q.subject_id and q.evidence_fingerprint
    assert q.residual_assessment.precision == "EXACT" and q.residual_assessment.exact_value == 200 and q.residual_assessment.basis == "derived_residual"
    assert all(p.state == ro.TRUE for p in q.predicates) and {p.name for p in q.predicates} == set(ro.PREDICATES)


def test_database_completeness_same_site_arithmetic_and_labels_cannot_satisfy_the_predicates():
    p, c = parent(500), child("1", 300)
    only_containment = ro.ResidualEvidence(containment=containment_for(p, [c]))
    q = ro.qualify_residual(p, [c], only_containment)
    assert q.level == ro.LEVEL_R2 and q.predicate(ro.CHILD_SET_COMPLETE).state == ro.UNKNOWN
    # counts that add up exactly (300 of 500) and a phase label ("Phase 1") are not completeness evidence
    two = [child("1", 200), child("2", 300)]
    q2 = ro.qualify_residual(p, two, ro.ResidualEvidence(containment=containment_for(p, two)))
    assert q2.level == ro.LEVEL_R2 and q2.predicate(ro.SIBLING_NON_OVERLAP_ESTABLISHED).state == ro.UNKNOWN
    # blank / non-string provenance is never evidence
    blank = ro.ResidualEvidence(containment=containment_for(p, [c]), child_set=((p.subject_id, (c.subject_id,), "   "),))
    assert ro.qualify_residual(p, [c], blank).level == ro.LEVEL_R2
    assert ro.qualify_residual(p, [c], ro.ResidualEvidence(containment=containment_for(p, [c]), child_set=((p.subject_id, (c.subject_id,), True),))).level == ro.LEVEL_R2


def test_child_set_evidence_must_name_exactly_the_supplied_children():
    p, kids = parent(500), [child("1", 200), child("2", 100)]
    ev = ro.ResidualEvidence(containment=containment_for(p, kids), non_overlap=pairs_for(kids), child_set=((p.subject_id, (kids[0].subject_id,), CHILD_SET),))
    q = ro.qualify_residual(p, kids, ev)
    assert q.level == ro.LEVEL_R2 and q.predicate(ro.CHILD_SET_COMPLETE).state == ro.FALSE


# --- 3-5, 9/10 R2 is context only ---------------------------------------------------------------------------------------------------------------------------

def test_r2_creates_no_subject_no_id_no_count_no_fingerprint_no_fit():
    p, c = parent(500), child("1", 300)
    q = ro.qualify_residual(p, [c], ro.ResidualEvidence(containment=containment_for(p, [c])))
    assert q.level == ro.LEVEL_R2
    assert q.subject_id is None and q.evidence_fingerprint is None and q.residual_value is None and q.residual_assessment is None and not q.is_subject
    assert q.context_text == ro.PLANNING_R2_TEXT
    with pytest.raises(NotAResidualSubject):
        assess_residual_fit(BUYER_PROFILES["nesten_homes"], _parent_facts(), q)
    assert not any("200" in str(v) for v in dataclasses.asdict(q).values() if isinstance(v, (str, int)))


def test_r3_creates_nothing_and_missing_evidence_is_never_zero():
    p = parent(500)
    for children in ([], [child("1", 300, basis="superseded")]):
        q = ro.qualify_residual(p, children)
        assert q.level == ro.LEVEL_R3 and q.residual_value is None and q.context_text is None and q.subject_id is None
    full = ro.qualify_residual(p, [child("1", 500)], qualified_evidence(p, [child("1", 500)]))
    assert full.level == ro.LEVEL_R3 and full.residual_value is None                         # zero is not an opportunity


def test_planning_500_300_incomplete_is_r2_with_no_200_and_qualified_is_r1_with_200():
    p, c = parent(500), child("1", 300)
    r2 = ro.qualify_residual(p, [c], ro.ResidualEvidence(containment=containment_for(p, [c]), non_overlap=pairs_for([c])))
    assert r2.level == ro.LEVEL_R2 and r2.residual_value is None
    assert q500_300()[2].level == ro.LEVEL_R1 and q500_300()[2].residual_value == 200


def test_the_benchmark_cases_match_their_proposed_expectations_and_are_unapproved():
    result = run_residual_benchmark()
    assert result["approved_by_product_owner"] is False and result["disagreements"] == []
    levels = {r["case_id"]: (r["actual_level"], r["actual_residual"]) for r in result["rows"]}
    assert levels["R15_qualified_500_300"] == (ro.LEVEL_R1, 200) and levels["R18_500_proven_complete_200_150"] == (ro.LEVEL_R1, 150)
    assert levels["R17_500_overlap_unknown_300_250"][1] is None and levels["R17b_500_proven_distinct_300_250"][0] == ro.LEVEL_R3
    assert levels["R19_amendment_no_double_subtraction"][0] == ro.LEVEL_R3 and levels["R19b_duplicate_child_counted_once"] == (ro.LEVEL_R1, 200)
    assert levels["R20_incompatible_metrics"][0] == ro.LEVEL_R3 and levels["R23_production_default_evidence"][0] == ro.LEVEL_R2


def test_no_negative_or_malformed_residual_can_become_an_opportunity():
    p = parent(500)
    kids = [child("1", 300), child("2", 250)]
    for ev in (ro.ResidualEvidence(containment=containment_for(p, kids)), qualified_evidence(p, kids)):
        q = ro.qualify_residual(p, kids, ev)
        assert q.residual_value is None and not q.is_subject
    assert ro.qualify_residual(parent(0), [child("1", 0)], qualified_evidence(parent(0), [child("1", 0)])).level != ro.LEVEL_R1
    assert ro.qualify_residual(parent(500, precision="UNKNOWN"), [child("1", 300)]).level == ro.LEVEL_R3


# --- 8 allocation arithmetic is only a trigger ------------------------------------------------------------------------------------------------------------

def test_allocation_coverage_arithmetic_triggers_r2_context_without_exposing_the_subtraction():
    case = allocation_case()
    assert case["actual_level"] == ro.LEVEL_R2 and case["trusted_count"] is None
    assert not re.search(r"[0-9]|available|homes remaining", case["text"], re.I)
    assert set(f.name for f in dataclasses.fields(ro.AllocationResidualContext)) == {"level", "text"}     # no number field exists
    partial = dict(capacity_accounting_status="ok", indicative_residual_capacity=400, number_of_sites_with_planning_activity=1, development_coverage_classification="PARTIAL_COVERAGE")
    for change in ({"capacity_accounting_status": "review_required"}, {"indicative_residual_capacity": 0}, {"indicative_residual_capacity": None},
                   {"number_of_sites_with_planning_activity": 0}, {"development_coverage_classification": "FULLY_ACCOUNTED_FOR"}):
        assert ro.allocation_residual_context(SimpleNamespace(**{**partial, **change})) is None
    assert ro.allocation_residual_context(None) is None


# --- 11-13 the POSSIBLE_FIT ceiling and the family order ------------------------------------------------------------------------------------------------

def _parent_facts():
    return bm.MatchingFacts(opportunity_type=bm.PLANNING_DELIVERY, unit_count=500, development_type_raw="residential", is_specialist_development=False, affordable_percentage=None,
                            affordable_percentage_trusted=False, affordable_unit_count=None, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=None,
                            has_phasing_evidence=False, matched_to_site=False)


def test_r1_classification_cannot_exceed_possible_fit_even_when_the_scale_is_perfect():
    p, c, q = q500_300()
    nesten = BUYER_PROFILES["nesten_homes"]
    raw = bm.assess_buyer_fit(nesten, ro_facts := __import__("app.policy.residual_fit", fromlist=["x"]).residual_matching_facts(_parent_facts(), q))
    assert raw.classification == STRONG_FIT                                                  # the unchanged matcher WOULD say STRONG for 200 homes inside the preferred range
    capped = assess_residual_fit(nesten, _parent_facts(), q)
    assert capped.classification == POSSIBLE_FIT and CAP_NOTE in capped.matches              # ... and the ceiling is applied explicitly and visibly
    assert any("unverified" in line for line in capped.investigate)
    for key in BUYER_PROFILES:
        assert assess_residual_fit(BUYER_PROFILES[key], _parent_facts(), q).classification != STRONG_FIT


def _subject(key, fit, *, investigative=False, slot=SLOT_PHASE, precision="EXACT"):
    return FamilySubject(domain="planning_delivery", anchor_id=SITE, subject_key=key, slot=slot, fit=fit, investigative=investigative, count_precision=precision)


def test_r1_can_represent_an_investigative_family_and_a_strong_real_phase_outranks_it():
    residual = _subject("planning_delivery:residual:61:aaaa", POSSIBLE_FIT, slot=SLOT_RESIDUAL)
    weak = _subject("planning_delivery:phase:61:P1", INSUFFICIENT_EVIDENCE, investigative=True)
    assert group_into_families([weak, residual])[0].representative == residual              # existing fit ordering, no residual-specific rank
    strong = _subject("planning_delivery:phase:61:P2", STRONG_FIT)
    assert group_into_families([residual, strong, weak])[0].representative == strong
    assert group_into_families([residual, strong])[0].related[0].subject == residual
    equal = _subject("planning_delivery:phase:61:P3", POSSIBLE_FIT)
    ordering = [f.representative.subject_key for f in group_into_families([residual, equal])]
    assert ordering == [group_into_families([equal, residual])[0].representative.subject_key]   # order-independent; the stable key decides a genuine tie


def test_r2_cannot_become_a_family_subject_or_representative():
    card = {"id": f"opp-residual-{SITE}-{'a' * 20}", "opportunity_type": "planning_delivery", "params": {"site_id": str(SITE)},
            "buyer_fit": SimpleNamespace(classification=POSSIBLE_FIT, is_investigative_exception=False)}
    with pytest.raises(UnsupportedSubject):
        subject_from_feed_card(card)                                                         # no derived identity -> not a subject
    card["residual_subject_id"] = f"planning_delivery:residual:{SITE}:{'a' * 20}"
    assert subject_from_feed_card(card).slot == SLOT_RESIDUAL
    with_context = {"id": "opp-lapse-61", "opportunity_type": "planning_delivery", "params": {"site_id": "61"}, "buyer_fit": card["buyer_fit"]}
    assert subject_from_feed_card(with_context) == subject_from_feed_card({**with_context, "potential_residual": ro.PLANNING_R2_TEXT})   # R2 context changes no subject


# --- 14-16 identity and fingerprint --------------------------------------------------------------------------------------------------------------------------

def test_r1_identity_is_deterministic_evidence_derived_and_order_independent():
    p, kids = parent(500), [child("1", 200), child("2", 150)]
    a = ro.qualify_residual(p, kids, qualified_evidence(p, kids))
    b = ro.qualify_residual(p, list(reversed(kids)), qualified_evidence(p, list(reversed(kids))))
    assert a.subject_id == b.subject_id and a.evidence_fingerprint == b.evidence_fingerprint
    assert re.fullmatch(rf"planning_delivery:residual:{SITE}:[0-9a-f]{{20}}", a.subject_id)
    dup = ro.qualify_residual(p, [*kids, kids[0]], qualified_evidence(p, kids))
    assert dup.subject_id == a.subject_id                                                    # duplicate equivalent evidence -> one subject
    changed_parent = ro.qualify_residual(parent(600), kids, qualified_evidence(parent(600), kids))
    assert changed_parent.subject_id == a.subject_id                                         # same scope identity ... but the fingerprint moves (below)
    assert changed_parent.evidence_fingerprint != a.evidence_fingerprint
    other_parent = parent(500)
    other_parent = dataclasses.replace(other_parent, subject_id=f"site:{SITE}:phase:Outline", scope_type="phase")
    assert ro.residual_subject_identity(SITE, other_parent.subject_id, [k.subject_id for k in kids]) != a.subject_id         # changed parent scope -> changed id
    smaller = [kids[0]]
    c = ro.qualify_residual(p, smaller, qualified_evidence(p, smaller))
    assert c.subject_id != a.subject_id                                                      # changed qualified child set -> changed id
    assert ro.residual_subject_identity(SITE, PARENT_ID, ["x"]) == ro.residual_subject_identity(SITE, PARENT_ID, ["x", "x"])


def test_r1_fingerprint_moves_on_material_evidence_and_is_independent_of_buyer_fit_and_order():
    p, kids = parent(500), [child("1", 200), child("2", 150)]
    base = ro.qualify_residual(p, kids, qualified_evidence(p, kids))
    def fp(par=p, children=kids, evidence=None):
        return ro.qualify_residual(par, children, evidence or qualified_evidence(par, children)).evidence_fingerprint
    assert fp() == base.evidence_fingerprint and fp(children=list(reversed(kids))) == base.evidence_fingerprint
    assert fp(par=parent(520)) != base.evidence_fingerprint                                   # parent count
    assert fp(children=[child("1", 200), child("2", 140)]) != base.evidence_fingerprint       # child count
    assert fp(children=[child("1", 200, ref="RM/OTHER"), kids[1]]) != base.evidence_fingerprint   # child source reference
    ev = qualified_evidence(p, kids)
    assert fp(evidence=dataclasses.replace(ev, containment=containment_for(p, kids, CONTAINMENT + " (second reading)"))) != base.evidence_fingerprint
    assert fp(evidence=dataclasses.replace(ev, non_overlap=pairs_for(kids, NON_OVERLAP + " v2"))) != base.evidence_fingerprint
    assert fp(evidence=dataclasses.replace(ev, child_set=((p.subject_id, tuple(k.subject_id for k in kids), CHILD_SET + " v2"),))) != base.evidence_fingerprint
    import ast
    tree = ast.parse(inspect.getsource(ro.residual_evidence_fingerprint))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not [n for n in names if re.search(r"buyer|fit|classification|rank|datetime|time|now|wording", n, re.I)]   # nothing buyer / fit / wording / time dependent


# --- 18 wording ---------------------------------------------------------------------------------------------------------------------------------------------

def test_r2_wording_never_implies_availability_or_a_number():
    for text in (ro.PLANNING_R2_TEXT, ro.ALLOCATION_R2_TEXT):
        assert text.startswith("Potential residual scope")
        assert not re.search(r"[0-9]|\bavailable\b|for sale|homes remaining|remaining (parcel|land|homes)|unbuilt|\bowns?\b", text, re.I), text
    assert "unverified" in ro.R1_CAVEAT.lower() and "availability" in ro.R1_CAVEAT.lower()


# --- 19/20 no Stage 2.6 producer, no schema, no model, purity ----------------------------------------------------------------------------------------------

def test_no_stage_2_6_evidence_producer_exists_and_only_the_residual_modules_touch_the_evidence_interface():
    offenders = []
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"child_set\s*=\s*\(|ResidualEvidence\(", text) and path.name not in ("residual_opportunity.py", "residual_feed.py"):
            offenders.append(path.name)
    assert offenders == []
    feed = (ROOT / "app/reporting/residual_feed.py").read_text(encoding="utf-8")
    assert "evidence_provider" in feed and "child_set=tuple(extra.child_set)" in feed        # the ONLY route for qualified (Stage 2.6) evidence is the injected provider
    assert "R1 is dormant by evidence" in (ROOT / "app/reporting/buyer_family_feed.py").read_text(encoding="utf-8")


def test_no_schema_model_or_network_in_the_residual_modules():
    from app.db.models import Base
    assert not [n for t in Base.metadata.tables.values() for n in (t.name, *(c.name for c in t.columns)) if "residual" in n.lower()]
    for module in ("app/reporting/residual_opportunity.py", "app/policy/residual_fit.py"):
        text = (ROOT / module).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+(sqlalchemy|requests|httpx|anthropic|openai|urllib|socket)", text, re.M | re.I), module
    assert not (ROOT / "migrations").exists() or not list((ROOT / "migrations").rglob("*residual*"))

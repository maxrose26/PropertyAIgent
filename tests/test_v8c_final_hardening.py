"""Stage 2.5B final pre-merge hardening: the residual AI/prompt contract (real prompt construction, no model call), the surface wording sweep, the residual identity ruling,
the unexpected-regression proofs, the strategic fingerprint pins and the benchmark approval record. Offline and deterministic."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re
from pathlib import Path

import pytest

import app.reporting.residual_opportunity as ro
from app.policy import buyer_matching as bm
from app.policy.buyer_profiles import BUYER_PROFILES
from app.reporting.allocation_intelligence_summary import PROMPT_VERSION, build_allocation_context, build_summary_prompt
from tests.test_allocation_intelligence_summary import (
    _make_allocation, _make_app_with_capacity, _make_council, _make_plan, _make_relationship, _make_site,
)

ROOT = Path(__file__).resolve().parents[1]


def _prompt(session, *, capacity, linked_units):
    _make_council(session)
    allocation = _make_allocation(session, _make_plan(session), minimum_dwellings=capacity)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    if linked_units:
        _make_app_with_capacity(session, site.id, "APP/1", linked_units)
    session.commit()
    context = build_allocation_context(session, allocation)
    return context, build_summary_prompt(context)


# --- AI grounding: R2 -------------------------------------------------------------------------------------------------------------------------------------------

def test_r2_prompt_supplies_no_residual_count_and_never_instructs_subtraction(session):
    context, prompt = _prompt(session, capacity=1000, linked_units=600)          # the Product Owner's 1,000 / 600 example: the internal subtraction is 400
    assert context.indicative_residual_capacity == 400 and context.development_coverage_classification == "PARTIAL_COVERAGE"
    assert not re.search(r"\b400\b", prompt) and "Indicative residual" not in prompt                 # 1. no trusted residual acquisition count is supplied
    assert "Potential residual scope: potential only" in prompt                                         # 4. potential / investigative only
    assert "a distinct residual acquisition scope and its capacity are not yet established" in prompt
    assert not re.search(r"(calculate|compute|work out|subtract|deduct)[^.\n]{0,60}(residual|remaining|unaccounted)", prompt.split("RULES")[0], re.I)     # 2. no instruction to calculate (data section)
    rules = prompt.split("RULES - follow every one of these exactly:")[1]
    assert re.search(r"0\. NEVER subtract planning-application or linked-site counts from the allocation capacity", rules)       # 3. explicit prohibition
    assert re.search(r"no availability, ownership, title, geometry or further-phase inference", rules)                                # 5. availability / ownership / title / parcel
    assert "do NOT recalculate any of these numbers yourself" in prompt                                                              # existing instruction preserved
    # the legitimate factual inputs are still supplied (not stripped merely to prevent arithmetic)
    assert "1,000" in prompt or "1000" in prompt
    assert "Identified planning application capacity: 600" in prompt
    assert PROMPT_VERSION == "allocation-intelligence-summary-v9"


def test_r3_prompt_makes_no_residual_proposition(session):
    _, prompt = _prompt(session, capacity=1000, linked_units=1000)
    assert "Potential residual scope: none indicated - make no residual or remaining-capacity statement" in prompt


# --- AI grounding: R1 ----------------------------------------------------------------------------------------------------------------------------------------------

def test_r1_may_be_supplied_to_a_model_only_as_derived_apparent_with_the_caveat():
    from benchmark.v8_residual_cases import child, parent, qualified_evidence
    p, c = parent(500), child("1", 300)
    r1 = ro.qualify_residual(p, [c], qualified_evidence(p, [c]))
    fact = ro.r1_prompt_fact(r1)
    assert "Derived (apparent)" in fact and "200 homes" in fact and ro.R1_CAVEAT in fact and "Do not recompute" in fact and "not treat it as available land" in fact
    r2 = ro.qualify_residual(p, [c], ro.ResidualEvidence(containment=tuple((c.subject_id, p.subject_id, "x") for _ in [0])))
    for qualification in (r2, ro.qualify_residual(p, [])):
        with pytest.raises(ValueError):
            ro.r1_prompt_fact(qualification)                                                    # R2 / R3 have no quantity to supply
    for module in ("allocation_intelligence_summary", "cross_site_intelligence", "scheme_summary", "local_plan_summary"):
        path = ROOT / "app/reporting" / f"{module}.py"
        if path.exists():
            assert "residual_value" not in path.read_text(encoding="utf-8") and "r1_prompt_fact" not in path.read_text(encoding="utf-8")   # no prompt uses R1 today


# --- surface wording sweep -----------------------------------------------------------------------------------------------------------------------------------------

SURFACES = (
    "app/ui/shell.py", "app/ui/pages/3b_Shortlist.py", "app/ui/pages/3_Local_Plan_Sites.py", "app/ui/pages/00_Dashboard.py", "app/reporting/family_presentation.py",
    "app/reporting/allocation_discovery.py", "app/reporting/allocation_report.py", "app/reporting/allocation_report_pdf.py", "app/reporting/ownership_control.py",
    "app/reporting/site_profile.py", "app/reporting/cross_site_intelligence.py", "app/reporting/allocation_intelligence_summary.py", "app/reporting/opportunity_signal.py",
    "app/reporting/opportunity_route.py", "app/reporting/opportunity_feed.py", "app/policy/allocation_planning_coverage.py", "app/reporting/residual_opportunity.py",
    "app/policy/residual_fit.py",
)
FORBIDDEN = re.compile(
    r"remaining acquisition scope|remaining (homes|land|parcel|capacity|units)|homes remaining|residual capacity:\s*[\{0-9]|[0-9,{}a-z_.]+ homes (are )?not (currently )?accounted|"
    r"available residual|residual (homes|land)\b|unaccounted-for (homes|land|capacity)", re.I)


def _string_literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def test_no_surface_string_asserts_remaining_scope_or_a_residual_quantity():
    offenders = []
    for relative in SURFACES:
        path = ROOT / relative
        if not path.exists():
            continue
        for text in _string_literals(path):
            for match in FORBIDDEN.finditer(text):
                offenders.append((relative, match.group(0)))
    assert offenders == [], offenders


def test_the_raw_internal_coverage_producer_is_only_reachable_through_the_neutral_wrapper_in_user_facing_paths():
    # the pinned producer still emits the raw coverage sentence (internal); every user-facing caller uses the wrapper that rewrites it to the R2 text
    for relative in ("app/reporting/opportunity_feed.py", "app/reporting/allocation_discovery.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "build_neutral_opportunity_signal" in text, relative
    for relative in ("app/reporting/opportunity_feed.py",):
        assert not re.search(r"\bbuild_opportunity_signal\(", (ROOT / relative).read_text(encoding="utf-8"))
    from app.reporting.opportunity_signal import build_neutral_opportunity_signal
    from app.reporting.allocation_development_coverage import DevelopmentCoverageResult
    fields = {f.name: None for f in dataclasses.fields(DevelopmentCoverageResult)}
    fields.update(allocation_capacity=1000, identified_application_capacity=600, indicative_residual_capacity=400, development_coverage_percentage=0.6,
                  development_coverage_classification="PARTIAL_COVERAGE", capacity_accounting_status="ok", number_of_sites_with_planning_activity=1)
    out = build_neutral_opportunity_signal(plan_status_bucket="adopted", coverage=DevelopmentCoverageResult(**fields), phasing={"classification": "NONE", "evidence": []})
    text = " ".join(out["reasons"])
    assert ro.ALLOCATION_R2_TEXT in text and not re.search(r"\b400\b|\b60%|not (currently )?accounted", text) and not FORBIDDEN.search(text)


def test_r2_texts_are_non_assertive():
    for text in (ro.PLANNING_R2_TEXT, ro.ALLOCATION_R2_TEXT, ro.POTENTIAL_RESIDUAL_SHORT):
        assert text.startswith("Potential residual scope — investigate")
        assert not re.search(r"[0-9]|\bavailable\b|\bremaining\b|\bowns?\b|\btitle\b|parcel|further phase|definitely|for sale", text, re.I), text
    assert "are not yet established" in ro.PLANNING_R2_TEXT and "are not yet established" in ro.ALLOCATION_R2_TEXT


# --- residual identity ruling (Product Owner decision 1) -----------------------------------------------------------------------------------------------------------

def test_parent_count_change_keeps_the_subject_id_but_moves_the_fingerprint_and_a_parent_scope_change_changes_the_id():
    from benchmark.v8_residual_cases import child, parent, qualified_evidence
    kids = [child("1", 200), child("2", 150)]
    base = ro.qualify_residual(parent(500), kids, qualified_evidence(parent(500), kids))
    bigger = ro.qualify_residual(parent(520), kids, qualified_evidence(parent(520), kids))
    assert base.subject_id == bigger.subject_id and base.evidence_fingerprint != bigger.evidence_fingerprint
    assert base.residual_value == 150 and bigger.residual_value == 170
    new_scope = dataclasses.replace(parent(500), subject_id="site:61:phase:Outline", scope_type="phase", scope_label="Outline")
    assert ro.residual_subject_identity(61, new_scope.subject_id, [k.subject_id for k in kids]) != base.subject_id


# --- differential allow-list: the four unexpected classes still fail ----------------------------------------------------------------------------------------------

def _forged(monkeypatch, facts, policy, v7, v8):
    import verification.transition.v7_parity as parity
    real = bm.assess_buyer_fit(policy, facts)
    monkeypatch.setattr(parity, "frozen_v7_assess_buyer_fit", lambda p, f, context=None: dataclasses.replace(real, classification=v7[0], is_investigative_exception=v7[1]))
    return parity.differential_category(policy, facts, None, dataclasses.replace(real, classification=v8[0], is_investigative_exception=v8[1]))[0]


def _strategic(minimum, indicative, maximum):
    from tests.test_v8_frozen_v7_oracle import _strategic_facts
    return _strategic_facts(minimum, indicative, maximum)


def test_the_four_unexpected_regression_classes_each_fail(monkeypatch):
    nesten, slb = BUYER_PROFILES["nesten_homes"], BUYER_PROFILES["strategic_land_buyer"]
    U = "UNEXPECTED_REGRESSION"
    # unexpected NOT_SUITABLE on a non-exact strategic capacity
    assert _forged(monkeypatch, _strategic(150, None, None), nesten, (bm.STRONG_FIT, False), (bm.NOT_SUITABLE, False)) == U
    # unexpected planning-delivery delta
    planning = dataclasses.replace(_strategic(150, None, 150), opportunity_type=bm.PLANNING_DELIVERY, count_assessment=None)
    assert _forged(monkeypatch, planning, nesten, (bm.STRONG_FIT, False), (bm.POSSIBLE_FIT, False)) == U
    # unexpected exact-strategic delta
    assert _forged(monkeypatch, _strategic(150, None, 150), nesten, (bm.STRONG_FIT, False), (bm.INSUFFICIENT_EVIDENCE, True)) == U
    # preserved Strategic Land route delta
    assert _forged(monkeypatch, _strategic(1500, None, 2500), slb, (bm.STRONG_FIT, True), (bm.INSUFFICIENT_EVIDENCE, False)) == U


# --- strategic fingerprint pins ---------------------------------------------------------------------------------------------------------------------------------

def test_strategic_capacity_kinds_are_fingerprint_visible_and_exact_is_unchanged():
    from tests.test_v8_strategic_fingerprint import facts, fingerprint
    exact, floor, ceiling = facts(150, None, 150), facts(150, None, None), facts(None, None, 150)
    assert fingerprint(exact) != fingerprint(floor)                      # exact 150 != minimum-only 150
    assert fingerprint(floor) != fingerprint(ceiling)                    # minimum-only 150 != maximum-only 150
    assert fingerprint(exact) != fingerprint(ceiling)
    from app.reporting.opportunity_universe import strategic_capacity_fingerprint_fields
    assert strategic_capacity_fingerprint_fields(exact) == {}            # exact: no new key, byte-for-byte pre-v8


def test_planning_delivery_fingerprints_are_not_broadened():
    source = (ROOT / "app/reporting/opportunity_universe.py").read_text(encoding="utf-8")
    assert source.count("strategic_capacity_fingerprint_fields(") == 2   # the definition and the single strategic call site only
    planning = source[source.index("def _planning_delivery"):] if "def _planning_delivery" in source else ""
    assert "capacity_semantics" not in planning and "strategic_capacity_fingerprint_fields" not in planning


# --- benchmark approval record ------------------------------------------------------------------------------------------------------------------------------------

# sha256 of the approved expectation fields (case id, route, v7 result, proposed v8 result, residual level, proposed count, representative expectation) for the 24 rows Product Owner
# REVIEW approved at 8fd1c7d. Any later change to an approved expectation changes this digest and FAILS here: the expectation is never edited to fit the code (STOP and report).


def _expectation_digest(table):
    keys = ("case_id", "route", "v7_result", "proposed_v8_result", "residual_level", "proposed_residual_count", "representative_expectation")
    payload = [[row.get(k) for k in keys] for row in table["rows"]]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def test_the_24_row_v8_expectation_table_is_approved_exactly_as_reviewed():
    from benchmark.v8_expectation_table import APPROVED_BY_PRODUCT_OWNER, EXPECTATION_DIGEST_AT_APPROVAL, build_v8_expectation_table
    table = build_v8_expectation_table()
    assert APPROVED_BY_PRODUCT_OWNER is True and table["approved_by_product_owner"] is True and len(table["rows"]) == 24
    assert all(r["approved_by_product_owner"] is True for r in table["rows"])
    assert table["disagreements"] == [] and table["unexpected_regressions"] == []
    assert _expectation_digest(table) == EXPECTATION_DIGEST_AT_APPROVAL

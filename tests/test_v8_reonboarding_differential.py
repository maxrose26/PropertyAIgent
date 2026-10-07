"""v8 production transition: the standalone re-onboarding dry run with the REAL frozen-v7 oracle reports the v7->v8 differential by category and refuses on anything outside the approved
narrow strategic deltas. Synthetic data only; real v8 matcher; no ordinary sync, reseed or model call."""
from __future__ import annotations

import pytest

import app.policy.buyer_profile_store as store
from app.db.models import LocalPlan, LocalPlanSite
from app.policy.mandate_reonboarding import PARITY_FAILED, PARITY_PASSED, plan_stale_mandate_reonboarding
from scripts.reonboard_stale_mandates import PARITY_ORACLE
from tests.test_v7c_mandate_reonboarding import _make_site
from verification.transition.v7_parity import v7_parity_oracle


@pytest.fixture
def universe(session):
    workspace = store.resolve_default_workspace(session)
    store.seed_default_buyer_profiles(session, workspace)
    for units in (75, 150):
        _make_site(session, unit_count=units)
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="adopted", raw_status="adopted")
    session.add(plan)
    session.commit()
    for ref, minimum, maximum in (("EX", 150, 150), ("RG", 300, 500), ("FL", 700, None), ("CE", None, 120)):      # exact, range, open floor, open ceiling
        session.add(LocalPlanSite(council_code="testcouncil", local_plan_id=plan.id, policy_reference=ref, site_name=f"Alloc {ref}", plan_name="Test Local Plan",
                                  plan_status="adopted", intended_use="residential", minimum_dwellings=minimum, maximum_capacity=maximum, site_area_hectares=5.0))
    session.commit()
    return session


def test_the_launcher_wires_the_frozen_v7_oracle():
    assert PARITY_ORACLE is v7_parity_oracle


def test_dry_run_counts_equal_and_expected_strategic_deltas_and_passes(universe):
    report = plan_stale_mandate_reonboarding(universe, parity_oracle=PARITY_ORACLE)
    assert report["parity"]["status"] == PARITY_PASSED and report["can_apply"] is True and report["read_only"] is True
    counts = report["parity"]["category_counts"]
    assert set(counts) <= {"EQUAL", "EXPECTED_STRATEGIC_DELTA"} and counts.get("EQUAL", 0) > 0
    assert report["parity"]["classification_mismatches"] == 0 and report["parity"]["investigative_mismatches"] == 0
    deltas = [d for entry in report["stale_mandates"] for d in entry["parity"]["expected_strategic_deltas_listed"]]
    assert deltas and all(d["opportunity_id"].startswith("strategic_land:allocation:") for d in deltas)           # deltas are strategic only
    assert not any(d["opportunity_id"].startswith("planning_delivery:") for d in deltas)                           # no planning-delivery delta is ever expected
    assert counts.get("EXPECTED_STRATEGIC_DELTA", 0) == len(deltas) or len(deltas) == 500
    assert plan_stale_mandate_reonboarding(universe, parity_oracle=PARITY_ORACLE)["plan_digest"] == report["plan_digest"]      # deterministic, binds the categories


def test_an_unexpected_delta_fails_closed_and_blocks_apply(universe, monkeypatch):
    import verification.transition.v7_parity as parity
    real = parity.frozen_v7_assess_buyer_fit

    def forged(policy, facts, context=None):
        out = real(policy, facts, context=context)
        if facts.opportunity_type == "planning_delivery":                       # an unexpected planning-delivery difference
            import dataclasses
            return dataclasses.replace(out, classification="NOT_SUITABLE" if out.classification != "NOT_SUITABLE" else "STRONG_FIT")
        return out
    monkeypatch.setattr(parity, "frozen_v7_assess_buyer_fit", forged)
    report = plan_stale_mandate_reonboarding(universe, parity_oracle=PARITY_ORACLE)
    assert report["parity"]["status"] == PARITY_FAILED and report["can_apply"] is False and report["blocking_reasons"]
    assert report["parity"]["classification_mismatches"] > 0

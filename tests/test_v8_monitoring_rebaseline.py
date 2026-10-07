"""v8 production transition: the controlled monitoring rebaseline of the intentional strategic capacity-semantics fingerprint change.

The 'pre-v8' state is simulated by baselining the monitoring table with ``strategic_capacity_fingerprint_fields`` returning nothing (exactly the pre-v8 fingerprint). Synthetic SQLite only."""
from __future__ import annotations

import inspect
import json
import re
import socket
from pathlib import Path

import pytest
from sqlalchemy import select

import app.reporting.opportunity_change as oc
import app.reporting.opportunity_universe as universe
import app.reporting.v8_monitoring_rebaseline as rb
from app.db.models import Application, LocalPlanSite, OpportunityMonitoringState
from tests.test_buyer_family_feed import LAPSE_AGE, World
from tests.test_v7c_monitoring_preview import WriteGuard, table

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def world(session, monkeypatch):
    return World(session, monkeypatch)


def seed_pre_v8(world, monkeypatch):
    """Planning sites + three strategic allocations (exact, range, and the exact one linked to nothing), baselined under PRE-v8 fingerprints."""
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)
    world.site(rm_age=300, rm_phase="Phase 1")
    exact = world.allocation(capacity=8400)
    ranged = world.allocation(capacity=500, minimum_dwellings=300)
    open_floor = world.allocation(capacity=700)
    open_floor.maximum_capacity = None                                   # minimum-only 700: open floor
    world.session.commit()
    monkeypatch.setattr(universe, "strategic_capacity_fingerprint_fields", lambda facts: {})      # the pre-v8 fingerprint
    oc.sync_opportunity_monitoring_state(world.session)
    monkeypatch.undo()                                                    # v8 behaviour again (note: also undoes World's evaluator patch; plan/preview do not use it)
    return exact, ranged, open_floor


def ids(prefix_rows):
    return {e["opportunity_id"] for e in prefix_rows}


def test_plan_includes_only_non_exact_strategic_allocations_and_is_read_only(session, world, monkeypatch):
    exact, ranged, floor = seed_pre_v8(world, monkeypatch)
    before = table(session)
    with WriteGuard(session):
        plan = rb.build_rebaseline_plan(session)
    assert table(session) == before and plan["read_only"] is True
    assert ids(plan["eligible"]) == {f"strategic_land:allocation:{ranged.id}", f"strategic_land:allocation:{floor.id}"}
    assert f"strategic_land:allocation:{exact.id}" not in ids(plan["eligible"]) | ids(plan["not_included"]) | ids(plan["blockers"])      # exact: fingerprint unchanged, nothing to do
    assert plan["planning_delivery_in_eligible"] == 0 and not any(i.startswith("planning_delivery:") for i in ids(plan["eligible"]))
    for entry in plan["eligible"]:
        assert entry["detector"] == "strategic_land:allocation" and set(entry["changed_fields"]) == {"capacity_semantics"} and entry["expected_v8_strategic_capacity_semantic_change"] is True
        assert entry["previous_fingerprint"] != entry["proposed_fingerprint"] and entry["changed_fields"]["capacity_semantics"]["old"] is None and entry["reason"]
    assert plan["can_apply"] is True and re.fullmatch(r"[0-9a-f]{64}", plan["plan_digest"])
    assert json.loads(json.dumps(plan, default=str)) is not None and rb.build_rebaseline_plan(session)["plan_digest"] == plan["plan_digest"]      # deterministic


def test_a_genuine_planning_change_is_reported_but_never_rebaselined(session, world, monkeypatch):
    seed_pre_v8(world, monkeypatch)
    session.query(Application).filter(Application.reference.like("RM/%")).first().decision = "Refused"
    session.commit()
    plan = rb.build_rebaseline_plan(session)
    assert any(n["opportunity_id"].startswith("planning_delivery:") for n in plan["not_included"])
    assert not any(e["opportunity_id"].startswith("planning_delivery:") for e in plan["eligible"])
    result = rb.apply_rebaseline(session, confirm=rb.CONFIRM_PHRASE, expected_plan_digest=plan["plan_digest"])
    after = oc.preview_ordinary_sync(session)
    still = {c["opportunity_id"] for c in after["changes"]}
    assert any(i.startswith("planning_delivery:") for i in still)                      # the genuine change is still visible to ordinary monitoring
    assert not (still & set(result["rebaselined_ids"])) and result["still_reported_changed_after_apply"] == []


def test_apply_requires_phrase_and_the_reviewed_digest_and_writes_only_the_manifest_fields(session, world, monkeypatch):
    exact, ranged, floor = seed_pre_v8(world, monkeypatch)
    plan = rb.build_rebaseline_plan(session)
    before = table(session)
    with pytest.raises(rb.RebaselineRefused):
        rb.apply_rebaseline(session, confirm="wrong", expected_plan_digest=plan["plan_digest"])
    with pytest.raises(rb.RebaselineRefused):
        rb.apply_rebaseline(session, confirm=rb.CONFIRM_PHRASE, expected_plan_digest="0" * 64)
    assert table(session) == before                                                    # refusals write nothing
    result = rb.apply_rebaseline(session, confirm=rb.CONFIRM_PHRASE, expected_plan_digest=plan["plan_digest"])
    assert sorted(result["rebaselined_ids"]) == sorted(ids(plan["eligible"])) and result["mode"] == "applied"
    after = table(session)
    changed = {k for k in after if after[k] != before[k]}
    assert changed == set(result["rebaselined_ids"])
    for key in changed:
        old, new = before[key], after[key]
        assert old[0] != new[0] and old[1] != new[1]                                    # fingerprint + fingerprint_fields updated
        assert old[2:] == new[2:]                                                       # classification / reasons / last_change_at untouched: a snapshot correction, not a change event
    assert oc.preview_ordinary_sync(session)["predicted"]["MATERIALLY_CHANGED"] == 0
    assert oc.sync_opportunity_monitoring_state(session)["materially_changed"] == 0     # the next ordinary sync reports UNCHANGED, not a phantom change
    with pytest.raises(rb.RebaselineRefused):
        rb.apply_rebaseline(session, confirm=rb.CONFIRM_PHRASE, expected_plan_digest=plan["plan_digest"])    # nothing left to do: a second apply is refused


def test_a_mixed_change_blocks_apply_and_is_never_hidden(session, world, monkeypatch):
    exact, ranged, floor = seed_pre_v8(world, monkeypatch)
    allocation = session.get(LocalPlanSite, ranged.id)
    allocation.site_area_hectares = 11.0                                                # a genuine evidence change coinciding with v8
    session.commit()
    plan = rb.build_rebaseline_plan(session)
    assert [b["opportunity_id"] for b in plan["blockers"]] == [f"strategic_land:allocation:{ranged.id}"] and plan["can_apply"] is False
    assert {"capacity_semantics", "site_area_hectares"} <= set(plan["blockers"][0]["changed_fields"])
    assert f"strategic_land:allocation:{ranged.id}" not in ids(plan["eligible"])
    before = table(session)
    with pytest.raises(rb.RebaselineRefused):
        rb.apply_rebaseline(session, confirm=rb.CONFIRM_PHRASE, expected_plan_digest=plan["plan_digest"])
    assert table(session) == before


def test_digest_moves_when_the_reviewed_state_drifts(session, world, monkeypatch):
    exact, ranged, floor = seed_pre_v8(world, monkeypatch)
    first = rb.build_rebaseline_plan(session)
    allocation = session.get(LocalPlanSite, floor.id)
    allocation.minimum_dwellings = 710                                                  # the open-floor figure changes after the dry run
    session.commit()
    second = rb.build_rebaseline_plan(session)
    assert second["plan_digest"] != first["plan_digest"]
    with pytest.raises(rb.RebaselineRefused):
        rb.apply_rebaseline(session, confirm=rb.CONFIRM_PHRASE, expected_plan_digest=first["plan_digest"])


def test_a_planning_delivery_id_can_never_be_eligible_even_if_a_preview_claims_it():
    preview = {"totals": {}, "changes": [{
        "opportunity_id": "planning_delivery:phase:1:A", "classification": "MATERIALLY_CHANGED", "reasons": [], "previous_fingerprint": "a", "new_fingerprint": "b",
        "changed_fields": {"capacity_semantics": {"old": None, "new": {"precision": "RANGE"}}}}]}
    plan = rb.build_rebaseline_plan(None, preview=preview)
    assert plan["eligible"] == [] and plan["blockers"] == [] and plan["not_included"][0]["opportunity_id"] == "planning_delivery:phase:1:A"


def test_exact_strategic_and_unrelated_fields_are_not_expected_semantic_changes():
    base = {"opportunity_id": "strategic_land:allocation:1", "classification": "MATERIALLY_CHANGED", "reasons": [], "previous_fingerprint": "a", "new_fingerprint": "b"}
    cases = [
        ({"capacity_semantics": {"old": None, "new": {"precision": "EXACT"}}}, "blockers"),                      # an EXACT kind never adds the key: anomalous, so it blocks rather than rebaselines
        ({"unit_count": {"old": 1, "new": 2}}, "not_included"),
        ({"capacity_semantics": {"old": {"precision": "RANGE"}, "new": {"precision": "RANGE", "lower": 1}}}, "blockers"),     # the key already existed: a genuine change of kind/bounds, never silently rebaselined
        ({"capacity_semantics": {"old": None, "new": {"precision": "RANGE"}}, "unit_count": {"old": 1, "new": 2}}, "blockers"),
    ]
    for fields, bucket in cases:
        plan = rb.build_rebaseline_plan(None, preview={"totals": {}, "changes": [{**base, "changed_fields": fields}]})
        assert plan["eligible"] == [] and len(plan[bucket]) == 1, (fields, plan)


def test_the_cli_is_registered_authorised_and_has_no_model_network_or_ordinary_sync_path(monkeypatch):
    manifest = json.loads((ROOT / "verification/stage1_cli_manifest.json").read_text(encoding="utf-8"))
    assert manifest["scripts/v8_monitoring_rebaseline.py"] == {"command": "v8_monitoring_rebaseline", "required_scope": "launch:v8_monitoring_rebaseline"}
    script = (ROOT / "scripts/v8_monitoring_rebaseline.py").read_text(encoding="utf-8")
    assert "@authorised_cli('v8_monitoring_rebaseline')" in script and "open(path, \"x\"" in script
    import ast
    for module in (script, inspect.getsource(rb)):
        tree = ast.parse(module)
        imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)} | {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert not any(re.match(r"(openai|anthropic|requests|httpx|urllib|socket)", m) or "bootstrap" in m for m in imported), imported
        assert not called & {"sync_opportunity_monitoring_state", "run_buyer_onboarding_baseline", "create_all"}, called      # no ordinary sync, no onboarding, no schema
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network attempted")))
    assert rb.CONFIRM_PHRASE == "REBASELINE V8 STRATEGIC CAPACITY SEMANTICS"

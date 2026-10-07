"""v8 production transition: deterministic ROLLBACK tools for the two production writes.

Property proved for each: forward -> expected post-state -> rollback -> the original state, compared over EVERY column of EVERY row of the owned tables (so the owned fields are byte/field-equal
and nothing else moved). Also: dry-run default (read-only), exact reviewed digest, confirm phrase, drift refusal, tamper refusal, single-transaction atomicity, double-apply refusal.
Synthetic SQLite only; no ordinary sync, reseed or model call."""
from __future__ import annotations

import datetime as dt
import inspect
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select

import app.policy.buyer_profile_store as store
import app.policy.mandate_reonboarding as mr
import app.policy.mandate_reonboarding_rollback as mrr
import app.reporting.opportunity_change as oc
import app.reporting.v8_monitoring_rebaseline as rb
import app.reporting.v8_monitoring_rollback as mrb
from app.db.models import Buyer, BuyerMandate, OpportunityMonitoringState
from tests.test_v7c_mandate_reonboarding import WriteGuard as MandateWriteGuard
from tests.test_v7c_mandate_reonboarding import _make_site
from tests.test_v7c_monitoring_preview import WriteGuard
from tests.test_v8_monitoring_rebaseline import seed_pre_v8
from tests.test_buyer_family_feed import World
from verification.transition.v7_parity import v7_parity_oracle

ROOT = Path(__file__).resolve().parents[1]


def snapshot(session, model):
    """Every column of every row, as plain comparable values."""
    session.expire_all()
    columns = [c.key for c in sa_inspect(model).columns]
    return {(row.opportunity_id,): {c: getattr(row, c) for c in columns} for row in session.execute(select(model)).scalars()}


def roundtrip(value):
    return json.loads(json.dumps(value, default=str))


# ========================= A. monitoring rebaseline rollback =====================================================================================================================

@pytest.fixture
def world(session, monkeypatch):
    return World(session, monkeypatch)


def forward_monitoring(session, world, monkeypatch):
    seed_pre_v8(world, monkeypatch)
    before = snapshot(session, OpportunityMonitoringState)
    plan = rb.build_rebaseline_plan(session)
    result = rb.apply_rebaseline(session, confirm=rb.CONFIRM_PHRASE, expected_plan_digest=plan["plan_digest"])
    forward = mrb.load_forward_artifacts(roundtrip(plan), roundtrip(result))             # via JSON: exactly what the audit files hold
    return before, plan, result, forward


def test_monitoring_forward_then_rollback_restores_every_column_of_every_row(session, world, monkeypatch):
    before, plan, result, forward = forward_monitoring(session, world, monkeypatch)
    mid = snapshot(session, OpportunityMonitoringState)
    owned = set(result["rebaselined_ids"])
    changed = {k for k in mid if mid[k] != before[k]}
    assert {k[0] for k in changed} == owned and owned
    for key in changed:                                                                   # forward changed ONLY the two owned columns
        assert {c for c in mid[key] if mid[key][c] != before[key][c]} <= {"fingerprint", "fingerprint_fields", "last_seen_at"}
    restore = mrb.build_restore_plan(session, forward)
    assert restore["can_apply"] is True and restore["blockers"] == [] and {e["current_state"] for e in restore["entries"]} == {mrb.AT_POST_STATE}
    out = mrb.apply_restore(session, forward, confirm=mrb.CONFIRM_PHRASE, expected_restore_digest=restore["restore_plan_digest"])
    assert out["all_restored"] is True and sorted(out["restored_ids"]) == sorted(owned)
    after = snapshot(session, OpportunityMonitoringState)
    assert after == before                                                                # EVERY column of EVERY row, including last_seen_at, is byte/field-equal to the original
    for opportunity_id in owned:                                                          # byte-exact: the stored JSON string and the hash are the originals
        row = session.execute(select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == opportunity_id)).scalar_one()
        original = before[(opportunity_id,)]
        assert row.fingerprint == original["fingerprint"] and row.fingerprint_fields == original["fingerprint_fields"]
    assert oc.preview_ordinary_sync(session)["predicted"]["MATERIALLY_CHANGED"] >= len(owned)   # back to the pre-v8 baseline: ordinary monitoring would see the v8 difference again


def test_monitoring_restore_plan_is_read_only_deterministic_and_requires_phrase_and_digest(session, world, monkeypatch):
    before, plan, result, forward = forward_monitoring(session, world, monkeypatch)
    mid = snapshot(session, OpportunityMonitoringState)
    with WriteGuard(session):
        restore = mrb.build_restore_plan(session, forward)
    assert snapshot(session, OpportunityMonitoringState) == mid and mrb.build_restore_plan(session, forward)["restore_plan_digest"] == restore["restore_plan_digest"]
    with pytest.raises(mrb.RollbackRefused):
        mrb.apply_restore(session, forward, confirm="nope", expected_restore_digest=restore["restore_plan_digest"])
    with pytest.raises(mrb.RollbackRefused):
        mrb.apply_restore(session, forward, confirm=mrb.CONFIRM_PHRASE, expected_restore_digest="0" * 64)
    assert snapshot(session, OpportunityMonitoringState) == mid


def test_monitoring_restore_refuses_when_a_row_has_drifted_or_was_already_restored(session, world, monkeypatch):
    before, plan, result, forward = forward_monitoring(session, world, monkeypatch)
    first = forward["entries"][0]["opportunity_id"]
    row = session.execute(select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == first)).scalar_one()
    row.fingerprint = "f" * 64                                                            # e.g. an ordinary sync or a manual edit after the forward apply
    session.commit()
    restore = mrb.build_restore_plan(session, forward)
    assert restore["can_apply"] is False and restore["blockers"][0]["current_state"] == mrb.DRIFTED
    snap = snapshot(session, OpportunityMonitoringState)
    with pytest.raises(mrb.RollbackRefused):
        mrb.apply_restore(session, forward, confirm=mrb.CONFIRM_PHRASE, expected_restore_digest=restore["restore_plan_digest"])
    assert snapshot(session, OpportunityMonitoringState) == snap                          # nothing written, not even the undrifted rows


def test_monitoring_second_restore_is_refused(session, world, monkeypatch):
    before, plan, result, forward = forward_monitoring(session, world, monkeypatch)
    restore = mrb.build_restore_plan(session, forward)
    mrb.apply_restore(session, forward, confirm=mrb.CONFIRM_PHRASE, expected_restore_digest=restore["restore_plan_digest"])
    again = mrb.build_restore_plan(session, forward)
    assert again["can_apply"] is False and {e["current_state"] for e in again["entries"]} == {mrb.ALREADY_RESTORED}
    with pytest.raises(mrb.RollbackRefused):
        mrb.apply_restore(session, forward, confirm=mrb.CONFIRM_PHRASE, expected_restore_digest=again["restore_plan_digest"])


def test_monitoring_forward_artifacts_are_integrity_checked(session, world, monkeypatch):
    before, plan, result, forward = forward_monitoring(session, world, monkeypatch)
    tampered = roundtrip(plan)
    tampered["eligible"][0]["previous_fingerprint"] = "0" * 64
    with pytest.raises(mrb.RollbackRefused):
        mrb.load_forward_artifacts(tampered, roundtrip(result))                           # fails its own digest
    wrong_result = roundtrip(result)
    wrong_result["rebaselined_ids"] = wrong_result["rebaselined_ids"][:-1]
    with pytest.raises(mrb.RollbackRefused):
        mrb.load_forward_artifacts(roundtrip(plan), wrong_result)
    not_applied = roundtrip(result)
    not_applied["mode"] = "refused"
    with pytest.raises(mrb.RollbackRefused):
        mrb.load_forward_artifacts(roundtrip(plan), not_applied)
    lossy = roundtrip(plan)
    lossy["eligible"][0]["previous_fingerprint_fields"] = None
    lossy["plan_digest"] = mrb.forward_digest_of(lossy["eligible"])
    with pytest.raises(mrb.RollbackRefused):
        mrb.load_forward_artifacts(lossy, roundtrip(result))                              # a lossy audit can never drive a restore


def test_monitoring_restore_is_one_transaction_and_rolls_back_completely_on_failure(session, world, monkeypatch):
    before, plan, result, forward = forward_monitoring(session, world, monkeypatch)
    mid = snapshot(session, OpportunityMonitoringState)
    restore = mrb.build_restore_plan(session, forward)
    real_commit = session.commit
    monkeypatch.setattr(session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("simulated failure at commit")))
    with pytest.raises(RuntimeError):
        mrb.apply_restore(session, forward, confirm=mrb.CONFIRM_PHRASE, expected_restore_digest=restore["restore_plan_digest"])
    monkeypatch.setattr(session, "commit", real_commit)
    assert snapshot(session, OpportunityMonitoringState) == mid                           # nothing partially restored


# ========================= B. mandate re-onboarding rollback ========================================================================================================================

@pytest.fixture
def seeded(session):
    workspace = store.resolve_default_workspace(session)
    store.seed_default_buyer_profiles(session, workspace)
    for units in (75, 150, 500):
        _make_site(session, unit_count=units)
    return session


def mandate_snapshot(session):
    out = {}
    for model in (BuyerMandate, Buyer):
        session.expire_all()
        for row in session.execute(select(model)).scalars():
            out[(model.__name__, row.id)] = {c.key: getattr(row, c.key) for c in sa_inspect(model).columns}
    return out


def forward_reonboarding(session, *, preset_old=False):
    if preset_old:                                                                        # a mandate that WAS onboarded earlier (non-null old values must be restored exactly)
        mandate = session.execute(select(BuyerMandate).order_by(BuyerMandate.id)).scalars().first()
        mandate.matching_fingerprint = "a" * 64
        mandate.onboarding_completed_at = dt.datetime(2026, 1, 2, 3, 4, 5, 678901)
        mandate.onboarding_summary = "reviewed=1 strong_fit=1 possible_fit=0 not_suitable=0 insufficient_evidence=0 investigative_exceptions=0"
        session.commit()
    before = mandate_snapshot(session)
    plan = mr.plan_stale_mandate_reonboarding(session, parity_oracle=v7_parity_oracle)
    report = mr.apply_stale_mandate_reonboarding(session, confirm=mr.CONFIRM_PHRASE, expected_plan_digest=plan["plan_digest"], parity_oracle=v7_parity_oracle)
    return before, plan, report, mrr.load_forward_report(roundtrip(report))


@pytest.mark.parametrize("preset_old", [False, True])
def test_reonboarding_forward_then_rollback_restores_every_column_of_every_mandate_and_buyer(seeded, preset_old):
    before, plan, report, forward = forward_reonboarding(seeded, preset_old=preset_old)
    mid = mandate_snapshot(seeded)
    changed = {key for key in mid if mid[key] != before[key]}
    assert changed and all(k[0] == "BuyerMandate" for k in changed)
    for key in changed:                                                                   # forward changed ONLY the three owned columns
        assert {c for c in mid[key] if mid[key][c] != before[key][c]} <= {"matching_fingerprint", "onboarding_completed_at", "onboarding_summary", "updated_at"}   # the three owned columns + the ORM onupdate timestamp
    restore = mrr.plan_mandate_reonboarding_rollback(seeded, forward)
    assert restore["can_apply"] is True and {e["current_state"] for e in restore["entries"]} == {mrr.AT_POST_STATE}
    out = mrr.apply_mandate_reonboarding_rollback(seeded, forward, confirm=mrr.CONFIRM_PHRASE, expected_restore_digest=restore["restore_plan_digest"])
    assert out["all_restored"] is True
    after = mandate_snapshot(seeded)
    assert after == before                                                                # EVERY column of EVERY mandate and buyer (rule fields, updated_at and the owned columns) equals the original
    if preset_old:
        first = after[("BuyerMandate", min(k[1] for k in after if k[0] == "BuyerMandate"))]
        assert first["onboarding_completed_at"] == dt.datetime(2026, 1, 2, 3, 4, 5, 678901) and first["matching_fingerprint"] == "a" * 64
    stale_again = mr.plan_stale_mandate_reonboarding(seeded, parity_oracle=v7_parity_oracle)
    assert stale_again["stale_mandates"]                                                  # the mandates are stale again, exactly as before the forward transition


def test_reonboarding_restore_plan_is_read_only_and_requires_phrase_and_digest(seeded):
    before, plan, report, forward = forward_reonboarding(seeded)
    mid = mandate_snapshot(seeded)
    with MandateWriteGuard(seeded):
        restore = mrr.plan_mandate_reonboarding_rollback(seeded, forward)
    assert mandate_snapshot(seeded) == mid and mrr.plan_mandate_reonboarding_rollback(seeded, forward)["restore_plan_digest"] == restore["restore_plan_digest"]
    with pytest.raises(mrr.RollbackRefused):
        mrr.apply_mandate_reonboarding_rollback(seeded, forward, confirm="nope", expected_restore_digest=restore["restore_plan_digest"])
    with pytest.raises(mrr.RollbackRefused):
        mrr.apply_mandate_reonboarding_rollback(seeded, forward, confirm=mrr.CONFIRM_PHRASE, expected_restore_digest="0" * 64)
    assert mandate_snapshot(seeded) == mid


def test_reonboarding_restore_refuses_on_drift_and_on_a_second_apply(seeded):
    before, plan, report, forward = forward_reonboarding(seeded)
    mandate = seeded.execute(select(BuyerMandate).order_by(BuyerMandate.id)).scalars().first()
    mandate.onboarding_summary = "edited after the forward apply"
    seeded.commit()
    restore = mrr.plan_mandate_reonboarding_rollback(seeded, forward)
    assert restore["can_apply"] is False and restore["blockers"][0]["current_state"] == mrr.DRIFTED
    snap = mandate_snapshot(seeded)
    with pytest.raises(mrr.RollbackRefused):
        mrr.apply_mandate_reonboarding_rollback(seeded, forward, confirm=mrr.CONFIRM_PHRASE, expected_restore_digest=restore["restore_plan_digest"])
    assert mandate_snapshot(seeded) == snap
    mandate.onboarding_summary = next(m["restore_snapshot"]["proposed_onboarding_summary"] for m in report["stale_mandates"] if m["mandate_id"] == mandate.id)
    seeded.commit()
    ok = mrr.plan_mandate_reonboarding_rollback(seeded, forward)
    mrr.apply_mandate_reonboarding_rollback(seeded, forward, confirm=mrr.CONFIRM_PHRASE, expected_restore_digest=ok["restore_plan_digest"])
    again = mrr.plan_mandate_reonboarding_rollback(seeded, forward)
    assert again["can_apply"] is False and {e["current_state"] for e in again["entries"]} == {mrr.ALREADY_RESTORED}


def test_reonboarding_forward_report_is_validated_and_lossy_reports_are_refused(seeded):
    before, plan, report, forward = forward_reonboarding(seeded)
    with pytest.raises(mrr.RollbackRefused):
        mrr.load_forward_report(roundtrip(plan))                                          # a dry-run report cannot drive a restore
    lossy = roundtrip(report)
    del lossy["stale_mandates"][0]["restore_snapshot"]
    with pytest.raises(mrr.RollbackRefused):
        mrr.load_forward_report(lossy)
    no_time = roundtrip(report)
    no_time["applied_onboarding_completed_at"] = None
    with pytest.raises(mrr.RollbackRefused):
        mrr.load_forward_report(no_time)


def test_reonboarding_restore_is_one_transaction_and_rolls_back_completely_on_failure(seeded, monkeypatch):
    before, plan, report, forward = forward_reonboarding(seeded)
    mid = mandate_snapshot(seeded)
    restore = mrr.plan_mandate_reonboarding_rollback(seeded, forward)
    real_commit = seeded.commit
    monkeypatch.setattr(seeded, "commit", lambda: (_ for _ in ()).throw(RuntimeError("simulated failure at commit")))
    with pytest.raises(RuntimeError):
        mrr.apply_mandate_reonboarding_rollback(seeded, forward, confirm=mrr.CONFIRM_PHRASE, expected_restore_digest=restore["restore_plan_digest"])
    monkeypatch.setattr(seeded, "commit", real_commit)
    assert mandate_snapshot(seeded) == mid


# ========================= C. wiring / safety ========================================================================================================================================

def test_the_rollback_clis_are_registered_authorised_dry_run_first_and_have_no_forbidden_paths():
    import ast
    cli = json.loads((ROOT / "verification/stage1_cli_manifest.json").read_text(encoding="utf-8"))
    service = json.loads((ROOT / "verification/stage1_service_manifest.json").read_text(encoding="utf-8"))
    for name in ("v8_monitoring_rollback", "v8_reonboarding_rollback"):
        assert cli[f"scripts/{name}.py"] == {"command": name, "required_scope": f"launch:{name}"}
        source = (ROOT / f"scripts/{name}.py").read_text(encoding="utf-8")
        assert f"@authorised_cli('{name}')" in source and 'parser.add_argument("--apply", action="store_true")' in source and 'open(path, "x"' in source
    assert service["app/policy/mandate_reonboarding_rollback.py"] == {"plan_mandate_reonboarding_rollback": "buyer.write", "apply_mandate_reonboarding_rollback": "buyer.write"}
    for module in (mrb, mrr):
        tree = ast.parse(inspect.getsource(module))
        imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)} | {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert not any(re.match(r"(openai|anthropic|requests|httpx|urllib|socket)", m) for m in imported), imported
        assert not called & {"sync_opportunity_monitoring_state", "seed_default_buyer_profiles", "run_buyer_onboarding_baseline", "create_all", "build_current_opportunity_universe"}, called
    assert mrb.CONFIRM_PHRASE == "RESTORE PRE-V8 MONITORING FINGERPRINTS" and mrr.CONFIRM_PHRASE == "RESTORE PRE-V8 MANDATE BASELINES"

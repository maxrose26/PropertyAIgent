"""Specification 027: the audited Nesten mandate sync (app.policy.mandate_sync) - OFFLINE, synthetic SQLite only.

The seeded Nesten mandate is put into the EXACT pre-correction state production holds (proven below by the whole-policy digest equalling the Gate B artifact digest prefix), then the dry-run /
apply contract is exercised: dry-run default, exact field diff, preserved state, drift refusal, confirmation, one transaction, rollback, STALE baseline, no re-onboarding / monitoring / model / reseed,
Nesten as the only target, and the plot decision pin.
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import inspect
import json
import re
import socket
from pathlib import Path

import pytest
from sqlalchemy import event, select

import app.policy.buyer_profile_store as store
import app.policy.mandate_sync as ms
from app.db.models import BuyerMandate, OpportunityMonitoringState
from app.policy.buyer_profiles import BUYER_PROFILES
from app.policy.mandate_sync import (
    APPROVED_CHANGES, BASELINE_FIELDS, CONFIRM_PHRASE, PRESERVED_FIELDS, SYNCABLE_RULE_FIELDS, MandateSyncRefused, apply_mandate_sync, compute_mandate_sync_plan, plan_mandate_sync,
    policy_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
GATE_B_ARTIFACT_NESTEN_DIGEST = "cc45186babbf1043"            # run_metadata.mandate_digests.nesten_homes in the Gate B1 production artifact (the STORED production mandate)
# The Nesten notes exactly as they were before f8e1c9b (reconstructed from git history f8e1c9b^:app/policy/buyer_profiles.py).
OLD_NOTES = ("Brief: \"residential sites with planning permission; OR sites allocated for residential development\" - read as accepting both adopted and emerging allocation status, since the "
             "brief does not restrict Nesten to adopted-only allocations. No affordable-percentage threshold below 100% is implemented (brief: \"do NOT invent an affordable-percentage threshold "
             "below 100%\").")


def mandates(session):
    session.expire_all()
    return {m.buyer.buyer_key: m for m in session.execute(select(BuyerMandate)).scalars()}


def row_state(mandate):
    return {column.name: getattr(mandate, column.name) for column in BuyerMandate.__table__.columns}


@pytest.fixture
def seeded(session):
    """Four seeded mandates; Nesten is then moved to the exact PRE-correction production state, with a FRESH onboarding baseline (so staleness is meaningful)."""
    workspace = store.resolve_default_workspace(session)
    store.seed_default_buyer_profiles(session, workspace)
    nesten = mandates(session)["nesten_homes"]
    nesten.target_unit_max, nesten.wholly_affordable_is_exclusion, nesten.notes = 100, True, OLD_NOTES
    session.commit()
    nesten = mandates(session)["nesten_homes"]
    nesten.matching_fingerprint = store.compute_buyer_mandate_fingerprint(store.mandate_to_policy(nesten))
    nesten.onboarding_completed_at = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc)
    nesten.onboarding_summary = "old baseline summary (operational state)"
    session.commit()
    return session


class WriteWatcher:
    def __init__(self, session):
        self.session, self.engine, self.writes, self.commits = session, session.get_bind(), [], 0

    def __enter__(self):
        def execute(conn, cursor, statement, *args):
            if not statement.lstrip().upper().startswith(("SELECT", "PRAGMA", "WITH")):
                self.writes.append(statement.split()[0].upper())

        def commit(session):
            self.commits += 1
        self.handlers = (execute, commit)
        event.listen(self.engine, "before_cursor_execute", execute)
        event.listen(self.session, "after_commit", commit)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self.handlers[0])
        event.remove(self.session, "after_commit", self.handlers[1])


def reviewed(session):
    return plan_mandate_sync(session, buyer_key="nesten_homes")


def apply(session, report, **overrides):
    kwargs = dict(buyer_key="nesten_homes", confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"])
    kwargs.update(overrides)
    return apply_mandate_sync(session, **kwargs)


# --- the exact historical -> canonical Nesten change ------------------------------------------------------------------------------------------

def test_the_seeded_old_state_is_exactly_the_production_state_and_the_pinned_digests_are_consistent(seeded):
    stored = ms.mandate_to_policy(mandates(seeded)["nesten_homes"])
    assert policy_sha256(stored) == APPROVED_CHANGES["nesten_homes"].expected_old_policy_sha256
    assert policy_sha256(stored).startswith(GATE_B_ARTIFACT_NESTEN_DIGEST)                                   # the digest the production artifact recorded
    assert APPROVED_CHANGES["nesten_homes"].expected_new_policy_sha256 == policy_sha256(BUYER_PROFILES["nesten_homes"])     # the approved canonical template
    template = BUYER_PROFILES["nesten_homes"]
    assert (template.target_unit_min, template.target_unit_max, template.wholly_affordable_is_exclusion) == (50, 200, False)
    assert template.notes != OLD_NOTES and template.notes.startswith(OLD_NOTES)                              # the accepted correction EXTENDS the brief; it does not rewrite it
    assert APPROVED_CHANGES["nesten_homes"].source_commit == "f8e1c9b61f6d2624d60959dc62a41cc4ddd8d20e"


def test_the_exact_field_diff_is_the_three_accepted_changes_and_unchanged_fields_are_omitted(seeded):
    report = reviewed(seeded)
    assert report["status"] == "READY" and report["applicable"] and report["blocking_reasons"] == []
    diff = {d["field"]: d for d in report["field_diff"]}
    assert list(diff) == ["target_unit_max", "wholly_affordable_is_exclusion", "notes"]                       # nothing else, in schema order
    assert (diff["target_unit_max"]["old"], diff["target_unit_max"]["proposed"]) == (100, 200)
    assert (diff["wholly_affordable_is_exclusion"]["old"], diff["wholly_affordable_is_exclusion"]["proposed"]) == (True, False)
    assert diff["notes"]["old"] == OLD_NOTES and diff["notes"]["proposed"] == BUYER_PROFILES["nesten_homes"].notes
    assert all(d["reason"] and "UNAPPROVED" not in d["reason"] and "f8e1c9b" in d["reason"] for d in diff.values())
    assert "target_unit_min" not in diff                                                                    # 50 -> 50 is omitted
    assert report["derived"] == {"discovery_before": (45, 110), "discovery_after": (45, 220)}
    assert report["matching_policy_version"] == 8


# --- dry-run default, determinism ----------------------------------------------------------------------------------------------------------

def test_dry_run_is_the_default_writes_nothing_and_is_deterministic(seeded):
    before = row_state(mandates(seeded)["nesten_homes"])
    with WriteWatcher(seeded) as watcher:
        first, second = reviewed(seeded), reviewed(seeded)
    assert watcher.writes == [] and watcher.commits == 0
    assert first == second and first["mode"] == "dry_run" and len(first["plan_digest"]) == 64
    assert row_state(mandates(seeded)["nesten_homes"]) == before
    import scripts.sync_nesten_mandate as cli
    args = cli.parse_args([])
    assert args.apply is False and args.confirm == "" and args.expect_digest == "" and args.audit_out is None
    source = open(cli.__file__, encoding="utf-8").read()
    assert "if args.apply:" in source and 'BUYER_KEY = "nesten_homes"' in source and "--buyer" not in source and 'open(target, "x"' in source


# --- apply: success, preserved state, one transaction ------------------------------------------------------------------------------------------

def test_apply_updates_only_the_approved_columns_and_preserves_everything_else(seeded):
    before = row_state(mandates(seeded)["nesten_homes"])
    others_before = {k: row_state(m) for k, m in mandates(seeded).items() if k != "nesten_homes"}
    report = reviewed(seeded)
    result = apply(seeded, report)
    after = row_state(mandates(seeded)["nesten_homes"])
    changed = {name for name in before if before[name] != after[name]}
    assert changed == {"target_unit_max", "wholly_affordable_is_exclusion", "notes", "updated_at"}            # updated_at is the automatic ORM audit stamp
    for name in PRESERVED_FIELDS:
        assert before[name] == after[name], name                                                             # identity, workspace, status, provenance, display name, baseline: untouched
    assert (after["target_unit_min"], after["target_unit_max"]) == (50, 200) and after["wholly_affordable_is_exclusion"] is False and after["notes"] == BUYER_PROFILES["nesten_homes"].notes
    assert result["verified_after"]["stored_policy_sha256"] == APPROVED_CHANGES["nesten_homes"].expected_new_policy_sha256
    assert {k: row_state(m) for k, m in mandates(seeded).items() if k != "nesten_homes"} == others_before       # Q: other buyers unchanged
    assert set(SYNCABLE_RULE_FIELDS).isdisjoint(PRESERVED_FIELDS) and set(BASELINE_FIELDS) <= set(PRESERVED_FIELDS)


def test_apply_is_one_transaction_and_a_second_run_is_refused_as_already_corrected(seeded):
    report = reviewed(seeded)
    with WriteWatcher(seeded) as watcher:
        apply(seeded, report)
    assert watcher.commits == 1 and set(watcher.writes) == {"UPDATE"}
    again = reviewed(seeded)
    assert again["status"] == "ALREADY_CORRECTED" and not again["applicable"]
    with pytest.raises(MandateSyncRefused, match="ALREADY_CORRECTED"):
        apply(seeded, again)


def test_a_failure_during_apply_rolls_everything_back(seeded):
    before = row_state(mandates(seeded)["nesten_homes"])
    report = reviewed(seeded)

    def explode(session):
        raise RuntimeError("boom at commit")
    event.listen(seeded, "before_commit", explode)
    try:
        with pytest.raises(RuntimeError, match="boom"):
            apply(seeded, report)
    finally:
        event.remove(seeded, "before_commit", explode)
    assert row_state(mandates(seeded)["nesten_homes"]) == before                                            # no partial update
    assert reviewed(seeded)["status"] == "READY"                                                             # still correctable afterwards


# --- guards ---------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field_name,value", [("target_unit_min", 60), ("target_unit_max", 150), ("specialist_development_is_exclusion", False), ("primary_requirement", "Something else"),
                                              ("acquisition_types", "STRATEGIC_LAND_CONTROL")])
def test_an_unexpected_old_state_refuses(seeded, field_name, value):
    row = mandates(seeded)["nesten_homes"]
    setattr(row, field_name, value)
    seeded.commit()
    report = reviewed(seeded)
    assert not report["applicable"] and report["blocking_reasons"] and report["status"] == "DRIFT"
    with pytest.raises(MandateSyncRefused):
        apply(seeded, report)
    assert getattr(mandates(seeded)["nesten_homes"], field_name) == value                                    # nothing was written


def test_drift_after_review_invalidates_the_plan_digest_and_refuses(seeded):
    report = reviewed(seeded)
    assert apply_nothing_changed(seeded, report) is None
    row = mandates(seeded)["nesten_homes"]
    row.primary_requirement = "Edited after the review"
    seeded.commit()
    with pytest.raises(MandateSyncRefused) as caught:
        apply(seeded, report)
    assert any("drift" in r or "changed" in r or "pre-correction" in r for r in caught.value.reasons)
    assert mandates(seeded)["nesten_homes"].target_unit_max == 100


def apply_nothing_changed(session, report):
    """A dry run repeated unchanged yields the identical digest (so only real drift can invalidate a review)."""
    assert reviewed(session)["plan_digest"] == report["plan_digest"]


def test_the_dry_run_reports_the_baseline_and_rule_fingerprint_identifiers(seeded):
    row = mandates(seeded)["nesten_homes"]
    report = reviewed(seeded)
    baseline = report["baseline"]
    assert baseline["stored_baseline_fingerprint_id"] == row.matching_fingerprint[:12] and len(baseline["stored_baseline_fingerprint_id"]) == 12
    assert baseline["onboarding_completed_at"].startswith("2026-09-20")
    assert baseline["current_rules_fingerprint_id"] == baseline["stored_baseline_fingerprint_id"]                      # fresh baseline: the stored baseline equals the current (old) rules
    proposed = baseline["proposed_rules_fingerprint_id"]
    assert len(proposed) == 12 and proposed != baseline["current_rules_fingerprint_id"] and baseline["stale_after_correction"] is True
    apply(seeded, report)
    row = mandates(seeded)["nesten_homes"]
    assert store.compute_buyer_mandate_fingerprint(store.mandate_to_policy(row))[:12] == proposed                          # exactly what a later re-onboarding would stamp
    assert row.matching_fingerprint[:12] == baseline["stored_baseline_fingerprint_id"]                                      # the old baseline is still the OLD one
    assert "fingerprint" not in " ".join(report["blocking_reasons"])


def test_the_digest_binds_identity_policy_version_diff_and_expected_states(seeded):
    base = compute_mandate_sync_plan(seeded, "nesten_homes")
    for attribute, value in (("mandate_id", 999), ("buyer_id", 999), ("workspace_id", 999), ("stored_sha256", "x"), ("proposed_sha256", "x"), ("expected_old_sha256", "x"),
                             ("diff", [{"field": "target_unit_max", "old": 100, "proposed": 300, "reason": "r"}]), ("status", "DRIFT"), ("stored_baseline_fingerprint_id", "abcdef012345")):
        mutated = dataclasses.replace(base, **{attribute: value})
        assert mutated.digest() != base.digest(), attribute
    assert "BUYER_MATCHING_POLICY_VERSION" in inspect.getsource(ms.MandateSyncPlan.digest)


def test_wrong_confirmation_or_wrong_digest_refuses_without_writing(seeded):
    report = reviewed(seeded)
    for overrides in ({"confirm": ""}, {"confirm": "yes"}, {"confirm": CONFIRM_PHRASE.lower()}, {"expected_plan_digest": ""}, {"expected_plan_digest": "0" * 64}):
        with pytest.raises(MandateSyncRefused):
            apply(seeded, report, **overrides)
    assert mandates(seeded)["nesten_homes"].target_unit_max == 100


@pytest.mark.parametrize("buyer", ["national_housebuilder", "strategic_land_buyer", "housing_association", "no_such_buyer"])
def test_nesten_is_the_only_authorised_target(seeded, buyer):
    nesten_report = reviewed(seeded)
    before = {k: row_state(m) for k, m in mandates(seeded).items()}
    plan = plan_mandate_sync(seeded, buyer_key=buyer)
    assert plan["status"] == "TARGET_NOT_APPROVED" and not plan["applicable"]
    with pytest.raises(MandateSyncRefused, match="no approved mandate correction"):
        apply(seeded, nesten_report, buyer_key=buyer)                                                        # the reviewed NESTEN plan cannot be applied to another buyer
    assert {k: row_state(m) for k, m in mandates(seeded).items()} == before
    assert list(APPROVED_CHANGES) == ["nesten_homes"]


def test_the_other_buyers_stored_mandates_equal_their_canonical_templates_and_stay_so(seeded):
    for key in ("national_housebuilder", "strategic_land_buyer", "housing_association"):
        assert policy_sha256(store.mandate_to_policy(mandates(seeded)[key])) == policy_sha256(BUYER_PROFILES[key])


def test_apply_requires_the_operator_command_boundary():
    manifest = json.loads((ROOT / "verification/stage1_service_manifest.json").read_text(encoding="utf-8"))
    assert manifest["app/policy/mandate_sync.py"] == {"plan_mandate_sync": "buyer.write", "apply_mandate_sync": "buyer.write"}     # exercised by the generic denial-before-inputs service tests
    cli_manifest = json.loads((ROOT / "verification/stage1_cli_manifest.json").read_text(encoding="utf-8"))
    assert cli_manifest["scripts/sync_nesten_mandate.py"] == {"command": "sync_nesten_mandate", "required_scope": "launch:sync_nesten_mandate"}
    tree = ast.parse((ROOT / "app/policy/mandate_sync.py").read_text(encoding="utf-8"))
    decorated = {n.name: [ast.unparse(d) for d in n.decorator_list] for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("plan_mandate_sync", "apply_mandate_sync")}
    assert decorated == {"plan_mandate_sync": ["command('buyer.write')"], "apply_mandate_sync": ["command('buyer.write')"]}
    assert "@authorised_cli('sync_nesten_mandate')" in (ROOT / "scripts/sync_nesten_mandate.py").read_text(encoding="utf-8")


# --- correction vs re-onboarding: STALE baseline, nothing automatic -----------------------------------------------------------------------------

def test_a_successful_correction_makes_the_old_baseline_stale_without_touching_it(seeded):
    row = mandates(seeded)["nesten_homes"]
    assert store.is_buyer_mandate_baseline_stale(row) is False                                               # the old baseline is FRESH for the old rules
    baseline_before = tuple(getattr(row, name) for name in BASELINE_FIELDS)
    report = reviewed(seeded)
    assert report["baseline"] == {**report["baseline"], "stored_baseline_present": True, "stale_before": False, "stale_after_correction": True}
    result = apply(seeded, report)
    row = mandates(seeded)["nesten_homes"]
    assert store.is_buyer_mandate_baseline_stale(row) is True and result["verified_after"]["baseline_stale"] is True
    assert tuple(getattr(row, name) for name in BASELINE_FIELDS) == baseline_before                           # left in place, NOT cleared and NOT restamped
    assert store.compute_buyer_mandate_fingerprint(store.mandate_to_policy(row)) != row.matching_fingerprint


def test_a_mandate_with_no_baseline_or_an_already_stale_baseline_is_handled_sensibly(seeded):
    row = mandates(seeded)["nesten_homes"]
    row.matching_fingerprint, row.onboarding_completed_at, row.onboarding_summary = None, None, None
    seeded.commit()
    report = reviewed(seeded)
    assert report["baseline"]["stored_baseline_present"] is False and report["baseline"]["stale_before"] is True and report["baseline"]["stale_after_correction"] is True
    apply(seeded, report)
    row = mandates(seeded)["nesten_homes"]
    assert (row.matching_fingerprint, row.onboarding_completed_at, row.onboarding_summary) == (None, None, None)     # still never onboarded: nothing was stamped
    assert store.is_buyer_mandate_baseline_stale(row) is True


def test_an_already_stale_baseline_stays_untouched_and_stale(seeded):
    row = mandates(seeded)["nesten_homes"]
    row.matching_fingerprint = "f" * 64                                                                  # a baseline from some other (older) rule set
    seeded.commit()
    report = reviewed(seeded)
    assert report["baseline"]["stale_before"] is True and report["status"] == "READY"
    apply(seeded, report)
    assert mandates(seeded)["nesten_homes"].matching_fingerprint == "f" * 64 and store.is_buyer_mandate_baseline_stale(mandates(seeded)["nesten_homes"]) is True


def test_an_archived_mandate_is_never_a_target(seeded):
    row = mandates(seeded)["nesten_homes"]
    row.status = "archived"
    seeded.commit()
    report = reviewed(seeded)
    assert report["status"] == "MANDATE_NOT_FOUND" and not report["applicable"]
    with pytest.raises(MandateSyncRefused):
        apply(seeded, report)


def test_the_audit_file_is_created_before_any_write_and_never_overwritten(seeded, tmp_path, monkeypatch):
    import scripts.sync_nesten_mandate as cli
    monkeypatch.setattr(cli, "get_session", lambda: seeded)
    monkeypatch.setattr(seeded, "close", lambda: None)
    out = tmp_path / "audit"
    assert cli.main.__wrapped__(["--audit-out", str(out)]) == 0
    first = sorted(out.iterdir())
    assert len(first) == 1 and json.loads(first[0].read_text(encoding="utf-8"))["mode"] == "dry_run"
    report = json.loads(first[0].read_text(encoding="utf-8"))
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory")
    with pytest.raises(OSError):                                                                      # an unusable audit path aborts BEFORE the apply can commit
        cli.main.__wrapped__(["--apply", "--confirm", CONFIRM_PHRASE, "--expect-digest", report["plan_digest"], "--audit-out", str(blocker)])
    assert mandates(seeded)["nesten_homes"].target_unit_max == 100


def test_correction_does_not_reonboard_monitor_reseed_or_call_a_model(seeded, monkeypatch):
    def forbidden(name):
        def boom(*a, **k):
            raise AssertionError(f"{name} must not be called by the mandate sync")
        return boom
    import app.policy.mandate_reonboarding as mr
    import app.reporting.opportunity_change as oc
    import app.reporting.opportunity_universe as universe
    for module, name in ((store, "run_buyer_onboarding_baseline"), (store, "seed_default_buyer_profiles"), (store, "bootstrap_acquisition_monitoring"), (mr, "apply_stale_mandate_reonboarding"),
                         (mr, "plan_stale_mandate_reonboarding"), (oc, "sync_opportunity_monitoring_state"), (oc, "preview_ordinary_sync"), (universe, "build_current_opportunity_universe")):
        monkeypatch.setattr(module, name, forbidden(f"{module.__name__}.{name}"))
    monkeypatch.setattr(socket.socket, "connect", forbidden("network"))
    monitoring_before = seeded.execute(select(OpportunityMonitoringState)).scalars().all()
    report = reviewed(seeded)
    apply(seeded, report)
    assert seeded.execute(select(OpportunityMonitoringState)).scalars().all() == monitoring_before == []
    source = (ROOT / "app/policy/mandate_sync.py").read_text(encoding="utf-8")
    code = re.sub(r'""".*?"""', "", source, flags=re.S)
    for name in ("run_buyer_onboarding_baseline", "seed_default_buyer_profiles", "bootstrap_acquisition_monitoring", "mandate_reonboarding", "opportunity_change", "opportunity_universe",
                 "openai", "anthropic", "requests", "httpx", "build_b2_context", "evaluate_buyer_fit", "assess_buyer_fit"):
        assert name not in code, name
    imports = {a.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "run_buyer_onboarding_baseline" not in imports and "seed_default_buyer_profiles" not in imports


def test_application_startup_and_default_seeding_never_mutate_existing_mandates(seeded):
    before = row_state(mandates(seeded)["nesten_homes"])
    store.seed_default_buyer_profiles(seeded, store.resolve_default_workspace(seeded))                         # the documented 'never overwrite' contract still holds
    assert row_state(mandates(seeded)["nesten_homes"]) == before and mandates(seeded)["nesten_homes"].target_unit_max == 100
    for path in (ROOT / "app").rglob("*.py"):
        if path.name != "mandate_sync.py":
            assert "mandate_sync" not in path.read_text(encoding="utf-8", errors="ignore"), path             # no application path invokes the sync


# --- plot decision pin ----------------------------------------------------------------------------------------------------------------------------

def test_a_material_plot_may_be_an_acquisition_subject_but_is_not_qualified_phasing_evidence():
    from app.pipeline.phase_tracking import group_applications_by_operative_scope
    from app.policy.buyer_matching import PHASING_NONE_IDENTIFIED
    from tests.test_acquisition_phasing import app as make_application
    plot = make_application(1, "Reserved matters for Plot A6 for the erection of 79 dwellings")
    assert ("A6", "plot") in group_applications_by_operative_scope([plot])                                    # a material plot survives as its own acquisition-level scope
    from tests.test_acquisition_phasing import state
    assert state([plot]) == PHASING_NONE_IDENTIFIED                                                          # ...but a plot alone is NOT qualified phasing evidence
    named_phase = make_application(2, "Reserved matters for Phase 2 of 79 dwellings")
    from app.policy.buyer_matching import PHASING_CURRENT_EVIDENCED_PHASE
    assert state([named_phase]) == PHASING_CURRENT_EVIDENCED_PHASE                                           # a genuine named phase still is
    assert state([plot, named_phase]) == PHASING_CURRENT_EVIDENCED_PHASE                                     # the plot neither adds to nor blocks it
    source = (ROOT / "app/reporting/acquisition_phasing.py").read_text(encoding="utf-8")
    assert 'kind != "phase"' in source                                                                       # the derivation was not changed by this gate

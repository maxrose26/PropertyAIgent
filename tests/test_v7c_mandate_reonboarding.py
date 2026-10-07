"""Stage 2.5B V7C-2: the standalone stale-mandate re-onboarding (app.policy.mandate_reonboarding) and its stale-evaluation guard.

Offline, synthetic data only, real matcher. The dry run must write nothing; apply must compute everything first, refuse without a passing same-universe parity oracle, the confirm
phrase and the REVIEWED plan digest, and commit exactly once; no ordinary monitoring sync, reseed or model call may occur anywhere on this path.
"""
from __future__ import annotations

import inspect
import json

import pytest
from sqlalchemy import event, func, select

import app.policy.buyer_profile_store as store
import app.policy.mandate_reonboarding as mr
import app.reporting.opportunity_change as oc
import app.reporting.opportunity_universe as universe_module
from app.db.models import AgentEvaluationClaim, AgentEvaluationHistory, BuyerMandate, OpportunityMonitoringState
from app.policy.mandate_reonboarding import (
    CONFIRM_PHRASE, PARITY_FAILED, PARITY_NOT_AVAILABLE, PARITY_PASSED, ParityVerdict, ReonboardingRefused, apply_stale_mandate_reonboarding,
    plan_stale_mandate_reonboarding,
)
from tests.test_buyer_family_feed import LAPSE_AGE, World


def _make_site(session, *, unit_count=75):
    """A real opportunity-producing site (approaching-lapse outline + reserved-matters phase) WITHOUT World's fake buyer-fit patch: these tests use the real matcher."""
    world = object.__new__(World)
    world.session, world.parent, world.phase, world.alloc, world.n = session, {}, {}, {}, getattr(session, "_v7c_sites", 0)
    session._v7c_sites = world.n + 1
    return world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, units_out=unit_count, units_rm=max(10, unit_count // 3))


def mandates(session):
    return {m.buyer.buyer_key: m for m in session.execute(select(BuyerMandate)).scalars()}


@pytest.fixture
def seeded(session):
    """Four seeded pilot mandates (never onboarded -> all stale) and a small universe."""
    workspace = store.resolve_default_workspace(session)
    store.seed_default_buyer_profiles(session, workspace)
    for units in (75, 150, 500):
        _make_site(session, unit_count=units)
    return session


def ok_oracle(policy, record, context, assessment):
    return ParityVerdict(True, True)


def baseline_columns(session):
    session.expire_all()
    return {key: (m.matching_fingerprint, m.onboarding_completed_at, m.onboarding_summary) for key, m in mandates(session).items()}


class WriteGuard:
    def __init__(self, session):
        self.session, self.engine, self.statements, self.commits = session, session.get_bind(), [], 0

    def __enter__(self):
        def execute(conn, cursor, statement, *args):
            self.statements.append(statement)
            assert statement.lstrip().upper().startswith(("SELECT", "PRAGMA", "WITH")), f"non-read statement: {statement[:80]}"

        def commit(session):
            raise AssertionError("committed")
        self.handlers = (execute, commit)
        event.listen(self.engine, "before_cursor_execute", execute)
        event.listen(self.session, "before_commit", commit)
        return self

    def __exit__(self, *exc):
        execute, commit = self.handlers
        event.remove(self.engine, "before_cursor_execute", execute)
        event.remove(self.session, "before_commit", commit)


# --- dry run (the default) --------------------------------------------------------------------------------------------------------------

def test_dry_run_is_the_default_writes_nothing_and_reports_audit_information(seeded):
    before = baseline_columns(seeded)
    with WriteGuard(seeded):
        report = plan_stale_mandate_reonboarding(seeded)
    assert baseline_columns(seeded) == before and not (seeded.new or seeded.dirty or seeded.deleted)
    assert report["mode"] == "dry_run" and report["read_only"] is True and report["universe_size"] >= 3
    assert [e["buyer_key"] for e in report["stale_mandates"]] == sorted(mandates(seeded))                     # deterministic order, every never-onboarded mandate
    first = report["stale_mandates"][0]
    assert set(first) >= {"buyer_key", "mandate_id", "old_fingerprint_id", "proposed_fingerprint_id", "old_onboarding_completed_at", "old_summary", "proposed_summary",
                          "opportunities_reviewed", "stored_vs_proposed_summary_delta", "drift_note", "parity"}
    assert first["old_fingerprint_id"] is None and len(first["proposed_fingerprint_id"]) == 12 and first["opportunities_reviewed"] == report["universe_size"]
    assert report["plan_digest"] and plan_stale_mandate_reonboarding(seeded)["plan_digest"] == report["plan_digest"]    # deterministic


def test_parity_is_not_available_without_an_oracle_and_blocks_apply(seeded):
    report = plan_stale_mandate_reonboarding(seeded)
    assert report["parity"]["status"] == PARITY_NOT_AVAILABLE and report["can_apply"] is False
    assert any("parity oracle not configured" in reason for reason in report["blocking_reasons"])
    before = baseline_columns(seeded)
    with pytest.raises(ReonboardingRefused):
        apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"])
    assert baseline_columns(seeded) == before


def test_the_standalone_path_runs_no_sync_no_reseed_no_bootstrap_and_builds_the_universe_once(seeded, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden call on the standalone re-onboarding path")
    monkeypatch.setattr(oc, "sync_opportunity_monitoring_state", forbidden)
    monkeypatch.setattr(store, "sync_opportunity_monitoring_state", forbidden, raising=False)
    monkeypatch.setattr(store, "seed_default_buyer_profiles", forbidden)
    monkeypatch.setattr(store, "bootstrap_acquisition_monitoring", forbidden)
    monkeypatch.setattr(store, "run_buyer_onboarding_baseline", forbidden)
    calls = {"universe": 0, "contexts": 0}
    real_universe = universe_module.build_current_opportunity_universe
    monkeypatch.setattr(universe_module, "build_current_opportunity_universe", lambda *a, **k: calls.__setitem__("universe", calls["universe"] + 1) or real_universe(*a, **k))
    import app.policy.buyer_matching_b2_context as b2
    real_context = b2.build_b2_context
    monkeypatch.setattr(b2, "build_b2_context", lambda *a, **k: calls.__setitem__("contexts", calls["contexts"] + 1) or real_context(*a, **k))
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)
    assert len(report["stale_mandates"]) == 4 and calls == {"universe": 1, "contexts": report["universe_size"]}      # ONCE for all four mandates, not per mandate
    assert seeded.execute(select(func.count()).select_from(OpportunityMonitoringState)).scalar() == 0


def test_proposed_results_equal_what_the_existing_onboarding_would_stamp(seeded):
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)
    proposed = {e["buyer_key"]: (e["proposed_summary"], e["proposed_fingerprint_id"]) for e in report["stale_mandates"]}
    for key, mandate in mandates(seeded).items():
        result = store.run_buyer_onboarding_baseline(seeded, mandate)              # the pre-existing path (shared evaluation helper), executed for comparison
        assert (result.summary_line, mandate.matching_fingerprint[:12]) == proposed[key]


def test_stale_detection_is_computed_and_fresh_mandates_are_untouched(seeded):
    one = mandates(seeded)["nesten_homes"]
    store.run_buyer_onboarding_baseline(seeded, one)
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)
    assert "nesten_homes" not in [e["buyer_key"] for e in report["stale_mandates"]] and report["fresh_mandates_untouched"] == 1
    scoped = plan_stale_mandate_reonboarding(seeded, buyer_keys=["housing_association"], parity_oracle=ok_oracle)
    assert [e["buyer_key"] for e in scoped["stale_mandates"]] == ["housing_association"]
    one.matching_fingerprint = "0" * 64                                            # a policy-version / field change makes it stale again
    seeded.commit()
    assert "nesten_homes" in [e["buyer_key"] for e in plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)["stale_mandates"]]


# --- parity -----------------------------------------------------------------------------------------------------------------------------

def test_a_parity_mismatch_fails_closed_and_is_reported_per_opportunity(seeded):
    def bad(policy, record, context, assessment):
        return ParityVerdict(classification_equal=False, investigative_equal=True, detail="synthetic divergence")
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=bad)
    assert report["parity"]["status"] == PARITY_FAILED and report["can_apply"] is False
    entry = report["stale_mandates"][0]
    assert entry["parity"]["status"] == PARITY_FAILED and entry["parity"]["classification_mismatches"] == report["universe_size"] and entry["parity"]["mismatches_listed"][0]["opportunity_id"]
    before = baseline_columns(seeded)
    with pytest.raises(ReonboardingRefused) as refused:
        apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"], parity_oracle=bad)
    assert "FAILED" in str(refused.value) and baseline_columns(seeded) == before


def test_parity_is_checked_for_every_opportunity_of_every_mandate_on_the_same_universe(seeded):
    seen = []
    def recording(policy, record, context, assessment):
        seen.append((policy.key, record.opportunity_id, assessment.classification, assessment.is_investigative_exception))
        return ParityVerdict(True, True)
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=recording)
    assert len(seen) == 4 * report["universe_size"] and report["parity"]["status"] == PARITY_PASSED
    assert all(e["parity"]["opportunities_compared"] == report["universe_size"] for e in report["stale_mandates"])
    assert {row[1] for row in seen if row[0] == "nesten_homes"} == {row[1] for row in seen if row[0] == "housing_association"}   # one shared universe


# --- apply ------------------------------------------------------------------------------------------------------------------------------

def test_apply_requires_confirm_and_the_reviewed_digest_and_writes_once(seeded):
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)
    before = baseline_columns(seeded)
    with pytest.raises(ReonboardingRefused):
        apply_stale_mandate_reonboarding(seeded, confirm="yes", expected_plan_digest=report["plan_digest"], parity_oracle=ok_oracle)
    with pytest.raises(ReonboardingRefused) as stale_plan:
        apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest="0" * 64, parity_oracle=ok_oracle)
    assert "plan changed since the reviewed dry run" in str(stale_plan.value) and baseline_columns(seeded) == before
    commits = []
    event.listen(seeded, "after_commit", lambda session: commits.append(1))
    applied = apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"], parity_oracle=ok_oracle)
    assert applied["mode"] == "applied" and len(commits) == 1                          # ONE controlled commit for all four mandates
    after = baseline_columns(seeded)
    assert all(fp and completed and summary for fp, completed, summary in after.values())
    assert {key: (v[0][:12], v[2]) for key, v in after.items()} == {e["buyer_key"]: (e["proposed_fingerprint_id"], e["proposed_summary"]) for e in report["stale_mandates"]}
    assert plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)["stale_mandates"] == []       # nothing stale afterwards (idempotent)
    # no monitoring, opportunity or evaluation writes
    assert seeded.execute(select(func.count()).select_from(OpportunityMonitoringState)).scalar() == 0
    assert seeded.execute(select(func.count()).select_from(AgentEvaluationHistory)).scalar() == 0
    assert seeded.execute(select(func.count()).select_from(AgentEvaluationClaim)).scalar() == 0


def test_drift_between_the_reviewed_dry_run_and_apply_refuses(seeded):
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)
    _make_site(seeded, unit_count=60)                                                    # the universe moves after review
    before = baseline_columns(seeded)
    with pytest.raises(ReonboardingRefused) as refused:
        apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"], parity_oracle=ok_oracle)
    assert "plan changed" in str(refused.value) and baseline_columns(seeded) == before


def test_a_computation_failure_for_any_mandate_writes_nothing(seeded):
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)
    calls = {"n": 0}
    def fails_late(policy, record, context, assessment):
        calls["n"] += 1
        if calls["n"] > report["universe_size"] * 2 + 1:                                 # during the THIRD mandate
            raise RuntimeError("synthetic failure")
        return ParityVerdict(True, True)
    before = baseline_columns(seeded)
    with pytest.raises(RuntimeError):
        apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"], parity_oracle=fails_late)
    assert baseline_columns(seeded) == before                                           # all computed first: the first two mandates were NOT written


def test_a_failure_during_the_controlled_write_rolls_everything_back(seeded):
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)
    before = baseline_columns(seeded)
    def boom(session):
        raise RuntimeError("synthetic commit failure")
    event.listen(seeded, "before_commit", boom)
    try:
        with pytest.raises(RuntimeError):
            apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"], parity_oracle=ok_oracle)
    finally:
        event.remove(seeded, "before_commit", boom)
    assert baseline_columns(seeded) == before


def test_stored_summary_is_secondary_a_difference_is_reported_but_never_blocks(seeded):
    for mandate in mandates(seeded).values():
        mandate.onboarding_summary = "reviewed=1 strong_fit=0 possible_fit=0 not_suitable=0 insufficient_evidence=1 investigative_exceptions=0"
        mandate.onboarding_completed_at = None
    seeded.commit()
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=ok_oracle)
    assert report["can_apply"] is True
    assert all(e["stored_vs_proposed_summary_delta"]["reviewed"] == {"old": 1, "new": report["universe_size"]} and "possible universe drift" in e["drift_note"]
               for e in report["stale_mandates"])


# --- structure: no secrets, no model, bootstrap preserved ---------------------------------------------------------------------------------

def test_the_tool_has_no_model_network_or_sync_dependency_and_registers_authorised_commands():
    import ast
    import json
    from pathlib import Path
    source = inspect.getsource(mr)
    tree = ast.parse(source)
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and any(t in m for t in ("openai", "requests", "opportunity_change", "agent_evaluation", "acquisition_evaluate", "monitoring")) for m in imported)
    root = Path(__file__).resolve().parents[1]
    services = json.loads((root / "verification/stage1_service_manifest.json").read_text())["app/policy/mandate_reonboarding.py"]
    assert services == {"plan_stale_mandate_reonboarding": "buyer.write", "apply_stale_mandate_reonboarding": "buyer.write"}
    clis = json.loads((root / "verification/stage1_cli_manifest.json").read_text())
    assert clis["scripts/reonboard_stale_mandates.py"]["required_scope"] == "launch:reonboard_stale_mandates"
    script = (root / "scripts/reonboard_stale_mandates.py").read_text()
    assert "authorised_cli('reonboard_stale_mandates')" in script and "--apply" in script and "PARITY_ORACLE = v6_parity_oracle" in script


def test_bootstrap_is_preserved_and_documented_as_not_the_approved_transition_path():
    assert "NOT the approved v7 transition path" in inspect.getsource(store.bootstrap_acquisition_monitoring)
    from pathlib import Path
    assert "NOT the approved v7 transition path" in (Path(__file__).resolve().parents[1] / "scripts/bootstrap_acquisition_monitoring.py").read_text()
    source = inspect.getsource(store.bootstrap_acquisition_monitoring)
    assert "sync_opportunity_monitoring_state(session, page_size=page_size)" in source and "seed_default_buyer_profiles(session, workspace)" in source   # semantics unchanged


def test_the_existing_command_boundaries_of_the_onboarding_functions_are_unchanged():
    """The helper extraction must not move the @command('buyer.write') decorator: run_buyer_onboarding_baseline keeps its operator check, session protection and audit log
    (and stays registered in the Stage 1 service manifest); the new pure helpers are plain functions called from inside commands."""
    import ast
    import json
    import textwrap
    from pathlib import Path
    tree = ast.parse(Path(inspect.getsourcefile(store)).read_text(encoding="utf-8"))
    decorated = {n.name: [ast.unparse(d) for d in n.decorator_list] for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert decorated["run_buyer_onboarding_baseline"] == ["command('buyer.write')"]
    assert decorated["bootstrap_acquisition_monitoring"] == ["command('buyer.write')"]
    assert decorated["evaluate_policy_over_universe"] == [] and decorated["summarise_onboarding_assessments"] == []
    services = json.loads((Path(__file__).resolve().parents[1] / "verification/stage1_service_manifest.json").read_text())["app/policy/buyer_profile_store.py"]
    assert services["run_buyer_onboarding_baseline"] == "buyer.write"
    assert getattr(store.run_buyer_onboarding_baseline, "__wrapped__", None) is not None          # the command wrapper is actually applied


# --- V7C parity oracle wiring (the TEMPORARY frozen v6 oracle) and digest binding -------------------------------------------------------------

from verification.transition.v6_parity import v6_parity_oracle   # noqa: E402  (transition-only; tests and the CLI script are its only callers)


def test_the_real_frozen_v6_oracle_passes_on_the_same_universe_and_a_passing_run_lists_no_per_opportunity_lines(seeded):
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=v6_parity_oracle)
    assert report["parity"]["status"] == PARITY_PASSED and report["can_apply"] is True
    assert report["parity"]["opportunities_compared"] == 4 * report["universe_size"] > 0
    assert report["parity"]["classification_mismatches"] == report["parity"]["investigative_mismatches"] == 0
    assert all(e["parity"]["mismatches_listed"] == [] and e["parity"]["status"] == PARITY_PASSED for e in report["stale_mandates"])      # no redundant PASS lines
    applied = apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"], parity_oracle=v6_parity_oracle)
    assert applied["mode"] == "applied" and plan_stale_mandate_reonboarding(seeded, parity_oracle=v6_parity_oracle)["stale_mandates"] == []


def test_the_cli_wires_the_frozen_oracle_and_the_application_package_does_not():
    import scripts.reonboard_stale_mandates as script
    assert script.PARITY_ORACLE is v6_parity_oracle
    import ast
    tree = ast.parse(inspect.getsource(mr))
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.startswith("verification") for m in imported)


def test_one_mismatching_opportunity_fails_the_plan_reports_non_secret_detail_and_blocks_apply(seeded):
    flipped = {}

    def one_bad(policy, record, context, assessment):
        verdict = v6_parity_oracle(policy, record, context, assessment)
        flipped.setdefault("target", (policy.key, record.opportunity_id))                      # the first (mandate, opportunity) pair, flipped EVERY time it recurs
        if (policy.key, record.opportunity_id) == flipped["target"]:
            flipped["id"] = record.opportunity_id
            return ParityVerdict(False, True, "synthetic", v6_classification="STRONG_FIT", v7_classification=assessment.classification,
                                 v6_investigative=False, v7_investigative=bool(assessment.is_investigative_exception))
        return verdict
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=one_bad)
    assert report["parity"]["status"] == PARITY_FAILED and report["parity"]["classification_mismatches"] == 1 and report["parity"]["investigative_mismatches"] == 0
    listed = [m for e in report["stale_mandates"] for m in e["parity"]["mismatches_listed"]]
    assert len(listed) == 1 and set(listed[0]) == {"buyer_key", "mandate_id", "opportunity_id", "v6_classification", "v7_classification", "v6_investigative", "v7_investigative", "detail"}
    assert listed[0]["opportunity_id"] == flipped["id"]
    before = baseline_columns(seeded)
    with pytest.raises(ReonboardingRefused) as refused:
        apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"], parity_oracle=one_bad)
    assert "FAILED" in str(refused.value) and baseline_columns(seeded) == before


def digest(session, **kw):
    return plan_stale_mandate_reonboarding(session, parity_oracle=kw.pop("oracle", v6_parity_oracle), **kw)["plan_digest"]


def test_the_digest_binds_the_reviewed_plan_every_apply_relevant_input_changes_it(seeded, monkeypatch):
    from app.db.models import Application
    base = digest(seeded)
    assert digest(seeded) == base                                                              # stable when nothing changed
    changes = {}

    # 1. opportunity universe identity: a new opportunity
    _make_site(seeded, unit_count=61)
    changes["universe: new opportunity"] = digest(seeded)
    # 2. opportunity evidence (same ids, different fingerprint): a decision changes
    seeded.query(Application).filter(Application.reference.like("OUT/%")).first().decision = "Refused"
    seeded.commit()
    changes["universe: evidence change"] = digest(seeded)
    # 3. proposed mandate fingerprint / outcomes: a mandate field changes
    nesten = mandates(seeded)["nesten_homes"]
    nesten.target_unit_max = nesten.target_unit_max + 17
    seeded.commit()
    changes["mandate: field change"] = digest(seeded)
    # 4. stale mandate set: one mandate becomes fresh
    store.run_buyer_onboarding_baseline(seeded, mandates(seeded)["housing_association"])
    changes["stale set: a mandate onboarded"] = digest(seeded)
    # 5. stored (old) fingerprint of a stale mandate
    strategic = mandates(seeded)["strategic_land_buyer"]
    strategic.matching_fingerprint = "f" * 64
    seeded.commit()
    changes["old fingerprint"] = digest(seeded)
    # 6. parity result
    changes["parity: failed"] = digest(seeded, oracle=lambda p, r, c, a: ParityVerdict(False, True))
    changes["parity: not available"] = digest(seeded, oracle=None)
    # 7. policy version
    import app.policy.buyer_matching as bm
    monkeypatch.setattr(bm, "BUYER_MATCHING_POLICY_VERSION", bm.BUYER_MATCHING_POLICY_VERSION + 1)
    monkeypatch.setattr(store, "BUYER_MATCHING_POLICY_VERSION", bm.BUYER_MATCHING_POLICY_VERSION)
    changes["policy version"] = digest(seeded)
    values = [base, *changes.values()]
    assert len(set(values)) == len(values), {k: v == base for k, v in changes.items()}          # every mutation yields a DIFFERENT digest (and each differs from the others)
    assert all(len(v) == 64 for v in values)


def test_a_reviewed_digest_does_not_apply_after_any_drift_and_the_digest_contains_no_secret_material(seeded):
    report = plan_stale_mandate_reonboarding(seeded, parity_oracle=v6_parity_oracle)
    nesten = mandates(seeded)["nesten_homes"]
    nesten.target_unit_min = nesten.target_unit_min + 1                                         # mandate drift after review
    seeded.commit()
    before = baseline_columns(seeded)
    with pytest.raises(ReonboardingRefused) as refused:
        apply_stale_mandate_reonboarding(seeded, confirm=CONFIRM_PHRASE, expected_plan_digest=report["plan_digest"], parity_oracle=v6_parity_oracle)
    assert "plan changed since the reviewed dry run" in str(refused.value) and baseline_columns(seeded) == before
    text = json.dumps(report)
    for forbidden in ("password", "secret", "token", "api_key", "OPENAI"):
        assert forbidden.lower() not in text.lower()

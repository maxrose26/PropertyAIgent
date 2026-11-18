"""Source-bound negative checks for the never-installed first-Tameside issuer.

These tests are NOT connected PG evidence or approval for historical source work.
"""
import pytest
from verification.ingestion_storage import intake_policy
from verification.ingestion_storage import inactive_tameside_first_issuer as candidate

def test_normal_daily_issuer_is_unchanged_and_candidate_is_withheld():
    before = intake_policy.policy_sql()
    assert candidate.FUNCTION not in before
    assert candidate.FUNCTION not in intake_policy.installation_script()
    assert "ingestion_register_disposable_catchup" not in before
    sql = candidate.render_inactive_tameside_first_issuer()
    assert intake_policy.policy_sql() == before
    assert sql.count("CREATE OR REPLACE FUNCTION public." + candidate.FUNCTION + "(") == 1
    assert "CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception(" not in sql
    assert "TAMESIDE_FIRST_MANIFEST_WITHHELD" in sql
    assert "status" in sql and "WITHHELD" in sql
    assert "GRANT EXECUTE" not in sql
    assert ("REVOKE ALL ON FUNCTION public." + candidate.FUNCTION +
            "(jsonb) FROM PUBLIC;") in sql
    assert "ingestion_provisioning_test" not in sql
    assert "ingestion_register_disposable_catchup" not in sql
    assert "current_database() IS DISTINCT FROM 'postgres'" in sql

def test_candidate_exact_first_batch_no_rolling_capture_and_no_second_run():
    sql = candidate.render_inactive_tameside_first_issuer()
    assert "item->'subject'->>'start' IS DISTINCT FROM '2026-09-15'" in sql
    assert "item->'subject'->>'end' IS DISTINCT FROM '2026-09-21'" in sql
    assert "item->'subject'->>'start'<>((clock_timestamp()" not in sql
    assert "item->'subject'->>'end'<>((clock_timestamp()" not in sql
    assert "a IS DISTINCT FROM 'S4_TAMESIDE_RECEIVED_20260915_20260921_V1'" in sql
    assert "max_runs' IS DISTINCT FROM '1'::jsonb" in sql
    assert "count(*) FROM jsonb_object_keys(p->'policy'->'councils')" in sql
    assert "ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb" in sql
    assert "hard_stop_generation')::integer IS DISTINCT FROM 16" in sql
    assert "TAMESIDE_FIRST_CAPTURE_BOUND" in sql
    assert "TAMESIDE_FIRST_MANIFEST_WITHHELD" in sql

def test_tampered_source_or_changed_issuer_anchor_refuses(monkeypatch):
    monkeypatch.setattr(candidate, "_policy_source_bytes", lambda: b"changed")
    with pytest.raises(ValueError, match="TAMESIDE_FIRST_POLICY_SOURCE_DRIFT"):
        candidate.render_inactive_tameside_first_issuer()


# PA-D004 v1.3: generated single-function, manifest-bound historical slices.
# Existing permanently WITHHELD first-Tameside function remains unchanged.
from datetime import datetime, timezone


def _candidate(council, start, end):
    return candidate.render_inactive_campaign_issuer(
        datetime(2026, 11, 16, 20, tzinfo=timezone.utc), council, start, end)


def test_one_inactive_issuer_name_and_canonical_binding_reused_across_periods():
    first = _candidate("tameside", "2026-09-15", "2026-09-21")
    second = _candidate("tameside", "2026-09-22", "2026-09-28")
    manchester = _candidate("manchester", "2026-09-15", "2026-09-21")
    assert len({x["period"] for x in (first, second, manchester)}) == 3
    assert all(x["review_status"] == "WITHHELD"
               and not x["collection_authorised"] and not x["installed"]
               for x in (first, second, manchester))
    assert all(x["sql"].count("CREATE OR REPLACE FUNCTION public."
                              + candidate.CAMPAIGN_FUNCTION + "(") == 1
               for x in (first, second, manchester))
    for entry, basis in ((first, "RECEIVED"), (second, "RECEIVED"),
                         (manchester, "VALIDATED")):
        sql = entry["sql"]
        assert entry["row"]["semantics"] == basis
        assert ("'campaign_source_plan_sha256' IS DISTINCT FROM '"
                + entry["source_plan_sha256"] + "'") in sql
        assert ("a IS DISTINCT FROM '" + entry["period"] + "'") in sql
        assert ("item->'subject'->>'start' IS DISTINCT FROM '"
                + entry["row"]["start"] + "'") in sql
        assert ("item->'subject'->>'end' IS DISTINCT FROM '"
                + entry["row"]["end"] + "'") in sql
        assert ("p->'rows'->0->'subject'->>'semantics' IS DISTINCT FROM '"
                + basis + "'") in sql
        assert "current_database() IS DISTINCT FROM 'postgres'" in sql
        assert "TAMESIDE_FIRST_MANIFEST_WITHHELD" not in sql
        assert "RAISE EXCEPTION 'CAMPAIGN_FINITE_MANIFEST_WITHHELD'" in sql
        assert "CAMPAIGN_FINITE_NO_LEGACY_OPERATION" in sql
        assert ("REVOKE ALL ON FUNCTION public." + candidate.CAMPAIGN_FUNCTION
                + "(jsonb) FROM PUBLIC;") in sql
        assert "GRANT EXECUTE" not in sql
    assert first["source_plan_sha256"] == manchester["source_plan_sha256"]
    assert first["sql"] != second["sql"] != manchester["sql"]
    assert candidate.CAMPAIGN_FUNCTION not in intake_policy.policy_sql()
    assert candidate.CAMPAIGN_FUNCTION not in intake_policy.installation_script()


@pytest.mark.parametrize("council,start,end,error", [
    ("trafford", "2026-09-15", "2026-09-21", "TRAFFORD_SOURCE_NOT_QUALIFIED"),
    ("tameside", "2026-09-14", "2026-09-20", "TEN_COUNCIL_BATCH_OUTSIDE_CAMPAIGN"),
    ("tameside", "2026-09-15", "2026-09-22", "TEN_COUNCIL_BATCH_OUTSIDE_CAMPAIGN"),
    ("tameside", "2026-11-10", "2026-11-16", "CAMPAIGN_FINITE_CURRENT_DAY_PARTIAL"),
    ("fake", "2026-09-15", "2026-09-21", "TEN_COUNCIL_BATCH_UNKNOWN_COUNCIL"),
])
def test_configurable_candidate_refuses_unqualified_partial_or_widened_scope(
        council, start, end, error):
    with pytest.raises(ValueError, match=error):
        _candidate(council, start, end)


def test_configurable_candidate_detects_changed_base_policy(monkeypatch):
    monkeypatch.setattr(candidate, "_policy_source_bytes", lambda: b"unreviewed")
    with pytest.raises(ValueError, match="TAMESIDE_FIRST_POLICY_SOURCE_DRIFT"):
        _candidate("tameside", "2026-09-15", "2026-09-21")


def test_single_stable_inactive_issuer_body_shared_by_multiple_weeks():
    """Owner payloads vary; installed SQL must NOT be cloned per week/council."""
    import hashlib
    stable=candidate.render_inactive_stable_campaign_issuer()
    assert stable.count("CREATE OR REPLACE FUNCTION public."
                        + candidate.CAMPAIGN_FUNCTION + "(")==1
    assert "CAMPAIGN_STABLE_MANIFEST_WITHHELD" in stable
    assert "CAMPAIGN_STABLE_OWNER_BATCH_INVALID" in stable
    assert "CAMPAIGN_STABLE_CAPTURE_INVALID" in stable
    assert "CAMPAIGN_STABLE_NO_LEGACY_OPERATION" in stable
    assert "FROM PUBLIC;" in stable and "GRANT EXECUTE" not in stable
    assert "2026-09-15" in stable  # fixed campaign fallback, not per-week SQL
    assert "2026-09-21" not in stable
    assert "OR (e->\'councils\')-ARRAY[\'tameside\',\'manchester\']" not in stable
    assert "campaign_batch\'->>\'semantics\')" in stable
    assert "OR item->'subject'->>'end' IS DISTINCT FROM" in stable
    assert "ctl->'intake_periods'->a->'campaign_batch'" in stable
    assert candidate.CAMPAIGN_FUNCTION not in intake_policy.installation_script()
    assert candidate.CAMPAIGN_FUNCTION not in intake_policy.policy_sql()
    first=candidate.prepare_inactive_campaign_owner_batch(
        datetime(2026,11,16,20,tzinfo=timezone.utc),
        "tameside","2026-09-15","2026-09-21")
    second=candidate.prepare_inactive_campaign_owner_batch(
        datetime(2026,11,16,20,tzinfo=timezone.utc),
        "manchester","2026-09-22","2026-09-28")
    sha=hashlib.sha256(stable.encode()).hexdigest()
    assert first["stable_issuer_sha256"]==second["stable_issuer_sha256"]==sha
    assert first["period"]!=second["period"]
    assert first["campaign_batch"]["semantics"]=="RECEIVED"
    assert second["campaign_batch"]["semantics"]=="VALIDATED"
    assert all(x["manifest_status"]=="WITHHELD"
               and x["max_runs"]==1 and x["expected_generation"]==16
               and not x["registered"] and not x["installed"]
               and not x["live_collection_authorised"]
               for x in (first,second))



def test_stable_campaign_owner_sql_never_accepts_unbound_private_evidence():
    """Future campaign issuer may only accept exact retained-evidence shape.

    This source-level boundary does NOT prove a live owner role or active
    registrar. Actual PostgreSQL installation and independent operational
    acceptance remain withheld; the always-deny sentinel must survive.
    """
    sql = candidate.render_inactive_stable_campaign_issuer()
    required = (
        "jsonb_typeof(e->'campaign_source_plan_sha256') IS DISTINCT FROM 'string'",
        "coalesce(e->>'campaign_source_plan_sha256','') !~ '^[0-9a-f]{64}$'",
        "e->>'evidence_backend' IS DISTINCT FROM 'POSTGRES_PILOT_V1'",
        "jsonb_typeof(e->'private_release') IS DISTINCT FROM 'object'",
        "e->'private_release'->>'schema' IS DISTINCT FROM 'PA_D002_LIVE_PRIVATE_V1'",
        "e->'private_release'->>'revision' IS DISTINCT FROM e->'execution_binding'->>'revision'",
        "e->'private_release'->>'semantics' IS DISTINCT FROM e->'campaign_batch'->>'semantics'",
        "e->'private_release'->'councils' IS DISTINCT FROM jsonb_build_array(e->'campaign_batch'->>'council')",
        "(e->'campaign_batch'->>'start')::date NOT BETWEEN 0 AND 6",
        "RAISE EXCEPTION 'CAMPAIGN_STABLE_MANIFEST_WITHHELD'",
    )
    for fragment in required:
        assert fragment in sql
    assert "GRANT EXECUTE" not in sql
    assert candidate.CAMPAIGN_FUNCTION not in intake_policy.installation_script()




@pytest.mark.parametrize("council,start,end,error",[
    ("trafford","2026-09-15","2026-09-21","TRAFFORD_SOURCE_NOT_QUALIFIED"),
    ("tameside","2026-09-15","2026-09-22","TEN_COUNCIL_BATCH_OUTSIDE_CAMPAIGN"),
    ("tameside","2026-11-10","2026-11-16","CAMPAIGN_FINITE_CURRENT_DAY_PARTIAL"),
])
def test_stable_owner_preview_refuses_unqualified_or_partial(council,start,end,error):
    with pytest.raises(ValueError,match=error):
        candidate.prepare_inactive_campaign_owner_batch(
            datetime(2026,11,16,20,tzinfo=timezone.utc),council,start,end)


def test_stable_issuer_does_not_tolerate_changed_pinned_policy(monkeypatch):
    monkeypatch.setattr(candidate,"_policy_source_bytes",lambda:b"changed")
    with pytest.raises(ValueError,match="CAMPAIGN_STABLE_POLICY_SOURCE_DRIFT"):
        candidate.render_inactive_stable_campaign_issuer()


def _inactive_owner_policy_fixture():
    """Synthetic contract shape only; NONE of these values grants authority."""
    from copy import deepcopy
    as_of = datetime(2026, 11, 17, 3, tzinfo=timezone.utc)
    preview = candidate.prepare_inactive_campaign_owner_batch(
        as_of, "tameside", "2026-09-15", "2026-09-21")
    stop = dict(global_stop=None, manual_stop=None,
                last_hard_stop="DAILY_INTAKE_SHARED_FAILURE",
                hard_stop_generation=16)
    binding = dict(revision="a" * 40, workflow_sha256="b" * 64,
                   manifest_sha256="c" * 64)
    policy = dict(
        expires_at=as_of.timestamp()+3600, max_runs=1, overlap_days=7,
        councils={"tameside":dict(contract="daily-intake-tameside",
                                   qualification_sha256="d" * 64)},
        expected_stop=deepcopy(stop), execution_binding=deepcopy(binding),
        test_evidence=False, screening_config="e" * 64,
        route="POOLER", hostaddr="1.1.1.1",
        mode=candidate.CAMPAIGN_MODE,
        campaign_batch=deepcopy(preview["campaign_batch"]),
        campaign_source_plan_sha256=preview["campaign_source_plan_sha256"],
        evidence_backend="POSTGRES_PILOT_V1",
        private_release=dict(schema="PA_D002_LIVE_PRIVATE_V1",
                             revision=binding["revision"],
                             councils=["tameside"], semantics="RECEIVED"))
    return as_of, preview["period"], policy, stop, binding


def test_inactive_owner_runtime_policy_requires_canonical_source_and_stop():
    """Owner-contract preflight can't promote reviewed SHAPE to live permission."""
    as_of, period, policy, stop, binding = _inactive_owner_policy_fixture()
    from verification.ingestion_storage.operational_owner import Owner
    result = Owner.review_inactive_campaign_period(
        as_of, "tameside", "2026-09-15", "2026-09-21",
        period=period, policy=policy, observed_stop=stop,
        execution_binding=binding)
    assert result["schema"] == "PA_D004_OWNER_RUNTIME_POLICY_OFFLINE_REVIEW_V1"
    assert result["period"] == period
    assert result["manifest_status"] == "WITHHELD"
    assert result["campaign_batch"]["semantics"] == "RECEIVED"
    assert result["campaign_source_plan_sha256"] == policy[
        "campaign_source_plan_sha256"]
    assert result["stable_issuer_sha256"]
    assert len(result["policy_sha256"]) == 64
    for flag in ("actual_role_acl_verified", "live_stop_observed",
                 "source_contract_qualified", "installer_authorised",
                 "owner_registration_authorised", "runtime_enabled",
                 "collection_authorised"):
        assert result[flag] is False
    assert "ingestion_register_campaign_once" not in intake_policy.installation_script()


@pytest.mark.parametrize("mutation,expected", [
    ("source_sha", "CAMPAIGN_OWNER_SOURCE_OR_SCOPE_DRIFT"),
    ("source_row", "CAMPAIGN_OWNER_SOURCE_OR_SCOPE_DRIFT"),
    ("wrong_mode", "CAMPAIGN_OWNER_SOURCE_OR_SCOPE_DRIFT"),
    ("two_councils", "CAMPAIGN_OWNER_SINGLE_COUNCIL"),
    ("wrong_semantics", "CAMPAIGN_OWNER_SOURCE_OR_SCOPE_DRIFT"),
    ("test_evidence", "CAMPAIGN_OWNER_SOURCE_OR_SCOPE_DRIFT"),
    ("max_runs_bool", "CAMPAIGN_OWNER_SOURCE_OR_SCOPE_DRIFT"),
    ("screening", "CAMPAIGN_OWNER_CONTRACT_OR_SCREENING"),
    ("contract_qual", "CAMPAIGN_OWNER_CONTRACT_OR_SCREENING"),
    ("role_loopback", "CAMPAIGN_OWNER_ROUTE_UNVERIFIED"),
    ("private_release", "CAMPAIGN_OWNER_PRIVATE_RELEASE_NOT_BOUND"),
    ("wrong_binding", "CAMPAIGN_OWNER_RUNTIME_BINDING"),
    ("expires", "CAMPAIGN_OWNER_EXPIRY"),
    ("unbounded", "CAMPAIGN_OWNER_POLICY_SCHEMA"),
])
def test_inactive_owner_runtime_policy_rejects_mutations(mutation, expected):
    as_of, period, policy, stop, binding = _inactive_owner_policy_fixture()
    if mutation == "source_sha":
        policy["campaign_source_plan_sha256"] = "f" * 64  # plausible SHA
    elif mutation == "source_row":
        policy["campaign_batch"]["start"] = "2026-09-22"
    elif mutation == "wrong_mode":
        policy["mode"] = None
    elif mutation == "two_councils":
        policy["councils"]["manchester"] = policy["councils"]["tameside"]
    elif mutation == "wrong_semantics":
        policy["campaign_batch"]["semantics"] = "VALIDATED"
    elif mutation == "test_evidence":
        policy["test_evidence"] = True
    elif mutation == "max_runs_bool":
        policy["max_runs"] = True  # Python True==1 but not an SQL integer
    elif mutation == "screening":
        policy["screening_config"] = "not-a-hash"
    elif mutation == "contract_qual":
        policy["councils"]["tameside"]["qualification_sha256"] = "changed"
    elif mutation == "role_loopback":
        policy["hostaddr"] = "127.0.0.1"
    elif mutation == "private_release":
        policy["private_release"]["revision"] = "f" * 40
    elif mutation == "wrong_binding":
        policy["execution_binding"]["revision"] = "f" * 40
    elif mutation == "expires":
        policy["expires_at"] = as_of.timestamp() + 604801
    elif mutation == "unbounded":
        policy["catchup_scope"] = {"start": "2026-09-15"}
    with pytest.raises(ValueError, match=expected):
        candidate.review_inactive_campaign_owner_policy(
            as_of, "tameside", "2026-09-15", "2026-09-21",
            period=period, policy=policy, observed_stop=stop,
            execution_binding=binding)


@pytest.mark.parametrize("mutation", ["generation14", "global_stop",
                                       "manual_stop", "snapshot_drift"])
def test_inactive_owner_runtime_policy_rejects_unreleased_stop(mutation):
    as_of, period, policy, stop, binding = _inactive_owner_policy_fixture()
    if mutation == "generation14":
        stop["hard_stop_generation"] = 14
        policy["expected_stop"]["hard_stop_generation"] = 14
    elif mutation == "global_stop":
        stop["global_stop"] = {"reason": "DAILY_INTAKE_SHARED_FAILURE"}
        policy["expected_stop"]["global_stop"] = stop["global_stop"]
    elif mutation == "manual_stop":
        stop["manual_stop"] = "DAILY_INTAKE_SHARED_FAILURE"
        policy["expected_stop"]["manual_stop"] = stop["manual_stop"]
    else:
        stop["last_hard_stop"] = "changed"
    with pytest.raises(ValueError, match="CAMPAIGN_OWNER_STOP_NOT_RELEASED"):
        candidate.review_inactive_campaign_owner_policy(
            as_of, "tameside", "2026-09-15", "2026-09-21",
            period=period, policy=policy, observed_stop=stop,
            execution_binding=binding)


def test_inactive_owner_runtime_policy_refuses_replayed_period():
    as_of, period, policy, stop, binding = _inactive_owner_policy_fixture()
    with pytest.raises(ValueError, match="CAMPAIGN_OWNER_PERIOD_NOT_CANONICAL"):
        candidate.review_inactive_campaign_owner_policy(
            as_of, "tameside", "2026-09-15", "2026-09-21",
            period="unbound-replay", policy=policy, observed_stop=stop,
            execution_binding=binding)


def test_inactive_runtime_batch_matches_owner_and_source_without_grant():
    """One canonical finite Tameside scope, checked at both proposed boundaries.

    The existing positive disposable PG collector is a DIFFERENT, test-only
    issuer: this review must never enable the stable production candidate.
    """
    from verification.ingestion_storage.daily_intake_runtime import (
        Runtime, review_inactive_campaign_runtime_batch,
    )
    from app.ingestion.ledger import Denied
    as_of, period, policy, stop, binding = _inactive_owner_policy_fixture()
    reviewed = review_inactive_campaign_runtime_batch(
        as_of, period=period, policy=policy, observed_stop=stop,
        execution_binding=binding)
    expected = candidate.prepare_inactive_campaign_owner_batch(
        as_of, "tameside", "2026-09-15", "2026-09-21")
    assert reviewed["schema"] == "PA_D004_INACTIVE_RUNTIME_BATCH_REVIEW_V1"
    assert reviewed["period"] == expected["period"]
    assert reviewed["scope"] == expected["campaign_batch"]
    assert reviewed["source_plan_sha256"] == expected[
        "campaign_source_plan_sha256"]
    assert reviewed["proposed_issuer_sha256"] == expected[
        "stable_issuer_sha256"]
    assert len(reviewed["owner_policy_sha256"]) == 64
    assert reviewed["manifest_status"] == "WITHHELD"
    assert not reviewed["owner_registration_authorised"]
    assert not reviewed["runtime_enabled"] and not reviewed[
        "collection_authorised"]
    runtime = object.__new__(Runtime)
    runtime.policy = policy
    runtime.test = False
    runtime.route_name = "POOLER"
    with pytest.raises(Denied, match="INTAKE_MODE_NOT_RELEASED"):
        runtime.intake_issuer()
    runtime.test = True
    runtime.route_name = "DISPOSABLE"
    with pytest.raises(Denied, match="INTAKE_MODE_NOT_RELEASED"):
        runtime.intake_issuer()


@pytest.mark.parametrize("mutation,refusal", [
    ("mode", "INTAKE_CAMPAIGN_REVIEW_MODE"),
    ("scope", "INTAKE_CAMPAIGN_REVIEW_SCOPE"),
    ("stop", "CAMPAIGN_OWNER_STOP_NOT_RELEASED"),
    ("sha", "CAMPAIGN_OWNER_SOURCE_OR_SCOPE_DRIFT"),
    ("semantics", "INTAKE_CAMPAIGN_RUNTIME_SEMANTICS_DRIFT"),
])
def test_inactive_runtime_review_refuses_drift(monkeypatch, mutation, refusal):
    from types import SimpleNamespace
    from verification.ingestion_storage import daily_intake_runtime
    as_of, period, policy, stop, binding = _inactive_owner_policy_fixture()
    if mutation == "mode":
        policy["mode"] = None
    elif mutation == "scope":
        policy["campaign_batch"]["unbounded"] = True
    elif mutation == "stop":
        stop["hard_stop_generation"] = 14
        policy["expected_stop"]["hard_stop_generation"] = 14
    elif mutation == "sha":
        policy["campaign_source_plan_sha256"] = "f" * 64
    else:
        monkeypatch.setattr(daily_intake_runtime, "binding_for",
                            lambda council: SimpleNamespace(
                                semantics="VALIDATED"))
    with pytest.raises((ValueError, daily_intake_runtime.Denied),
                       match=refusal):
        daily_intake_runtime.review_inactive_campaign_runtime_batch(
            as_of, period=period, policy=policy,
            observed_stop=stop, execution_binding=binding)



def test_historical_owner_pregrant_observation_requires_no_update_privilege():
    """Source-level regression: production postgres has no proven UPDATE.

    This is a negative boundary check, NOT a connected PostgreSQL result.
    The advisory snapshot must be read-only; the *issuer* does the locked
    expected_stop comparison after temporary capability is acquired.
    """
    import inspect
    from verification.ingestion_storage.operational_owner import Owner

    source = inspect.getsource(Owner.register_intake_period)
    start = source.index("rows=self.q(c,\"SELECT outcome FROM public.ingestion_work_items \"")
    grant = source.index("self.q(c,'GRANT ingestion_barrier_releaser", start)
    pregrant = source[start:grant]
    assert '"WHERE key=repeat(\'0\',64)")' in pregrant
    assert "FOR SHARE" not in pregrant and "FOR UPDATE" not in pregrant
    assert "operation='campaign_owner_preflight'" in pregrant
    assert pregrant.index("campaign_owner_preflight") < pregrant.index("CAMPAIGN_OWNER_STOP_CHANGED_BEFORE_GRANT")
    # This assertion prevents incorrectly replacing the issuer's protective
    # locking CAS with only an unlocked owner-side SELECT.
    stable = candidate.render_inactive_stable_campaign_issuer()
    assert ("SELECT outcome::jsonb INTO STRICT ctl FROM "
            "public.ingestion_work_items WHERE key=repeat('0',64) "
            "FOR UPDATE;") in stable
    assert "e->'expected_stop' IS DISTINCT FROM" in stable
    assert "CAMPAIGN_STABLE_MANIFEST_WITHHELD" in stable
    assert "ingestion_register_campaign_once" not in intake_policy.installation_script()

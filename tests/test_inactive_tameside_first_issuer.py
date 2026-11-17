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
    ("tameside", "2026-11-16", "2026-11-16", "CAMPAIGN_FINITE_CURRENT_DAY_PARTIAL"),
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


@pytest.mark.parametrize("council,start,end,error",[
    ("trafford","2026-09-15","2026-09-21","TRAFFORD_SOURCE_NOT_QUALIFIED"),
    ("tameside","2026-09-15","2026-09-22","TEN_COUNCIL_BATCH_OUTSIDE_CAMPAIGN"),
    ("tameside","2026-11-16","2026-11-16","CAMPAIGN_FINITE_CURRENT_DAY_PARTIAL"),
])
def test_stable_owner_preview_refuses_unqualified_or_partial(council,start,end,error):
    with pytest.raises(ValueError,match=error):
        candidate.prepare_inactive_campaign_owner_batch(
            datetime(2026,11,16,20,tzinfo=timezone.utc),council,start,end)


def test_stable_issuer_does_not_tolerate_changed_pinned_policy(monkeypatch):
    monkeypatch.setattr(candidate,"_policy_source_bytes",lambda:b"changed")
    with pytest.raises(ValueError,match="CAMPAIGN_STABLE_POLICY_SOURCE_DRIFT"):
        candidate.render_inactive_stable_campaign_issuer()

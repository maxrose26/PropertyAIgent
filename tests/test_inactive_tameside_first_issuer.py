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


def test_disposable_pg_parses_withheld_sql_and_refuses_source_authority():
    """PG17 syntax, public EXECUTE refusal and zero controller mutations.

    A disposable-only installation for negative testing; no positive live
    historical issuer, owner runtime or source call is exercised.
    """
    import json
    from tests.e2e_pg_world import disposable_world
    for world in disposable_world():
        with world["connect"]("provisioning_migrator") as c:
            c.execute(intake_policy.installation_script(disposable_catchup=True))
            c.execute(candidate.render_inactive_tameside_first_issuer())
            public_execute = c.execute(
                "SELECT has_function_privilege('ingestion_worker_login',"
                "'public.ingestion_register_tameside_first_once(jsonb)','EXECUTE')"
            ).fetchone()[0]
            assert public_execute is False
            controller_before = world["boot"].execute(
                "SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)"
            ).fetchone()[0]
            request = dict(operation="intake_period",
                           period=candidate.PERIOD, policy={})
            with pytest.raises(Exception, match="TAMESIDE_FIRST_SCOPE_OR_STOP"):
                c.execute(
                    "SELECT public.ingestion_register_tameside_first_once(%s::jsonb)",
                    (json.dumps(request),)
                )
            controller_after = world["boot"].execute(
                "SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)"
            ).fetchone()[0]
            assert controller_after == controller_before

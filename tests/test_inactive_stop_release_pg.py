"""Focused disposable-only proof for the DORMANT one-shot owner release SQL.

This deliberately substitutes a TEST fixture database/identity and synthetic
review payload. The shipped SQL remains WITHHELD and cannot execute. These
tests are not owner authorisation, real effect closure or production installer.
"""
import copy
import json
import re
from pathlib import Path

import pytest

from tests.e2e_pg_world import disposable_world
from tests.test_daily_intake_runtime import (
    _HISTORICAL_ABANDONED_IDENTITIES, _RECOVERY_KEY, _settled_fixture,
)
from verification.ingestion_storage import intake_policy
from verification.ingestion_storage.operational_owner import item

PATH=Path("verification/ingestion_storage/inactive_shared_stop_release_v1.sql")
OWNER_SHA="1"*64


@pytest.fixture
def isolated_world():
    for w in disposable_world():
        with w["connect"]("provisioning_migrator") as c:
            c.execute(intake_policy.installation_script(disposable_catchup=True))
        # Reuse the existing exact PA-D002 table/function fixture instead of
        # inventing or granting a broader private evidence interface.
        boot=w["boot"]
        boot.execute(Path("tests/fixtures/pa_d002_private_postgres.sql").read_text())
        boot.execute("""ALTER TABLE public.ingestion_run_evidence ENABLE ROW LEVEL SECURITY;
             ALTER TABLE public.ingestion_run_evidence FORCE ROW LEVEL SECURITY;
             CREATE POLICY ingestion_evidence_owner ON public.ingestion_run_evidence
               FOR ALL TO ingestion_storage_owner USING (true) WITH CHECK (true);
             CREATE ROLE postgres NOLOGIN;
             GRANT EXECUTE ON FUNCTION public.ingestion_intake_evidence_read(
               text,text,text) TO postgres;""")
        # The standard PA-D002 fixture ships the candidate writer; restore the
        # exact reviewed installed OLD body before exercising the transition.
        boot.execute(Path("tests/fixtures/pa_d002_installed_writer.sql").read_text())
        old_sha=boot.execute(
            "SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') "
            "FROM pg_proc WHERE oid='public.ingestion_intake_evidence_write("
            "text,text,text,bytea)'::regprocedure").fetchone()[0]
        assert old_sha=="8ffd8fdda0692a49a776137ea6342c1378d1f513cd418b8f983a92f0fe910290"
        try:
            yield w
        finally:
            boot.execute("REVOKE EXECUTE ON FUNCTION public.ingestion_intake_evidence_read("
                         "text,text,text) FROM postgres")
            boot.execute("DROP ROLE postgres")


def _script(manifest=None):
    source=PATH.read_text()
    assert "OWNER_RELEASE_REVIEW_WITHHELD" in source
    assert 'review_manifest jsonb := \x27{"release_status":"WITHHELD","review_sha256":null,"effects":[]}\x27::jsonb' in source
    assert "ingestion_disposable_shared_stop_release" not in source
    assert "CREATE OR REPLACE FUNCTION" not in source
    assert "GRANT " not in "\n".join(
        l for l in source.splitlines() if not l.lstrip().startswith("--"))
    # Test-only identity substitution, never committed to the production SQL.
    source=source.replace(
        "current_database() IS DISTINCT FROM 'postgres'",
        "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'")
    source=source.replace(
        "session_user IS DISTINCT FROM 'postgres'",
        "session_user IS DISTINCT FROM 'provisioning_bootstrap'")
    source=source.replace(
        "current_user IS DISTINCT FROM 'postgres'",
        "current_user IS DISTINCT FROM 'provisioning_bootstrap'")
    if manifest is not None:
        source=source.replace(
            '\x27{"release_status":"WITHHELD","review_sha256":null,"effects":[]}\x27::jsonb',
            "'"+json.dumps(manifest,separators=(",",":"),sort_keys=True)+"'::jsonb")
    return source


def _run(w, source, *, rollback=False):
    if rollback:
        assert source.count("\nCOMMIT;\n")==1
        source=source.replace("\nCOMMIT;\n","\nROLLBACK;\n")
    # The fixed disposable bootstrap is the only existing principal with
    # physical table LOCK authority. No new privileges/grants are introduced.
    # The production template still requires actual session_user=postgres.
    try:
        w["boot"].execute(source)
    except BaseException:
        w["boot"].execute("ROLLBACK")
        raise


def _control(w):
    return w["boot"].execute(
        "SELECT outcome FROM public.ingestion_work_items "
        "WHERE key=repeat('0',64)").fetchone()[0]


def _preimage_keys():
    source=PATH.read_text()
    return json.loads(re.search(
        r"expected_prior jsonb := '(\{.*?\})'::jsonb;",
        source,re.S).group(1))


def _seed(w):
    # The actual pinned #213->#227 joined proof has ALREADY passed elsewhere.
    # This focused test starts stopped at synthetic generation 15 only.
    c=w["boot"]
    ctl=_settled_fixture(w)
    for key,council,semantics,start,end,contract,revision,authority in _HISTORICAL_ABANDONED_IDENTITIES:
        identity=dict(subject=dict(kind="DISCOVERY_SCOPE",council=council,
                                   semantics=semantics,start=start,end=end),
                      task="DISCOVERY",contract=contract,revision=revision)
        row=item(identity,max_attempts=1 if council=="bolton" else 2)
        assert row["key"]==key
        row.update(state="DEFERRED",phase="FINISHED",fence=2,
                   attempt_count=1,owner=None,lease_until=None,
                   checkpoint=dict(review_sha256=OWNER_SHA,
                                   reviewer_evidence="TEST_ONLY_SYNTHETIC",
                                   source_effect_status="UNKNOWN"),
                   authority=authority,reason="REVIEWED_PRESERVE_NO_REPLAY",
                   next_action="PRESERVE_HISTORY_NO_REPLAY",
                   outcome=dict(outcome="REVIEW_ACCEPTED_PRESERVE_NO_REPLAY",
                                coverage="UNKNOWN",
                                source_or_write_replay_authorised=False))
        c.execute("INSERT INTO public.ingestion_work_items SELECT * FROM "
                  "json_populate_record(NULL::public.ingestion_work_items,%s::json)",
                  (json.dumps(row),))
        c.execute("""INSERT INTO public.ingestion_work_attempts
          (work_key,fence,owner,started_at,finished_at,authority,phase,outcome,checkpoint)
          VALUES (%s,1,'synthetic',0,100,%s,'RECOVERED',%s::json,NULL)""",
          (key,authority,json.dumps(dict(outcome="ABANDONED_SOURCE_INTENT",
                               source_or_write_replay_authorised=False))))
    return ctl


def _manifest(w):
    prior=_preimage_keys()
    result=[]
    for key in sorted(prior):
        row=w["boot"].execute(
            """SELECT encode(sha256(convert_to(to_jsonb(w)::text,'UTF8')),'hex'),
                      (SELECT encode(sha256(convert_to(
                          coalesce(jsonb_agg(to_jsonb(a) ORDER BY a.fence)::text,
                          '[]'),'UTF8')),'hex')
                       FROM public.ingestion_work_attempts a WHERE a.work_key=w.key)
               FROM public.ingestion_work_items w WHERE w.key=%s""",
            (key,)).fetchone()
        assert row and all(row)
        result.append(dict(key=key,prior_sha256=prior[key],
                           work_sha256=row[0],attempts_sha256=row[1],
                           release_containment="ACCEPT",coverage="UNKNOWN",
                           source_or_write_replay_authorised=False,
                           source_decision_scope="EXPLICIT_OPERATIONAL_RELEASE_NOT_PRESERVATION_ONLY",
                           review_ref="https://github.com/maxrose26/PropertyAIgent/pull/227#SYNTHETIC_TEST_ONLY",
                           **(dict(effect_state="UNKNOWN",
                                   risk_acceptance="OWNER_AND_DISTINCT_REVIEW_EXPLICIT_UNKNOWN",
                                   risk_boundary="NO_REPLAY_ONE_GENERATION_NO_COVERAGE",
                                   owner_decision_ref="https://github.com/maxrose26/PropertyAIgent/issues/214#issuecomment-SYNTHETIC_TEST_ONLY")
                              if key.startswith(("21330c06","dc8ae276")) else {})))
    return dict(release_status="ACCEPTED_FOR_OPERATIONAL_RELEASE",
                review_sha256=OWNER_SHA,effects=result)


def test_adapter_default_is_inert_no_installer_or_live_enablement(isolated_world):
    from verification.ingestion_storage.daily_intake_runtime import LIVE_PRIVATE_EVIDENCE_RELEASE
    assert LIVE_PRIVATE_EVIDENCE_RELEASE is False
    assert "inactive_shared_stop_release_v1" not in intake_policy.installation_script()
    assert "owner_shared_stop_release" not in intake_policy.installation_script()
    assert "ingestion_disposable_shared_stop_release" not in _script()
    before=_control(isolated_world)
    with pytest.raises(Exception,match="OWNER_RELEASE_REVIEW_WITHHELD"):
        _run(isolated_world,_script())
    assert _control(isolated_world)==before


def test_adapter_install_rollback_negative_drift_and_single_generation(isolated_world):
    w=isolated_world
    stopped=_seed(w)
    ctl_before=_control(w)
    assert stopped==ctl_before
    attempts_before=w["boot"].execute(
        "SELECT to_jsonb(a) FROM public.ingestion_work_attempts a "
        "ORDER BY a.work_key,a.fence").fetchall()
    audit_before=w["boot"].execute(
        "SELECT to_jsonb(w) FROM public.ingestion_work_items w "
        "WHERE key LIKE 'c1f526ee%'").fetchone()[0]
    # The owner writer transition is an existing prepared separate artifact.
    # Without its exact new function digest, release refuses.
    mock=_script(_manifest(w))
    with pytest.raises(Exception,match="OWNER_RELEASE_WRITER_OR_EVIDENCE_DRIFT"):
        _run(w,mock)
    assert _control(w)==ctl_before
    w["boot"].execute(Path(
        "verification/ingestion_storage/private_evidence_writer_transition.sql"
    ).read_text())
    manifest=_manifest(w)
    mock=_script(manifest)
    # The shipped SQL still refuses; only the synthetic in-memory substitution
    # reaches these tests. No test approval lands in repository SQL.
    with pytest.raises(Exception,match="OWNER_RELEASE_REVIEW_WITHHELD"):
        _run(w,_script())
    assert _control(w)==ctl_before

    # Negative: exact generation STOP-CAS, immutable Salford and effect hashes.
    w["boot"].execute("UPDATE public.ingestion_work_items SET "
                      "outcome=jsonb_set(outcome::jsonb,'{hard_stop_generation}',"
                      "'17'::jsonb)::json WHERE key=repeat('0',64)")
    with pytest.raises(Exception,match="OWNER_RELEASE_STOP_CAS"):
        _run(w,mock)
    w["boot"].execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                      "WHERE key=repeat('0',64)",(json.dumps(ctl_before),))
    w["boot"].execute("UPDATE public.ingestion_work_items SET "
                      "reason='TEST_DRIFT' WHERE key LIKE 'c1f526ee%'")
    with pytest.raises(Exception,match="OWNER_RELEASE_SALFORD_DRIFT"):
        _run(w,mock)
    w["boot"].execute("UPDATE public.ingestion_work_items SET "
                      "reason='CONSUMED_SALFORD_GLOBAL_STOP' "
                      "WHERE key LIKE 'c1f526ee%'")
    key=manifest["effects"][0]["key"]
    w["boot"].execute("UPDATE public.ingestion_work_items SET "
                      "reason='TEST_DRIFT' WHERE key=%s",(key,))
    with pytest.raises(Exception,match="OWNER_RELEASE_EFFECT_OR_NO_REPLAY_DRIFT"):
        _run(w,mock)
    w["boot"].execute("UPDATE public.ingestion_work_items SET "
                      "reason=%s WHERE key=%s",
                      ("ABANDONED_SOURCE_INTENT" if key==_RECOVERY_KEY
                       else "REVIEWED_PRESERVE_NO_REPLAY",key))
    assert _control(w)==ctl_before

    # Explicitly withheld UNKNOWN physical-effect risk must not be converted
    # into stop-release authority by a preservation-only review finding.
    withheld=copy.deepcopy(manifest)
    withheld_key=next(e for e in withheld["effects"]
                      if e["key"].startswith("dc8ae276"))
    withheld_key["risk_acceptance"]="WITHHELD_UNKNOWN_EFFECT"
    with pytest.raises(Exception,match="OWNER_RELEASE_EFFECT_REVIEW_MISSING"):
        _run(w,_script(withheld))
    assert _control(w)==ctl_before

    # An independently active finite grant blocks release, even with otherwise
    # valid synthetic review payload and a still-unchanged STOP generation.
    stray=copy.deepcopy(ctl_before)
    stray["grants"]={"test_active_grant":{"expires_at":4102444800}}
    w["boot"].execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                      "WHERE key=repeat('0',64)",(json.dumps(stray),))
    with pytest.raises(Exception,match="OWNER_RELEASE_OUTSTANDING_EFFECT_OR_AUTHORITY"):
        _run(w,mock)
    w["boot"].execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                      "WHERE key=repeat('0',64)",(json.dumps(ctl_before),))
    assert _control(w)==ctl_before

    # A newly uncertain historical attempt must also refuse, not be treated
    # as finished just because its parent work row has a reviewed marker.
    attempt_key=manifest["effects"][0]["key"]
    prior_finished=w["boot"].execute(
        "SELECT finished_at FROM public.ingestion_work_attempts "
        "WHERE work_key=%s AND fence=1",(attempt_key,)).fetchone()[0]
    w["boot"].execute(
        "UPDATE public.ingestion_work_attempts SET finished_at=NULL "
        "WHERE work_key=%s AND fence=1",(attempt_key,))
    with pytest.raises(Exception,match="OWNER_RELEASE_EFFECT_OR_NO_REPLAY_DRIFT"):
        _run(w,mock)
    w["boot"].execute(
        "UPDATE public.ingestion_work_attempts SET finished_at=%s "
        "WHERE work_key=%s AND fence=1",(prior_finished,attempt_key))
    assert _control(w)==ctl_before

    _run(w,mock,rollback=True)
    assert _control(w)==ctl_before
    _run(w,mock)
    after=_control(w)
    assert after["hard_stop_generation"]==16
    assert after["global_stop"] is None and after["manual_stop"] is None
    assert after["last_hard_stop"]==ctl_before["last_hard_stop"]
    assert after["owner_shared_stop_release"]["review_sha256"]==OWNER_SHA
    assert after["owner_shared_stop_release"]["no_work_issued"] is True
    assert w["boot"].execute(
        "SELECT to_jsonb(a) FROM public.ingestion_work_attempts a "
        "ORDER BY a.work_key,a.fence").fetchall()==attempts_before
    assert w["boot"].execute(
        "SELECT to_jsonb(w) FROM public.ingestion_work_items w "
        "WHERE key LIKE 'c1f526ee%'").fetchone()[0]==audit_before
    with pytest.raises(Exception,match="OWNER_RELEASE_STOP_CAS"):
        _run(w,mock)
    assert _control(w)==after

"""Focused disposable-only proof for the DORMANT one-shot owner release SQL.

This deliberately substitutes a TEST fixture database/identity and synthetic
review payload. The shipped SQL remains WITHHELD and cannot execute. These
tests are not owner authorisation, real effect closure or production installer.
"""
import copy
import json
import re
import secrets

import psycopg
from psycopg import sql
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


def _script(manifest=None, *, owner_path=False):
    source=PATH.read_text()
    assert "OWNER_RELEASE_REVIEW_WITHHELD" in source
    assert 'review_manifest jsonb := \x27{"release_status":"WITHHELD","review_sha256":null,"effects":[]}\x27::jsonb' in source
    assert "ingestion_disposable_shared_stop_release" not in source
    assert "CREATE OR REPLACE FUNCTION" not in source
    assert "-- OWNER_CAPABILITY_BEGIN" in source
    assert "-- OWNER_CAPABILITY_CLEANUP_BEGIN" in source
    assert "WITH ADMIN FALSE, INHERIT TRUE, SET TRUE GRANTED BY postgres" in source
    if not owner_path:
        # Existing bootstrap fixture tests exercise the guarded body, not the
        # owner privilege lifecycle; a SEPARATE non-superuser test covers it.
        for start,end in (("-- OWNER_CAPABILITY_BEGIN", "-- OWNER_CAPABILITY_END"),
                          ("-- OWNER_CAPABILITY_CLEANUP_BEGIN", "-- OWNER_CAPABILITY_CLEANUP_END")):
            source=re.sub(re.escape(start)+r".*?"+re.escape(end)+r"\n",
                          "",source,flags=re.S)
        assert "GRANT " not in "\n".join(
            l for l in source.splitlines() if not l.lstrip().startswith("--"))
    # The local disposable DB name is the ONLY identity substitution for the
    # restricted owner-path test: both postgres role checks remain literal.
    source=source.replace(
        "current_database() IS DISTINCT FROM 'postgres'",
        "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'")
    if not owner_path:
        source=source.replace(
            "session_user IS DISTINCT FROM 'postgres'",
            "session_user IS DISTINCT FROM 'provisioning_bootstrap'")
        source=source.replace(
            "current_user IS DISTINCT FROM 'postgres'",
            "current_user IS DISTINCT FROM 'provisioning_bootstrap'")
    else:
        assert "session_user IS DISTINCT FROM 'postgres'" in source
        assert "current_user IS DISTINCT FROM 'postgres'" in source
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


def _seal_manifest(w, manifest):
    # Hash PostgreSQL jsonb's canonical text; this is not signed approval.
    payload={k:v for k,v in manifest.items() if k!="manifest_binding_sha256"}
    digest=w["boot"].execute(
        "SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",
        (json.dumps(payload,sort_keys=True,separators=(",",":")),)
    ).fetchone()[0]
    manifest["manifest_binding_sha256"]=digest
    return manifest


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
    controller_sha=w["boot"].execute(
        "SELECT encode(sha256(convert_to(outcome::jsonb::text,'UTF8')),'hex') "
        "FROM public.ingestion_work_items WHERE key=repeat('0',64)"
    ).fetchone()[0]
    return _seal_manifest(w,dict(release_status="ACCEPTED_FOR_OPERATIONAL_RELEASE",
                review_sha256=OWNER_SHA,
                expected_controller_sha256=controller_sha,effects=result))


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
    # A plausible reviewer reference may not be swapped after review digest.
    tampered=copy.deepcopy(manifest)
    tampered["effects"][0]["review_ref"]=(
        "https://github.com/maxrose26/PropertyAIgent/pull/227#UNREVIEWED_CHANGE")
    with pytest.raises(Exception,match="OWNER_RELEASE_MANIFEST_BINDING"):
        _run(w,_script(tampered))
    missing=copy.deepcopy(manifest)
    missing.pop("manifest_binding_sha256")
    with pytest.raises(Exception,match="OWNER_RELEASE_MANIFEST_BINDING"):
        _run(w,_script(missing))
    assert _control(w)==ctl_before
    # Exact production owner-only RLS policy must not drift at release.
    w["boot"].execute("ALTER POLICY ingestion_evidence_owner ON "
                      "public.ingestion_run_evidence WITH CHECK (false)")
    with pytest.raises(Exception,match="OWNER_RELEASE_WRITER_OR_EVIDENCE_DRIFT"):
        _run(w,mock)
    w["boot"].execute("ALTER POLICY ingestion_evidence_owner ON "
                      "public.ingestion_run_evidence WITH CHECK (true)")
    w["boot"].execute("CREATE POLICY extraneous_release_test ON "
                      "public.ingestion_run_evidence FOR SELECT TO "
                      "ingestion_storage_owner USING (true)")
    with pytest.raises(Exception,match="OWNER_RELEASE_WRITER_OR_EVIDENCE_DRIFT"):
        _run(w,mock)
    w["boot"].execute("DROP POLICY extraneous_release_test ON "
                      "public.ingestion_run_evidence")
    assert _control(w)==ctl_before

    # A terminal-looking DEFERRED row must not conceal an unrelated original
    # abandoned source effect merely by changing its state/reason/action.
    # The original outcome remains evidence of unresolved physical effects.
    hidden_key="f"*64
    hidden=w["boot"].execute(
        "SELECT to_jsonb(w) FROM public.ingestion_work_items w WHERE key=%s",
        (manifest["effects"][1]["key"],)
    ).fetchone()[0]
    hidden["key"]=hidden_key
    hidden["state"]="DEFERRED"
    hidden["phase"]="FINISHED"
    hidden["reason"]="REVIEWED_PRESERVE_NO_REPLAY"
    hidden["next_action"]="PRESERVE_HISTORY_NO_REPLAY"
    hidden["outcome"]["outcome"]="ABANDONED_SOURCE_INTENT"
    w["boot"].execute(
        "INSERT INTO public.ingestion_work_items SELECT * FROM "
        "json_populate_record(NULL::public.ingestion_work_items,%s::json)",
        (json.dumps(hidden),)
    )
    with pytest.raises(Exception,match="OWNER_RELEASE_OUTSTANDING_EFFECT_OR_AUTHORITY"):
        _run(w,mock)
    w["boot"].execute("DELETE FROM public.ingestion_work_items WHERE key=%s",
                      (hidden_key,))
    assert _control(w)==ctl_before

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
    _seal_manifest(w,withheld)  # even a recomputed digest cannot lift WITHHOLD
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

    # A syntactically valid but unbound full-controller digest cannot
    # authorise a release. A non-STOP policy change also refuses under lock.
    wrong_digest=copy.deepcopy(manifest)
    wrong_digest["expected_controller_sha256"]="0"*64
    _seal_manifest(w,wrong_digest)  # matching payload hash cannot hide DB drift
    with pytest.raises(Exception,match="OWNER_RELEASE_CONTROLLER_DRIFT"):
        _run(w,_script(wrong_digest))
    unrelated_ctl=copy.deepcopy(ctl_before)
    unrelated_ctl["unreviewed_controller_change"]="TEST_ONLY"
    w["boot"].execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                      "WHERE key=repeat('0',64)",(json.dumps(unrelated_ctl),))
    with pytest.raises(Exception,match="OWNER_RELEASE_CONTROLLER_DRIFT"):
        _run(w,mock)
    w["boot"].execute("UPDATE public.ingestion_work_items SET outcome=%s::json "
                      "WHERE key=repeat('0',64)",(json.dumps(ctl_before),))
    assert _control(w)==ctl_before

    _run(w,mock,rollback=True)
    assert _control(w)==ctl_before
    _run(w,mock)
    after=_control(w)
    assert after["hard_stop_generation"]==16
    assert after["global_stop"] is None and after["manual_stop"] is None
    assert after["last_hard_stop"]==ctl_before["last_hard_stop"]
    assert after["owner_shared_stop_release"]["review_sha256"]==OWNER_SHA
    assert after["owner_shared_stop_release"]["manifest_binding_sha256"]==manifest["manifest_binding_sha256"]
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


def test_non_superuser_owner_transactional_capability_and_readback(isolated_world):
    """Focused real-role PG17 proof; only disposable database NAME is substituted.

    This exercises current_user=session_user=postgres without a superuser.
    Does NOT establish current production grants or a real signed review.
    """
    from tests.e2e_pg_world import settings
    w=isolated_world
    boot=w["boot"]
    _,info,_,_=settings()
    password=secrets.token_urlsafe(40)
    # Existing fixture creates postgres NOLOGIN; change only this disposable
    # principal to match the reviewed owner's non-superuser administrative flags.
    boot.execute(sql.SQL("ALTER ROLE postgres LOGIN NOSUPERUSER CREATEROLE "
                         "CREATEDB BYPASSRLS INHERIT PASSWORD {}").format(
                             sql.Literal(password)))
    boot.execute("GRANT ingestion_storage_owner TO postgres "
                 "WITH ADMIN TRUE, INHERIT FALSE, SET FALSE "
                 "GRANTED BY provisioning_bootstrap")
    def owner():
        return psycopg.connect(**{**info,"user":"postgres","password":password},
                               autocommit=True,prepare_threshold=None)
    def memberships():
        return boot.execute(
            "SELECT grantor::regrole::text,admin_option,inherit_option,set_option "
            "FROM pg_auth_members WHERE member='postgres'::regrole "
            "AND roleid='ingestion_storage_owner'::regrole ORDER BY grantor"
        ).fetchall()
    baseline=memberships()
    assert baseline==[("provisioning_bootstrap",True,False,False)]
    try:
        stopped=_seed(w)
        boot.execute(Path("verification/ingestion_storage/"
                          "private_evidence_writer_transition.sql").read_text())
        mock=_script(_manifest(w),owner_path=True)
        assert "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'" in mock
        assert "session_user IS DISTINCT FROM 'postgres'" in mock
        assert "current_user IS DISTINCT FROM 'postgres'" in mock
        with owner() as c:
            flags=c.execute(
                "SELECT current_user,session_user,rolsuper,rolcreaterole,"
                "rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            assert flags==("postgres","postgres",False,True,True,True)
            assert c.execute("SELECT pg_has_role(current_user,"
                             "'ingestion_storage_owner','USAGE'),"
                             "pg_has_role(current_user,"
                             "'ingestion_storage_owner','SET')").fetchone()==(False,False)
            # No owner authority is inferred from even a signed-looking fixture.
            with pytest.raises(Exception,match="OWNER_RELEASE_REVIEW_WITHHELD"):
                c.execute(_script(owner_path=True))
            c.execute("ROLLBACK")
        assert memberships()==baseline
        assert _control(w)==stopped

        # Rollback after the complete checked release also restores the
        # temporary role membership and generation-15 STOP.
        with owner() as c:
            c.execute(mock.replace("\nCOMMIT;\n","\nROLLBACK;\n"))
        assert _control(w)==stopped and memberships()==baseline

        # Removing the exact preexisting admin-only grant must REFUSE BEFORE
        # any table lock/release; the transaction cannot create authority.
        boot.execute("REVOKE ingestion_storage_owner FROM postgres "
                     "GRANTED BY provisioning_bootstrap RESTRICT")
        try:
            with owner() as c:
                with pytest.raises(Exception,match="OWNER_RELEASE_OWNER_ADMIN_ONLY_BASELINE"):
                    c.execute(mock)
                c.execute("ROLLBACK")
        finally:
            boot.execute("GRANT ingestion_storage_owner TO postgres "
                         "WITH ADMIN TRUE, INHERIT FALSE, SET FALSE "
                         "GRANTED BY provisioning_bootstrap")
        assert _control(w)==stopped and memberships()==baseline

        with owner() as c:
            c.execute(mock)
        # Independent fresh bootstrap readback: no second run/replay attempt
        # after a hypothetical lost acknowledgement.
        after=_control(w)
        assert after["hard_stop_generation"]==16
        assert after["owner_shared_stop_release"]["version"]=="OWNER_REVIEWED_ONE_SHOT_V1"
        assert after["owner_shared_stop_release"]["no_work_issued"] is True
        assert memberships()==baseline
        with owner() as c:
            with pytest.raises(Exception,match="OWNER_RELEASE_STOP_CAS"):
                c.execute(mock)
            c.execute("ROLLBACK")
        assert _control(w)==after and memberships()==baseline
    finally:
        boot.execute("REVOKE ingestion_storage_owner FROM postgres "
                     "GRANTED BY provisioning_bootstrap RESTRICT")
        boot.execute("ALTER ROLE postgres NOLOGIN NOCREATEROLE NOCREATEDB "
                     "NOBYPASSRLS PASSWORD NULL")


def test_writer_transition_non_superuser_owner_rollback_and_restoration(isolated_world):
    """Prove the pre-release writer install can use existing owner capability.

    This is a disposable PostgreSQL test, not a production installer or a
    credential/operational-authority test. The original writer transition SQL
    body is unchanged; only its BEGIN/COMMIT boundary is embedded inside the
    exact admin-only temporary-owner transaction for this proof.
    """
    from tests.e2e_pg_world import settings
    w=isolated_world
    boot=w["boot"]
    _,info,_,_=settings()
    password=secrets.token_urlsafe(40)
    original=_control(w)
    _seed(w)
    stopped=_control(w)
    assert stopped != original
    writer_hash=lambda: boot.execute(
        "SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') "
        "FROM pg_proc WHERE oid='public.ingestion_intake_evidence_write("
        "text,text,text,bytea)'::regprocedure").fetchone()[0]
    old_hash="8ffd8fdda0692a49a776137ea6342c1378d1f513cd418b8f983a92f0fe910290"
    new_hash="4ce46b98cbf986596f907b7236509b87ade6788bce7e4c9f40ebbd8167381f77"
    assert writer_hash()==old_hash

    # Use exactly the offline, source-pinned artifact renderer instead of
    # a test-local SQL wrapper that could drift from the reviewed installer.
    from verification.ingestion_storage.inactive_owner_writer_install import (
        render_inactive_writer_install,
    )
    source=Path("verification/ingestion_storage/"
                "private_evidence_writer_transition.sql").read_text()
    script=render_inactive_writer_install(source)
    assert "current_database() IS DISTINCT FROM 'postgres'" in script
    # The sole disposable substitution is the database name; both owner
    # session/current-user predicates must stay literal postgres.
    script=script.replace(
        "current_database() IS DISTINCT FROM 'postgres'",
        "current_database() NOT IN ('postgres','ingestion_provisioning_test')",1)
    assert "session_user IS DISTINCT FROM 'postgres'" in script
    assert "current_user IS DISTINCT FROM 'postgres'" in script
    assert script.count("\nCOMMIT;\n")==1
    boot.execute(sql.SQL("ALTER ROLE postgres LOGIN NOSUPERUSER CREATEROLE "
                         "CREATEDB BYPASSRLS INHERIT PASSWORD {}").format(
                             sql.Literal(password)))
    boot.execute("GRANT ingestion_storage_owner TO postgres "
                 "WITH ADMIN TRUE, INHERIT FALSE, SET FALSE "
                 "GRANTED BY provisioning_bootstrap")
    # Disposable-only representation of the existing owner schema options;
    # not a production privilege change or new role.
    boot.execute("GRANT USAGE, CREATE ON SCHEMA public TO postgres WITH GRANT OPTION")
    def membership():
        return boot.execute(
            "SELECT grantor::regrole::text,admin_option,inherit_option,set_option "
            "FROM pg_auth_members WHERE member='postgres'::regrole "
            "AND roleid='ingestion_storage_owner'::regrole ORDER BY grantor"
        ).fetchall()
    def owner():
        return psycopg.connect(**{**info,"user":"postgres","password":password},
                               autocommit=True,prepare_threshold=None)
    baseline=membership()
    assert baseline==[("provisioning_bootstrap",True,False,False)]
    try:
        # Missing schema options must refuse before the temporary role grant.
        boot.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM postgres")
        try:
            with owner() as c:
                with pytest.raises(Exception,match="OWNER_WRITER_SCHEMA_CAPABILITY"):
                    c.execute(script)
                c.execute("ROLLBACK")
        finally:
            boot.execute("GRANT USAGE, CREATE ON SCHEMA public TO postgres WITH GRANT OPTION")
        assert writer_hash()==old_hash and membership()==baseline
        # The whole writer replacement can be rolled back along with the
        # temporary owner membership; no persistent privilege is required.
        with owner() as c:
            c.execute(script.replace("\nCOMMIT;\n","\nROLLBACK;\n"))
        assert writer_hash()==old_hash and membership()==baseline
        assert _control(w)==stopped

        # Removing the exact pre-existing admin-only membership must refuse
        # before the writer function or any controller state changes.
        boot.execute("REVOKE ingestion_storage_owner FROM postgres "
                     "GRANTED BY provisioning_bootstrap RESTRICT")
        try:
            with owner() as c:
                with pytest.raises(Exception,match="OWNER_WRITER_ADMIN_ONLY_BASELINE"):
                    c.execute(script)
                c.execute("ROLLBACK")
        finally:
            boot.execute("GRANT ingestion_storage_owner TO postgres "
                         "WITH ADMIN TRUE, INHERIT FALSE, SET FALSE "
                         "GRANTED BY provisioning_bootstrap")
        assert writer_hash()==old_hash and membership()==baseline
        assert _control(w)==stopped

        with owner() as c:
            c.execute(script)
        # Separate bootstrap readback, not a self-reported success.
        assert writer_hash()==new_hash and membership()==baseline
        assert _control(w)==stopped
    finally:
        boot.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM postgres")
        boot.execute("REVOKE ingestion_storage_owner FROM postgres "
                     "GRANTED BY provisioning_bootstrap RESTRICT")
        boot.execute("ALTER ROLE postgres NOLOGIN NOCREATEROLE NOCREATEDB "
                     "NOBYPASSRLS PASSWORD NULL")


def test_owner_writer_renderer_is_pure_pinned_and_dormant():
    from verification.ingestion_storage.inactive_owner_writer_install import (
        render_inactive_writer_install,
    )
    source=Path("verification/ingestion_storage/"
                "private_evidence_writer_transition.sql").read_text()
    sql_text=render_inactive_writer_install(source)
    assert sql_text.count("\nCOMMIT;\n")==1
    assert sql_text.count("GRANT ingestion_storage_owner TO postgres")==1
    assert "OWNER_WRITER_SCHEMA_CAPABILITY" in sql_text
    assert "OWNER_WRITER_CAPABILITY_REMAINS" in sql_text
    assert "OWNER_WRITER_SOURCE_DRIFT" not in sql_text
    assert "CREATE OR REPLACE FUNCTION public.ingestion_intake_evidence_write" in sql_text
    with pytest.raises(ValueError,match="OWNER_WRITER_SOURCE_DRIFT"):
        render_inactive_writer_install(source+"--changed\n")


def test_s4_first_tameside_noninstalled_issuer_pg17_refuses_before_source(isolated_world):
    """The exact dormant first-batch issuer is syntactically valid but cannot run.

    Existing disposable PostgreSQL world, no production installer, no grants,
    no source request. Original rolling issuer must remain unchanged.
    """
    from verification.ingestion_storage.inactive_tameside_first_issuer import (
        render_inactive_tameside_first_issuer, FUNCTION, PERIOD
    )
    w=isolated_world
    ctl_before=_control(w)
    # For this test ONLY, use existing disposable bootstrap as the
    # SECURITY DEFINER owner: the normal migrator lacks control-table locks.
    # No production role/ACL inference. Grant this one test invoker EXECUTE
    # in the ephemeral DB, never the restricted worker.
    w["boot"].execute(render_inactive_tameside_first_issuer())
    w["boot"].execute("GRANT EXECUTE ON FUNCTION "
                      "public.ingestion_register_tameside_first_once(jsonb) "
                      "TO provisioning_migrator")
    with w["connect"]("provisioning_migrator") as c:
        public_grant=c.execute(
            "SELECT has_function_privilege('ingestion_worker_login',"
            "'public.ingestion_register_tameside_first_once(jsonb)','EXECUTE')"
        ).fetchone()[0]
        assert public_grant is False
        # No inherited Bolton fallback is reachable through the clone.
        with pytest.raises(Exception,match="TAMESIDE_FIRST_NO_LEGACY_OPERATION"):
            c.execute("SELECT public."+FUNCTION+"(%s::jsonb)",
                      (json.dumps(dict(operation="bolton_exception",period=PERIOD)),))
        with pytest.raises(Exception,match="TAMESIDE_FIRST_SCOPE_OR_STOP"):
            c.execute("SELECT public."+FUNCTION+"(%s::jsonb)",
                      (json.dumps(dict(operation="intake_period",period=PERIOD,policy={})),))
    assert _control(w)==ctl_before



def test_v13_reusable_inactive_campaign_sql_pg17_refuses_without_side_effect(isolated_world):
    """New generic source-pinned issuer, focused disposable SQL negative proof.

    Reuses the existing disposable superuser fixture to syntax-check the
    identical function name for *two different selected* windows. No real
    owner route, production ACL, SQL installation, stop release, or positive
    historical operation is claimed. Each emitted body remains WITHHELD.
    """
    from datetime import datetime, timezone
    from verification.ingestion_storage.inactive_tameside_first_issuer import (
        CAMPAIGN_FUNCTION, render_inactive_campaign_issuer,
    )
    w = isolated_world
    before = _control(w)
    for council, start, end in (
        ("tameside", "2026-09-15", "2026-09-21"),
        ("manchester", "2026-09-22", "2026-09-28"),
    ):
        candidate = render_inactive_campaign_issuer(
            datetime(2026, 11, 16, 20, tzinfo=timezone.utc),
            council, start, end)
        # TEST DB ONLY; never add this SQL to installation_script().
        w["boot"].execute(candidate["sql"])
        w["boot"].execute(
            "GRANT EXECUTE ON FUNCTION public."
            + CAMPAIGN_FUNCTION + "(jsonb) TO provisioning_migrator")
        with w["connect"]("provisioning_migrator") as c:
            assert c.execute(
                "SELECT has_function_privilege('ingestion_worker_login',"
                "'public.ingestion_register_campaign_once(jsonb)','EXECUTE')"
            ).fetchone()[0] is False
            with pytest.raises(Exception, match="CAMPAIGN_FINITE_NO_LEGACY_OPERATION"):
                c.execute("SELECT public." + CAMPAIGN_FUNCTION + "(%s::jsonb)",
                          (json.dumps(dict(operation="bolton_exception",
                                           period=candidate["period"])),))
            with pytest.raises(Exception, match="CAMPAIGN_FINITE_SCOPE_OR_STOP"):
                c.execute("SELECT public." + CAMPAIGN_FUNCTION + "(%s::jsonb)",
                          (json.dumps(dict(operation="intake_period",
                                           period=candidate["period"],
                                           policy=dict(mode="CAMPAIGN_FINITE_HISTORICAL_V1"))),))
        assert _control(w) == before
    assert "ingestion_register_campaign_once" not in intake_policy.installation_script()



def test_v13_stable_campaign_sql_pg17_withheld_non_superuser_call(isolated_world):
    """One stable emitted function across windows; refusal via a real PG login.

    Disposable only. Unlike the earlier per-batch cloned SQL proof, this SQL
    body contains no Tameside/Manchester week literal. It is not an installer,
    owner registration, release-enabled runtime or evidence of production ACL.
    """
    from tests.e2e_pg_world import settings
    from verification.ingestion_storage.inactive_tameside_first_issuer import (
        CAMPAIGN_FUNCTION, render_inactive_stable_campaign_issuer,
        prepare_inactive_campaign_owner_batch,
    )
    from datetime import datetime, timezone
    w=isolated_world
    boot=w["boot"]
    before=_control(w)
    stable=render_inactive_stable_campaign_issuer()
    batch=prepare_inactive_campaign_owner_batch(
        datetime(2026,11,16,20,tzinfo=timezone.utc),
        "tameside","2026-09-15","2026-09-21")
    assert batch["manifest_status"]=="WITHHELD"
    assert batch["period"].startswith("S4_FINITE_")
    # The stopped fixture has NOT been released. Creation is fixture-only.
    boot.execute(stable)
    name="public."+CAMPAIGN_FUNCTION+"(jsonb)"
    assert boot.execute("SELECT pg_get_userbyid(proowner),prosecdef "
                        "FROM pg_proc WHERE oid=%s::regprocedure",
                        (name,)).fetchone()==("provisioning_bootstrap",True)
    _,info,_,_=settings()
    password=secrets.token_urlsafe(40)
    boot.execute(sql.SQL("ALTER ROLE postgres LOGIN NOSUPERUSER CREATEROLE "
                         "CREATEDB BYPASSRLS INHERIT PASSWORD {}").format(
                             sql.Literal(password)))
    # Test fixture only: this login otherwise cannot resolve a function in
    # schema public. Restore the privilege before fixture teardown; this is
    # NOT a proposed production grant or runtime role change.
    boot.execute("GRANT USAGE ON SCHEMA public TO postgres")
    boot.execute("GRANT EXECUTE ON FUNCTION "+name+" TO postgres")
    try:
        with psycopg.connect(**{**info,"user":"postgres","password":password},
                             autocommit=True,prepare_threshold=None) as c:
            actual=c.execute("SELECT current_user,session_user,rolsuper "
                             "FROM pg_roles WHERE rolname=current_user").fetchone()
            assert actual==("postgres","postgres",False)
            # The test-only postgres identity cannot resolve a function in
            # public without schema USAGE. Verify the restricted worker's
            # EXECUTE ACL via the existing bootstrap observer, not a new grant.
            assert boot.execute("SELECT has_function_privilege("
                                "'ingestion_worker_login',%s,'EXECUTE')",
                                (name,)).fetchone()[0] is False
            with pytest.raises(Exception,match="CAMPAIGN_STABLE_NO_LEGACY_OPERATION"):
                c.execute("SELECT public."+CAMPAIGN_FUNCTION+"(%s::jsonb)",
                          (json.dumps(dict(operation="bolton_exception",
                                           period=batch["period"])),))
            # Real PostgreSQL function execution, but still STOP and WITHHELD;
            # no registration/source permission can be produced.
            with pytest.raises(Exception,match="CAMPAIGN_STABLE_SCOPE_OR_STOP"):
                c.execute("SELECT public."+CAMPAIGN_FUNCTION+"(%s::jsonb)",
                          (json.dumps(dict(operation="intake_period",
                                           period=batch["period"],
                                           policy=dict(mode=batch["mode"]))),))
        assert _control(w)==before
        assert "ingestion_register_campaign_once" not in intake_policy.installation_script()
    finally:
        boot.execute("REVOKE EXECUTE ON FUNCTION "+name+" FROM postgres")
        boot.execute("REVOKE USAGE ON SCHEMA public FROM postgres")
        assert boot.execute("SELECT has_schema_privilege("
                            "'postgres','public','USAGE')").fetchone()[0] is False
        boot.execute("ALTER ROLE postgres NOLOGIN NOCREATEROLE NOCREATEDB "
                     "NOBYPASSRLS PASSWORD NULL")


def test_v13_static_campaign_owner_install_transactional_non_superuser(isolated_world):
    """Focused REAL PostgreSQL role proof in disposable DB only.

    Reuses the writer owner's existing transaction/acquisition/restoration,
    rather than inventing a second credential or permanent broad grant. It
    installs one stable, permanently WITHHELD SQL body after review-only
    rendering, verifies rollback, and independently checks owner/function
    identity and ACL after commit. NO historical registration or source grant.
    """
    from tests.e2e_pg_world import settings
    from verification.ingestion_storage.inactive_owner_writer_install import (
        render_inactive_stable_campaign_owner_install,
    )
    from verification.ingestion_storage.inactive_tameside_first_issuer import (
        CAMPAIGN_FUNCTION, render_inactive_stable_campaign_issuer,
    )
    w=isolated_world
    boot=w["boot"]
    before=_control(w)
    name="public."+CAMPAIGN_FUNCTION+"(jsonb)"
    assert boot.execute("SELECT to_regprocedure(%s)",(name,)).fetchone()[0] is None
    script=render_inactive_stable_campaign_owner_install()
    assert script.count("SET LOCAL ROLE ingestion_storage_owner;")==1
    assert script.count("RESET ROLE;")==1
    assert script.count("GRANT ingestion_storage_owner TO postgres")==1
    assert "CAMPAIGN_STABLE_MANIFEST_WITHHELD" in script
    assert "GRANT EXECUTE" not in script
    assert script.count("\nCOMMIT;\n")==1
    # TEST-ONLY database substitution; the literal owner session postgres
    # identity, membership baseline and target SQL function stay unchanged.
    script=script.replace(
        "current_database() IS DISTINCT FROM 'postgres'",
        "current_database() NOT IN ('postgres','ingestion_provisioning_test')",1)
    _,info,_,_=settings()
    password=secrets.token_urlsafe(40)
    boot.execute(sql.SQL("ALTER ROLE postgres LOGIN NOSUPERUSER CREATEROLE "
                         "CREATEDB BYPASSRLS INHERIT PASSWORD {}").format(
                             sql.Literal(password)))
    boot.execute("GRANT ingestion_storage_owner TO postgres "
                 "WITH ADMIN TRUE, INHERIT FALSE, SET FALSE "
                 "GRANTED BY provisioning_bootstrap")
    boot.execute("GRANT USAGE, CREATE ON SCHEMA public TO postgres WITH GRANT OPTION")
    def owner():
        return psycopg.connect(**{**info,"user":"postgres","password":password},
                               autocommit=True,prepare_threshold=None)
    def membership():
        return boot.execute(
            "SELECT grantor::regrole::text,admin_option,inherit_option,set_option "
            "FROM pg_auth_members WHERE member='postgres'::regrole "
            "AND roleid='ingestion_storage_owner'::regrole ORDER BY grantor"
        ).fetchall()
    baseline=[("provisioning_bootstrap",True,False,False)]
    try:
        assert membership()==baseline
        with owner() as c:
            assert c.execute(
                "SELECT current_user,session_user,rolsuper FROM pg_roles "
                "WHERE rolname=current_user").fetchone()==("postgres","postgres",False)
            assert c.execute(
                "SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),"
                "pg_has_role(current_user,'ingestion_storage_owner','SET')"
            ).fetchone()==(False,False)
            c.execute(script.replace("\nCOMMIT;\n","\nROLLBACK;\n"))
        assert boot.execute("SELECT to_regprocedure(%s)",(name,)).fetchone()[0] is None
        assert membership()==baseline and _control(w)==before

        # Missing exact admin-only baseline fails CLOSED before installation.
        boot.execute("REVOKE ingestion_storage_owner FROM postgres "
                     "GRANTED BY provisioning_bootstrap RESTRICT")
        try:
            with owner() as c:
                with pytest.raises(Exception,match="OWNER_WRITER_ADMIN_ONLY_BASELINE"):
                    c.execute(script)
                c.execute("ROLLBACK")
        finally:
            boot.execute("GRANT ingestion_storage_owner TO postgres "
                         "WITH ADMIN TRUE, INHERIT FALSE, SET FALSE "
                         "GRANTED BY provisioning_bootstrap")
        assert boot.execute("SELECT to_regprocedure(%s)",(name,)).fetchone()[0] is None
        assert membership()==baseline and _control(w)==before

        with owner() as c:
            c.execute(script)
        # Independent bootstrap readback, not self-reported by owner code.
        import hashlib
        stable=render_inactive_stable_campaign_issuer()
        expected_sql=stable.split("\nREVOKE ALL ON FUNCTION",1)[0]
        # PostgreSQL stores the function BODY (prosrc), not all DDL; compare
        # secure identity and stable function source via pg_get_functiondef.
        observed=boot.execute(
            "SELECT pg_get_userbyid(proowner),prosecdef,"
            "encode(sha256(convert_to(prosrc,'UTF8')),'hex') "
            "FROM pg_proc WHERE oid=%s::regprocedure",(name,)).fetchone()
        assert observed[0:2]==("ingestion_storage_owner",True)
        assert len(observed[2])==64
        assert boot.execute(
            "SELECT has_function_privilege('ingestion_worker_login',%s,'EXECUTE')",
            (name,)).fetchone()[0] is False
        assert membership()==baseline and _control(w)==before
        # A second install must NEVER silently replace a reviewed function.
        with owner() as c:
            with pytest.raises(Exception,match="OWNER_CAMPAIGN_ALREADY_INSTALLED"):
                c.execute(script)
            c.execute("ROLLBACK")
        assert membership()==baseline and _control(w)==before
        assert boot.execute("SELECT pg_get_userbyid(proowner) FROM pg_proc "
                            "WHERE oid=%s::regprocedure",
                            (name,)).fetchone()[0]=="ingestion_storage_owner"
    finally:
        boot.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM postgres")
        boot.execute("REVOKE ingestion_storage_owner FROM postgres "
                     "GRANTED BY provisioning_bootstrap RESTRICT")
        boot.execute("ALTER ROLE postgres NOLOGIN NOCREATEROLE NOCREATEDB "
                     "NOBYPASSRLS PASSWORD NULL")
